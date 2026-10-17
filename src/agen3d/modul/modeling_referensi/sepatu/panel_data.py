"""Resep sepatu M2 GENERIK (Tugas 11): panel upper dari poligon DATA kelas warna, bukan kode khusus per sepatu.

Sepatu = unit sol (sol.py) + panel dari data. Panel didefinisikan di proyek.toml `[[model.panel]]`:
  nama (= panel ekstraksi `[[ekstraksi.panel]]`), peran (slot material), lapis = [d_dalam, d_luar] mm dari S,
  jahitan (bool), alas = "upper" (cangkang lapis S) | "midsole" (wilayah cat pada midsole, mis. kaset tumit).
Panel upper = cangkang lapis ∩ prisma poligon sisi itu (poligon luar dikurangi lubang, diekstrusi sepanjang Y, dibatasi
separuh sisi: lateral y >= garis tengah plan, medial sebaliknya) − lubang tali. Panel alas midsole = potongan midsole di
dalam prisma, digabung kembali ke objek midsole sebagai slot material kedua (QC M1 tetap membaca satu objek midsole).
Lapisan saling tumpuk diatur oleh `lapis` (celah >= 0,2 mm antar lapisan yang bersinggungan: AM-13).
"""
import bmesh
import bpy
import numpy as np
from mathutils import Vector

from ....inti.material import bahan
from ..geometri import boolean, bvh_dunia, kotak_loft, mesh_obj, prisma_xz, salin
from . import data
from .bentuk import JAHIT
from .tali import _offset_xz, _resample_xz

ABU_PERAN = (0.55, 0.55, 0.56)  # material netral M2 untuk peran yang tidak ada di bahan_netral


def spesifikasi():
    return data.KONFIG.get("model", {}).get("panel", [])


def bahan_peran(mat, peran):
    if peran not in mat:
        mat[peran] = bpy.data.materials.get(peran) or bahan(peran, ABU_PERAN, 0.6)
    return mat[peran]


def pemotong_sisi(nama, sisi, B, tmp, geser=(0.0, 0.0), sumber=None):
    """Prisma wilayah panel di satu sisi (None bila tidak ada data). geser (x, z) mm dan sumber (sisi data lain)
    hanya untuk uji negatif AM-10."""
    polis = data.panel_kelas(nama, sumber or sisi)
    if not polis:
        return None
    pot = None
    gs = lambda L: [(p[0] + geser[0], p[1] + geser[1]) for p in L]
    for i, pg in enumerate(polis):
        pr = prisma_xz(f"_pr_{nama}_{sisi}_{i}", gs(pg["luar"]))
        for j, h in enumerate(pg["lubang"]):
            boolean(pr, prisma_xz(f"_lb_{nama}_{sisi}_{i}_{j}", gs(h), -250.0, 250.0), "DIFFERENCE", hapus=True)
        if pot is None:
            pot = pr
        else:
            boolean(pot, pr, "UNION", hapus=True)
    L = data.PANJANG
    xs = list(np.arange(-8.0, L + 8.0, 0.5))
    sg = 1.0 if sisi == "lateral" else -1.0
    c = data.model("upper", "celah_sisi_mm", 0.4) / 2  # celah garis tengah antar potongan L/M (jahitan tumit; AM-13)
    separuh = kotak_loft(f"_sp_{nama}_{sisi}", xs,
                         lambda x: tuple(sorted((B.plan(min(max(x, 0.0), L))[0] + sg * c, sg * 250.0))),
                         lambda x: (-60.0, 400.0), tmp)
    boolean(pot, separuh, "INTERSECT", hapus=True)
    return pot


def pemotong_plan(nama, tmp):
    """Prisma tegak (sepanjang Z) gabungan poligon zona tapak `nama` (data.TAPAK), dalam koordinat model (mm)."""
    zona = (data.TAPAK or {}).get("zona", {}).get(nama)
    if not zona or not zona["poligon"]:
        return None
    pot = None
    for i, pg in enumerate(zona["poligon"]):
        P = data.plan_xy(pg["luar"])
        n = len(P)
        V = [(x / 1000.0, y / 1000.0, z / 1000.0) for z in (-60.0, 80.0) for x, y in P]
        F = [tuple(range(n)), tuple(range(n, 2 * n))[::-1]] + [(j, (j + 1) % n, n + (j + 1) % n, n + j) for j in range(n)]
        pr = mesh_obj(f"_pz_{nama}_{i}", V, F, tmp, validasi=False)
        if pot is None:
            pot = pr
        else:
            boolean(pot, pr, "UNION", hapus=True)
    return pot


