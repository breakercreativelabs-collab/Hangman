"""Ekstrak DATA panel upper sepatu untuk modeling M2 (foto tetap di klien/, tidak masuk repo).

Keluaran `referensi_am1_panel.json` (mm, sistem sumbu sama dengan referensi_am1.json):
- `gelap_<sisi>`: per kolom x (1 mm) daftar rentang z yang gelap (mudguard, swoosh, kerah, lubang tali)
- `swoosh_<sisi>`: [x, z_bawah, z_atas] komponen gelap terbesar di atas garis mudguard dan di bawah kerah
- `garis_tepi_<sisi>`: titik [x, z] garis tepi/jahitan panel (lembah luma tipis di area terang)
- `lubang_tali_<sisi>`: pusat [x, z] gumpalan gelap kecil di pita atas (eyelet)
Pemisahan suede abu vs mesh putih TIDAK lewat warna (tumpang tindih karena bayangan), tetapi lewat garis tepi.

  blender -b --factory-startup -P blender_cli.py -- modeling_referensi ekstrak_panel --ref <folder> [--proyek am1]
      [--data <referensi.json>] [--out <json>]   (bawaan: file data proyek)
"""
import json

import numpy as np

from .foto import baca_foto


def rerata_kotak(img, r):
    """Rata-rata kotak (2r+1)^2 lewat integral image."""
    pad = np.pad(img, r + 1, mode="edge")
    ii = pad.cumsum(0).cumsum(1)
    k = 2 * r + 1
    s = ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]
    return s[: img.shape[0], : img.shape[1]] / (k * k)


def label(m):
    """Komponen terhubung 4-arah (BFS sederhana, cukup untuk masker ~1500 px)."""
    lab = np.zeros(m.shape, np.int32)
    n = 0
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        n += 1
        tumpuk = [(y0, x0)]
        lab[y0, x0] = n
        while tumpuk:
            y, x = tumpuk.pop()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < m.shape[0] and 0 <= xx < m.shape[1] and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    tumpuk.append((yy, xx))
    return lab, n


def proses(REF, PANJANG, nama, toe_kiri, garis_mud):
    p = baca_foto(REF, nama, 2)  # baris 0 = atas
    m = p[..., 3] > 0.99
    ys, xs = np.nonzero(m)
    x0, x1, tanah = xs.min(), xs.max(), ys.max()
    sk = PANJANG / (x1 - x0 + 1)  # mm/px
    luma = 0.2126 * p[..., 0] + 0.7152 * p[..., 1] + 0.0722 * p[..., 2]
    to_x = (lambda X: (X - x0) * sk) if toe_kiri else (lambda X: (x1 - X) * sk)
    to_z = lambda Y: (tanah - Y) * sk
    gelap = m & (luma < 0.35)
    terang = m & (luma >= 0.6)
    # garis tepi: lembah luma tipis (< rata-rata lokal 1,5 mm - 0,07) di dalam area terang
    lok = rerata_kotak(np.where(m, luma, 0.9), max(1, int(round(1.5 / sk))))
    tepi = terang & (luma < lok - 0.07)
    # rentang gelap per kolom 1 mm
    gelap_kol = []
    for xm in np.arange(0, PANJANG, 1.0):
        X = int(round(x0 + xm / sk)) if toe_kiri else int(round(x1 - xm / sk))
        if not (0 <= X < m.shape[1]):
            continue
        run, mulai = [], None
        kol = gelap[:, X]
        for Y in range(m.shape[0]):
            if kol[Y] and mulai is None:
                mulai = Y
            elif not kol[Y] and mulai is not None:
                if (Y - mulai) * sk >= 0.8:
                    run.append([round(to_z(Y - 1), 1), round(to_z(mulai), 1)])
                mulai = None
        gelap_kol.append([round(float(xm), 1), run])
    # swoosh: komponen gelap terbesar yang seluruhnya di atas garis mudguard (+3 mm) dan di bawah 85% tinggi tumit
    gm = np.array(garis_mud, float)
    z_mud = lambda xmm: np.interp(xmm, gm[:, 0], gm[:, 1])
    kand = gelap.copy()
    Ys, Xs = np.nonzero(kand)
    for Y, X in zip(Ys, Xs):
        xmm, zmm = to_x(X), to_z(Y)
        if zmm < z_mud(xmm) + 3.0 or zmm > 95.0:
            kand[Y, X] = False
    lab, n = label(kand)
    swoosh = []
    if n:
        ukuran = np.bincount(lab.ravel())[1:]
        sw = lab == (int(np.argmax(ukuran)) + 1)
        for X in np.unique(np.nonzero(sw)[1])[:: max(1, int(round(1.0 / sk)))]:
            zs = np.nonzero(sw[:, X])[0]
            swoosh.append([round(to_x(X), 1), round(to_z(zs.max()), 1), round(to_z(zs.min()), 1)])
        swoosh.sort()
    # lubang tali: gumpalan gelap kecil (2-40 mm^2) di pita atas (z > 70 mm)
    kecil = gelap.copy()
    Ys, Xs = np.nonzero(kecil)
    for Y, X in zip(Ys, Xs):
        if to_z(Y) < 70.0:
            kecil[Y, X] = False
    lab2, n2 = label(kecil)
    lubang = []
    for i in range(1, n2 + 1):
        Yi, Xi = np.nonzero(lab2 == i)
        luas = len(Yi) * sk * sk
        if 2.0 <= luas <= 40.0:
            lubang.append([round(to_x(Xi.mean()), 1), round(to_z(Yi.mean()), 1), round(luas, 1)])
    lubang.sort()
    Yt, Xt = np.nonzero(tepi)
    sel = np.unique(np.c_[np.round(to_x(Xt)), np.round(to_z(Yt))], axis=0)  # dedup grid 1 mm
    return dict(gelap=gelap_kol, swoosh=swoosh, garis_tepi=sel.astype(float).tolist(), lubang_tali=lubang,
                skala_mm_per_px=round(float(sk), 4))


def ekstrak_panel(REF, DATA_JSON, OUT, ek):
    """REF: folder foto; DATA_JSON: referensi kontur (garis mudguard, panjang); OUT: JSON panel; ek: [ekstraksi]."""
    DATA = json.load(open(DATA_JSON, encoding="utf-8"))
    PANJANG = DATA["kalibrasi"]["panjang_luar_mm"]
    lat = proses(REF, PANJANG, "lateral", True, DATA["garis_mudguard_atas_lateral"])
    med = proses(REF, PANJANG, "medial", False, DATA["garis_mudguard_atas_lateral"])  # garis mudguard medial ~ lateral [D]
    out = dict(versi=ek["versi_panel"], tanggal=ek["tanggal"], catatan=ek["catatan_panel"], lateral=lat, medial=med)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, default=float)
    for k, v in (("lateral", lat), ("medial", med)):
        print("PANEL", k, "swoosh kolom", len(v["swoosh"]), "x", v["swoosh"][0][0] if v["swoosh"] else None, "-",
              v["swoosh"][-1][0] if v["swoosh"] else None, "| tepi titik", len(v["garis_tepi"]), "| lubang", len(v["lubang_tali"]))
