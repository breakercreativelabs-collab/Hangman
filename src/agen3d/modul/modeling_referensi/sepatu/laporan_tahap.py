"""QC bertingkat resep sepatu (Tugas 11 lewat proyek am90): tahap M1 (bawah) atau M2 (bawah + upper panel), material
netral, tanpa membangun tahap berikutnya.

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- modeling_referensi qc --proyek <id> --tahap m1|m2
      [--tanpa_negatif 1]   (QC cepat per job; uji negatif hanya saat kode QC berubah)
Keluaran: <out>/qc_<proyek>_<tahap>.json + contact_sheet_<tahap>.jpg; .blend + render di artefak.
M1: AM-01..08 + QC-11 (upper blok). M2: + AM-09 kehalusan, AM-10 IoU tiap panel data per sisi (qc_panel), AM-12 tali,
AM-13 lapisan (panel data), AM-14 peran. Proyek tanpa panel data (am1) memakai laporan penuh (`--tahap semua`).
"""
import os
import time

import bpy

from ....inti import io, lembar
from ....inti.qc import tertangkap
from ....inti.render import atur_render
from . import data
from .laporan import BANGUN_TAHAP, M1_ID, NEGATIF, jalankan_qc
from .panel_data import lapisan_data
from .qc_material import qc_kapsul_tembus, qc_slot_material, qc_warna_peran, render_netral
from .qc_panel import qc_panel_iou
from .qc_upper import qc_halus, qc_lapisan, qc_material, qc_tali
from .sol import bangun_sepatu
from .tampak import overlay_tumit, render_tampak, swatch_png
from ..qc_siluet import overlay_masker

TAMPAK = {"m1": ["samping_lateral", "samping_medial", "tiga_perempat", "tiga_perempat_belakang", "atas", "makro_jendela"],
          "m2": ["samping_lateral", "samping_medial", "tiga_perempat", "tiga_perempat_belakang", "atas", "makro_jendela",
                 "makro_tali"]}
TAMPAK["m3"] = TAMPAK["m2"]
KUNCI_M2_M3 = {"upper", "bahan_param", "tukar_peran", "slot_kosong", "bahan_default", "peran_hilang"}
NEGATIF_M2 = [  # generik panel data: nama, parameter bangun, QC yang WAJIB gagal
    ("upper blok M1 bergelombang (C-A3)", dict(upper="blok"), {"AM-09"}),
    ("upper M2 dari data mentah (C-A3)", dict(upper="m2_mentah"), {"AM-09"}),
    ("panel swoosh digeser 5 mm", dict(panel_param=dict(geser={"swoosh": (5.0, 0.0)})),
     {"AM-10:iou_swoosh_lateral", "AM-10:iou_swoosh_medial"}),
    ("panel medial dari data lateral", dict(panel_param=dict(medial_dari_lateral=True)), {"AM-10:iou_swoosh_medial"}),
    ("tali turun 3 mm", dict(tali_turun_mm=3.0), {"AM-12:tali_jarak_min_mm"}),
    ("4 pasang lubang", dict(n_pasang=4), {"AM-12:lubang_tali_wajar"}),
    ("lubang digeser 5 mm", dict(geser_lubang_mm=5.0), {"AM-12:lubang_tali_wajar"}),
    ("lapisan berimpit (tanpa offset)", dict(gap_lapis=False), {"AM-13"}),
    ("material tali tanpa nama peran", dict(peran_hilang="tali"), {"AM-14"}),
]
NEGATIF_M3 = [  # material colorway (generik): peran tertukar, warna salah, kapsul opak, slot kosong, abu default
    ("peran tertukar mudguard/overlay", dict(tukar_peran=("mudguard", "overlay")),
     {"AM-15:warna_mudguard", "AM-15:warna_overlay"}),
    ("warna swoosh salah (#D02F6B)", dict(bahan_param=dict(hex_salah={"swoosh": "#D02F6B"})), {"AM-15:warna_swoosh"}),
    ("kapsul opak", dict(bahan_param=dict(kapsul_mode="opak")), {"AM-17"}),
    ("slot swoosh kosong", dict(slot_kosong="swoosh"), {"AM-18"}),
    ("aksen abu default (nama peran benar)", dict(bahan_default="aksen"), {"AM-18"}),
]


def negatif_tahap(tahap):
    m1 = [n for n in NEGATIF if set(w.split(":")[0] for w in n[2]) <= M1_ID and not KUNCI_M2_M3 & set(n[1])]
    return m1 + (NEGATIF_M2 if tahap in ("m2", "m3") else []) + (NEGATIF_M3 if tahap == "m3" else [])


