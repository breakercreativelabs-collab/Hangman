"""Perakit: rancangan bentuk (TOML, ditulis Claude dari prompt) -> SDF -> mesh -> QC angka -> render lembar kontak.

Kontrak rancangan (lihat proyek/kuda_catur/rancangan.toml): [objek] (ukuran target, voxel), [[bagian]] (resep putar |
bantal), [[detail]] (kurangi_/tambah_ bola | kapsul | kotak | deret_kapsul | kerucut | garis | elipsoid, pahat_bidang),
[[kerangka]] (koordinat lokal u-y-w + skala, mis. sepanjang kepala; detail memakai `kerangka = nama`), [bahan], [qc].
Perakit tidak menebak: kunci yang hilang / resep tak dikenal = galat keras (Claude yang melengkapi rancangan).
"""
import os
import time
import tomllib

import numpy as np

from ...inti import io, log, qc
from . import sdf

RESEP = ("putar", "bantal", "aset")
DETAIL = ("kurangi_bola", "tambah_bola", "kurangi_kapsul", "kurangi_kotak", "tambah_kotak", "kurangi_deret_kapsul", "tambah_kerucut",
          "kurangi_kerucut", "pahat_bidang", "kurangi_garis", "tambah_garis", "tambah_elipsoid", "kurangi_elipsoid")


def muat_rancangan(path):
    with open(path, "rb") as f:
        r = tomllib.load(f)
    for b in r["bagian"]:
        if b["resep"] not in RESEP:
            raise ValueError(f"resep '{b['resep']}' belum ada di katalog {RESEP} (catat sebagai celah)")
    for d in r.get("detail", []):
        if d["jenis"] not in DETAIL:
            raise ValueError(f"detail '{d['jenis']}' belum ada di katalog {DETAIL} (catat sebagai celah)")
    return r


def batas(r):
    """Kotak kisi (mm) yang memuat semua bagian + 2 mm, atau [objek] batas_mm bila ditulis (bentuk susun primitif)."""
    if "batas_mm" in r["objek"]:
        return [list(v) for v in r["objek"]["batas_mm"]]
    xs, ys, zs = [], [], []
    for b in r["bagian"]:
        if b["resep"] == "putar":
            rmax = max(p[0] for p in b["profil"])
            xs += [-rmax, rmax]
            ys += [-rmax, rmax]
            zs += [p[1] for p in b["profil"]]
        else:
            xs += [p[0] for p in b["siluet"]]
            zs += [p[1] for p in b["siluet"]]
            hmax = max(t[1] for t in b["tebal_z"])
            ys += [-hmax, hmax]
    for d in r.get("detail", []):
        if d["jenis"].endswith("kerucut"):
            for p, rad in ((d["a"], d["r1"]), (d["b"], d["r2"])):
                xs += [p[0] - rad, p[0] + rad]
                ys += [-abs(p[1]) - rad, abs(p[1]) + rad]
                zs += [p[2] - rad, p[2] + rad]
    return [min(xs) - 2, min(ys) - 2, min(zs) - 2], [max(xs) + 2, max(ys) + 2, max(zs) + 2]


def ke_dunia(kerangka, p, s=1.0):
    """Titik [u, y, w] di kerangka lokal (asal [x, z], sudut derajat menunduk) -> [x, y, z] dunia; s = cermin Y."""
    if kerangka is None:
        return (p[0], s * p[1], p[2])
    a, k = np.radians(kerangka["sudut"]), kerangka.get("skala", 1.0)
    ax, az = kerangka["asal"]
    u, y, w = p[0] * k, p[1] * k, p[2] * k
    return (ax + u * np.cos(a) + w * np.sin(a), s * y, az - u * np.sin(a) + w * np.cos(a))


def lokal(kerangka, X, Y, Z):
    """Koordinat dunia -> lokal kerangka (u, y, w) dalam satuan lokal + skala (mm per satuan)."""
    if kerangka is None:
        return X, Y, Z, 1.0
    a, k = np.radians(kerangka["sudut"]), kerangka.get("skala", 1.0)
    dx, dz = X - kerangka["asal"][0], Z - kerangka["asal"][1]
    return (dx * np.cos(a) - dz * np.sin(a)) / k, Y / k, (dx * np.sin(a) + dz * np.cos(a)) / k, k


