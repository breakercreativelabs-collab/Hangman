"""Jalur aset (keputusan pengguna 2026-10-17): untuk bentuk organik, cari model 3D terbuka BERLISENSI, nilai kualitasnya
dengan angka (KA-01..07), lalu sesuaikan (skala, putar, potong, gabung dengan bagian buatan perakit) lewat SDF ->
mesh baru yang tertutup dan lolos QC KC. Non-generatif: tidak ada AI yang membuat bentuk; atribusi wajib.

Aset hanya disimpan di klien/ (tidak di repo). Rancangan: [[bagian]] resep = "aset" dengan model, objek, lisensi,
atribusi, putar_z, tinggi_mm (tinggi aset utuh setelah skala), potong_z (simpan z >= potong_z), halus_potong.
"""
import math
import os

import numpy as np

from ...inti import io, qc

LISENSI_BOLEH = ("CC0", "CC-BY", "CC-BY-4.0", "CC-BY 4.0", "PUBLIC DOMAIN", "MIT")


def muat_aset(b):
    """Impor glTF, ambil satu objek, transform dunia diterapkan, alas di asal (pusat XY), skala ke `tinggi_mm`,
    putar Z `putar_z`. Mengembalikan (titik mm Nx3, segitiga Mx3)."""
    import bpy
    sumber = io.path_repo(b["model"])
    if not os.path.isfile(sumber):
        raise FileNotFoundError(f"aset {b['model']} tidak ada (unduh dulu ke klien/; lihat sumber di rancangan)")
    sebelum = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=sumber)
    baru = [o for o in bpy.data.objects if o not in sebelum]
    target = next((o for o in baru if o.name == b["objek"]), None)
    if target is None:
        raise ValueError(f"objek '{b['objek']}' tidak ada di aset; tersedia: {[o.name for o in baru if o.type == 'MESH']}")
    me = target.data.copy()
    me.transform(target.matrix_world)
    if b.get("subdiv", 0):  # haluskan aset low-poly: las vertex (bmesh) dulu, lalu Catmull-Clark (subdivision surface)
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6 * max(target.dimensions))
        bm.to_mesh(me)
        bm.free()
        tmp = bpy.data.objects.new("aset_tmp", me)
        bpy.context.scene.collection.objects.link(tmp)
        mod = tmp.modifiers.new("subdiv", "SUBSURF")
        mod.levels = mod.render_levels = int(b["subdiv"])
        ev = tmp.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me2 = bpy.data.meshes.new_from_object(ev)
        bpy.data.objects.remove(tmp)
        bpy.data.meshes.remove(me)
        me = me2
    me.calc_loop_triangles()
    t = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", t)
    t = t.reshape(-1, 3)
    f = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", f)
    for o in baru:
        bpy.data.objects.remove(o)
    bpy.data.meshes.remove(me)
    t, f = las(t, f.reshape(-1, 3))
    pusat = np.array([(t[:, 0].min() + t[:, 0].max()) / 2, (t[:, 1].min() + t[:, 1].max()) / 2, t[:, 2].min()])
    t = (t - pusat) * (b["tinggi_mm"] / (t[:, 2].max() - t[:, 2].min()))
    a = math.radians(b.get("putar_z", 0.0))
    x, y = t[:, 0] * math.cos(a) - t[:, 1] * math.sin(a), t[:, 0] * math.sin(a) + t[:, 1] * math.cos(a)
    return np.c_[x, y, t[:, 2]], f


def las(titik, seg, tol=1e-6):
    """Satukan vertex berposisi sama (glTF memecah vertex di sambungan UV/normal -> tampak bocor & ribuan bagian
    lepas padahal bentuknya menyatu). Toleransi relatif ukuran objek; buang segitiga degeneratif."""
    skala = float(np.ptp(titik, axis=0).max()) or 1.0
    kunci = np.round(titik / (skala * tol)).astype(np.int64)
    _, idx, inv = np.unique(kunci, axis=0, return_index=True, return_inverse=True)
    seg = inv.ravel()[seg]
    seg = seg[(seg[:, 0] != seg[:, 1]) & (seg[:, 1] != seg[:, 2]) & (seg[:, 0] != seg[:, 2])]
    return titik[idx], seg


