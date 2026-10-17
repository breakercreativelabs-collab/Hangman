"""Ekstrak DATA tapak (outsole) dari foto SOL beralfa: zona warna (poligon plan) + peta alur (bump), generik.

Zona: piksel sol diberi kelas oleh aturan warna proyek (`[[ekstraksi.kelas]]`), lalu kelas dipetakan ke peran zona
(`[ekstraksi.tapak] zona = {peran: [kelas, ...]}`), filter mayoritas, penutupan, poligon (mm, sistem profil_plan_sol:
x dari ujung toe, y dari tepi atas foto sol). Resep membangun zona sebagai prisma sepanjang Z yang memotong outsole
(panel `alas = "outsole"`). Peta alur: lembah L* lokal (rata-rata kotak 3 mm - L*, dinormalkan) di grid 0,5 mm = alur
gelap antar lug; disimpan PNG keabuan kecil (data turunan, bukan foto) untuk bump material tapak.

  blender -b --factory-startup -P blender_cli.py -- modeling_referensi ekstrak_tapak --ref <folder> [--proyek am90]
"""
import json
import os

import numpy as np

from .berkas import tulis_json_ringkas
from .foto import baca_foto
from .kelas import klasifikasi, komponen_label, mayoritas, srgb_lab
from .panel import rerata_kotak
from .poligon import poligon_mm

LANGKAH = 2  # sama dengan kontur (mm_per_px_sol dihitung pada langkah 2)


def ekstrak_tapak(REF, DATA_JSON, OUT_JSON, OUT_PNG, ek):
    import bpy
    DATA = json.load(open(DATA_JSON, encoding="utf-8"))
    sk = DATA["kalibrasi"]["mm_per_px_sol"]
    cfg = ek["tapak"]
    p = baca_foto(REF, "sol", LANGKAH)
    m = p[..., 3] > 0.99
    ys, xs = np.nonzero(m)
    x0, y0 = xs.min(), ys.min()
    to_x = lambda X: (X - x0) * sk
    to_y = lambda Y: (Y - y0) * sk
    px = lambda v: max(1, int(round(v / sk)))
    peta0, nama_k = klasifikasi(p[..., :3], m, ek["kelas"])
    peta = mayoritas(peta0, len(nama_k), px(cfg.get("mayoritas_mm", 1.0)))
    k_id = {n: i for i, n in enumerate(nama_k)}
    zona = {}
    for peran, kelas in cfg["zona"].items():
        mk = np.isin(peta, [k_id[k] for k in kelas if k in k_id]) & m
        r = px(cfg.get("tutup_mm", 1.0))
        mk = rerata_kotak((rerata_kotak(mk.astype(np.float32), r) > 0).astype(np.float32), r) > 0.999
        if cfg.get("luar_mm"):  # zona di tepi plan diperluas ke latar: prisma menutup dinding outsole melengkung
            mk |= (rerata_kotak(mk.astype(np.float32), px(cfg["luar_mm"])) > 0) & ~m
        lab, n = komponen_label(mk)
        pol = []
        for i in range(1, n + 1):
            mi = lab == i
            if mi.sum() * sk * sk >= cfg.get("luas_min_mm2", 30.0):
                # poligon_mm memetakan baris lewat to_z; di sini baris = y plan (bukan tinggi)
                pol.append(poligon_mm(mi, to_x, to_y, cfg.get("eps_mm", 0.15), sk, 9e9, cfg.get("chaikin", 2)))
        zona[peran] = dict(poligon=pol, luas_mm2=round(float(mk.sum() * sk * sk), 1))
    # peta alur di grid 0,5 mm (baris 0 = y plan 0 = tepi atas foto sol)
    L = srgb_lab(np.clip(p[..., :3], 0, 1))[..., 0]
    Lm = np.where(m, L, np.nan)
    rata = rerata_kotak(np.nan_to_num(Lm, nan=float(np.nanmean(Lm))), px(cfg.get("alur_jendela_mm", 3.0)))
    alur = np.clip((rata - L) / cfg.get("alur_skala_L", 8.0), 0.0, 1.0) * m
    for x0h, x1h, y0h, y1h in cfg.get("hapus", []):  # wilayah dihapus dari peta alur (mis. teks merek: model = cermin)
        Xh, Yh = to_x(np.arange(m.shape[1])), to_y(np.arange(m.shape[0]))
        alur[np.ix_((Yh >= y0h) & (Yh <= y1h), (Xh >= x0h) & (Xh <= x1h))] = 0.0
    g = cfg.get("grid_mm", 0.5)
    W = float(to_x(xs.max()) + sk)
    H = float(to_y(ys.max()) + sk)
    gx, gy = np.arange(0.0, W, g), np.arange(0.0, H, g)
    X = np.clip(np.round(x0 + gx / sk).astype(int), 0, m.shape[1] - 1)
    Y = np.clip(np.round(y0 + gy / sk).astype(int), 0, m.shape[0] - 1)
    a = alur[Y][:, X]
    img = bpy.data.images.new("_tapak_alur", len(gx), len(gy))
    rgba = np.ones((len(gy), len(gx), 4), np.float32)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = a
    img.pixels.foreach_set(rgba[::-1].ravel())  # Blender: baris 0 = bawah
    img.filepath_raw, img.file_format = OUT_PNG, "PNG"
    img.save()
    bpy.data.images.remove(img)
    out = dict(versi=1, tanggal=ek["tanggal"], catatan=cfg.get("catatan", ""), zona=zona,
               alur=dict(png=os.path.basename(OUT_PNG), grid_mm=g, lebar_mm=round(W, 2), tinggi_mm=round(H, 2),
                         konvensi="piksel (i, j) = (y plan = i*grid, x = j*grid); baris 0 PNG = y 0 (tepi atas foto sol)"))
    tulis_json_ringkas(OUT_JSON, out)
    print("TAPAK zona", {k: (v["luas_mm2"], len(v["poligon"])) for k, v in zona.items()},
          "| alur", a.shape, "rata", round(float(a.mean()), 3))