def arah_dunia(kerangka, n, s=1.0):
    """Vektor arah lokal (u, y, w) -> dunia (tanpa skala)."""
    if kerangka is None:
        return np.array((n[0], s * n[1], n[2]), float)
    a = np.radians(kerangka["sudut"])
    return np.array((n[0] * np.cos(a) + n[2] * np.sin(a), s * n[1], -n[0] * np.sin(a) + n[2] * np.cos(a)), float)


def luas_bidang(titik, muka, r):
    """KC-07 per pahat_bidang ber-`min_luas_mm2`: luas (mm2) bidang datar (muka <= 0,1 mm dari bidang, normal <= 8 deg,
    dalam 1,5 x wilayah) dan sudut lipat tepi = persentil 75 sudut normal muka di cincin 0,7 mm di luar bidang terhadap
    normal bidang (tepi keras = besar, dihaluskan = kecil). Sisi cermin: diambil yang terkecil."""
    kerangka = {k["nama"]: k for k in r.get("kerangka", [])}
    t = sdf.segitiga(muka)
    a, b, c = titik[t[:, 0]], titik[t[:, 1]], titik[t[:, 2]]
    pusat, silang = (a + b + c) / 3, np.cross(b - a, c - a)
    luas = np.linalg.norm(silang, axis=1) / 2
    nf = silang / np.maximum(2 * luas[:, None], 1e-12)
    from mathutils.kdtree import KDTree
    kd = KDTree(len(pusat))
    for i, p in enumerate(pusat):
        kd.insert(p, i)
    kd.balance()
    hasil = []
    for d in r.get("detail", []):
        if d["jenis"] != "pahat_bidang" or "min_luas_mm2" not in d:
            continue
        kr = kerangka.get(d.get("kerangka"))
        k = kr.get("skala", 1.0) if kr else 1.0
        per_sisi = []
        for s in ((1.0, -1.0) if d.get("cermin") else (1.0,)):
            n = arah_dunia(kr, d["normal"], s)
            n /= np.linalg.norm(n)
            p0, pw = np.array(ke_dunia(kr, d["titik"], s)), np.array(ke_dunia(kr, d["pusat"], s))
            dekat = np.linalg.norm(pusat - pw, axis=1) <= 1.5 * k * max(d["setengah"])
            pilih = dekat & (np.abs((pusat - p0) @ n) <= 0.1) & (nf @ n >= np.cos(np.radians(8)))
            # cincin 0,7 mm di luar bidang: muka bukan-bidang dekat muka bidang; tepi keras = normalnya jauh dari n
            cincin = {j for i in np.flatnonzero(pilih)[::3] for _, j, _ in kd.find_range(pusat[i], 0.7)}
            cincin = np.array(sorted(j for j in cincin if not pilih[j]), int)
            sudut = np.degrees(np.arccos(np.clip(nf[cincin] @ n, -1, 1))) if len(cincin) else np.zeros(0)
            per_sisi.append((float(luas[pilih].sum()), float(np.percentile(sudut, 75)) if len(sudut) else 0.0))
        hasil.append((d["nama"], min(v[0] for v in per_sisi), d["min_luas_mm2"], min(v[1] for v in per_sisi),
                      d.get("min_sudut_tepi", r["qc"].get("min_sudut_tepi", 20.0))))
    return hasil


