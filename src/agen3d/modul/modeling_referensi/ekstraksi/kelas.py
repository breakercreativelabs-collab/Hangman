"""Ekstrak DATA panel dari foto beralfa lewat KELAS WARNA (generik untuk colorway apa pun; foto tetap di klien/).

Ambang luma AM1 (gelap < 0,35 / mudguard < 0,45 / terang >= 0,6) hanya cocok untuk colorway hitam/putih: pada AM90
biru langit mudguard ber-luma 0,57 (tidak "gelap") dan pucat Hydrogen hampir sama terang dengan putih. Di sini tiap
piksel diberi kelas oleh ATURAN berurutan di proyek.toml `[[ekstraksi.kelas]]` (L*, C*, a*, b* CIELAB; aturan
pertama yang cocok menang). C* (kroma) dan b* hampir tidak berubah oleh bayangan, sehingga putih/pucat/jenuh terpisah;
L* hanya dipakai untuk memisah dua biru jenuh atau hitam.

  blender -b --factory-startup -P blender_cli.py -- modeling_referensi ekstrak_kelas --ref <folder> [--proyek am90]

Keluaran `proyek/<id>/<data.kelas>` (mm, sumbu sama dengan kontur: x dari ujung toe, z dari tanah):
- per sisi: `garis_atas_midsole` [x, z], `jendela` [x, z_bawah, z_atas] (rangkaian kontigu terpanjang), `komponen`
  {kelas: [{luas_mm2, bbox, pusat, poligon {luar, lubang}}]} (komponen dipisah erosi `pisah_mm`, poligon.py)
- garis midsole + jendela juga digabung ke JSON referensi kontur (kunci `garis_mudguard_bawah_<sisi>` = garis atas
  midsole dan `jendela_air_<sisi>`, nama kunci sama dengan AM1 agar resep sol dipakai apa adanya).
Overlay peta kelas + garis (cek mata sekali) disimpan di folder foto (klien/), bukan repo.
"""
import json
import os

import numpy as np

from .berkas import tulis_json_ringkas
from .foto import baca_foto
from .panel import rerata_kotak
from .poligon import poligon_mm

LANGKAH = 2  # 3144 px -> 1572 px (~0,19 mm/px)


