"""Laporan QC resep sepatu: semua cek AM-01..18 + QC-11, uji negatif (25), contact sheet bentuk + material, qc_am1.json.

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- modeling_referensi qc [--proyek am1]
      [--out <folder>] [--artefak <folder>] [--tanpa_negatif 1] [--negatif <teks>] [--tahap m1|m2|m3|semua]
Keluaran: <out>/qc_am1.json + contact_sheet.jpg (bentuk M1+M2) + contact_sheet_m3.jpg (bawaan proyek/<id>/hasil);
.blend model (dipakai tvc) + render/ di artefak (bawaan dari proyek.toml [keluaran]).
--negatif <teks>: hanya uji negatif yang namanya memuat teks itu (pengembangan; laporan resmi = semua).
--tahap m1|m2: QC bertingkat (laporan_tahap.py): m1 bagian bawah (AM-01..08 + QC-11, upper blok), m2 + upper panel
data (AM-09/10/12/13/14), material netral; qc_<proyek>_<tahap>.json + contact_sheet_<tahap>.jpg. --tanpa_negatif 1 = QC cepat per job (negatif hanya saat kode QC berubah).
Kode keluar 1 jika ada QC gagal ATAU ada uji negatif yang tidak tertangkap.
"""
import os
import time

import bpy

from ....inti import io, lembar
from ....inti.qc import cek, iou, tertangkap
from ....inti.render import atur_render
from ...product_shot.api import qc_kaca
from . import data
from .ambang import AMBANG, PIX
from .qc_bawah import (masker, masker_data, peta_samping, qc_jendela, qc_midsole, qc_takik, qc_tapak,
                       qc_ukuran)
from .qc_material import qc_holo, qc_kapsul_tembus, qc_slot_material, qc_warna_peran, render_holo, render_netral
from .qc_upper import qc_halus, qc_lapisan, qc_material, qc_mudguard, qc_swoosh, qc_tali
from .sol import bangun_sepatu
from .studio import pakai_studio
from .tampak import overlay_mudguard, overlay_tumit, render_p3, render_tampak, swatch_png
from ..qc_siluet import overlay_masker


M1_ID = {"AM-01", "AM-02", "AM-03", "AM-04", "AM-05", "AM-06", "AM-07", "AM-08", "QC-11"}
BANGUN_TAHAP = {"m1": dict(upper="blok", palet="netral"), "semua": {}}


def jalankan_qc(folder, tahap="semua"):
    """Semua cek untuk scene saat ini (tahap m1: hanya bagian bawah). Mengembalikan (cek, artefak untuk overlay)."""
    os.makedirs(folder, exist_ok=True)
    hasil, art = [], {}
    for view, nama, id_ in (("samping", "iou_siluet_samping_lateral", "AM-01"), ("bawah", "iou_plan_bawah", "AM-02")):
        m, hs, vs = masker(view, folder)
        d = masker_data(view, hs, vs)
        nilai = iou(m, d)
        konteks = f"{m.sum()} px model, {d.sum()} px data, {PIX} mm/px"
        if view == "samping":
            konteks += " (data yang sama dipakai membangun: cek konsistensi build, bukan bukti independen)"
        hasil.append(cek(id_, nama, nilai, nilai >= AMBANG["iou_min"], f">= {AMBANG['iou_min']}", konteks))
        art[view] = (m, d)
        if view == "samping":
            dm = masker_data("samping_medial", hs, vs)
            nilai, lantai_data = iou(m, dm), iou(d, dm)
            a = AMBANG["iou_medial_min"]
            hasil.append(cek("AM-06", "iou_siluet_samping_medial", nilai, nilai >= a, f">= {a}",
                             f"data medial independen dari build; lantai derau data (IoU lateral vs medial) {lantai_data:.4f}"))
            art["medial"] = (m, dm)
    c3, art["midsole"] = qc_midsole()
    hasil.append(c3)
    peta, xs, zs = peta_samping(150.0, 296.0, 0.0, 60.0, 1)
    art["peta"] = (peta, xs, zs)
    hasil.append(qc_jendela(peta, xs, zs, "lateral"))
    pm, xm, zm = peta_samping(170.0, 265.0, 0.0, 40.0, -1)
    hasil.append(qc_jendela(pm, xm, zm, "medial"))
    art["peta_medial"] = (pm, xm, zm)
    hasil += qc_ukuran()
    hasil.append(qc_takik())
    lantai = pakai_studio("review")
    c7, art["bawah_render"] = qc_tapak(folder, art["bawah"][0], lantai)
    hasil += c7
    kaca = qc_kaca()  # QC-11 product-shot: kapsul bening harus berongga
    hasil += kaca or [cek("QC-11", "kaca_berongga_rasio_dinding", 1.0, False, "objek bening ada", "kapsul tidak ditemukan")]
    if tahap == "m1":
        return hasil, art
    # M2 upper
    c9, art["halus"] = qc_halus()
    hasil.append(c9)
    c10, art["swoosh"] = qc_swoosh()
    hasil += c10
    c11, art["mudguard"] = qc_mudguard()
    hasil.append(c11)
    hasil += qc_tali()
    hasil.append(qc_lapisan())
    hasil.append(qc_material())
    # M3 material P3
    views = render_netral(folder)
    c15, art["swatch"] = qc_warna_peran(views)
    hasil += c15
    art["netral"] = views
    art["holo"] = render_holo(folder)
    c16, art["holo_hue"] = qc_holo(art["holo"])
    hasil.append(c16)
    c17, art["kapsul_probe"] = qc_kapsul_tembus(folder)
    hasil.append(c17)
    hasil.append(qc_slot_material())
    return hasil, art