def _detail(X, Y, Z, d, cermin_y, kerangka=None):
    s = -1.0 if cermin_y else 1.0
    j = d["jenis"]
    dunia = lambda p: ke_dunia(kerangka, p, s)  # noqa: E731
    k = kerangka.get("skala", 1.0) if kerangka else 1.0  # ukuran (r, jari) ikut skala kerangka
    d = {kk: ([v * k for v in vv] if kk == "jari" else vv * k if kk in ("r", "r1", "r2") else vv) for kk, vv in d.items()}
    if "titik" in d and kerangka:
        d["titik"] = [list(t[:3]) + [t[3] * k] if len(t) > 3 else t for t in d["titik"]]
    if j in ("kurangi_bola", "tambah_bola"):
        return sdf.sdf_bola(X, Y, Z, dunia(d["pusat"]), d["r"])
    if j.endswith("elipsoid"):
        sudut = (kerangka["sudut"] if kerangka else 0.0) + d.get("sudut", 0.0)
        return sdf.elipsoid(X, Y, Z, dunia(d["pusat"]), d["jari"], sudut)
    if j.endswith("kerucut"):
        return sdf.kerucut(X, Y, Z, dunia(d["a"]), dunia(d["b"]), d["r1"], d["r2"], d.get("skala", (1.0, 1.0, 1.0)))
    if j == "kurangi_kapsul":
        return sdf.sdf_kapsul(X, Y, Z, dunia(d["a"]), dunia(d["b"]), d["r"])
    if j.endswith("_kotak"):  # di kerangka lokal: kotak ikut berputar (mis. irisan miring mitra gajah)
        if kerangka:
            U, V, W, _ = lokal(kerangka, X, Y, Z)
            p = d["pusat"]
            return sdf.kotak(U, V * s, W, p, d["setengah"], d["r"] / k) * k  # setengah: satuan lokal
        return sdf.kotak(X, Y, Z, dunia(d["pusat"]), d["setengah"], d["r"])
    if j.endswith("_garis"):  # tabung sepanjang polyline [x, y, z(, r)]; r per titik = tabung meruncing
        medan = None
        for a, b in zip(d["titik"][:-1], d["titik"][1:]):
            ra, rb = (a[3] if len(a) > 3 else d["r"]), (b[3] if len(b) > 3 else d["r"])
            k = sdf.kerucut(X, Y, Z, dunia(a), dunia(b), ra, rb, d.get("skala", (1.0, 1.0, 1.0)))
            medan = k if medan is None else np.minimum(medan, k)
        return medan
    medan = None  # kurangi_deret_kapsul: kapsul searah Y sepanjang lebar_y di tiap titik (x, z)
    for x, z in d["titik"]:
        k = sdf.sdf_kapsul(X, Y, Z, (x, -d["lebar_y"] / 2, z), (x, d["lebar_y"] / 2, z), d["r"])
        medan = k if medan is None else np.minimum(medan, k)
    return medan


def pola_melingkar(daftar):
    """Detail ber-`putar_n` = n salinan diputar mengelilingi sumbu Z (mulai `putar_awal` derajat), koordinat dunia.
    Untuk mahkota bergerigi, deret lubang, jari-jari roda, dll."""
    for d in daftar:
        n = d.get("putar_n")
        if not n:
            yield d
            continue
        for i in range(n):
            a = np.radians(d.get("putar_awal", 0.0) + 360.0 * i / n)
            c, s_ = np.cos(a), np.sin(a)
            yield {k: ([v[0] * c - v[1] * s_, v[0] * s_ + v[1] * c, v[2]] if k in ("pusat", "a", "b") else v)
                   for k, v in d.items() if k not in ("putar_n", "putar_awal")}


def permukaan_y(total, x, y, z, px, pz):
    """y permukaan (mm, sisi +Y) medan saat ini di kolom (px, pz): nol terluar sepanjang Y, interpolasi linear."""
    i, k = int(np.abs(x - px).argmin()), int(np.abs(z - pz).argmin())
    kol = total[i, :, k]
    dalam = np.flatnonzero(kol < 0)
    if not len(dalam):
        raise ValueError(f"detail di (x {px}, z {pz}) tidak menyentuh benda (kolom kosong)")
    j = dalam.max()
    if j + 1 >= len(y):
        return float(y[j])
    a, b = kol[j], kol[j + 1]
    return float(y[j] + (y[j + 1] - y[j]) * a / (a - b))


def tempel_permukaan(d, total, x, y, z):
    """Posisi Y detail relatif permukaan (bukan ditebak): `kedalaman` (ukir, mm masuk) atau `tonjol` (tempel, mm keluar).
    Y = permukaan +/- jari-jari; berlaku untuk pusat atau tiap titik garis. Bentuk berubah -> detail tetap menempel."""
    d = dict(d)
    r = d.get("r", d.get("r1", 0.0))
    geser = (r - d["kedalaman"]) if "kedalaman" in d else (d["tonjol"] - r)
    if "pusat" in d:
        px, _, pz = d["pusat"]
        d["pusat"] = [px, permukaan_y(total, x, y, z, px, pz) + geser, pz]
    if "titik" in d and len(d["titik"][0]) >= 3:
        d["titik"] = [[t[0], permukaan_y(total, x, y, z, t[0], t[2]) + geser, t[2]] + list(t[3:]) for t in d["titik"]]
    return d


