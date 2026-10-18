"""Shape recipes as signed distance fields (SDF, numpy, mm; negative = inside) + SDF -> quad mesh (openvdb).

Recipes: lathe (revolved r-z profile), cushion (side silhouette inflated with thickness h(x, z) and a rounded cross
section). Details: sphere, capsule, rounded box, merged/carved with smooth union/subtraction (polynomial, k mm).
Fully deterministic: the same design -> the same mesh.
"""
import numpy as np


def grid(bottom, top, vox):
    """x, y, z axes (mm) of the voxel grid from corner `bottom` to `top`."""
    return [np.arange(b, a + vox, vox, dtype=np.float32) for b, a in zip(bottom, top)]


def polygon2d(u, v, poly):
    """Signed distance from points (u, v) to a closed polygon [(u, v)...] (negative inside, even-odd). u.shape = v.shape."""
    P = np.asarray(poly, np.float32)
    d2 = np.full(u.shape, np.inf, np.float32)
    is_inside = np.zeros(u.shape, bool)
    for (ua, va), (ub, vb) in zip(P, np.roll(P, -1, axis=0)):
        eu, ev = ub - ua, vb - va
        wu, wv = u - ua, v - va
        t = np.clip((wu * eu + wv * ev) / max(eu * eu + ev * ev, 1e-12), 0.0, 1.0)
        d2 = np.minimum(d2, (wu - eu * t) ** 2 + (wv - ev * t) ** 2)
        cross = (va > v) != (vb > v)
        with np.errstate(divide="ignore", invalid="ignore"):
            xs = ua + (v - va) * eu / np.where(ev == 0, 1e-12, ev)
        is_inside ^= cross & (u < xs)
    return np.where(is_inside, -1.0, 1.0).astype(np.float32) * np.sqrt(d2)


def smooth_profile(profile, step=0.3, sharp=()):
    """Polygon profile -> centripetal Catmull-Rom curve (through every point), sampled every ~`step` mm.
    Removes the conical bands that revolving straight segments produces. The curve can bulge outward at corners
    (pawn rev 1: +0.3 mm), so corner points (indices in `sharp`, plus both ends) split the curve: each piece is smoothed
    separately."""
    cuts = sorted({0, len(profile) - 1, *sharp})
    if len(cuts) > 2:
        result = []
        for a, b in zip(cuts[:-1], cuts[1:]):
            part = smooth_profile(profile[a:b + 1], step)
            result += part if not result else part[1:]
        return result
    P = np.asarray(profile, float)
    out = [P[0]]
    for i in range(len(P) - 1):
        p0, p1, p2 = P[max(i - 1, 0)], P[i], P[i + 1]
        p3 = P[min(i + 2, len(P) - 1)]
        t1 = t0 = 0.0
        t1 = t0 + max(np.linalg.norm(p1 - p0), 1e-6) ** 0.5
        t2 = t1 + max(np.linalg.norm(p2 - p1), 1e-6) ** 0.5
        t3 = t2 + max(np.linalg.norm(p3 - p2), 1e-6) ** 0.5
        n = max(int(np.ceil(np.linalg.norm(p2 - p1) / step)), 1)
        for t in np.linspace(t1, t2, n + 1)[1:]:
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out = np.array(out)
    out[:, 0] = np.maximum(out[:, 0], 0.0)
    return out.tolist()


def lathe(X, Y, Z, profile, vox=None):
    """Revolve profile [(r, z)...] (closed via the axis) around the Z axis. With `vox`: the 2D distance is computed once
    on a fine (r, z) grid (vox/2) and sampled bilinearly -> ~100x faster than computing it per 3D voxel."""
    R = np.sqrt(X * X + Y * Y)
    if vox is None:
        return polygon2d(R, Z, profile)
    h = vox / 2
    z0 = float(Z[0, 0, 0])
    rr = np.arange(0.0, float(R.max()) + 2 * h, h, dtype=np.float32)
    zz = z0 + np.arange(Z.shape[2], dtype=np.float32) * vox
    d2 = polygon2d(*np.meshgrid(rr, zz, indexing="ij"), profile)
    fi = R / h
    i0 = np.minimum(fi.astype(np.int32), len(rr) - 2)
    t = fi - i0
    k = np.broadcast_to(np.arange(Z.shape[2]), R.shape)
    return d2[i0, k] * (1 - t) + d2[i0 + 1, k] * t


def cushion_thickness(x, z, b):
    """Half thickness h(x, z) (mm): interpolated thickness_z, tapering linearly from taper_x0 toward +X."""
    tz = np.asarray(b["thickness_z"], np.float32)
    h = np.interp(z, tz[:, 0], tz[:, 1]).astype(np.float32)
    h = h - np.maximum(x - b["taper_x0"], 0.0) * b["taper_rate"]
    if "thickness_x" in b:  # thickness multiplier along X (e.g. the back of the neck narrowing into the mane ridge)
        tx = np.asarray(b["thickness_x"], np.float32)
        h = h * np.interp(x, tx[:, 0], tx[:, 1]).astype(np.float32)
    return np.maximum(h, 0.5)


def cushion(x, y, z, b):
    """Silhouette (x, z) extruded symmetrically in Y with half thickness h(x, z) and a rounded cross section (radius r)."""
    xx, zz = np.meshgrid(x, z, indexing="ij")
    d2 = polygon2d(xx, zz, b["silhouette"])[:, None, :]
    h = cushion_thickness(xx, zz, b)[:, None, :]
    r = np.minimum(np.float32(b["round_mm"]), h - 0.05)
    qx, qy = d2 + r, np.abs(y)[None, :, None] - h + r
    outer = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
    return np.minimum(np.maximum(qx, qy), 0) + outer - r


