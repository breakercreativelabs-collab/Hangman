"""QC resep sepatu M2 (upper): AM-09 kehalusan, AM-10 IoU swoosh per sisi, AM-11 garis mudguard, AM-12 tali + lubang,
AM-13 lapisan panel tidak z-fighting, AM-14 slot material bernama peran."""
import bpy
import numpy as np
from mathutils import Vector

from ....inti.qc import cek, iou
from ....inti.scene import objek_produk
from ..geometri import bvh_dunia
from ..penyaring import gauss
from ..qc_siluet import di_dalam, ray_ob, riak_deg
from . import data
from .ambang import AMBANG, SW
from .bentuk import R_TALI, TERAKHIR


# ---------------- M2: upper (AM-09 .. AM-14) ----------------
def cari_objek(*nama):
    for n in nama:
        ob = bpy.data.objects.get(n)
        if ob is not None:
            return ob
    return None


def _garis_acuan():
    """Fungsi halus untuk MENEMPATKAN garis ukur AM-09 (sama untuk model baik dan negatif)."""
    xs, _, zt = data.profil_samping("lateral")
    g1, v1 = gauss(xs, zt, 2.0)
    mid, _ = data.garis_midsole()
    g2, v2 = gauss(mid[:, 0], mid[:, 1], 3.0)
    gp = np.arange(0.0, data.PANJANG, 0.5)
    g3, v3 = gauss(gp, np.array([data.plan_y(x)[0] for x in gp]), 2.0)
    return (lambda x: float(np.interp(x, g1, v1)), lambda x: float(np.interp(x, g2, v2)),
            lambda x: float(np.interp(x, g3, v3)))


def qc_halus():
    """AM-09 (C-A3): kehalusan permukaan upper. Ray ke badan upper saja (panel = offset badan, ikut halus/bergelombang):
    4 garis samping (lateral/medial x 35%/60% tinggi upper, x 20-275 mm) + 3 garis atas toe box (x 15-85, y tengah
    dan +-10 mm), tiap 1 mm. Nilai = RMS riak normal terbesar antar garis (derajat)."""
    ob = cari_objek("upper", "upper_blok")
    a = AMBANG["riak_deg"]
    if ob is None:
        return cek("AM-09", "riak_normal_upper_deg", 99.0, False, f"<= {a} deg", "objek upper tidak ada"), {}
    zt, mt, cy = _garis_acuan()
    garis = {}
    for sisi, sg in (("lateral", 1), ("medial", -1)):
        for f in (0.35, 0.6):
            n = []
            for x in np.arange(20.0, 275.0, 1.0):
                h = ray_ob(ob, (x, sg * 300.0, mt(x) + f * (zt(x) - mt(x))), (0, -sg, 0), True)
                if h:
                    n.append(tuple(h[1]))
            garis[f"{sisi}_{int(f * 100)}"] = n
    for off in (-10.0, 0.0, 10.0):
        n = []
        for x in np.arange(15.0, 85.0, 1.0):
            h = ray_ob(ob, (x, cy(x) + off, 300.0), (0, 0, -1), True)
            if h:
                n.append(tuple(h[1]))
        garis[f"atas_{int(off)}"] = n
    nilai = {k: (riak_deg(v) if len(v) >= 40 else 99.0) for k, v in garis.items()}
    terburuk = max(nilai, key=nilai.get)
    v = nilai[terburuk]
    return cek("AM-09", "riak_normal_upper_deg", v, v <= a, f"<= {a} deg",
               f"objek {ob.name}; terburuk {terburuk}; " + ", ".join(f"{k} {w:.3f}" for k, w in nilai.items())), nilai


def masker_swoosh_data(sisi, xs, zs, geser=(0.0, 0.0)):
    x, lo, hi = data.poligon_swoosh(sisi)
    x = x + geser[0]
    LO, HI = np.interp(xs, x, lo) + geser[1], np.interp(xs, x, hi) + geser[1]
    dalam = (xs >= x[0]) & (xs <= x[-1])
    Z = zs[:, None]
    return (Z >= LO[None]) & (Z <= HI[None]) & dalam[None]


