"""Generic geometry for modeling from data (mm in data, meters in the scene): mesh from lists, section lofts,
cutter prisms/lofts, EXACT booleans, offset/shell, tube along a polyline, world BVH, material slot cleanup."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def mm(v):
    return v / 1000.0


def mesh_obj(name, vs, fs, collection=None, mat=None, recalc=True, validation=True):
    """Mesh object from vertices (m) + faces. recalc=False for shells: the inner surface deliberately faces inward
    (recalc would flip it outward, so the EXACT boolean would read the shell as a solid body).
    validation=False: mesh used as is (M1 lofts/prisms)."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in vs], [], [tuple(f) for f in fs])
    if validation:
        me.validate()
    if recalc:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    if mat:
        me.materials.append(mat)
    return ob


def loft(name, xs, ring, collection=None):
    """Closed mesh: ring[i] = list of (y, z) mm at x = xs[i] mm. Ends capped with n-gons (constant-x plane)."""
    n = len(ring[0])
    vs = [(mm(x), mm(y), mm(z)) for x, c in zip(xs, ring) for y, z in c]
    fs = [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j)
          for i in range(len(xs) - 1) for j in range(n)]
    fs += [tuple(range(n))[::-1], tuple(range((len(xs) - 1) * n, len(xs) * n))]
    return mesh_obj(name, vs, fs, collection, validation=False)


def xz_prism(name, poly, y0=-200.0, y1=200.0):
    """Cutter prism: (x, z) mm polygon extruded along Y."""
    n = len(poly)
    vs = [(mm(x), mm(y), mm(z)) for y in (y0, y1) for x, z in poly]
    fs = [tuple(range(n)), tuple(range(n, 2 * n))[::-1]]
    fs += [(j, (j + 1) % n, n + (j + 1) % n, n + j) for j in range(n)]
    return mesh_obj(name, vs, fs, validation=False)