# ---------------- uji negatif ----------------
NEGATIF = [  # nama, parameter bangun, QC yang WAJIB gagal ("AM-xx" atau "AM-xx:nama_cek")
    ("jendela digeser 5 mm", dict(geser_jendela_mm=5.0), {"AM-04"}),
    ("skala +3%", dict(skala=1.03), {"AM-05", "AM-06"}),
    ("midsole 3 mm terlalu tebal", dict(midsole_tambah_mm=3.0), {"AM-03"}),
    ("tanpa jendela", dict(tanpa_jendela=True), {"AM-04"}),
    ("kapsul pejal", dict(kapsul_pejal=True), {"QC-11"}),
    ("dasar sol median-5 (v1, C-A2)", dict(dasar="median5"), {"AM-08"}),
    ("tapak gelombang (v1, C-A1)", dict(tapak="gelombang"), {"AM-07"}),
    ("tanpa tapak", dict(tapak="polos"), {"AM-07"}),
    ("upper blok M1 bergelombang (C-A3)", dict(upper="blok"), {"AM-09"}),
    ("upper M2 dari data mentah (C-A3)", dict(upper="m2_mentah"), {"AM-09"}),
    ("swoosh digeser 5 mm", dict(geser_swoosh_mm=5.0), {"AM-10:iou_swoosh_lateral", "AM-10:iou_swoosh_medial"}),
    ("swoosh medial dari data lateral", dict(swoosh_medial_dari_lateral=True), {"AM-10:iou_swoosh_medial"}),
    ("mudguard naik 4 mm", dict(geser_mudguard_mm=4.0), {"AM-11"}),
    ("tali turun 3 mm", dict(tali_turun_mm=3.0), {"AM-12:tali_jarak_min_mm"}),
    ("4 pasang lubang", dict(n_pasang=4), {"AM-12:lubang_tali_wajar"}),
    ("lubang digeser 5 mm", dict(geser_lubang_mm=5.0), {"AM-12:lubang_tali_wajar"}),
    ("lapisan berimpit (tanpa offset)", dict(gap_lapis=False), {"AM-13"}),
    ("material tali tanpa nama peran", dict(peran_hilang="tali"), {"AM-14"}),
    # M3 material P3
    ("peran tertukar mudguard/upper_mesh", dict(tukar_peran=("mudguard", "upper_mesh")),
     {"AM-15:warna_mudguard", "AM-15:warna_upper_mesh"}),
    ("peran tertukar lining/upper_mesh", dict(tukar_peran=("lining", "upper_mesh")),
     {"AM-15:warna_lining", "AM-15:warna_upper_mesh"}),
    ("warna swoosh salah (#D02F6B)", dict(bahan_param=dict(hex_salah={"swoosh": "#D02F6B"})), {"AM-15:warna_swoosh"}),
    ("swoosh diffuse polos", dict(bahan_param=dict(swoosh="polos")), {"AM-16"}),
    ("kapsul opak", dict(bahan_param=dict(kapsul_mode="opak")), {"AM-17"}),
    ("slot eyelet kosong", dict(slot_kosong="eyelet"), {"AM-18"}),
    ("aksen_chrome abu default (nama peran benar)", dict(bahan_default="aksen_chrome"), {"AM-18"}),
]
RENDER_NEGATIF = {"upper blok M1 bergelombang (C-A3)": "tiga_perempat", "upper M2 dari data mentah (C-A3)": "tiga_perempat",
                  "lapisan berimpit (tanpa offset)": "makro_swoosh"}