def qc_swoosh():
    """AM-10: IoU garis luar swoosh (proyeksi sepanjang Y, ray ke objek swoosh sisi itu saja) vs poligon data sisi
    itu. Dua sisi = dua cek independen (data lateral & medial dari foto berbeda; posisi beda ~11 mm)."""
    hasil, art = [], {}
    a = AMBANG["iou_swoosh_min"]
    for sisi, sg in (("lateral", 1), ("medial", -1)):
        xs = np.arange(130.0, 270.0, SW) + SW / 2
        zs = np.arange(50.0, 105.0, SW) + SW / 2
        d = masker_swoosh_data(sisi, xs, zs)
        lantai = iou(d, masker_swoosh_data(sisi, xs, zs, (0.5, 0.5)))
        ob = cari_objek(f"swoosh_{sisi}")
        m = np.zeros_like(d)
        if ob is not None:
            for i, z in enumerate(zs):
                for j, x in enumerate(xs):
                    m[i, j] = ray_ob(ob, (x, sg * 300.0, z), (0, -sg, 0)) is not None
        v = iou(m, d)
        hasil.append(cek("AM-10", f"iou_swoosh_{sisi}", v, v >= a, f">= {a}",
                         f"{int(m.sum())} px model, {int(d.sum())} px data, {SW} mm/px; acuan data: IoU data vs data "
                         f"geser (0,5; 0,5) mm = {lantai:.4f} (dasar ambang)" + ("" if ob else "; objek swoosh tidak ada")))
        art[sisi] = (m, d)
    return hasil, art


def qc_mudguard():
    """AM-11: garis atas mudguard (proyeksi lateral, ray ke objek mudguard saja): z teratas yang masih kena mudguard
    (scan 0,5 mm + bisection 0,01 mm) di setiap x data, kecuali ujung toe tempat mudguard menutup sampai siluet
    atas (garis data < 3 mm dari siluet). Rata-rata |model - data|."""
    ob = cari_objek("mudguard")
    mg = np.array(data.DATA["garis_mudguard_atas_lateral"], float)
    xs, _, zt = data.profil_samping("lateral")
    a = AMBANG["mudguard_mm"]
    pakai = [(x, z) for x, z in mg if np.interp(x, xs, zt) - z > 3.0]
    if ob is None:
        return cek("AM-11", "garis_atas_mudguard_galat_rata_mm", 99.0, False, f"<= {a} mm", "objek mudguard tidak ada"), None
    kena = lambda x, z: ray_ob(ob, (x, 300.0, z), (0, -1, 0)) is not None
    hasil = []
    for x, zd in pakai:
        zz = np.arange(zd - 12.0, zd + 12.0, 0.5)
        k = [kena(x, z) for z in zz]
        idx = [i for i in range(len(zz) - 1) if k[i] and not k[i + 1]]
        if not idx:
            hasil.append(np.nan)
            continue
        lo, hi = zz[idx[-1]], zz[idx[-1] + 1]
        while hi - lo > 0.01:
            m = (lo + hi) / 2
            lo, hi = (m, hi) if kena(x, m) else (lo, m)
        hasil.append((lo + hi) / 2)
    zm = np.array(hasil)
    zd = np.array([z for _, z in pakai])
    ok = ~np.isnan(zm)
    g = np.abs(zm[ok] - zd[ok])
    v = float(g.mean()) if ok.any() else 99.0
    lulus = v <= a and ok.mean() >= 0.95
    return cek("AM-11", "garis_atas_mudguard_galat_rata_mm", v, lulus, f"<= {a} mm (>= 95% titik terukur)",
               f"{ok.sum()}/{len(ok)} titik (x >= {pakai[0][0]:.1f}; {len(mg) - len(pakai)} titik toe dilewati), "
               f"maks {g.max():.2f} mm, median {np.median(g):.2f}; medial = garis lateral [D]"), \
        (np.array([p[0] for p in pakai]), zd, zm)


