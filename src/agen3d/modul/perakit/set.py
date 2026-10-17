"""Set catur di papan: 6 jenis bidak (masing-masing dari rancangan perakit) disusun di posisi awal, QC SET (KS-01..06)
+ uji negatif, render beberapa tampak -> lembar_set.jpg. Konfigurasi: proyek/<id>/set.toml.

Model bidak diambil dari artefak/perakit/<proyek bidak>/model.glb; bila belum ada atau lebih tua dari rancangannya,
dibangun dulu (mode pratinjau, tanpa render). Bidak sejenis memakai mesh yang sama (instans), tidak disalin.
"""
import math
import os
import time
import tomllib

import numpy as np

from ...inti import io, log, qc

URUTAN = ("raja", "ratu", "gajah", "kuda", "benteng", "pion")  # urutan tinggi set Staunton (tinggi -> rendah)
JUMLAH = {"raja": 1, "ratu": 1, "gajah": 2, "kuda": 2, "benteng": 2, "pion": 8}  # per warna
BELAKANG = ("benteng", "kuda", "gajah", "ratu", "raja", "gajah", "kuda", "benteng")  # petak a..h baris 1 / 8


def muat_set(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def posisi_awal():
    """[(petak 'e1', warna, jenis)] 32 bidak posisi awal standar."""
    hasil = []
    for warna, baris_b, baris_p in (("putih", 1, 2), ("hitam", 8, 7)):
        for i, j in enumerate(BELAKANG):
            hasil.append((f"{'abcdefgh'[i]}{baris_b}", warna, j))
            hasil.append((f"{'abcdefgh'[i]}{baris_p}", warna, "pion"))
    return hasil


def model_bidak(rancangan):
    """(path glb, laporan QC) satu jenis bidak; bangun dulu (pratinjau, tanpa render) bila belum ada/kedaluwarsa."""
    rancangan = io.path_repo(rancangan)
    out = io.artefak("perakit", os.path.basename(os.path.dirname(rancangan)))
    glb, lap = os.path.join(out, "model.glb"), os.path.join(out, "laporan_qc.json")
    if not os.path.isfile(glb) or os.path.getmtime(glb) < os.path.getmtime(rancangan):
        from . import perakit
        log.info(f"set: membangun {os.path.relpath(rancangan, io.path_repo())} (belum ada / kedaluwarsa)")
        perakit.rakit(rancangan, out, render=False, mode="pratinjau")
    import json
    with open(lap, encoding="utf-8") as f:
        return glb, json.load(f)


def qc_set(kotak, ukuran, lulus_bidak, susunan):
    """QC SET (ATURAN_QC perakit, KS). ukuran = {jenis: (tinggi mm, diameter alas mm)}; lulus_bidak = {jenis: bool};
    susunan = [(petak, warna, jenis)]."""
    t = [ukuran[j][0] for j in URUTAN]
    urut = all(a > b for a, b in zip(t, t[1:]))
    rasio_raja = ukuran["raja"][1] / kotak
    rasio_maks = max(a for _, a in ukuran.values()) / kotak
    petak = [p for p, _, _ in susunan]
    hitung = {(w, j): sum(1 for _, ww, jj in susunan if (ww, jj) == (w, j)) for w in ("putih", "hitam") for j in URUTAN}
    raja_ratu = {(p, j) for p, _, j in susunan if j in ("raja", "ratu")} == {("e1", "raja"), ("d1", "ratu"),
                                                                          ("e8", "raja"), ("d8", "ratu")}
    sah = len(petak) == 32 and len(set(petak)) == 32 and all(hitung[(w, j)] == JUMLAH[j] for w, j in hitung) and raja_ratu
    gagal_bidak = [j for j in URUTAN if not lulus_bidak.get(j)]
    return [
        qc.cek("KS-01", "urutan tinggi raja > ratu > gajah > kuda > benteng > pion",
               dict(zip(URUTAN, [round(x, 1) for x in t])), urut, "turun tegas"),
        qc.cek("KS-02", "alas raja / sisi petak", rasio_raja, 0.68 <= rasio_raja <= 0.80,
               "0,68-0,80 (panduan 75-78%, rentang sumber 68-85%)"),
        qc.cek("KS-03", "sisi petak (mm)", kotak, 50.0 <= kotak <= 60.0, "50-60 mm (FIDE, turnamen)"),
        qc.cek("KS-04", "alas terbesar / sisi petak", rasio_maks, rasio_maks <= 0.80, "<= 0,80 (ada celah antar bidak)"),
        qc.cek("KS-05", "posisi awal sah", "sah" if sah else "tidak sah", sah,
               "32 bidak, petak unik, jumlah per jenis, raja e / ratu d"),
        qc.cek("KS-06", "semua bidak lulus QC sendiri (KC/KA)", gagal_bidak or "semua", not gagal_bidak,
               "laporan_qc tiap jenis lulus"),
    ]


def uji_negatif_set(kotak, ukuran, lulus_bidak, susunan):
    tukar = [(p, w, {"raja": "ratu", "ratu": "raja"}.get(j, j)) for p, w, j in susunan]
    rusak = [
        ("pion setinggi 2x", kotak, dict(ukuran, pion=(ukuran["pion"][0] * 2, ukuran["pion"][1])), lulus_bidak, susunan,
         ["KS-01"]),
        ("petak 40 mm", 40.0, ukuran, lulus_bidak, susunan, ["KS-02", "KS-03", "KS-04"]),
        ("petak 70 mm", 70.0, ukuran, lulus_bidak, susunan, ["KS-02", "KS-03"]),
        ("alas kuda 50 mm", kotak, dict(ukuran, kuda=(ukuran["kuda"][0], 50.0)), lulus_bidak, susunan, ["KS-04"]),
        ("raja-ratu tertukar", kotak, ukuran, lulus_bidak, tukar, ["KS-05"]),
        ("dua bidak satu petak", kotak, ukuran, lulus_bidak, susunan[:-1] + [("e1",) + susunan[-1][1:]], ["KS-05"]),
        ("kuda gagal QC sendiri", kotak, ukuran, dict(lulus_bidak, kuda=False), susunan, ["KS-06"]),
    ]
    hasil = []
    for nama, k, u, lb, s, wajib in rusak:
        ok, gagal = qc.tertangkap(qc_set(k, u, lb, s), wajib)
        hasil.append(dict(nama=nama, wajib=wajib, gagal=gagal, tertangkap=ok))
        print(f"  negatif set {'OK ' if ok else 'BOCOR'} {nama}: gagal {gagal}")
    return hasil


def _impor(glb):
    """Impor glb -> (mesh data, tinggi mm, diameter alas mm). Objek impor dibuang; mesh dipakai bersama."""
    import bpy
    sebelum = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    baru = [o for o in bpy.data.objects if o not in sebelum]
    ob = next(o for o in baru if o.type == "MESH")
    me = ob.data.copy()
    me.transform(ob.matrix_world)
    for o in baru:
        bpy.data.objects.remove(o)
    t = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", t)
    t = t.reshape(-1, 3) * 1000.0
    bawah = t[t[:, 2] < t[:, 2].min() + 1.0]
    return me, float(np.ptp(t[:, 2])), float(2 * np.hypot(bawah[:, 0], bawah[:, 1]).max())


def _papan(s, kotak):
    """Papan: 64 petak (kotak tipis, puncak z = 0) + badan papan berbingkai di bawahnya. Satuan meter."""
    import bpy
    from ...inti import material, warna
    mm = 0.001
    terang = material.bahan("petak_terang", warna.lin(s.get("petak_terang", "#B9A586")), kasar=0.5)
    gelap = material.bahan("petak_gelap", warna.lin(s.get("petak_gelap", "#4A3A2C")), kasar=0.5)
    sisi = 8 * kotak + 2 * s.get("bingkai_mm", 20.0)
    tebal = s.get("tebal_papan_mm", 14.0)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, -(tebal / 2 + 0.6) * mm))
    badan = bpy.context.active_object
    badan.scale = (sisi * mm, sisi * mm, tebal * mm)
    badan.data.materials.append(material.bahan("bingkai", warna.lin(s.get("bingkai", "#2E241C")), kasar=0.45))
    for f in range(8):
        for r in range(8):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=((f - 3.5) * kotak * mm, (r - 3.5) * kotak * mm,
                                                                -0.3 * mm))
            p = bpy.context.active_object
            p.scale = (kotak * mm * 0.999, kotak * mm * 0.999, 0.6 * mm)
            p.data.materials.append(gelap if (f + r) % 2 == 0 else terang)  # a1 gelap
    return sisi, tebal