def _gabung_ke(target, potongan, mat_baru):
    """Gabungkan geometri `potongan` ke objek `target` dengan slot material `mat_baru` (indeks baru)."""
    target.data.materials.append(mat_baru)
    k = len(target.data.materials) - 1
    bm = bmesh.new()
    bm.from_mesh(target.data)
    n0 = len(bm.faces)
    bm.from_mesh(potongan.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces[n0:]:
        f.material_index = k
    bm.to_mesh(target.data)
    bm.free()
    lama = potongan.data
    bpy.data.objects.remove(potongan)
    bpy.data.meshes.remove(lama)


def bangun_panel_data(B, cangkang, potong_atas, klip_l, lub, pk, tmp, mat, geser=None, medial_dari_lateral=False):
    """Semua panel data. cangkang(nama, d_in, d_out, koleksi) dari upper.py; potong_atas/klip_l = pemotong kerah/lidah;
    lub = silinder lubang tali. Kembalikan {nama_objek: objek} (panel upper per sisi).
    Uji negatif: geser {panel: (x, z) mm}; medial_dari_lateral = panel medial dibangun dari poligon lateral."""
    obs = {}
    for sp in spesifikasi():
        nama, peran = sp["nama"], sp["peran"]
        if sp.get("alas", "upper") != "upper":  # alas midsole/outsole: bangun_panel_alas() setelah boolean sol (sol.py)
            continue
        m = bahan_peran(mat, peran)
        g = (geser or {}).get(nama, (0.0, 0.0))
        pot = {s: pemotong_sisi(nama, s, B, tmp, g, "lateral" if medial_dari_lateral and s == "medial" else None)
               for s in ("lateral", "medial")}
        d_in, d_out = sp["lapis"]
        sh = cangkang(f"_c_{nama}", d_in, d_out, tmp)
        sh["lipat"] = d_in < 0  # offset ke dalam bisa terlipat di sudut berjari-jari kecil: boolean self-intersection
        sh.data.materials.append(m)
        boolean(sh, potong_atas, "DIFFERENCE", transfer=True)
        boolean(sh, klip_l, "INTERSECT")
        bagian = []
        for s, c in pot.items():
            if c is None:
                continue
            ob = salin(sh, f"{nama}_{s}", pk)
            boolean(ob, c, "INTERSECT", hapus=True)
            if len(ob.data.polygons):
                bagian.append(ob)
            else:
                bpy.data.objects.remove(ob)
        if not bagian:
            continue
        ob = bagian[0]
        for lain in bagian[1:]:  # potongan L + M satu objek: tanpa celah/muka berimpit di garis tengah toe/tumit
            boolean(ob, lain, "UNION", hapus=True)
        ob.name = ob.data.name = nama
        if lub is not None:
            boolean(ob, lub, "DIFFERENCE", transfer=True)
        ob["peran"], ob["panel"] = peran, nama
        obs[ob.name] = ob
    return obs


def bangun_panel_alas(B, mat):
    """Panel `alas = "midsole"` (wilayah cat, mis. kaset tumit): dipanggil sol.py SETELAH semua boolean midsole
    (rongga, jendela). Semua potongan dibuat dari midsole asli dulu lalu digabung paling akhir sebagai slot material
    kedua: mesh gabungan berisi muka potong internal (non-manifold) yang membuat boolean EXACT berikutnya gagal
    (AM90-C10: midsole 19 587 -> 110 muka)."""
    tmp = bpy.data.collections.new("_tmp_alas")
    bpy.context.scene.collection.children.link(tmp)
    for sp in spesifikasi():
        alas = sp.get("alas", "upper")
        if alas not in ("midsole", "outsole"):
            continue
        mid = bpy.data.objects[alas]
        nama, m = sp["nama"], bahan_peran(mat, sp["peran"])
        if alas == "outsole":  # zona tapak dari foto sol: prisma poligon plan sepanjang Z (ekstraksi/tapak.py)
            pot = {"plan": pemotong_plan(nama, tmp)}
        else:
            pot = {s: pemotong_sisi(nama, s, B, tmp) for s in ("lateral", "medial")}
        kep = {}
        for s, c in pot.items():
            if c is not None:
                kep[s] = salin(mid, f"_{nama}_{s}", tmp)
                boolean(kep[s], c, "INTERSECT")
        for s, c in pot.items():
            if c is not None:
                boolean(mid, c, "DIFFERENCE", hapus=True)
        for k in kep.values():
            if len(k.data.polygons):
                _gabung_ke(mid, k, m)
        mid[f"panel_{nama}"] = True
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp)