def qc_tali():
    """AM-12: (a) tali tidak menembus upper: jarak bertanda garis tengah tali ke semua objek produk lain (BVH, tanda
    dari normal permukaan terdekat) - r >= 0; antar segmen tali >= 2r. (b) lubang: 6-7 pasang, jarak antar lubang
    10-16 mm per sisi, dan 2 lubang besar data per sisi (luas >= 10 mm2) masing-masing punya lubang model dalam 3 mm (x, z)."""
    from mathutils.kdtree import KDTree
    jalur = TERAKHIR.get("jalur_tali") if bpy.data.objects.get("tali") else None
    lub = TERAKHIR.get("lubang") if bpy.data.objects.get("tali") else None
    if not jalur or not lub:
        return [cek("AM-12", "tali_jarak_min_mm", -99.0, False, ">= 0 mm", "tali tidak ada"),
                cek("AM-12", "lubang_tali_wajar", 0, False, "6-7 pasang", "tali tidak ada")]
    root = bpy.data.objects["PRODUCT_ROOT"].matrix_world
    dunia = lambda p: (root @ (Vector(p) / 1000.0)) * 1000.0
    lain = [o for o in objek_produk() if o.name not in ("tali", "jahitan")]
    bvhs = [(o.name, bvh_dunia([o])[0]) for o in lain]
    r = R_TALI * root.to_scale()[0]
    jarak, terburuk = 1e9, None
    pts, sid = [], []
    for s, j in enumerate(jalur):
        for p in j:
            q = dunia(p)
            pts.append(q)
            sid.append(s)
            for nama, b in bvhs:
                loc, _, _, d = b.find_nearest(q, r + 1.0)
                if loc is None:
                    continue
                sd = -d if di_dalam(b, q) else d
                if sd - r < jarak:
                    jarak, terburuk = sd - r, f"{nama} ({q.x:.1f}, {q.y:.1f}, {q.z:.1f})"
    jarak = min(jarak, 1.0)
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    antar = 1e9
    for i, p in enumerate(pts):
        for _, k, d in kd.find_range(p, 2 * r + 1.0):
            if sid[k] != sid[i]:
                antar = min(antar, d)
    a = AMBANG["tali_jarak_mm"]
    c1 = cek("AM-12", "tali_jarak_min_mm", float(jarak), jarak >= a and antar >= 2 * r - 1e-6, f">= {a} mm (dan antar segmen >= 2r)",
             f"{len(jalur)} segmen, r {r:.2f} mm, terdekat: {terburuk}; jarak antar segmen min "
             f"{antar if antar < 1e8 else float('inf'):.2f} mm (>= {2 * r:.2f})")
    # lubang
    n = min(len(lub["lateral"]), len(lub["medial"]))
    jarak_l = {s: float(np.median(np.diff(sorted(p[0] for p in lub[s])))) if len(lub[s]) > 1 else 0.0 for s in lub}
    galat = []
    for s in ("lateral", "medial"):
        for xd, zd, _ in TERAKHIR["lubang_data"][s]:  # zd None = deret [D] proyek (hanya x)
            galat.append(min(max(abs(p[0] - xd), abs(p[2] - zd) if zd is not None else 0.0) for p in lub[s]))
    gmax = max(galat) if galat else 0.0  # proyek tanpa lubang data (deret [D] dari proyek.toml): hanya jumlah + jarak
    ok = 6 <= n <= 7 and all(10.0 <= v <= 16.0 for v in jarak_l.values()) and gmax <= AMBANG["lubang_mm"]
    c2 = cek("AM-12", "lubang_tali_wajar", n, ok, f"6-7 pasang, jarak 10-16 mm, lubang data <= {AMBANG['lubang_mm']} mm",
             f"jarak lateral {jarak_l['lateral']:.2f} / medial {jarak_l['medial']:.2f} mm; "
             + f"galat {len(galat)} lubang acuan " + ", ".join(f"{g:.2f}" for g in galat) + " mm"
             + (" (acuan = deret [D] proyek.toml, x saja)" if any(d[1] is None for s in TERAKHIR["lubang_data"]
                                                                  for d in TERAKHIR["lubang_data"][s]) else " (lubang lain [D])"))
    return [c1, c2]