def medan(r, langkah=None):
    """SDF lengkap rancangan pada kisi voxel. Mengembalikan (medan [x, y, z], asal mm, vox mm).
    langkah(nama, medan, asal, vox): dipanggil tiap bagian/detail selesai (mode tonton)."""
    vox = r["objek"]["voxel_mm"]
    x, y, z = sdf.kisi(*batas(r), vox)
    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
    total = None
    for b in r["bagian"]:
        if b["resep"] == "aset":  # jalur aset: model terbuka berlisensi -> SDF (aset.py), dinilai KA-01..07
            from . import aset
            m, lap = aset.medan_aset(b, (float(x[0]), float(y[0]), float(z[0])), vox, X.shape, Z,
                                     negatif=r.get("_mode") == "penuh")
            r.setdefault("_laporan_aset", []).append(dict(bagian=b["nama"], model=b["model"], objek=b["objek"],
                                                         lisensi=b.get("lisensi"), atribusi=b.get("atribusi"), **lap))
            for c in lap["cek"]:
                print(f"  {c['id']} {'LULUS' if c['lulus'] else 'GAGAL'} {c['nama']}: {c['nilai']} ({c['ambang']})")
            print(f"  aset {b['objek']}: skor {lap['skor']} nilai {lap['nilai']}")
        elif b["resep"] == "putar":  # profil_halus = langkah mm kurva Catmull-Rom (tanpa = poligon apa adanya)
            prof = sdf.haluskan_profil(b["profil"], b["profil_halus"], b.get("profil_tajam", ())) if "profil_halus" in b else b["profil"]
            m = sdf.putar(X, Y, Z, prof, vox)
        else:
            m = sdf.bantal(x, y, z, b)
        total = m if total is None else sdf.gabung(total, m, r["objek"]["gabung_halus_mm"])
        if langkah:
            langkah(b["nama"], total, (float(x[0]), float(y[0]), float(z[0])), vox)
    kerangka = {k["nama"]: k for k in r.get("kerangka", [])}
    for d in pola_melingkar(r.get("detail", [])):
        kr = kerangka[d["kerangka"]] if "kerangka" in d else None
        if "kedalaman" in d or "tonjol" in d:
            d = tempel_permukaan(d, total, x, y, z)
        for cermin in ((False, True) if d.get("cermin") else (False,)):
            if d["jenis"] == "pahat_bidang":  # di kerangka lokal bila ada (bidang ikut arah kepala)
                s_ = -1.0 if cermin else 1.0
                t_, n_, p_ = d["titik"], d["normal"], d["pusat"]
                U, V, W, k = lokal(kr, X, Y, Z)
                total = sdf.pahat(total, U, V, W, (t_[0], s_ * t_[1], t_[2]), (n_[0], s_ * n_[1], n_[2]),
                                  (p_[0], s_ * p_[1], p_[2]), d["setengah"], d.get("transisi", 1.5), k)
                continue
            m = _detail(X, Y, Z, d, cermin, kr)
            k = d.get("halus", 0.0)
            total = sdf.gabung(total, m, k) if d["jenis"].startswith("tambah") else sdf.kurang(total, m, k)
        if langkah:
            langkah(d.get("nama", d["jenis"]), total, (float(x[0]), float(y[0]), float(z[0])), vox)
    return total, (float(x[0]), float(y[0]), float(z[0])), vox


def tepi_manifold(muka):
    """(jumlah tepi, tepi yang tidak dipakai tepat 2 muka)."""
    m = np.asarray(muka)
    e = np.sort(np.stack([m, np.roll(m, -1, axis=1)], -1).reshape(-1, 2), axis=1)
    _, n = np.unique(e, axis=0, return_counts=True)
    return len(n), int((n != 2).sum())


def jarak_cermin(titik, muka, langkah=5):
    """Galat simetri Y (mm): maks jarak titik cermin (subsampel) ke PERMUKAAN mesh (BVH mathutils; tahan decimate)."""
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons(titik.tolist(), np.asarray(muka).tolist())
    return max(bvh.find_nearest((p[0], -p[1], p[2]))[3] for p in titik[::langkah])