def bangun_jahitan_data(B, obs, mat, pk):
    """Jahitan putus-putus 1,5 mm di dalam keliling setiap panel `jahitan = true` (poligon data, per sisi), dipetakan
    ke S + normal (cara C-A6: offset di bidang xz, lipatan di takik dibuang). Tinggi = lapis luar panel + 0,1 mm."""
    J = JAHIT
    V, F = [], []
    n_dash = {}

    def titik_S(x, z, sisi, angkat):
        y = B.y_sisi(x, z, sisi)
        if y is None:
            return None
        ya, yb = B.y_sisi(x + 0.3, z, sisi), B.y_sisi(x, z + 0.3, sisi)
        if ya is None or yb is None:
            return None
        n = Vector((0.3, ya - y, 0.0)).cross(Vector((0.0, yb - y, 0.3))).normalized()
        if (n.y > 0) != (sisi == "lateral"):
            n = -n
        return Vector((x, y, z)) + n * angkat, n

    def dash(titik):
        seg, acc, on, start, prev = [], 0.0, True, None, None
        for g in titik:
            if g is None:
                prev = None
                continue
            if prev is None:
                start, on, acc = g, True, 0.0
            else:
                acc += (g[0] - prev[0]).length
                if on and acc >= J["dash"]:
                    seg.append((start, g))
                    on, acc = False, 0.0
                elif not on and acc >= J["jeda"]:
                    on, acc, start = True, 0.0, g
            prev = g
        for (p0, n0), (p1, n1) in seg:
            t = (p1 - p0).normalized()
            n = (n0 + n1).normalized()
            u = n.cross(t).normalized()
            h, w = J["tebal"] / 2, J["lebar"] / 2
            kot = [c + u * su * w + n * sn * h for c in (p0, p1) for su, sn in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            o = len(V)
            V.extend(tuple(k) for k in kot)
            F.extend([(o, o + 1, o + 2, o + 3), (o + 7, o + 6, o + 5, o + 4), (o, o + 4, o + 5, o + 1),
                      (o + 1, o + 5, o + 6, o + 2), (o + 2, o + 6, o + 7, o + 3), (o + 3, o + 7, o + 4, o)])
        return len(seg)

    for sp in spesifikasi():
        if not sp.get("jahitan") or sp.get("alas", "upper") != "upper":
            continue
        n_dash[sp["nama"]] = 0
        ob_p = obs.get(sp["nama"])
        if ob_p is None:
            continue
        bvh = bvh_dunia([ob_p])[0]  # AM90-C13: titik jahitan hanya bila panel ada di situ (poligon diperluas melewati
        # siluet/kerah: S tetap ada di atas kerah yang sudah dipotong -> jahitan melayang)
        for sisi in ("lateral", "medial"):
            for pg in data.panel_kelas(sp["nama"], sisi):
                P = np.array(pg["luar"], float)
                luas = 0.5 * float(np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(np.roll(P[:, 0], -1), P[:, 1]))
                poli = _resample_xz([tuple(p) for p in P] + [tuple(P[0])], 0.25)[:-1]
                garis = _offset_xz(poli, J["offset"] if luas > 0 else -J["offset"], True)  # ke dalam poligon
                angkat = sp["lapis"][1] + 0.1
                tt = [None if q is None else titik_S(q[0], q[1], sisi, angkat) for q in garis]
                tt = [t_ if t_ is not None and (bvh.find_nearest(t_[0], 1.0)[0] is not None) else None for t_ in tt]
                n_dash[sp["nama"]] += dash(tt)
    if not V:
        return None
    ob = mesh_obj("jahitan", np.array(V) / 1000.0, F, pk, mat["tali"])
    for k, v in n_dash.items():
        ob[f"dash_{k}"] = v
    return ob


def lapisan_data():
    """Nama objek lapisan untuk AM-13 (proyek panel data): badan, mesh, lidah + semua panel upper data."""
    return ["upper", "panel_mesh", "lidah"] + sorted(o.name for o in bpy.data.objects if o.get("panel") and
                                                    o.name in bpy.context.scene.objects)