def susun(path_set, out, render=True, sampel=24):
    """Bangun adegan set + QC KS + negatif + lembar_set.jpg. Kode keluar 0 = lulus + semua negatif tertangkap."""
    t0 = time.time()
    cfg = muat_set(path_set)
    s = cfg["set"]
    kotak = float(s["kotak_mm"])
    sumber = {}
    for j in URUTAN:  # bangun dulu (perakit mengosongkan scene)
        try:
            sumber[j] = model_bidak(cfg["bidak"][j])
        except FileNotFoundError as e:  # mis. aset berlisensi belum diunduh ke klien/ (paket publik)
            if j not in cfg.get("bidak_cadangan", {}):
                raise
            log.info(f"set: {j} memakai cadangan {cfg['bidak_cadangan'][j]} ({e})")
            cfg["bidak"][j] = cfg["bidak_cadangan"][j]
            sumber[j] = model_bidak(cfg["bidak"][j])
    import bpy
    from mathutils import Vector
    from ...inti import kamera, lembar, material, render, scene, warna
    from . import adegan
    scene.siapkan_scene()
    mesh, ukuran = {}, {}
    for j in URUTAN:
        mesh[j], tinggi, alas = _impor(sumber[j][0])
        ukuran[j] = (tinggi, alas)
        log.info(f"set: {j} tinggi {tinggi:.1f} mm, alas {alas:.1f} mm")
    lulus_bidak = {j: bool(sumber[j][1].get("lulus")) for j in URUTAN}
    susunan = posisi_awal()
    cek = qc_set(kotak, ukuran, lulus_bidak, susunan)
    for c in cek:
        print(f"  {c['id']} {'LULUS' if c['lulus'] else 'GAGAL'} {c['nama']}: {c['nilai']} ({c['ambang']})")
    neg = uji_negatif_set(kotak, ukuran, lulus_bidak, susunan)
    bahan = {w: material.bahan(f"bidak_{w}", warna.lin(s[w]), kasar=0.45 if w == "putih" else 0.3)
             for w in ("putih", "hitam")}
    salinan = {}
    for j in URUTAN:  # mesh per warna (bahan melekat di data mesh), dipakai bersama oleh bidak sejenis
        for w in ("putih", "hitam"):
            m = mesh[j].copy()
            m.materials.clear()
            m.materials.append(bahan[w])
            for p in m.polygons:
                p.use_smooth = True
            salinan[(j, w)] = m
    mm = 0.001
    for petak, w, j in susunan:
        ob = bpy.data.objects.new(f"{w}_{j}_{petak}", salinan[(j, w)])
        f, r = "abcdefgh".index(petak[0]), int(petak[1]) - 1
        ob.location = ((f - 3.5) * kotak * mm, (r - 3.5) * kotak * mm, 0.0)
        if j == "kuda":  # moncong model ke +X -> menghadap lawan
            ob.rotation_euler.z = math.radians(90 if w == "putih" else -90)
        scene.koleksi("PRODUCT").objects.link(ob)
    sisi, tebal = _papan(s, kotak)
    os.makedirs(out, exist_ok=True)
    gambar = []
    if render:
        render.atur_render("uji")
        adegan._studio(skala=sisi * mm / 0.12, lantai_z=-(tebal + 0.6) * mm)
        bpy.context.scene.view_settings.exposure = s.get("eksposur", -1.0)
        for i, (az, el, jarak, tz, tx, ty) in enumerate(s["tampak"]):
            tgt = Vector((tx * mm, ty * mm, tz * mm))
            cam = kamera.kamera(f"kam_set_{i}", tgt + kamera.arah(az, el) * jarak * mm, (0, 0, 0), lensa=50)
            kamera.hadap(cam, tgt)
            gambar.append((render.render_gambar(cam, os.path.join(out, f"set_{i}.png"), 720, 540, sampel, False),
                           f"az {az} el {el}", all(c["lulus"] for c in cek)))
        lembar.buat([("SET", gambar[:2]), ("DEKAT", gambar[2:])], os.path.join(out, "lembar_set.jpg"),
                    s.get("nama", "SET"), tinggi_sel=360)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "set.blend"))
    laporan = dict(set=os.path.relpath(path_set, io.path_repo()), kotak_mm=kotak,
                   ukuran={j: [round(a, 2), round(b, 2)] for j, (a, b) in ukuran.items()},
                   bidak={j: cfg["bidak"][j] for j in URUTAN}, cek=cek, negatif=neg,
                   detik=round(time.time() - t0, 1), **qc.ringkas(cek, neg))
    io.tulis_json(os.path.join(out, "laporan_set.json"), laporan)
    log.info(f"selesai {laporan['detik']} s; lulus {laporan['lulus']}; negatif "
             f"{laporan['negatif_tertangkap']}/{laporan['negatif_jumlah']}")
    return 0 if laporan["lulus"] and laporan["negatif_tertangkap"] == laporan["negatif_jumlah"] else 1