def sdf_sphere(X, Y, Z, center, r):
    return np.sqrt((X - center[0]) ** 2 + (Y - center[1]) ** 2 + (Z - center[2]) ** 2) - r


def sdf_capsule(X, Y, Z, a, b, r):
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    ab = b - a
    t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1] + (Z - a[2]) * ab[2]) / float(ab @ ab), 0, 1)
    return np.sqrt((X - a[0] - ab[0] * t) ** 2 + (Y - a[1] - ab[1] * t) ** 2 + (Z - a[2] - ab[2] * t) ** 2) - r


def ellipsoid(X, Y, Z, center, radius, angle=0.0):
    """Ellipsoid (iq approximation) with radii (ru, ry, rw) on local axes: u = (cos a, 0, -sin a), y, w = (sin a, 0, cos a);
    a = `angle` in degrees (rotation about the Y axis, positive = the +u end tilts down)."""
    a = np.radians(angle)
    dx, dy, dz = X - center[0], Y - center[1], Z - center[2]
    u, w = dx * np.cos(a) - dz * np.sin(a), dx * np.sin(a) + dz * np.cos(a)
    k0 = np.sqrt((u / radius[0]) ** 2 + (dy / radius[1]) ** 2 + (w / radius[2]) ** 2)
    k1 = np.sqrt((u / radius[0] ** 2) ** 2 + (dy / radius[1] ** 2) ** 2 + (w / radius[2] ** 2) ** 2)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def box(X, Y, Z, center, half_size, r):
    q = [np.abs(P - c) - (s - r) for P, c, s in zip((X, Y, Z), center, half_size)]
    outer = np.sqrt(sum(np.maximum(k, 0) ** 2 for k in q))
    return outer + np.minimum(np.maximum(np.maximum(q[0], q[1]), q[2]), 0) - r


def cone(X, Y, Z, a, b, r1, r2, scale=(1.0, 1.0, 1.0)):
    """Rounded cone from a (radius r1) to b (r2), optionally flattened per axis (scale < 1 = flatter).
    iq "round cone" SDF; scaling makes it approximate (good enough for the zero surface)."""
    a = np.asarray(a, np.float32)
    s = np.asarray(scale, np.float32)
    P = [(Q - c) / k for Q, c, k in zip((X, Y, Z), a, s)]
    ba = (np.asarray(b, np.float32) - a) / s
    l2 = float(ba @ ba)
    rr = r1 - r2
    a2, il2 = l2 - rr * rr, 1.0 / l2
    y = P[0] * ba[0] + P[1] * ba[1] + P[2] * ba[2]
    z = y - l2
    x2 = sum((Pi * l2 - bi * y) ** 2 for Pi, bi in zip(P, ba))
    y2, z2 = y * y * l2, z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d = np.where(np.sign(z) * a2 * z2 > k, np.sqrt(x2 + z2) * il2 - r2,
                 np.where(np.sign(y) * a2 * y2 < k, np.sqrt(x2 + y2) * il2 - r1,
                          (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1))
    return d * float(s.min())


def carve(d, X, Y, Z, points, normal, center, half_size, transition, scale=1.0):
    """Carve a flat plane: remove material on the +normal side of the plane through `points`, only inside the region
    box (center, half_size), with a smooth `transition` at the region boundary. Produces hard edges (carved look).
    X, Y, Z may be local skeleton coordinates; `scale` = mm per local unit (distances are converted back to mm)."""
    n = np.asarray(normal, np.float32)
    n = n / np.linalg.norm(n)
    plane = ((X - points[0]) * n[0] + (Y - points[1]) * n[1] + (Z - points[2]) * n[2]) * scale
    w = np.clip(-box(X, Y, Z, center, half_size, 0.0) / max(transition, 1e-3), 0.0, 1.0)
    return d + w * (np.maximum(d, plane) - d)


def merge(a, b, k):
    """Smooth union (fillet ~k mm)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def subtract(a, b, k):
    """a minus b (carving) with a smooth edge of ~k mm."""
    return -merge(-a, b, k)


def sdf_to_mesh(field, origin, vox):
    """SDF (array [x, y, z]) -> (points mm Nx3, quads Mx4) on the zero surface, normals facing outward."""
    import openvdb
    g = openvdb.FloatGrid(float(field.max()))
    g.copyFromArray(np.ascontiguousarray(field, np.float32))
    points, quad = g.convertToQuads(0.0)
    points = np.asarray(points, np.float64) * vox + np.asarray(origin, np.float64)
    quad = np.asarray(quad, np.int64)
    if volume(points, quad) < 0:
        quad = quad[:, ::-1]
    return points, quad


def triangle(quad):
    q = np.asarray(quad)
    return np.vstack([q[:, [0, 1, 2]], q[:, [0, 2, 3]]]) if q.shape[1] == 4 else q


def volume(points, faces):
    """Signed volume of a closed mesh (mm3) and its center of mass, from tetrahedra to the origin."""
    t = triangle(faces)
    a, b, c = points[t[:, 0]], points[t[:, 1]], points[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def centroid(points, faces):
    t = triangle(faces)
    a, b, c = points[t[:, 0]], points[t[:, 1]], points[t[:, 2]]
    v = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    return ((a + b + c) / 4.0 * v[:, None]).sum(0) / v.sum()
