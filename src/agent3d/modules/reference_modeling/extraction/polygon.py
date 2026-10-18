"""Binary mask -> contour polygon (mm): marching squares + segment chaining + Douglas-Peucker. Pure numpy (no scipy).

Used by extract_class: panels that are not convex per column (e.g. a pale overlay surrounding a mesh window) cannot be
stored as a per-column [x, z_bottom, z_top] hull (the hull fills the area in between). The outer polygon + holes are
used by the shoe recipe as region prisms (outer prism minus hole prisms).
"""
import numpy as np


# marching-squares cell edges: 0 = top (y, x+.5), 1 = right (y+.5, x+1), 2 = bottom (y+1, x+.5), 3 = left (y+.5, x)
_EDGE = {1: [(3, 2)], 2: [(2, 1)], 3: [(3, 1)], 4: [(1, 0)], 5: [(3, 0), (1, 2)], 6: [(2, 0)], 7: [(3, 0)],
         8: [(0, 3)], 9: [(0, 2)], 10: [(0, 1), (2, 3)], 11: [(0, 1)], 12: [(1, 3)], 13: [(1, 2)], 14: [(2, 3)]}


def _points(y, x, e):
    return {0: (y, x + 0.5), 1: (y + 0.5, x + 1.0), 2: (y + 1.0, x + 0.5), 3: (y + 0.5, x)}[e]


def contour(mk):
    """Contour loops (list of (n, 2) [y, x] pixel arrays, points at cell edge midpoints) of a binary mask."""
    m = np.pad(mk.astype(np.uint8), 1)
    case = m[:-1, :-1] * 8 + m[:-1, 1:] * 4 + m[1:, 1:] * 2 + m[1:, :-1] * 1  # TL TR BR BL
    seg = {}
    for y, x in zip(*np.nonzero((case > 0) & (case < 15))):
        for a, b in _EDGE[int(case[y, x])]:
            p, q = _points(y, x, a), _points(y, x, b)
            seg[p] = q
    loops = []
    while seg:
        p0, q = seg.popitem()
        loop = [p0]
        while q != p0 and q in seg:
            loop.append(q)
            q = seg.pop(q)
        if len(loop) >= 4:
            loops.append(np.array(loop) - 1.0)  # drop padding
    return loops


def rdp(P, eps):
    """Douglas-Peucker (iterative) for an open polyline."""
    if len(P) < 3:
        return P
    save = np.zeros(len(P), bool)
    save[0] = save[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        d = b - a
        n = np.hypot(*d)
        seg = P[i + 1:j]
        distance = np.abs(d[0] * (seg[:, 1] - a[1]) - d[1] * (seg[:, 0] - a[0])) / n if n > 0 else np.hypot(*(seg - a).T)
        k = int(np.argmax(distance))
        if distance[k] > eps:
            save[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return P[save]


def chaikin(P, n):
    """Chaikin smoothing of a closed loop (n iterations): pixel/RDP stair corners get rounded, the shape stays (new points
    at 1/4 and 3/4 of each edge)."""
    for _ in range(n):
        Q = np.roll(P, -1, 0)
        P = np.stack([0.75 * P + 0.25 * Q, 0.25 * P + 0.75 * Q], 1).reshape(-1, 2)
    return P


def marked_area(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def polygon_mm(mk, to_x, to_z, eps_mm, sk, hole_area_min_mm2=4.0, smoothness=0):
    """Component mask -> dict(outer=[[x, z], ...], hole=[[[x, z], ...], ...]) in mm, simplified with eps_mm.
    Largest loop = outer; other loops with area >= hole_area_min = holes (lace holes, gaps between panels)."""
    loops = []
    for L in contour(mk):
        L = np.vstack([L, L[:1]])
        xz = np.c_[to_x(L[:, 1]), to_z(L[:, 0])]
        # rdp on a closed loop: split at the point farthest from the start so both ends stay fixed
        k = int(np.argmax(np.hypot(*(xz - xz[0]).T)))
        s = np.vstack([rdp(xz[:k + 1], eps_mm)[:-1], rdp(xz[k:], eps_mm)[:-1]])
        if len(s) >= 3:
            loops.append(chaikin(s, smoothness) if smoothness else s)
    if not loops:
        return None
    area = [abs(marked_area(L)) for L in loops]
    i = int(np.argmax(area))
    rounded = lambda L: [[round(float(a), 2), round(float(b), 2)] for a, b in L]
    return dict(outer=rounded(loops[i]),
                hole=[rounded(L) for j, L in enumerate(loops) if j != i and area[j] >= hole_area_min_mm2])