def qc_mesh(titik, muka, r):
    """QC KC-01..06 (ATURAN_QC.md perakit) pada mesh mm. Kembalikan daftar cek."""
    o, q = r["objek"], r["qc"]
    tinggi = float(titik[:, 2].max() - titik[:, 2].min())
    bawah = titik[titik[:, 2] < titik[:, 2].min() + 3.0]
    diam = float(2 * np.sqrt(bawah[:, 0] ** 2 + bawah[:, 1] ** 2).max())
    n_tepi, buruk = tepi_manifold(muka)
    simetri = jarak_cermin(titik, muka)
    tb = sdf.titik_berat(titik, muka)
    tapak = bawah[bawah[:, 2] < titik[:, 2].min() + 0.05]
    r_tapak = float(np.sqrt(tapak[:, 0] ** 2 + tapak[:, 1] ** 2).max()) if len(tapak) else 0.0
    r_tb = float(np.hypot(tb[0], tb[1]))
    n_seg = len(sdf.segitiga(muka))
    bidang = luas_bidang(titik, muka, r)
    kurang = [f"{n} {v:.1f}mm2/{a:.0f}deg" for n, v, m, a, ma in bidang if v < m or a < ma]
    tambahan = [qc.cek("KC-07", "tepi keras bidang pahat", min((a for *_, a, _ in bidang), default=0.0), not kurang,
                       "tiap bidang: luas >= min_luas_mm2 DAN sudut lipat tepi (P75) >= min_sudut_tepi",
                       "; ".join(f"{n} {v:.1f}mm2 {a:.0f}deg" for n, v, _, a, _ in bidang) +
                       (f" | KURANG: {kurang}" if kurang else ""))] if bidang else []
    return tambahan + [
        qc.cek("KC-01", "tinggi", tinggi, abs(tinggi - o["tinggi_mm"]) <= q["toleransi_tinggi_mm"],
               f"{o['tinggi_mm']} +-{q['toleransi_tinggi_mm']} mm"),
        qc.cek("KC-02", "diameter alas", diam, abs(diam - o["diameter_alas_mm"]) <= q["toleransi_diameter_mm"],
               f"{o['diameter_alas_mm']} +-{q['toleransi_diameter_mm']} mm"),
        qc.cek("KC-03", "manifold", buruk, buruk == 0, f"0 dari {n_tepi} tepi"),
        qc.cek("KC-04", "simetri cermin Y", simetri, simetri <= q["toleransi_simetri_mm"],
               f"<= {q['toleransi_simetri_mm']} mm"),
        qc.cek("KC-05", "stabil berdiri", r_tb, r_tb <= 0.5 * r_tapak, f"titik berat <= 0,5 x r tapak ({r_tapak:.1f})",
               f"titik berat {tb.round(2).tolist()}"),
        qc.cek("KC-06", "jumlah segitiga", n_seg, n_seg <= q["maks_poligon"], f"<= {q['maks_poligon']}"),
    ]


def haluskan(titik, muka, n):
    """Laplacian sederhana n kali (perusak uji negatif KC-07: meniru 'semua empuk')."""
    m = np.asarray(muka)
    e = np.vstack([m[:, [0, 1]], m[:, [1, 2]], m[:, [2, 0]]])
    t = titik.copy()
    for _ in range(n):
        jum, cacah = np.zeros_like(t), np.zeros(len(t))
        np.add.at(jum, e[:, 0], t[e[:, 1]])
        np.add.at(cacah, e[:, 0], 1)
        t = 0.5 * t + 0.5 * jum / np.maximum(cacah, 1)[:, None]
    return t


def uji_negatif(titik, muka, r):
    """Tiap KC wajib gagal pada mesh yang sengaja dirusak."""
    rusak = [
        ("tinggi x1,05", lambda t, m: (t * [1, 1, 1.05], m), ["KC-01"]),
        ("alas melebar 4%", lambda t, m: (t * [1.04, 1.04, 1], m), ["KC-02"]),
        ("satu muka dibuang", lambda t, m: (t, m[1:]), ["KC-03"]),
        ("geser Y 1 mm di atas z 30", lambda t, m: (t + np.where(t[:, 2:3] > 30, [0, 1.0, 0], 0), m), ["KC-04"]),
        ("kepala maju 25 mm", lambda t, m: (t + np.where(t[:, 2:3] > 13, [25.0, 0, 0], 0), m), ["KC-05"]),
        ("batas poligon 1000", lambda t, m: (t, m), ["KC-06"]),
    ] + ([("dihaluskan Laplacian 20x (fillet ~1,5 mm = semua empuk)", lambda t, m: (haluskan(t, m, 20), m), ["KC-07"])]
         if any(d["jenis"] == "pahat_bidang" and "min_luas_mm2" in d for d in r.get("detail", [])) else [])
    hasil = []
    for nama, f, wajib in rusak:
        t2, m2 = f(titik.copy(), muka.copy())
        r2 = dict(r, qc=dict(r["qc"], maks_poligon=1000)) if "poligon" in nama else r
        cek = qc_mesh(t2, m2, r2)
        ok, gagal = qc.tertangkap(cek, wajib)
        nilai = {c["id"]: c["nilai"] for c in cek if c["id"] in wajib}
        hasil.append(dict(nama=nama, wajib=wajib, gagal=gagal, tertangkap=ok, nilai_wajib=nilai))
        print(f"  negatif {'OK ' if ok else 'BOCOR'} {nama}: gagal {gagal}; nilai {nilai}")
    return hasil