RENDER_NEGATIF_M3 = {  # negatif M3: render diambil dari artefak QC (tanpa render tambahan)
    "peran tertukar mudguard/upper_mesh": lambda a: a["netral"][2][0],
    "peran tertukar lining/upper_mesh": lambda a: a["netral"][3][0],
    "warna swoosh salah (#D02F6B)": lambda a: a["holo"][0][0],
    "swoosh diffuse polos": lambda a: a["holo"][1][0],
    "kapsul opak": lambda a: a["kapsul_probe"],
}


def main(argv):
    opsi = io.opsi(argv, dict(proyek="am1", out="", artefak="", tanpa_negatif="0", negatif="", tahap="semua"))
    tahap = opsi["tahap"]
    if tahap in ("m1", "m2", "m3"):
        from .laporan_tahap import main_tahap
        return main_tahap(opsi)
    data.muat_data(opsi["proyek"])
    out = os.path.abspath(opsi["out"] or data.path_keluaran("hasil"))  # C-10
    folder_r = os.path.abspath(opsi["artefak"] or data.path_keluaran("render"))
    blend = data.path_keluaran("blend") if not opsi["artefak"] else os.path.join(folder_r, os.path.basename(
        data.path_keluaran("blend")))
    os.makedirs(folder_r, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    t0 = time.time()

    obs = bangun_sepatu()
    t_bangun = time.time() - t0
    perangkat = atur_render("uji")
    sc = bpy.context.scene
    sc.cycles.use_denoising = False
    cek_utama, art = jalankan_qc(folder_r)
    t_qc = time.time() - t0
    for c in cek_utama:
        print(("LULUS " if c["lulus"] else "GAGAL ") + f"{c['id']} {c['nama']} = {c['nilai']} ({c['ambang']}) {c['konteks']}")
    ovl = {
        "samping": overlay_masker(*art["samping"], os.path.join(folder_r, "overlay_samping.png")),
        "bawah": overlay_masker(*art["bawah"], os.path.join(folder_r, "overlay_bawah.png")),
        "medial": overlay_masker(*art["medial"], os.path.join(folder_r, "overlay_medial.png")),
        "tumit": overlay_tumit(art, os.path.join(folder_r, "overlay_tumit.png")),
        "swoosh_lateral": overlay_masker(*art["swoosh"]["lateral"], os.path.join(folder_r, "overlay_swoosh_lateral.png")),
        "swoosh_medial": overlay_masker(*art["swoosh"]["medial"], os.path.join(folder_r, "overlay_swoosh_medial.png")),
        "mudguard": overlay_mudguard(art["mudguard"], os.path.join(folder_r, "overlay_mudguard.png")),
    }
    tampak = render_tampak(folder_r)
    p3 = render_p3(folder_r)
    swatch = swatch_png(folder_r, art["swatch"])
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)

    negatif = []
    pilih = [n for n in NEGATIF if not opsi["negatif"] or opsi["negatif"] in n[0]]
    if opsi["tanpa_negatif"] != "1":
        for nama, param, wajib in pilih:
            bangun_sepatu(**param)
            atur_render("uji")
            bpy.context.scene.cycles.use_denoising = False
            slug = "".join(ch if ch.isalnum() else "_" for ch in nama)
            folder_n = os.path.join(folder_r, "negatif", slug)
            hasil, art_n = jalankan_qc(folder_n)
            ok, gagal = tertangkap(hasil, wajib)
            negatif.append(dict(nama=nama, parameter=param, wajib_gagal=sorted(wajib), gagal=gagal, tertangkap=ok,
                                nilai={f"{c['id']} {c['nama']}": c["nilai"] for c in hasil}))
            negatif[-1]["_render"] = art_n["bawah_render"]
            if nama in RENDER_NEGATIF:
                negatif[-1]["_render"] = render_tampak(folder_n, {RENDER_NEGATIF[nama]})[RENDER_NEGATIF[nama]]
            if nama in RENDER_NEGATIF_M3:
                negatif[-1]["_render_m3"] = RENDER_NEGATIF_M3[nama](art_n)
            print(("TERTANGKAP " if ok else "LOLOS(!) ") + f"negatif '{nama}': gagal {gagal}")

    def lab(c):
        return f"{c['id']} {c['nilai']}"
    by = {c["id"]: c for c in cek_utama}
    nil = lambda nama: next(c["nilai"] for c in cek_utama if c["nama"] == nama)
    semua = lambda i: all(c["lulus"] for c in cek_utama if c["id"] == i)
    baris = [
        ("TAMPAK (CYCLES CPU UJI, EKSPOSUR -1)", [
            (tampak["samping_lateral"], "samping lateral (kanan)", True),
            (tampak["samping_medial"], "samping medial (kiri)", True),
            (tampak["tiga_perempat"], "3/4 depan", True),
            (tampak["tiga_perempat_belakang"], "3/4 belakang (kerah, lining)", True),
            (tampak["atas"], "atas (celah lidah, tali)", True)]),
        ("MAKRO + BAWAH", [
            (tampak["makro_swoosh"], f"makro swoosh + jahitan AM-13 lapis {nil('lapis_jarak_min_mm')} mm", semua("AM-13")),
            (tampak["makro_tali"], f"makro tali AM-12 jarak {nil('tali_jarak_min_mm')} mm", semua("AM-12")),
            (tampak["makro_jendela"], f"makro jendela AM-08 takik {nil('takik_dinding_midsole_mm')} mm", semua("AM-04") and semua("AM-08")),
            (art["bawah_render"], f"bawah AM-07 banding {nil('banding_kolom_bawah')} tapak {nil('kontras_tapak_bawah')}", semua("AM-07"))]),
        ("OVERLAY M1: ABU = SAMA, BIRU = MODEL SAJA, MERAH = DATA SAJA / KONTUR DATA",
         [(ovl["samping"], "siluet samping " + lab(by["AM-01"]), semua("AM-01")),
          (ovl["medial"], "siluet MEDIAL " + lab(by["AM-06"]), semua("AM-06")),
          (ovl["bawah"], "plan bawah " + lab(by["AM-02"]), semua("AM-02")),
          (ovl["tumit"], "midsole merah " + lab(by["AM-03"]) + " jendela kuning", semua("AM-03") and semua("AM-04"))]),
        ("OVERLAY M2: SWOOSH (WARNA SAMA) + MUDGUARD (MERAH = DATA, CYAN = MODEL)",
         [(ovl["swoosh_lateral"], f"swoosh lateral AM-10 {nil('iou_swoosh_lateral')}", nil("iou_swoosh_lateral") >= AMBANG["iou_swoosh_min"]),
          (ovl["swoosh_medial"], f"swoosh medial AM-10 {nil('iou_swoosh_medial')}", nil("iou_swoosh_medial") >= AMBANG["iou_swoosh_min"]),
          (ovl["mudguard"], "garis atas mudguard " + lab(by["AM-11"]) + f" mm; AM-09 riak {nil('riak_normal_upper_deg')} deg",
           semua("AM-11") and semua("AM-09"))]),
    ]
    neg_r = [(n["_render"], f"NEGATIF {n['nama']}: gagal " + " ".join(n["gagal"]), False) for n in negatif
             if n["nama"].startswith(("tapak gelombang", "dasar sol")) or n["nama"] in RENDER_NEGATIF]
    if neg_r:
        baris.append(("UJI NEGATIF (HARUS MERAH)", neg_r))
    lulus = all(c["lulus"] for c in cek_utama)
    neg_ok = all(n["tertangkap"] for n in negatif)
    status = f"QC {'LULUS' if lulus else 'GAGAL'} - NEGATIF {sum(n['tertangkap'] for n in negatif)}/{len(negatif)}"
    sheet, _ = lembar.buat(baris, os.path.join(out, "contact_sheet.jpg"),
                           f"{data.KONFIG['proyek']['judul_lembar']} M1+M2 BENTUK - " + status)

    # contact sheet M3 (material P3)
    c15 = {c["nama"][6:]: c for c in cek_utama if c["id"] == "AM-15"}
    hh = art["holo_hue"]
    palet = data.KONFIG["palet"]["nama"].upper()
    baris_m3 = [
        (f"STUDIO {palet} (CEK MATA, EKSPOSUR -0,5)", [
            (p3["p3_hero"], "hero 3/4", True),
            (p3["p3_lateral"], "samping lateral (kanan)", True),
            (p3["p3_medial"], "samping medial (kiri)", True)]),
        ("MAKRO (AM-16 SWOOSH 2 SUDUT, CAHAYA NETRAL) + KAPSUL + MESH/SUEDE", [
            (art["holo"][0][0], f"swoosh az 0: hue {hh[0] * 360:.0f} deg", semua("AM-16")),
            (art["holo"][1][0], f"swoosh az 50: hue {hh[1] * 360:.0f} deg; AM-16 {nil('holo_selisih_hue_deg')} deg",
             semua("AM-16")),
            (p3["p3_makro_kapsul"], f"kapsul AM-17 tembus {nil('kapsul_tembus_luma')}", semua("AM-17")),
            (p3["p3_makro_mesh"], "mesh lavender + suede butter + jahitan", True)]),
        ("SWATCH PERAN: KIRI = HEX P3, KANAN = MEDIAN RENDER NETRAL (AM-15)",
         [(swatch[k], f"{k} {c15[k]['nilai']}", c15[k]["lulus"]) for k in data.PERAN[:5] if k in swatch]),
        ("", [(swatch[k], f"{k} {c15[k]['nilai']}", c15[k]["lulus"]) for k in data.PERAN[5:] if k in swatch]),
        ("RENDER QC WARNA NETRAL (EKSPOSUR 0) + MAKRO EYELET", [
            (art["netral"][0][0], "netral lateral", semua("AM-15")),
            (art["netral"][2][0], "netral 3/4", semua("AM-15")),
            (art["netral"][5][0], f"eyelet chrome AM-18 slot salah {nil('slot_material_non_default')}", semua("AM-18"))]),
    ]
    neg_m3 = [(n["_render_m3"], f"NEGATIF {n['nama']}: gagal " + " ".join(n["gagal"]), False) for n in negatif
              if n.get("_render_m3")]
    if neg_m3:
        baris_m3.append(("UJI NEGATIF M3 (HARUS MERAH)", neg_m3))
    m3_ok = all(semua(i) for i in ("AM-15", "AM-16", "AM-17", "AM-18"))
    sheet_m3, _ = lembar.buat(baris_m3, os.path.join(out, "contact_sheet_m3.jpg"),
                              f"{data.KONFIG['proyek']['judul_lembar']} M3 MATERIAL {palet} - M3 {'LULUS' if m3_ok else 'GAGAL'} - " + status)
    for n in negatif:
        n.pop("_render", None)
        n.pop("_render_m3", None)

    laporan = dict(
        proyek=data.KONFIG["proyek"]["laporan"], data=data.sumber_data(),
        blender=bpy.app.version_string, perangkat=perangkat, waktu_bangun_s=round(t_bangun, 1),
        waktu_qc_s=round(t_qc, 1), waktu_total_s=round(time.time() - t0, 1),
        lulus=lulus, gagal=[c["id"] + " " + c["nama"] for c in cek_utama if not c["lulus"]],
        ambang=AMBANG, cek=cek_utama, uji_negatif=negatif, uji_negatif_semua_tertangkap=neg_ok,
        model=obs.get("info_upper", {}),
        swatch={k: dict(hex=v[0], median_render=[round(float(c), 3) for c in v[1]], piksel=v[2])
                for k, v in art["swatch"].items()},
        file=dict(contact_sheet=os.path.relpath(sheet, out), contact_sheet_m3=os.path.relpath(sheet_m3, out),
                  blend=os.path.relpath(blend, out)),
    )
    io.tulis_json(os.path.join(out, f"qc_{opsi['proyek']}.json"), laporan)
    print(f"QC {data.KONFIG['proyek']['judul_lembar']}: {'LULUS' if lulus else 'GAGAL'}; negatif {sum(n['tertangkap'] for n in negatif)}/{len(negatif)}; "
          f"{laporan['waktu_total_s']} s ({perangkat})")
    return 0 if lulus and neg_ok else 1
