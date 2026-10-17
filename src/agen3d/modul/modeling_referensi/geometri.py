"""Geometri generik untuk modeling dari data (mm di data, meter di scene): mesh dari list, loft penampang,
prisma/loft pemotong, boolean EXACT, offset/cangkang, tabung sepanjang polyline, BVH dunia, rapikan slot material."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def mm(v):
    return v / 1000.0


def mesh_obj(nama, vs, fs, koleksi=None, mat=None, recalc=True, validasi=True):
    """Objek mesh dari vertex (m) + face. recalc=False untuk cangkang: permukaan dalam sengaja menghadap ke dalam
    (recalc akan membaliknya keluar, sehingga boolean EXACT membaca cangkang sebagai benda pejal).
    validasi=False: mesh dipakai apa adanya (loft/prisma M1)."""
    me = bpy.data.meshes.new(nama)
    me.from_pydata([tuple(v) for v in vs], [], [tuple(f) for f in fs])
    if validasi:
        me.validate()
    if recalc:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
    ob = bpy.data.objects.new(nama, me)
    (koleksi or bpy.context.scene.collection).objects.link(ob)
    if mat:
        me.materials.append(mat)
    return ob


def loft(nama, xs, cincin, koleksi=None):
    """Mesh tertutup: cincin[i] = list (y, z) mm di x = xs[i] mm. Tutup ujung n-gon (bidang x tetap)."""
    n = len(cincin[0])
    vs = [(mm(x), mm(y), mm(z)) for x, c in zip(xs, cincin) for y, z in c]
    fs = [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j)
          for i in range(len(xs) - 1) for j in range(n)]
    fs += [tuple(range(n))[::-1], tuple(range((len(xs) - 1) * n, len(xs) * n))]
    return mesh_obj(nama, vs, fs, koleksi, validasi=False)


def prisma_xz(nama, poli, y0=-200.0, y1=200.0):
    """Prisma pemotong: poligon (x, z) mm diekstrusi sepanjang Y."""
    n = len(poli)
    vs = [(mm(x), mm(y), mm(z)) for y in (y0, y1) for x, z in poli]
    fs = [tuple(range(n)), tuple(range(n, 2 * n))[::-1]]
    fs += [(j, (j + 1) % n, n + (j + 1) % n, n + j) for j in range(n)]
    return mesh_obj(nama, vs, fs, validasi=False)


def terapkan(ob):
    """Bekukan modifier (tanpa operator/konteks UI)."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    lama = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(lama)


def boolean(ob, operand, op="DIFFERENCE", hapus=False, transfer=False):
    """Boolean EXACT langsung dibekukan. Objek bertanda ob['lipat'] memakai self-intersection (offset >= 1 mm
    melipat sedikit di daerah tersembunyi; lebih lambat). hapus=True: operand dihapus sesudahnya."""
    m = ob.modifiers.new("bool", "BOOLEAN")
    m.operation, m.solver, m.object = op, "EXACT", operand
    m.use_self = bool(ob.get("lipat", False))
    if transfer:
        m.material_mode = "TRANSFER"
    terapkan(ob)
    if hapus:
        bpy.data.objects.remove(operand)
    return ob


def salin(ob, nama, koleksi):
    b = ob.copy()
    b.data = ob.data.copy()
    b.name = nama
    b.data.name = nama
    for k in list(b.users_collection):
        k.objects.unlink(b)
    koleksi.objects.link(b)
    return b


def grid_loft(cincin_list):
    """Cincin (list (x, y, z) mm) -> vs (mm), fs; tutup ujung dengan kipas ke titik pusat."""
    n = len(cincin_list[0])
    V = [v for c in cincin_list for v in c]
    F = [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j)
         for i in range(len(cincin_list) - 1) for j in range(n)]
    for i, rev in ((0, True), (len(cincin_list) - 1, False)):
        c = np.mean(np.array(cincin_list[i]), axis=0)
        V.append(tuple(c))
        k = len(V) - 1
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            F.append((b, a, k) if rev else (a, b, k))
    return np.array(V, float), F


def normal_vertex(V, F):
    """Normal vertex (rata-rata berbobot luas) dari mesh tertutup, arah keluar + face berorientasi keluar."""
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


def kotak_loft(nama, xs, fy, fz, koleksi=None, mat=None):
    """Pemotong: loft persegi panjang per x. fy(x) -> (y0, y1), fz(x) -> (z0, z1) (mm). Satuan mesh = m."""
    cin = []
    for x in xs:
        y0, y1 = fy(x)
        z0, z1 = fz(x)
        cin.append([(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)])
    V, F = grid_loft(cin)
    return mesh_obj(nama, V / 1000.0, F, koleksi, mat)


def cincin_loft(nama, xs, fcin, koleksi=None, mat=None):
    """Pemotong/bentuk: loft cincin bebas, fcin(x) -> list (y, z) mm."""
    cin = [[(x, y, z) for y, z in fcin(x)] for x in xs]
    V, F = grid_loft(cin)
    return mesh_obj(nama, V / 1000.0, F, koleksi, mat)


def tabung(titik, r, n=10):
    """Tabung sepanjang polyline (mm) dengan frame transport sejajar; ujung ditutup. Kembalikan (V, F) mm."""
    P = [Vector(p) for p in titik]
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


def catmull(titik, per_seg=6):
    """Kurva Catmull-Rom melewati titik (ujung diekstrapolasi). Kembalikan list Vector."""
    P = [Vector(p) for p in titik]
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
    """Torus di pusat c dengan sumbu n (mm). Kembalikan (V, F)."""
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


def bevel_panel(panel, lebar=0.25):
    """Tepi panel dibevel (geometri): tepi potong boolean tajam 90 derajat -> 2 segmen 0,25 mm.
    C-A5: n-gon hasil boolean ditriangulasi dulu; bevel pada n-gon besar tak-planar = belang shading per stasiun."""
    for ob in panel:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
        bm.to_mesh(ob.data)
        bm.free()
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width, m.segments, m.limit_method, m.angle_limit = mm(lebar), 2, "ANGLE", math.radians(40)
        m.harden_normals = False
        m.use_clamp_overlap = True
        terapkan(ob)


def bvh_dunia(obs):
    """BVH gabungan objek (koordinat dunia, mm, sesudah modifier). Kembalikan (BVH, array vertex mm)."""
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


def rapikan_slot(ob):
    """C-A8: boolean EXACT menambah slot KOSONG untuk operand tanpa material. Midsole: semua muka di slot kosong itu
    (material midsole masuk sebagai slot 1) = material default Blender sejak M1. Muka di slot kosong dipindah ke slot
    material pertama, slot kosong dibuang, indeks dipetakan ulang (AM-18)."""
    mats = list(ob.data.materials)
    isi = [i for i, m in enumerate(mats) if m is not None]
    if len(isi) == len(mats) or not isi:
        return
    peta = {lama: baru for baru, lama in enumerate(isi)}
    idx = np.empty(len(ob.data.polygons), np.int32)
    ob.data.polygons.foreach_get("material_index", idx)
    idx = np.array([peta.get(int(i), 0) for i in idx], np.int32)
    ob.data.materials.clear()
    for i in isi:
        ob.data.materials.append(mats[i])
    ob.data.polygons.foreach_set("material_index", idx)
    ob.data.update()