def rakit(path_rancangan, out, render=True, sampel=32, mode="penuh", tonton=""):
    """Bangun model dari rancangan, QC + uji negatif, ekspor .blend/.glb + lembar kontak. Kode keluar 0 = lulus.
    mode "pratinjau": QC angka tetap, tanpa uji negatif, 1 render cepat (pratinjau.png) - untuk iterasi < 1 menit;
    "penuh" (serah/final): semua uji negatif + lembar kontak 6 tampak + banding.
    tonton = folder: tiap langkah ditulis untuk add-on mode tonton di Blender yang terbuka (tonton.py)."""
    t0 = time.time()
    waktu = {}
    r = muat_rancangan(path_rancangan)
    r["_mode"] = mode
    rekam = None
    if tonton:
        from .tonton import Perekam
        rekam = Perekam(tonton, r["objek"]["nama"])
    m, asal, vox = medan(r, rekam.langkah if rekam else None)
    waktu["medan"] = round(time.time() - t0, 1)
    log.info(f"medan {m.shape} vox {vox} mm ({waktu['medan']} s)")
    titik, quad = sdf.ke_mesh(m, asal, vox)
    del m
    log.info(f"mesh {len(titik)} titik, {len(quad)} quad ({time.time() - t0:.1f} s)")
    from . import adegan
    ob = adegan.objek_mesh(r["objek"]["nama"], titik, quad, r["objek"].get("target_segitiga"))
    titik, muka = adegan.data_mesh(ob)
    cek = qc_mesh(titik, muka, r)
    if r.get("_laporan_aset"):  # KA-08 ikut menentukan lulus: aset tanpa ciri wajib (mis. mata) = gagal
        from . import aset
        cek += aset.kelengkapan(r)
    for c in cek:
        print(f"  {c['id']} {'LULUS' if c['lulus'] else 'GAGAL'} {c['nama']}: {c['nilai']} ({c['ambang']})")
    waktu["mesh_qc"] = round(time.time() - t0, 1)
    neg = uji_negatif(titik, muka, r) if mode == "penuh" else []
    for la in r.get("_laporan_aset", []):  # uji negatif juri aset ikut dihitung (KA wajib tertangkap)
        neg += la.get("negatif", [])
    if mode == "penuh" and any(c["id"] == "KA-08" for c in cek):
        neg += aset.uji_negatif_kelengkapan(r)
    os.makedirs(out, exist_ok=True)
    adegan.ekspor(ob, out)
    if rekam:
        rekam.selesai(os.path.join(out, "model.glb"))
    if not render:
        lembar = None
    elif mode == "pratinjau":
        lembar = adegan.pratinjau(ob, out, tampak=r["objek"].get("pratinjau", ((35, 18),)), r=r)
    else:
        lembar = adegan.lembar_kontak(ob, r, cek, out, sampel)
    waktu["total"] = round(time.time() - t0, 1)
    laporan = dict(rancangan=os.path.relpath(path_rancangan, io.path_repo()), titik=len(titik),
                   segitiga=len(sdf.segitiga(muka)), detik=round(time.time() - t0, 1), mode=mode, waktu=waktu,
                   lembar=os.path.relpath(lembar, io.path_repo()) if lembar else None, cek=cek,
                   negatif=neg, aset=r.get("_laporan_aset"), **qc.ringkas(cek, neg))
    io.tulis_json(os.path.join(out, "laporan_qc.json"), laporan)
    log.info(f"selesai {laporan['detik']} s; lulus {laporan['lulus']}; negatif "
             f"{laporan['negatif_tertangkap']}/{laporan['negatif_jumlah']}")
    return 0 if laporan["lulus"] and laporan["negatif_tertangkap"] == laporan["negatif_jumlah"] else 1