def nilai_aset(titik, seg, b):
    """Juri kualitas aset KA-01..07 (ATURAN_QC perakit). Skor 0-100 = persen cek lulus berbobot; nilai A/B/C."""
    e = np.sort(np.vstack([seg[:, [0, 1]], seg[:, [1, 2]], seg[:, [2, 0]]]), axis=1)
    _, n_e = np.unique(e, axis=0, return_counts=True)
    bocor = float((n_e != 2).mean())
    a, bb, c = titik[seg[:, 0]], titik[seg[:, 1]], titik[seg[:, 2]]
    vol = float(np.einsum("ij,ij->i", a, np.cross(bb, c)).sum() / 6.0)
    sisi = np.stack([np.linalg.norm(bb - a, axis=1), np.linalg.norm(c - bb, axis=1), np.linalg.norm(a - c, axis=1)], 1)
    luas = np.linalg.norm(np.cross(bb - a, c - a), axis=1) / 2
    rasio = sisi.max(1) ** 2 / np.maximum(4 * luas / math.sqrt(3), 1e-12)  # 1 = sama sisi
    serpih = float((rasio > 10).mean())
    # bagian lepas: komponen terhubung lewat union-find tepi
    induk = np.arange(len(titik))

    def akar(i):
        while induk[i] != i:
            induk[i] = induk[induk[i]]
            i = induk[i]
        return i
    for p, q in e:
        rp, rq = akar(p), akar(q)
        if rp != rq:
            induk[rp] = rq
    pakai = np.unique(seg)
    lepas = len({akar(i) for i in pakai})
    from mathutils.kdtree import KDTree
    kd = KDTree(len(titik))
    for i, p in enumerate(titik):
        kd.insert(p, i)
    kd.balance()
    sim = float(np.median([kd.find((p[0], -p[1], p[2]))[2] for p in titik[::max(len(titik) // 3000, 1)]]))
    lis = str(b.get("lisensi", "")).upper()
    cek = [
        qc.cek("KA-01", "lisensi terbuka + atribusi", lis, any(lis.startswith(x) for x in LISENSI_BOLEH) and
               bool(b.get("atribusi")), "CC0/CC-BY/MIT + atribusi tertulis"),
        qc.cek("KA-02", "tepi bocor (non-manifold)", bocor, bocor <= 0.001, "<= 0,1% tepi (SDF butuh mesh tertutup; "
               "uji negatif: lubang 10% = 0,3-1% lolos ambang lama 1%)"),
        qc.cek("KA-03", "orientasi normal (volume > 0)", vol, vol > 0, "volume bertanda > 0"),
        qc.cek("KA-04", "segitiga serpih (rasio > 10)", serpih, serpih <= 0.05, "<= 5%"),
        qc.cek("KA-05", "jumlah segitiga", len(seg), 2000 <= len(seg) <= 500000, "2.000-500.000"),
        qc.cek("KA-06", "bagian lepas", lepas, lepas <= b.get("maks_lepas", 3), f"<= {b.get('maks_lepas', 3)}"),
        qc.cek("KA-07", "simetri cermin Y (median)", sim, sim <= b.get("toleransi_simetri_aset", 0.5),
               f"<= {b.get('toleransi_simetri_aset', 0.5)} mm (aset simetris)"),
    ]
    bobot = dict(zip([f"KA-0{i}" for i in range(1, 8)], (30, 15, 10, 10, 10, 10, 15)))
    skor = sum(bobot[c["id"]] for c in cek if c["lulus"])
    nilai = "A" if skor >= 85 and cek[0]["lulus"] else "B" if skor >= 65 and cek[0]["lulus"] else "C"
    return dict(skor=skor, nilai=nilai, cek=cek)


def uji_negatif_aset(titik, seg, b):
    """Tiap KA wajib gagal pada aset yang sengaja dirusak (aturan repo: QC baru wajib uji negatif)."""
    n = len(seg)
    serpih = np.c_[np.arange(0, 3000, 3), np.arange(1, 3000, 3), np.arange(2, 3000, 3)] % len(titik)
    t_serpih = np.vstack([titik, titik[serpih[:, 0]] + [0, 0, 0], titik[serpih[:, 0]] + [5.0, 0, 0],
                          titik[serpih[:, 0]] + [10.0, 0.001, 0]])
    k = len(titik)
    m = np.arange(len(serpih))
    seg_serpih = np.vstack([seg, np.c_[k + m, k + len(serpih) + m, k + 2 * len(serpih) + m]] * 1)
    rusak = [
        ("lisensi kosong", titik, seg, dict(b, lisensi="", atribusi=""), "KA-01"),
        ("10% segitiga dibuang", titik, seg[n // 10:], b, "KA-02"),
        ("normal dibalik", titik, seg[:, ::-1], b, "KA-03"),
        ("segitiga serpih ditambahkan", t_serpih, np.vstack([seg_serpih] + [seg_serpih[n:]] * 40), b, "KA-04"),
        ("dipangkas ke 1.000 segitiga", titik, seg[:1000], b, "KA-05"),
        ("5 salinan terpisah", np.vstack([titik + [60.0 * i, 0, 0] for i in range(5)]),
         np.vstack([seg + len(titik) * i for i in range(5)]), b, "KA-06"),
        ("separuh +Y digeser 2 mm", titik + np.where(titik[:, 1:2] > 0, [0, 0, 2.0], 0), seg, b, "KA-07"),
    ]
    hasil = []
    for nama, t, f, bb, wajib in rusak:
        cek = nilai_aset(t, f, bb)["cek"]
        ok, gagal = qc.tertangkap(cek, [wajib])
        hasil.append(dict(nama=nama, wajib=[wajib], gagal=gagal, tertangkap=ok))
        print(f"  negatif aset {'OK ' if ok else 'BOCOR'} {nama}: gagal {gagal}")
    return hasil


CIRI_WAJIB = {  # KA-08: ciri anatomi yang wajib ada per jenis objek (pelajaran: aset kuda nilai A tapi tanpa mata)
    "kuda": ("mata", "telinga", "lubang hidung", "mulut", "surai"),
}


def kelengkapan(r):
    """KA-08: setiap ciri wajib jenis objek harus ada, baik di aset (`ciri_aset`, dinyatakan Claude setelah memeriksa
    render close-up aset) maupun sebagai [[detail]] yang namanya memuat ciri itu. Nilai = ciri yang hilang."""
    hasil = []
    for b in r["bagian"]:
        if b["resep"] != "aset" or "jenis_objek" not in b:
            continue
        ada = set(b.get("ciri_aset", ())) | {c for c in CIRI_WAJIB.get(b["jenis_objek"], ())
                                             for d in r.get("detail", []) if c in d.get("nama", "")}
        hilang = [c for c in CIRI_WAJIB.get(b["jenis_objek"], ()) if c not in ada]
        hasil.append(qc.cek("KA-08", f"kelengkapan ciri wajib ({b['jenis_objek']})", hilang or "lengkap", not hilang,
                            "semua: " + ", ".join(CIRI_WAJIB.get(b["jenis_objek"], ("jenis tak dikenal",)))))
    return hasil


def uji_negatif_kelengkapan(r):
    """KA-08 wajib gagal bila detail mata dibuang (cacat asli aset kuda)."""
    rusak = dict(r, detail=[d for d in r.get("detail", []) if "mata" not in d.get("nama", "")])
    ok, gagal = qc.tertangkap(kelengkapan(rusak), ["KA-08"])
    print(f"  negatif aset {'OK ' if ok else 'BOCOR'} detail mata dibuang: gagal {gagal}")
    return [dict(nama="detail mata dibuang", wajib=["KA-08"], gagal=gagal, tertangkap=ok)]


def medan_aset(b, asal, vox, bentuk, Z, negatif=False):
    """SDF aset di kisi perakit (level set OpenVDB dari segitiga; nilai mm, negatif di dalam) + potong z bawah."""
    import openvdb
    from . import sdf
    titik, seg = muat_aset(b)
    lap = nilai_aset(titik, seg, b)
    if negatif:
        lap["negatif"] = uji_negatif_aset(titik, seg, b)
    p = ((titik - np.asarray(asal)) / vox).astype(np.float32)  # koordinat indeks kisi
    g = openvdb.FloatGrid.createLevelSetFromPolygons(p, triangles=seg.astype(np.uint32),
                                                     transform=openvdb.createLinearTransform(1.0),
                                                     exBandWidth=4.0, inBandWidth=1.0e4)
    m = np.full(bentuk, g.background, np.float32)
    g.copyToArray(m, ijk=(0, 0, 0))
    m *= vox  # satuan indeks -> mm
    if "perpanjang_dari_z" in b:  # penampang di z itu diteruskan lurus ke bawah (badan menyatu ke alas, bukan "kelereng")
        k0 = int(np.abs(Z[0, 0, :] - b["perpanjang_dari_z"]).argmin())
        m[:, :, :k0] = m[:, :, k0:k0 + 1]
    if "potong_z" in b:
        m = sdf.kurang(m, Z - b["potong_z"], b.get("halus_potong", 0.0))  # buang wilayah z < potong_z (SDF negatif di bawah)
    return m, lap