def apply(ob):
    """Apply modifiers (no operators/UI context)."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)


def boolean(ob, operand, op="DIFFERENCE", delete=False, transfer=False):
    """EXACT boolean, applied immediately. Objects flagged ob['fold'] use self-intersection (offsets >= 1 mm
    fold slightly in hidden areas; slower). delete=True: the operand is removed afterwards."""
    m = ob.modifiers.new("bool", "BOOLEAN")
    m.operation, m.solver, m.object = op, "EXACT", operand
    m.use_self = bool(ob.get("fold", False))
    if transfer:
        m.material_mode = "TRANSFER"
    apply(ob)
    if delete:
        bpy.data.objects.remove(operand)
    return ob


def copy(ob, name, collection):
    b = ob.copy()
    b.data = ob.data.copy()
    b.name = name
    b.data.name = name
    for k in list(b.users_collection):
        k.objects.unlink(b)
    collection.objects.link(b)
    return b


def grid_loft(ring_list):
    """Rings (lists of (x, y, z) mm) -> vs (mm), fs; ends capped with a fan to the center point."""
    n = len(ring_list[0])
    V = [v for c in ring_list for v in c]
    F = [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j)
         for i in range(len(ring_list) - 1) for j in range(n)]
    for i, rev in ((0, True), (len(ring_list) - 1, False)):
        c = np.mean(np.array(ring_list[i]), axis=0)
        V.append(tuple(c))
        k = len(V) - 1
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            F.append((b, a, k) if rev else (a, b, k))
    return np.array(V, float), F


def normal_vertex(V, F):
    """Vertex normals (area-weighted mean) of a closed mesh, pointing outward + faces oriented outward."""
    me = bpy.data.meshes.new("_tmp")
    me.from_pydata([tuple(v) for v in V], [], F)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    bm.verts.index_update()
    N = np.array([tuple(v.normal) for v in bm.verts])
    Fo = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    bpy.data.meshes.remove(me)
    return N, Fo


def loft_box(name, xs, fy, fz, collection=None, mat=None):
    """Cutter: rectangular loft along length, per x. fy(x) -> (y0, y1), fz(x) -> (z0, z1) (mm). Mesh units = m."""
    rings = []
    for x in xs:
        y0, y1 = fy(x)
        z0, z1 = fz(x)
        rings.append([(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)])
    V, F = grid_loft(rings)
    return mesh_obj(name, V / 1000.0, F, collection, mat)


def loft_rings(name, xs, fcin, collection=None, mat=None):
    """Cutter/shape: free-ring loft, fcin(x) -> list of (y, z) mm."""
    rings = [[(x, y, z) for y, z in fcin(x)] for x in xs]
    V, F = grid_loft(rings)
    return mesh_obj(name, V / 1000.0, F, collection, mat)


def tube(points, r, n=10):
    """Tube along a polyline (mm) with a parallel-transport frame; ends capped. Returns (V, F) in mm."""
    P = [Vector(p) for p in points]
    T = [(P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized() for i in range(len(P))]
    a = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    u = T[0].cross(a).normalized()
    V, F = [], []
    for i, (p, t) in enumerate(zip(P, T)):
        if i:
            u = (u - t * u.dot(t)).normalized()
        v = t.cross(u)
        for j in range(n):
            ang = 2 * math.pi * j / n
            V.append(tuple(p + (u * math.cos(ang) + v * math.sin(ang)) * r))
    for i in range(len(P) - 1):
        for j in range(n):
            F.append((i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j))
    F.append(tuple(range(n))[::-1])
    F.append(tuple(range((len(P) - 1) * n, len(P) * n)))
    return V, F


def catmull(points, per_seg=6):
    """Catmull-Rom curve through the points (ends extrapolated). Returns a list of Vectors."""
    P = [Vector(p) for p in points]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(per_seg):
            t = k / per_seg
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2])
    return out


def torus(c, n, R, r, seg=20, seg2=8):
    """Torus at center c with axis n (mm). Returns (V, F)."""
    a = Vector((1, 0, 0)) if abs(n.x) < 0.9 else Vector((0, 1, 0))
    u = n.cross(a).normalized()
    v = n.cross(u)
    V, F = [], []
    for i in range(seg):
        A = 2 * math.pi * i / seg
        d = u * math.cos(A) + v * math.sin(A)
        for j in range(seg2):
            b = 2 * math.pi * j / seg2
            V.append(tuple(c + d * (R + r * math.cos(b)) + n * (r * math.sin(b))))
    for i in range(seg):
        for j in range(seg2):
            i2, j2 = (i + 1) % seg, (j + 1) % seg2
            F.append((i * seg2 + j, i2 * seg2 + j, i2 * seg2 + j2, i * seg2 + j2))
    return V, F


def bevel_panel(panel, width=0.25):
    """Bevel panel edges (geometry): sharp 90-degree boolean cut edges -> 2 segments of 0.25 mm.
    C-A5: boolean n-gons are triangulated first; bevelling large non-planar n-gons = shading stripes per station."""
    for ob in panel:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
        bm.to_mesh(ob.data)
        bm.free()
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width, m.segments, m.limit_method, m.angle_limit = mm(width), 2, "ANGLE", math.radians(40)
        m.harden_normals = False
        m.use_clamp_overlap = True
        apply(ob)


def world_bvh(obs):
    """Combined BVH of objects (world coordinates, mm, after modifiers). Returns (BVH, vertex array in mm)."""
    dg = bpy.context.evaluated_depsgraph_get()
    V, F = [], []
    for ob in obs:
        e = ob.evaluated_get(dg)
        me = e.to_mesh()
        mw = ob.matrix_world
        o = len(V)
        V += [tuple((mw @ v.co) * 1000.0) for v in me.vertices]
        F += [tuple(i + o for i in p.vertices) for p in me.polygons]
        e.to_mesh_clear()
    return BVHTree.FromPolygons(V, F), np.array(V)


def tidy_slot(ob):
    """C-A8: the EXACT boolean adds an EMPTY slot for operands without a material. Midsole: all faces sat in that empty
    slot (the midsole material came in as slot 1) = Blender default material since M1. Faces in empty slots move to the
    first material slot, empty slots are dropped, indices remapped (AM-18)."""
    mats = list(ob.data.materials)
    contents = [i for i, m in enumerate(mats) if m is not None]
    if len(contents) == len(mats) or not contents:
        return
    mapping = {old: new for new, old in enumerate(contents)}
    idx = np.empty(len(ob.data.polygons), np.int32)
    ob.data.polygons.foreach_get("material_index", idx)
    idx = np.array([mapping.get(int(i), 0) for i in idx], np.int32)
    ob.data.materials.clear()
    for i in contents:
        ob.data.materials.append(mats[i])
    ob.data.polygons.foreach_set("material_index", idx)
    ob.data.update()
