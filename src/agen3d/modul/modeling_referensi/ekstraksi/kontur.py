"""Ekstrak DATA referensi sepatu dari foto produk (foto tetap di klien/, tidak masuk repo).

Keluaran `referensi_am1.json` hanya berisi angka turunan (mm): profil siluet samping,
profil lebar tampak atas, garis panel dari segmentasi warna, dan kalibrasi skala.
Prinsip: Python menghitung, Claude memutuskan. Model 3D dibangun dari angka ini, lalu
dicek dengan QC IoU siluet per pandangan.

  blender -b --factory-startup -P blender_cli.py -- modeling_referensi ekstrak_kontur --ref <folder> [--proyek am1]
      [--out <json>]   (bawaan: proyek/<id>/<data.referensi>; pengaturan & ukuran lab: proyek.toml [ekstraksi])

Konvensi sumbu (sama dengan product_shot): X = panjang (0 = ujung toe, + ke tumit),
Y = lebar (+ = sisi yang terlihat di foto 'lateral'), Z = tinggi (0 = tanah).
"""
import json
import os

import numpy as np

from .foto import baca_foto


def ekstrak_kontur(REF, OUT, ek):
    """REF: folder foto (lateral/medial/atas/tumit/sol .png beralfa); OUT: JSON keluaran; ek: proyek.toml [ekstraksi]."""
    LANGKAH = 2  # 3144 px -> 1572 px

    # Ukuran lab independen dari proyek.toml [ekstraksi.lab] (AM1: RunRepeat US M 9)
    LAB = dict(ek["lab"])


    def baca(nama):
        return baca_foto(REF, nama, LANGKAH)  # baris 0 = atas gambar

    def kotak(m):
        ys, xs = np.nonzero(m)
        return xs.min(), xs.max(), ys.min(), ys.max()


    def pisah_pasangan(m):
        """Tampak atas/tumit berisi sepasang sepatu: potong di kolom kosong terpanjang di tengah."""
        kol = m.sum(0)
        x0, x1, _, _ = kotak(m)
        kosong = np.nonzero(kol[x0:x1] == 0)[0] + x0
        if not len(kosong):
            raise RuntimeError("pasangan tidak terpisah")
        tengah = int(np.median(kosong))
        kiri, kanan = m.copy(), m.copy()
        kiri[:, tengah:] = False
        kanan[:, :tengah] = False
        return kiri, kanan


    # ---------- 1. Kalibrasi skala dari foto SOL (bidang sol ~sejajar kamera, perspektif minimal) ----------
    # Foto tampak atas TIDAK dipakai untuk skala: kerah/tumit lebih dekat ke kamera sehingga membesar
    # (uji: lebar tumit 95,9 mm vs lab 81,8; panjang 313 mm vs perkiraan ~297).
    # Rasio tumit/forefoot siluet = 0,89 di sol DAN atas, lab 0,758 -> lebar tumit lab diukur di titik lain,
    # jadi hanya lebar forefoot (titik terlebar sepatu = midsole) yang dipakai. Status: [D] +-2%.
    sol = baca("sol")
    m_sol = sol[..., 3] > 0.99
    x0, x1, y0, y1 = kotak(m_sol)  # toe di kiri, tumit di kanan
    panjang_px = x1 - x0 + 1
    lebar_kol = np.array([m_sol[:, x].sum() for x in range(x0, x1 + 1)], np.float32)
    skala_sol = LAB["lebar_forefoot_mm"] / lebar_kol[: panjang_px // 2].max()
    panjang_mm = panjang_px * skala_sol
    lebar_tumit_mm = float(lebar_kol[panjang_px // 2:].max() * skala_sol)

    # profil tampak bawah (= garis luar plan): x dari toe (mm), y_min/y_max dari tepi atas gambar (mm)
    profil_atas = []
    for k in range(0, panjang_px, max(1, int(round(2.0 / skala_sol)))):
        ys = np.nonzero(m_sol[:, x0 + k])[0]
        if len(ys):
            profil_atas.append([round(k * skala_sol, 2), round((ys.min() - y0) * skala_sol, 2), round((ys.max() - y0) * skala_sol, 2)])

    # ---------- 2. Tampak samping: siluet atas/bawah per kolom ----------
    def profil_samping(nama, toe_kiri=True):
        p = baca(nama)
        m = p[..., 3] > 0.99
        x0, x1, y0, y1 = kotak(m)
        sk = panjang_mm / (x1 - x0 + 1)  # skala dari panjang tampak atas
        tanah = y1  # titik terendah siluet = tanah
        hasil = []
        for k in range(0, x1 - x0 + 1, max(1, int(round(2.0 / sk)))):
            x = x0 + k if toe_kiri else x1 - k
            ys = np.nonzero(m[:, x])[0]
            if not len(ys):
                continue
            hasil.append([round(k * sk, 2), round((tanah - ys.max()) * sk, 2), round((tanah - ys.min()) * sk, 2)])
        return p, m, (x0, x1, y0, y1), sk, hasil


    p_lat, m_lat, bb_lat, sk_lat, prof_lat = profil_samping("lateral", toe_kiri=True)
    p_med, m_med, bb_med, sk_med, prof_med = profil_samping("medial", toe_kiri=False)
    tinggi_tumit_mm = max(z for x, _, z in prof_lat if x > 0.7 * panjang_mm)

    # ---------- 3. Garis panel dari warna (colorway FD9082-107: hitam = mudguard/swoosh, putih = midsole) ----------
    def garis_panel(p, m, bb, sk, toe_kiri=True):
        """Pindai tiap kolom dari tanah ke atas: outsole -> midsole terang -> mudguard gelap.
        v1 (ambang luma < 0,08) hanya menangkap jahitan, bukan suede hitam -> v2 pakai urutan lapisan.
        Kembalikan batas atas/bawah mudguard dan bingkai jendela Air (piksel tak-terang di dalam midsole)."""
        x0, x1, y0, y1 = bb
        rgb, tanah = p[..., :3], y1
        luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        mm = lambda n: max(1, int(round(n / sk)))
        mud_atas, mud_bawah, jendela = [], [], []
        for k in range(0, x1 - x0 + 1, mm(2.0)):
            x = x0 + k if toe_kiri else x1 - k
            kol, msk = luma[:, x], m[:, x]
            dasar = np.nonzero(msk)[0]
            if not len(dasar):
                continue
            y = dasar.max() - mm(LAB["outsole_mm"])     # dasar per kolom (toe spring), lalu lewati outsole
            while y > y0 and msk[y] and kol[y] < 0.6:   # sisa outsole gelap
                y -= 1
            if not msk[y] or kol[y] < 0.6:
                continue
            mid_bawah = y
            while y > y0 and msk[y] and not (kol[y - mm(3.0):y + 1] < 0.35).all():  # midsole (boleh ada celah jendela)
                y -= 1
            mid_atas = y
            while y > y0 and msk[y] and kol[y] < 0.45:  # mudguard gelap
                y -= 1
            if mid_atas - y < mm(3.0):
                continue
            z = lambda yy: round((tanah - yy) * sk, 2)
            mud_bawah.append([round(k * sk, 2), z(mid_atas)])
            mud_atas.append([round(k * sk, 2), z(y)])
            celah = np.nonzero(kol[mid_atas + mm(2.0):mid_bawah - mm(2.0)] < 0.6)[0]
            if len(celah) >= mm(3.0):
                jendela.append([round(k * sk, 2), z(mid_atas + mm(2.0) + celah.max()), z(mid_atas + mm(2.0) + celah.min())])
        return mud_atas, mud_bawah, jendela


    if ek.get("garis_luma", True):  # AM1 (hitam/putih): garis dari ambang luma; colorway lain: ekstrak_kelas
        mud_atas_lat, mud_bawah_lat, jendela_lat = garis_panel(p_lat, m_lat, bb_lat, sk_lat, True)

    kal = dict(metode="[D] lebar forefoot siluet SOL = %s mm (lab midsole); +-2%%" % ("%g" % LAB["lebar_forefoot_mm"]).replace(".", ","),
               mm_per_px_sol=round(float(skala_sol), 4), panjang_luar_mm=round(float(panjang_mm), 1),
               lebar_tumit_siluet_mm=round(lebar_tumit_mm, 1))
    if "panjang_internal_mm" in LAB:  # AM1
        kal.update(catatan_lebar_tumit_lab="81,8 mm diukur di titik lain (rasio siluet 0,89 vs lab 0,758 di 2 foto)",
                   cek_panjang_luar_vs_internal_mm=round(float(panjang_mm - LAB["panjang_internal_mm"]), 1))
    else:  # cek silang skala: rasio lebar tumit/forefoot siluet sol vs lab (dua ukuran lab independen)
        r_sil = lebar_tumit_mm / LAB["lebar_forefoot_mm"]
        r_lab = LAB["lebar_tumit_mm"] / LAB["lebar_forefoot_mm"]
        kal.update(rasio_tumit_forefoot_siluet=round(float(r_sil), 4), rasio_tumit_forefoot_lab=round(float(r_lab), 4),
                   selisih_rasio_pct=round(float(100 * (r_sil / r_lab - 1)), 2))
    kal["tinggi_maks_tumit_mm"] = round(float(tinggi_tumit_mm), 1)
    data = dict(
        versi=ek["versi_kontur"], tanggal=ek["tanggal"],
        catatan=ek["catatan_kontur"],
        sumber_foto={k: ek["pola_sumber_foto"].format(v) for k, v in ek["sumber_foto"].items()},
        kalibrasi=kal,
        konvensi="x = mm dari ujung toe; z = mm dari tanah; profil_plan_sol: [x, y_min, y_max] mm (tampak bawah)",
        profil_samping_lateral=prof_lat,   # [x, z_bawah, z_atas]
        profil_samping_medial=prof_med,
        profil_plan_sol=profil_atas,       # [x, y_min, y_max] dari foto sol
    )
    # kunci lab: AM1 memakai nama lama (data.py membaca keduanya)
    data["lab_runrepeat_us9" if "panjang_internal_mm" in LAB else "lab"] = LAB
    if ek.get("garis_luma", True):
        data.update(garis_mudguard_atas_lateral=mud_atas_lat,    # [x, z] batas atas panel hitam bawah
                    garis_mudguard_bawah_lateral=mud_bawah_lat,  # [x, z] = atas midsole putih
                    jendela_air_lateral=jendela_lat)  # [x, z_bawah, z_atas] piksel tak-terang di dalam midsole
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1, default=float)
    print("KALIBRASI", json.dumps(data["kalibrasi"]))
    print("JUMLAH", len(prof_lat), len(prof_med), len(profil_atas))