LAPISAN = ("upper", "panel_mesh", "mudguard", "eyestay_lateral", "eyestay_medial", "overlay_tumit",
           "swoosh_lateral", "swoosh_medial", "lidah")


def qc_lapisan(lapisan=LAPISAN):
    """AM-13: lapisan panel tidak z-fighting dan tidak saling tembus. Untuk setiap pasangan objek lapisan: (a) jumlah
    pasangan segitiga yang berpotongan (BVH overlap) = 0; (b) jarak vertex ke permukaan objek lain >= 0,2 mm
    (sampel <= 6000 vertex per objek). Di luar cek: midsole (panel sengaja tertanam 2 mm), eyelet, tali, jahitan."""
    obs = [bpy.data.objects[n] for n in lapisan if bpy.data.objects.get(n)]
    a = AMBANG["lapis_mm"]
    if len(obs) < len(lapisan):
        return cek("AM-13", "lapis_jarak_min_mm", -1.0, False, f">= {a} mm, 0 potongan", "objek lapisan tidak lengkap")
    data = {o.name: bvh_dunia([o]) for o in obs}
    potong, pasangan = 0, []
    for i, o1 in enumerate(obs):
        for o2 in obs[i + 1:]:
            k = len(data[o1.name][0].overlap(data[o2.name][0]))
            if k:
                potong += k
                pasangan.append(f"{o1.name}/{o2.name} {k}")
    rng = np.random.default_rng(0)
    dmin, dimana = 1e9, ""
    for o1 in obs:
        V = data[o1.name][1]
        if len(V) > 6000:
            V = V[rng.choice(len(V), 6000, replace=False)]
        for o2 in obs:
            if o2 is o1:
                continue
            b = data[o2.name][0]
            for v in V:
                hit = b.find_nearest(Vector(v), 1.0)
                if hit[0] is not None and hit[3] < dmin:
                    dmin, dimana = hit[3], f"{o1.name} ke {o2.name} di ({v[0]:.0f}, {v[1]:.0f}, {v[2]:.0f})"
    dmin = min(dmin, 1.0)
    return cek("AM-13", "lapis_jarak_min_mm", float(dmin), potong == 0 and dmin >= a, f">= {a} mm, 0 potongan",
               f"{len(obs)} objek, segitiga berpotongan {potong}" + (f" ({'; '.join(pasangan[:4])})" if pasangan else "")
               + f"; terdekat {dimana}")


def qc_material():
    """AM-14: slot material per bagian memakai nama peran P3 (selera.md); semua 10 peran ada, tiap objek produk
    memakai peran sebagai material utama."""
    pakai, salah = set(), []
    PERAN = data.daftar_peran()
    for ob in objek_produk():
        nama = [m.name for m in ob.data.materials if m]
        pakai |= set(nama)
        if not nama or nama[0] not in PERAN:
            salah.append(ob.name)
    hilang = [p for p in PERAN if p not in pakai]
    return cek("AM-14", "slot_material_peran", len(PERAN) - len(hilang), not hilang and not salah,
               f"{len(PERAN)} peran", ("hilang: " + ", ".join(hilang) + "; " if hilang else "")
               + ("objek tanpa peran: " + ", ".join(salah) if salah else "semua objek memakai peran"))