# ---------------- warna ----------------
def srgb_lab(rgb):
    """sRGB 0..1 (nilai tampilan) -> CIELAB (D65)."""
    c = np.clip(rgb, 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def klasifikasi(rgb, m, aturan):
    """aturan: list dict {nama, L=[lo, hi], C=[..], a=[..], b=[..]} (batas opsional). Kembalikan peta indeks
    (-1 = latar, len(aturan) = 'lain') dan daftar nama."""
    lab = srgb_lab(rgb[m])
    fit = dict(L=lab[:, 0], a=lab[:, 1], b=lab[:, 2], C=np.hypot(lab[:, 1], lab[:, 2]))
    kls = np.full(len(lab), len(aturan), np.int32)
    bebas = np.ones(len(lab), bool)
    for i, a in enumerate(aturan):
        ok = bebas.copy()
        for k in ("L", "C", "a", "b"):
            if k in a:
                lo, hi = a[k]
                ok &= (fit[k] >= lo) & (fit[k] < hi)
        kls[ok] = i
        bebas &= ~ok
    peta = np.full(m.shape, -1, np.int32)
    peta[m] = kls
    return peta, [a["nama"] for a in aturan] + ["lain"]


def mayoritas(peta, n, r):
    """Filter mayoritas kotak (2r+1)^2: jahitan, kilap, dan tepi bayangan kecil ikut kelas sekitarnya."""
    skor = np.stack([rerata_kotak((peta == k).astype(np.float32), r) for k in range(n)])
    out = skor.argmax(0).astype(np.int32)
    out[peta < 0] = -1
    return out


# ---------------- komponen terhubung (numpy, tanpa scipy) ----------------
def komponen_label(m):
    """Label 4-tetangga lewat propagasi minimum + lompatan pointer. Kembalikan (label, n); 0 = latar."""
    h, w = m.shape
    idx = np.arange(h * w, dtype=np.int64).reshape(h, w)
    BES = h * w
    lab = np.where(m, idx, BES)
    while True:
        lama = lab
        t = lab.copy()
        for sl_a, sl_b in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                           ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                           ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                           ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
            t[sl_a] = np.minimum(t[sl_a], lab[sl_b])
        t = np.where(m, t, BES)
        flat = t.ravel()
        isi = flat < BES
        for _ in range(4):  # lompatan pointer: label = label dari label
            flat[isi] = flat[flat[isi]]
        lab = flat.reshape(h, w)
        if np.array_equal(lab, lama):
            break
    u, inv = np.unique(lab[m], return_inverse=True)
    out = np.zeros((h, w), np.int32)
    out[m] = inv + 1
    return out, len(u)


def pisah_komponen(mk, r):
    """Komponen setelah erosi kotak r px (memutus jembatan tipis < 2r, mis. swoosh yang menyentuh mudguard sewarna),
    lalu label ditumbuhkan kembali ke dalam masker asli (r + 1 langkah, 4-tetangga)."""
    er = rerata_kotak(mk.astype(np.float32), r) > 0.999 if r > 0 else mk
    lab, n = komponen_label(er)
    for _ in range(r + 2):
        t = lab.copy()
        for a, b in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                     ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                     ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                     ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
            t[a] = np.maximum(t[a], lab[b])
        lab = np.where(mk & (lab == 0), t, lab)
    return lab, n


def warna_terang(rgb, mk):
    """Warna dasar panel dari foto [F-foto]: median sRGB piksel yang L*-nya di persentil 50-90 panel itu (sisi terkena
    cahaya kunci, tanpa bayangan dalam dan kilap spekular). Hex tampilan, dibandingkan AM-15 di render netral."""
    if mk.sum() < 50:
        return None
    px = rgb[mk]
    L = srgb_lab(px)[:, 0]
    lo, hi = np.percentile(L, [50, 90])
    med = np.median(px[(L >= lo) & (L <= hi)], 0)
    return "#" + "".join("%02X" % int(round(float(np.clip(c, 0, 1)) * 255)) for c in med)


def run_terpanjang(baris, celah_mm):
    """Baris [x, ...] terurut x: ambil rangkaian kontigu terpanjang (jarak antar x <= celah_mm). Jendela palsu kecil
    (bayangan hangat di toe) dibuang."""
    if not baris:
        return baris
    runs, cur = [], [baris[0]]
    for r in baris[1:]:
        if r[0] - cur[-1][0] <= celah_mm:
            cur.append(r)
        else:
            runs.append(cur)
            cur = [r]
    runs.append(cur)
    return max(runs, key=lambda u: u[-1][0] - u[0][0])


# ---------------- ekstraksi per sisi ----------------
def proses_kelas(REF, PANJANG, nama, toe_kiri, ek):
    p = baca_foto(REF, nama, LANGKAH)  # baris 0 = atas
    m = p[..., 3] > 0.99
    ys, xs = np.nonzero(m)
    x0, x1, tanah = xs.min(), xs.max(), ys.max()
    sk = PANJANG / (x1 - x0 + 1)  # mm/px (sama dengan kontur.profil_samping)
    to_x = (lambda X: (X - x0) * sk) if toe_kiri else (lambda X: (x1 - X) * sk)
    to_z = lambda Y: (tanah - Y) * sk
    px = lambda mm_: max(1, int(round(mm_ / sk)))
    cfg = ek["kelas_cfg"]
    aturan = ek["kelas"]
    peta0, nama_k = klasifikasi(p[..., :3], m, aturan)
    peta = mayoritas(peta0, len(nama_k), px(cfg.get("mayoritas_mm", 0.6)))
    k_id = {n: i for i, n in enumerate(nama_k)}
    ids = lambda daftar: [k_id[n] for n in daftar if n in k_id]
    k_out, k_mid, k_jen = ids(cfg["outsole"]), ids(cfg["midsole"]), ids(cfg["jendela"])

    # garis atas midsole + jendela: pindai lapisan dari dasar per kolom (dasar per kolom = toe spring)
    garis, jendela, OUT = [], [], ek["lab"]["outsole_mm"]
    celah_maks = px(cfg.get("celah_mm", 1.5))
    for k in range(0, x1 - x0 + 1, px(1.0)):
        X = x0 + k if toe_kiri else x1 - k
        kol, msk = peta[:, X], m[:, X]
        dasar = np.nonzero(msk)[0]
        if not len(dasar):
            continue
        y = dasar.max() - px(OUT)  # lewati outsole (tebal lab), lalu sisa outsole berwarna outsole
        while y > 0 and msk[y] and kol[y] in k_out and kol[y] not in k_mid:
            y -= 1
        if not msk[y] or kol[y] not in k_mid + k_jen:
            continue
        mid_bawah, y_atas, celah = y, y, 0
        while y > 0 and msk[y]:
            if kol[y] in k_mid or kol[y] in k_jen:
                y_atas, celah = y, 0
            else:
                celah += 1
                if celah > celah_maks:
                    break
            y -= 1
        if (mid_bawah - y_atas) * sk < cfg.get("midsole_min_mm", 3.0):
            continue
        garis.append([round(to_x(X), 2), round(to_z(y_atas), 2)])
        pita = kol[y_atas:mid_bawah + 1]
        jj = np.nonzero(np.isin(pita, k_jen))[0]
        if len(jj) * sk >= cfg.get("jendela_kolom_mm", 3.0):
            jendela.append([round(to_x(X), 2), round(to_z(y_atas + jj.max()), 2), round(to_z(y_atas + jj.min()), 2)])

    if not toe_kiri:
        jendela.sort()
    jendela = run_terpanjang(jendela, cfg.get("jendela_celah_mm", 2.5))

    # komponen per kelas (dipisah erosi pisah_mm): ringkasan untuk memilih panel; luas >= luas_min_mm2
    xmm, zmm = to_x(np.arange(m.shape[1])), to_z(np.arange(m.shape[0]))
    komp, masker_k = {}, {}
    for nk in cfg.get("panel_kelas", []):
        if nk not in k_id:
            continue
        lab_k, n = pisah_komponen(peta == k_id[nk], int(round(cfg.get("pisah_mm", 0.0) / sk)))
        luas = np.bincount(lab_k.ravel(), minlength=n + 1)[1:] * sk * sk
        daftar = []
        for i in np.nonzero(luas >= cfg.get("luas_min_mm2", 20.0))[0]:
            Ys, Xs = np.nonzero(lab_k == i + 1)
            xa, za = to_x(Xs), to_z(Ys)
            daftar.append(dict(id=int(i + 1), luas_mm2=round(float(luas[i]), 1),
                               bbox=[round(float(xa.min()), 1), round(float(xa.max()), 1),
                                     round(float(za.min()), 1), round(float(za.max()), 1)],
                               pusat=[round(float(xa.mean()), 1), round(float(za.mean()), 1)]))
        komp[nk] = sorted(daftar, key=lambda d: -d["luas_mm2"])
        masker_k[nk] = lab_k

    # panel = gabungan komponen terpilih (proyek.toml [[ekstraksi.panel]]): kelas, zona pusat komponen, rentang luas,
    # potong kotak opsional, penutupan morfologis, isi lubang -> poligon per komponen hasil (mm)
    def kotak(b):
        return (((xmm >= b[0]) & (xmm <= b[1]))[None, :]) & (((zmm >= b[2]) & (zmm <= b[3]))[:, None])
    panel = {}
    sisi = "lateral" if toe_kiri else "medial"
    for sp in ek.get("panel", []):
        zona = sp.get(f"zona_{sisi}", sp["zona"])
        lo, hi = sp.get("luas", [0.0, 1e9])
        mk = np.zeros(m.shape, bool)
        for nk in sp["kelas"]:
            for c in komp.get(nk, []):
                if zona[0] <= c["pusat"][0] <= zona[1] and zona[2] <= c["pusat"][1] <= zona[3] and lo <= c["luas_mm2"] <= hi:
                    mk |= masker_k[nk] == c["id"]
        if "potong" in sp:
            mk &= kotak(sp.get(f"potong_{sisi}", sp["potong"]))
        r = px(sp["tutup_mm"]) if sp.get("tutup_mm") else 0
        if r:
            mk = rerata_kotak((rerata_kotak(mk.astype(np.float32), r) > 0).astype(np.float32), r) > 0.999
        rb = px(sp["buka_mm"]) if sp.get("buka_mm") else 0
        if rb:  # pembukaan: duri sempit (< 2 r) dibuang
            mk = rerata_kotak((rerata_kotak(mk.astype(np.float32), rb) > 0.999).astype(np.float32), rb) > 0
        luar = sp.get("luar_mm", cfg.get("luar_mm", 0.0))
        if luar:  # panel di tepi siluet diperluas ke latar: prisma menutup tepi melengkung (toe, tumit)
            r_l = px(luar)
            mk |= (rerata_kotak(mk.astype(np.float32), r_l) > 0) & ~m
        if sp.get("isi_lubang"):
            luar, _ = komponen_label(~mk)
            tepi = np.unique(np.r_[luar[0], luar[-1], luar[:, 0], luar[:, -1]])
            mk |= ~np.isin(luar, tepi[tepi > 0]) & (luar > 0)
        lab_p, n = komponen_label(mk)
        pol = []
        for i in range(1, n + 1):
            mi = lab_p == i
            if mi.sum() * sk * sk >= cfg.get("luas_min_mm2", 20.0):
                pol.append(poligon_mm(mi, to_x, to_z, cfg.get("eps_mm", 0.15), sk, sp.get("lubang_min_mm2", 4.0),
                                      cfg.get("chaikin", 0)))
        Ys, Xs = np.nonzero(mk)
        panel[sp["nama"]] = dict(peran=sp["peran"], luas_mm2=round(float(mk.sum() * sk * sk), 1), poligon=pol,
                                 warna=warna_terang(p[..., :3], mk & m),
                                 bbox=[round(float(to_x(Xs).min()), 1), round(float(to_x(Xs).max()), 1),
                                       round(float(to_z(Ys).min()), 1), round(float(to_z(Ys).max()), 1)] if len(Xs) else None)
    porsi = {n: round(float((peta == i).sum() / m.sum()), 4) for i, n in enumerate(nama_k)}
    zz = to_z(np.arange(m.shape[0]))[:, None] * np.ones((1, m.shape[1]))
    g = np.array(garis) if garis else np.zeros((0, 2))
    xx = to_x(np.arange(m.shape[1]))[None, :] * np.ones((m.shape[0], 1))
    z_mid = np.interp(xx, g[:, 0], g[:, 1]) if len(g) else np.zeros_like(xx)
    warna_kelas = {n: warna_terang(p[..., :3], peta == i) for i, n in enumerate(nama_k)}
    warna_kelas["putih_upper"] = warna_terang(p[..., :3], (peta == k_id.get("putih", -9)) & (zz > z_mid + 5.0))
    warna_kelas["putih_midsole"] = warna_terang(p[..., :3], (peta == k_id.get("putih", -9)) & (zz < z_mid - 2.0)
                                                & (zz > OUT + 1.0))
    vis = dict(p=p, m=m, peta=peta, to_x=to_x, to_z=to_z, sk=sk, x0=x0, x1=x1, tanah=tanah, toe_kiri=toe_kiri)
    return dict(skala_mm_per_px=round(float(sk), 4), porsi_kelas=porsi, warna_kelas=warna_kelas,
                garis_atas_midsole=garis, jendela=jendela, komponen=komp, panel=panel), vis


# ---------------- overlay cek mata ----------------
WARNA_PETA = np.array([[0.90, 0.10, 0.30], [0.24, 0.70, 0.30], [1.00, 0.88, 0.10], [0.00, 0.51, 0.78],
                       [0.96, 0.51, 0.19], [0.57, 0.12, 0.71], [0.27, 0.94, 0.94], [0.94, 0.20, 0.90],
                       [0.82, 0.96, 0.24], [0.98, 0.75, 0.83], [0.00, 0.50, 0.50], [0.67, 0.43, 0.16]])


def overlay(REF, nama, hasil, vis, n_kelas):
    """Atas: foto + garis midsole (merah) + jendela (kuning). Bawah: peta kelas. PNG ke folder foto (klien/)."""
    import bpy
    p, m, peta, sk = vis["p"], vis["m"], vis["peta"], vis["sk"]
    h, w = m.shape
    foto = np.where(m[..., None], p[..., :3], 0.12)
    pk = np.full((h, w, 3), 0.12)
    for i in range(n_kelas):
        pk[peta == i] = WARNA_PETA[i % len(WARNA_PETA)]

    def X_dari(x):
        return int(round(vis["x0"] + x / sk)) if vis["toe_kiri"] else int(round(vis["x1"] - x / sk))

    def Y_dari(z):
        return int(round(vis["tanah"] - z / sk))

    def titik(img, x, z, c, r=2):
        X, Y = X_dari(x), Y_dari(z)
        img[max(0, Y - r):Y + r + 1, max(0, X - r):X + r + 1] = c
    for x, z in hasil["garis_atas_midsole"]:
        titik(foto, x, z, (1, 0, 0))
        titik(pk, x, z, (1, 1, 1))
    for x, zb, zt in hasil["jendela"]:
        for z in (zb, zt):
            titik(foto, x, z, (1, 0.9, 0))
    for i, pn in enumerate(hasil["panel"].values()):  # kontur poligon panel di foto (warna per panel; lubang hitam)
        c = WARNA_PETA[(i + 6) % len(WARNA_PETA)]
        for pg in pn["poligon"]:
            for loop, warna in [(pg["luar"], c)] + [(L, (0, 0, 0)) for L in pg["lubang"]]:
                P = np.array(loop + loop[:1])
                for a, b in zip(P[:-1], P[1:]):
                    for t in np.linspace(0, 1, max(2, int(np.hypot(*(b - a)) / sk))):
                        titik(foto, *(a + (b - a) * t), warna, 1)
    gab = np.concatenate([foto, pk], 0)[::-1]  # Blender: baris 0 = bawah
    rgba = np.concatenate([gab, np.ones(gab.shape[:2] + (1,))], -1).astype(np.float32)
    im = bpy.data.images.new(f"_kelas_{nama}", w, 2 * h)
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw, im.file_format = os.path.join(REF, f"_overlay_kelas_{nama}.png"), "PNG"
    im.save()
    bpy.data.images.remove(im)


def ekstrak_kelas(REF, DATA_JSON, OUT, ek):
    """REF: folder foto; DATA_JSON: referensi kontur (panjang; digabungi garis midsole + jendela); OUT: JSON kelas."""
    DATA = json.load(open(DATA_JSON, encoding="utf-8"))
    PANJANG = DATA["kalibrasi"]["panjang_luar_mm"]
    out = dict(versi=ek["versi_kelas"], tanggal=ek["tanggal"], catatan=ek["catatan_kelas"], aturan=ek["kelas"],
               pengaturan=ek["kelas_cfg"])
    n_kelas = len(ek["kelas"]) + 1
    for nama, toe_kiri in (("lateral", True), ("medial", False)):
        hasil, vis = proses_kelas(REF, PANJANG, nama, toe_kiri, ek)
        out[nama] = hasil
        overlay(REF, nama, hasil, vis, n_kelas)
        DATA[f"garis_mudguard_bawah_{nama}"] = hasil["garis_atas_midsole"]  # = garis atas midsole (nama kunci AM1)
        DATA[f"jendela_air_{nama}"] = hasil["jendela"]
        print("KELAS", nama, "porsi", hasil["porsi_kelas"], "| garis midsole", len(hasil["garis_atas_midsole"]),
              "| jendela kolom", len(hasil["jendela"]),
              "| komponen", {k: len(v) for k, v in hasil["komponen"].items()},
              "| panel", {k: (v["luas_mm2"], len(v["poligon"])) for k, v in hasil["panel"].items()})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tulis_json_ringkas(OUT, out)
    tulis_json_ringkas(DATA_JSON, DATA)