def qc_tahap(folder, tahap):
    hasil, art = jalankan_qc(folder, "m1")
    if tahap in ("m2", "m3"):
        c9, art["halus"] = qc_halus()
        hasil.append(c9)
        c10, art["panel"] = qc_panel_iou()
        hasil += c10
        hasil += qc_tali()
        hasil.append(qc_lapisan(lapisan_data()))
        hasil.append(qc_material())
    if tahap == "m3":
        art["netral"] = render_netral(folder)
        c15, art["swatch"] = qc_warna_peran(art["netral"])
        hasil += c15
        c17, art["kapsul_probe"] = qc_kapsul_tembus(folder)
        hasil.append(c17)
        hasil.append(qc_slot_material())
    return hasil, art


def main_tahap(opsi):
    proyek, tahap = opsi["proyek"], opsi["tahap"]
    data.muat_data(proyek)
    out = os.path.abspath(opsi["out"] or data.path_keluaran("hasil"))  # C-10
    folder_r = os.path.abspath(opsi["artefak"] or data.path_keluaran("render"))
    blend = os.path.join(os.path.dirname(data.path_keluaran("blend")) if not opsi["artefak"] else folder_r,
                         f"{proyek}_{tahap}.blend")
    os.makedirs(folder_r, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    dasar = BANGUN_TAHAP.get(tahap, dict(palet="netral") if tahap == "m2" else {})
    t0 = time.time()
    obs = bangun_sepatu(**dasar)
    # AM90-C15: ambil nilai dari objek SEKARANG; uji negatif membangun ulang scene sehingga objek lama terhapus
    info_model = dict(model=obs.get("info_upper", {}), kapsul_sekat_x_mm=list(obs["kapsul"].get("sekat_x_mm", [])))
    t_bangun = time.time() - t0
    perangkat = atur_render("uji")
    bpy.context.scene.cycles.use_denoising = False
    cek_utama, art = qc_tahap(folder_r, tahap)
    t_qc = time.time() - t0
    for c in cek_utama:
        print(("LULUS " if c["lulus"] else "GAGAL ") + f"{c['id']} {c['nama']} = {c['nilai']} ({c['ambang']}) {c['konteks']}")
    ovl = {k: overlay_masker(*art[k], os.path.join(folder_r, f"overlay_{k}.png")) for k in ("samping", "bawah", "medial")}
    ovl["tumit"] = overlay_tumit(art, os.path.join(folder_r, "overlay_tumit.png"))
    for k, (m, d) in art.get("panel", {}).items():
        ovl[k] = overlay_masker(m[::-1], d[::-1], os.path.join(folder_r, f"overlay_panel_{k}.png"))
    tampak = render_tampak(folder_r, set(TAMPAK[tahap]))
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)

    negatif = []
    pilih = [n for n in negatif_tahap(tahap)  # --negatif "a|b": hanya negatif yang namanya memuat salah satu teks
             if not opsi["negatif"] or any(t in n[0] for t in opsi["negatif"].split("|"))]
    if opsi["tanpa_negatif"] != "1":
        for nama, param, wajib in pilih:
            bangun_sepatu(**{**dasar, **param})
            atur_render("uji")
            bpy.context.scene.cycles.use_denoising = False
            slug = "".join(ch if ch.isalnum() else "_" for ch in nama)
            hasil, art_n = qc_tahap(os.path.join(folder_r, f"negatif_{tahap}", slug), tahap)
            ok, gagal = tertangkap(hasil, wajib)
            negatif.append(dict(nama=nama, parameter={k: str(v) for k, v in param.items()}, wajib_gagal=sorted(wajib),
                                gagal=gagal, tertangkap=ok, nilai={f"{c['id']} {c['nama']}": c["nilai"] for c in hasil},
                                _render=art_n["bawah_render"]))
            print(("TERTANGKAP " if ok else "LOLOS(!) ") + f"negatif '{nama}': gagal {gagal}")

    by = {c["id"]: c for c in cek_utama}
    nil = lambda nama: next((c["nilai"] for c in cek_utama if c["nama"] == nama), None)
    semua = lambda i: all(c["lulus"] for c in cek_utama if c["id"] == i)
    lab = lambda c: f"{c['id']} {c['nilai']}"
    upper_lbl = "UPPER = BLOK KASAR" if tahap == "m1" else "UPPER PANEL DATA, MATERIAL NETRAL"
    baris = [
        (f"TAMPAK {tahap.upper()} (CYCLES UJI, EKSPOSUR -1; {upper_lbl})", [
            (tampak["samping_lateral"], "samping lateral", True), (tampak["samping_medial"], "samping medial", True),
            (tampak["tiga_perempat"], "3/4 depan", True), (tampak["tiga_perempat_belakang"], "3/4 belakang", True)]),
        ("MAKRO + ATAS + BAWAH", [
            (tampak["makro_jendela"], f"makro jendela AM-08 takik {nil('takik_dinding_midsole_mm')} mm",
             semua("AM-04") and semua("AM-08")),
            (tampak["atas"], "atas" + (f" AM-12 tali {nil('tali_jarak_min_mm')} mm" if tahap == "m2" else ""),
             tahap == "m1" or semua("AM-12"))]
         + ([(tampak["makro_tali"], f"makro tali AM-13 lapis {nil('lapis_jarak_min_mm')} mm", semua("AM-13"))]
            if tahap == "m2" else [])
         + [(art["bawah_render"], f"bawah AM-07 banding {nil('banding_kolom_bawah')} tapak {nil('kontras_tapak_bawah')}",
             semua("AM-07"))]),
        ("OVERLAY M1: ABU = SAMA, BIRU = MODEL SAJA, MERAH = DATA SAJA / KONTUR DATA",
         [(ovl["samping"], "siluet samping " + lab(by["AM-01"]), semua("AM-01")),
          (ovl["medial"], "siluet MEDIAL " + lab(by["AM-06"]), semua("AM-06")),
          (ovl["bawah"], "plan bawah " + lab(by["AM-02"]), semua("AM-02")),
          (ovl["tumit"], "midsole merah " + lab(by["AM-03"]) + " jendela kuning", semua("AM-03") and semua("AM-04"))]),
    ]
    if tahap == "m3":
        c15 = {c["nama"][6:]: c for c in cek_utama if c["id"] == "AM-15"}
        sw = swatch_png(folder_r, art["swatch"])
        baris.insert(0, ("RENDER NETRAL M3 (QC WARNA AM-15, EKSPOSUR 0) + MAKRO KAPSUL AM-17", [
            (art["netral"][0][0], "netral lateral", semua("AM-15")), (art["netral"][2][0], "netral 3/4", semua("AM-15")),
            (art["netral"][3][0], "netral 3/4 belakang", semua("AM-15")),
            (art["kapsul_probe"], f"kapsul AM-17 tembus {nil('kapsul_tembus_luma')}", semua("AM-17"))]))
        per = list(sw)
        for i in range(0, len(per), 6):
            baris.insert(1 + i // 6, ("SWATCH PERAN: KIRI = HEX FOTO, KANAN = MEDIAN RENDER NETRAL (AM-15)" if i == 0 else "",
                                      [(sw[k], f"{k} {c15[k]['nilai']}", c15[k]["lulus"]) for k in per[i:i + 6] if k in c15]))
    if tahap in ("m2", "m3"):
        c10 = {c["nama"][4:]: c for c in cek_utama if c["id"] == "AM-10"}
        for sisi in ("lateral", "medial"):
            baris.append((f"OVERLAY PANEL {sisi.upper()} (AM-10, PROYEKSI Y; AM-09 RIAK {nil('riak_normal_upper_deg')} DEG)",
                          [(ovl[k], f"{k} {c10[k]['nilai']}", c10[k]["lulus"]) for k in c10 if k.endswith(sisi) and k in ovl]))
    neg_r = [(n["_render"], f"NEGATIF {n['nama']}: gagal " + " ".join(n["gagal"]), False) for n in negatif
             if n["nama"].startswith(("tapak gelombang", "dasar sol"))]
    if neg_r:
        baris.append(("UJI NEGATIF (HARUS MERAH)", neg_r))
    lulus = all(c["lulus"] for c in cek_utama)
    neg_ok = all(n["tertangkap"] for n in negatif)
    status = f"QC {tahap.upper()} {'LULUS' if lulus else 'GAGAL'} - NEGATIF {sum(n['tertangkap'] for n in negatif)}/{len(negatif)}"
    sheet, _ = lembar.buat(baris, os.path.join(out, f"contact_sheet_{tahap}.jpg"),
                           f"{data.KONFIG['proyek']['judul_lembar']} {tahap.upper()} - " + status)
    for n in negatif:
        n.pop("_render", None)
    laporan = dict(proyek=data.KONFIG["proyek"]["laporan"], tahap=tahap, data=data.sumber_data(),
                   blender=bpy.app.version_string, perangkat=perangkat, waktu_bangun_s=round(t_bangun, 1),
                   waktu_qc_s=round(t_qc, 1), waktu_total_s=round(time.time() - t0, 1), lulus=lulus,
                   gagal=[c["id"] + " " + c["nama"] for c in cek_utama if not c["lulus"]], cek=cek_utama,
                   uji_negatif=negatif, uji_negatif_semua_tertangkap=neg_ok, **info_model,
                   file=dict(contact_sheet=os.path.relpath(sheet, out), blend=os.path.relpath(blend, out)))
    io.tulis_json(os.path.join(out, f"qc_{proyek}_{tahap}.json"), laporan)
    print(f"QC {data.KONFIG['proyek']['judul_lembar']} {tahap.upper()}: {'LULUS' if lulus else 'GAGAL'}; negatif "
          f"{sum(n['tertangkap'] for n in negatif)}/{len(negatif)}; {laporan['waktu_total_s']} s ({perangkat})")
    return 0 if lulus and neg_ok else 1
