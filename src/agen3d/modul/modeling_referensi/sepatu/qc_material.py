"""QC resep sepatu M3 (material palet proyek): AM-15 warna per peran (render netral), AM-16 swoosh iridescent,
AM-17 kapsul translusen, AM-18 slot material non-default."""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from ....inti import warna
from ....inti.io import baca_png
from ....inti.kamera import hadap as hadap_ke, kamera, sinar
from ....inti.material import bsdf
from ....inti.qc import cek
from ....inti.render import render_gambar
from ....inti.scene import objek_produk
from ...product_shot.api import qc_kaca
from ..geometri import mesh_obj, mm
from ..qc_siluet import hue_rata
from . import data
from .ambang import AMBANG
from .bahan_p3 import P3
from .sol import MARGIN_KAPSUL
from .studio import pakai_studio


# ---------------- M3: material P3 (AM-15 .. AM-18) ----------------
# peran yang diharapkan untuk slot UTAMA (indeks 0) tiap objek, ditetapkan dari struktur M2 (bukan dari material yang
# terpasang): material yang tertukar antar objek tetap terdeteksi. Slot lain (mis. lining di muka potong) tidak disampel.
OBJEK_PERAN = {"upper": "lining", "panel_mesh": "upper_mesh", "lidah": "upper_mesh", "mudguard": "mudguard",
               "eyestay_lateral": "overlay_suede", "eyestay_medial": "overlay_suede", "overlay_tumit": "overlay_suede",
               "swoosh_lateral": "swoosh", "swoosh_medial": "swoosh", "eyelet": "aksen_chrome", "tali": "tali",
               "jahitan": "tali", "midsole": "midsole", "outsole": "outsole", "kapsul_air": "kapsul_air"}
LOGAM = ("aksen_chrome",)  # AM-15: warna logam = pantulan lingkungan; hanya nilai yang diuji
HADAP_MIN = 0.7      # AM-15: hanya piksel yang permukaannya hampir tegak lurus kamera (|n.v| >= 0,7; Fresnel/sheen/holo
                     # di sudut landai bukan warna bahan)


def peran_struktur(ob, slot):
    """Peran yang DIHARAPKAN untuk (objek, slot) dari struktur model, bukan dari material terpasang. AM1: slot utama
    objek di OBJEK_PERAN. Panel data (Tugas 11): slot 0 = ob['peran']; midsole/outsole slot >= 1 = panel alas objek itu
    (urutan [[model.panel]] alas = "midsole"/"outsole", digabung panel_data.bangun_panel_alas). Lainnya None (tidak disampel)."""
    if ob.get("panel"):
        return ob["peran"] if slot == 0 else None
    if slot == 0:
        return OBJEK_PERAN.get(ob.name)
    if ob.name in ("midsole", "outsole"):
        alas = [sp["peran"] for sp in data.KONFIG.get("model", {}).get("panel", []) if sp.get("alas") == ob.name]
        return alas[slot - 1] if slot - 1 < len(alas) else None
    return None


def piksel_peran(path, cam, langkah=2, hadap_min=HADAP_MIN, objek=None):
    """Warna render (ruang tampilan, PNG) per peran: piksel yang sinar kameranya pertama mengenai slot utama objek
    produk, bukan tepi siluet (4 tetangga = objek sama), dan |n.v| >= hadap_min. objek: batasi ke nama objek tertentu.
    Mengembalikan {peran: array (n, 3)}."""
    sc = bpy.context.scene
    rgb = baca_png(path)
    h, w = rgb.shape[:2]
    dg = bpy.context.evaluated_depsgraph_get()
    kena = {}
    for x, y, o, d in sinar(cam, w, h, langkah):
        ok, loc, nor, idx, ob, _ = sc.ray_cast(dg, o, d)
        if not ok or ob is None or (objek and ob.name not in objek):
            continue
        peran = peran_struktur(ob, ob.data.polygons[idx].material_index)
        if peran is None:
            continue
        kena[(x, y)] = ((ob.name, peran), abs(nor.dot(d)))
    hasil = {}
    for (x, y), (nama, hadap) in kena.items():
        tetangga = [kena.get((x + dx, y + dy), (None,))[0] for dx, dy in ((langkah, 0), (-langkah, 0), (0, langkah),
                                                                           (0, -langkah))]
        if hadap < hadap_min or any(t != nama for t in tetangga):
            continue
        hasil.setdefault(nama[1], []).append(rgb[y, x])
    return {k: np.array(v) for k, v in hasil.items()}


def render_netral(folder):
    """Render QC warna AM-15: cahaya review netral (lampu putih, dunia abu), eksposur 0, Khronos PBR Neutral
    (sama dengan QC-10 product-shot). Mengembalikan [(path, kamera)]."""
    sc = bpy.context.scene
    pakai_studio("review")
    sc.view_settings.view_transform, sc.view_settings.exposure = "Khronos PBR Neutral", 0.0
    den, sc.cycles.use_denoising = sc.cycles.use_denoising, True
    px = data.model("tampak", "pusat_x_mm", 147.0) / 1000  # relatif tengah sepatu (AM1 0,147 m: identik)
    pusat = Vector((px, 0.0, 0.06))
    cams = {"samping_lateral": (kamera("CAM_samping", (px, 0.6, 0.068), (math.pi / 2, 0, math.pi), 0.32), None),
            "samping_medial": (kamera("CAM_samping_m", (px, -0.6, 0.068), (math.pi / 2, 0, 0), 0.32), None),
            "tiga_perempat": (kamera("CAM_34", (px - 0.317, 0.33, 0.23), (0, 0, 0), lensa=50), pusat),
            "tiga_perempat_belakang": (kamera("CAM_34b", (px + 0.313, -0.26, 0.24), (0, 0, 0), lensa=50), pusat),
            "atas": (kamera("CAM_atas", (px, 0.0, 0.6), (0, 0, 0), 0.32), None),
            # eyelet chrome (torus r 0,45 mm) hanya terukur di makro
            "makro_tali": (kamera("CAM_m_tali", (0.10, 0.16, 0.22), (0, 0, 0), lensa=60), Vector((0.145, 0.0, 0.112)))}
    out = []
    for nama, (cam, t) in cams.items():
        if t is not None:
            hadap_ke(cam, t)
        w, h = (640, 300) if nama == "atas" else (640, 340) if nama.startswith("samping") else (640, 420)
        out.append((render_gambar(cam, os.path.join(folder, f"warna_{nama}.png"), w, h, 32, False), cam))
    sc.cycles.use_denoising = den
    return out


def qc_warna_peran(views):
    """AM-15: warna tiap peran di render netral vs hex P3. Median RGB piksel peran (semua view) -> HSV, aturan QC-10:
    saturasi target >= 0,2: rasio saturasi >= 0,60 dan selisih hue <= 20 deg; target netral/pastel (< 0,2):
    |selisih nilai| <= 0,35, saturasi piksel <= pastel_sat_maks, dan hue <= 20 deg bila saturasi piksel & target >= 0,05
    (pastel tertukar dengan pastel lain = beda hue); logam (LOGAM): hanya |selisih nilai| (warna = pantulan sekitar)."""
    kumpul = {}
    for path, cam in views:
        for k, v in piksel_peran(path, cam).items():
            kumpul.setdefault(k, []).append(v)
    hasil, swatch = [], {}
    A = AMBANG
    for peran in data.daftar_peran():
        hexa = P3()[peran][0]
        ht, st, vt = warna.hsv(warna.hex_rgb(hexa))
        if peran not in kumpul:
            hasil.append(cek("AM-15", f"warna_{peran}", "n/a", False, "piksel peran ada", "tidak terlihat di render netral"))
            continue
        px = np.vstack(kumpul[peran])
        med = np.median(px, 0)
        hp, sp, vp = warna.hsv(med)
        swatch[peran] = (hexa, med, len(px))
        if st >= 0.2:
            rasio, dh = sp / st, warna.dhue(hp, ht)
            ok = rasio >= A["saturasi_rasio_min"] and dh <= A["hue_selisih_maks"]
            hasil.append(cek("AM-15", f"warna_{peran}", float(rasio), ok,
                             f"rasio sat >= {A['saturasi_rasio_min']}, hue <= {A['hue_selisih_maks']} deg",
                             f"{hexa}: hue selisih {dh:.1f} deg, median {np.round(med, 3).tolist()}, {len(px)} px"))
        elif peran in LOGAM:
            dv = abs(vp - vt)
            ok = dv <= A["nilai_selisih_maks"]
            hasil.append(cek("AM-15", f"warna_{peran}", float(dv), ok, f"|dV| <= {A['nilai_selisih_maks']} (logam)",
                             f"{hexa}: logam = pantulan sekitar (sat {sp:.3f}, hue {hp * 360:.0f} bukan warna bahan), "
                             f"median {np.round(med, 3).tolist()}, {len(px)} px"))
        else:
            dv = abs(vp - vt)
            dh = warna.dhue(hp, ht) if sp >= A["pastel_hue_sat_min"] and st >= A["pastel_hue_sat_min"] else 0.0
            ok = dv <= A["nilai_selisih_maks"] and sp <= A["pastel_sat_maks"] and dh <= A["hue_selisih_maks"]
            hasil.append(cek("AM-15", f"warna_{peran}", float(dv), ok,
                             f"|dV| <= {A['nilai_selisih_maks']}, sat <= {A['pastel_sat_maks']}, hue <= "
                             f"{A['hue_selisih_maks']} deg jika sat >= {A['pastel_hue_sat_min']} (pastel/netral)",
                             f"{hexa}: sat piksel {sp:.3f} (target {st:.3f}), hue selisih {dh:.1f} deg "
                             f"({hp * 360:.0f} vs {ht * 360:.0f}), median {np.round(med, 3).tolist()}, {len(px)} px"))
    return hasil, swatch


SW_TARGET = Vector((0.205, 0.04, 0.078))  # pusat swoosh lateral (m)
SUDUT_HOLO = (0.0, 50.0)  # deg azimut dari normal swoosh (+Y) ke arah tumit; elevasi 10 deg


def render_holo(folder, prefix="holo"):
    """AM-16: makro swoosh lateral dari 2 sudut kamera, cahaya netral (eksposur 0)."""
    sc = bpy.context.scene
    pakai_studio("review")
    sc.view_settings.view_transform, sc.view_settings.exposure = "Khronos PBR Neutral", 0.0
    den, sc.cycles.use_denoising = sc.cycles.use_denoising, True
    out = []
    for az in SUDUT_HOLO:
        a, el = math.radians(az), math.radians(10.0)
        lok = SW_TARGET + Vector((math.sin(a) * math.cos(el), math.cos(a) * math.cos(el), math.sin(el))) * 0.24
        cam = kamera(f"CAM_holo_{int(az)}", tuple(lok), (0, 0, 0), lensa=60)
        hadap_ke(cam, SW_TARGET)
        out.append((render_gambar(cam, os.path.join(folder, f"{prefix}_{int(az)}.png"), 480, 320, 32, False), cam))
    sc.cycles.use_denoising = den
    return out


def qc_holo(views):
    """AM-16: swoosh iridescent = rata-rata hue piksel swoosh berubah antar sudut kamera. Piksel swoosh lateral
    (semua sudut |n.v|, bukan tepi), hue sirkular berbobot saturasi per sudut; nilai = selisih hue terbesar antar sudut."""
    hue, n = [], []
    for path, cam in views:
        px = piksel_peran(path, cam, 1, 0.0, {"swoosh_lateral"}).get("swoosh", np.zeros((0, 3)))
        hh, k = hue_rata(px) if len(px) else (float("nan"), 0)
        hue.append(hh)
        n.append(k)
    a = AMBANG["holo_hue_min"]
    if any(math.isnan(x) for x in hue):
        return cek("AM-16", "holo_selisih_hue_deg", 0.0, False, f">= {a} deg", f"piksel swoosh kurang: {n}"), hue
    d = max(warna.dhue(x, y) for i, x in enumerate(hue) for y in hue[i + 1:])
    return cek("AM-16", "holo_selisih_hue_deg", float(d), d >= a, f">= {a} deg",
               "hue " + " / ".join(f"az {s:.0f}: {x * 360:.0f} deg ({k} px)" for s, x, k in zip(SUDUT_HOLO, hue, n))), hue


def qc_kapsul_tembus(folder):
    """AM-17: kapsul pink translusen. Probe emisif kecil (kubus 3 mm) di rongga kapsul (di antara sekat), dirender
    makro jendela dua kali (probe tersembunyi / tampil, seed sama): kenaikan luma rata-rata piksel kapsul.
    Kapsul opak menutup probe sepenuhnya (selisih ~0). Ditambah: QC-11 berongga harus lulus."""
    sc = bpy.context.scene
    kap = bpy.data.objects.get("kapsul_air")
    a = AMBANG["kapsul_tembus_min"]
    if kap is None:
        return cek("AM-17", "kapsul_tembus_luma", 0.0, False, f">= {a}", "kapsul tidak ada"), None
    pakai_studio("review")
    sc.view_settings.view_transform, sc.view_settings.exposure = "Khronos PBR Neutral", 0.0
    jx0, jx1, jz0, jz1 = data.bbox_jendela_data()
    sekat = sorted(kap.get("sekat_x_mm", []))
    batas = [jx0 - MARGIN_KAPSUL[0]] + list(sekat) + [jx1 + MARGIN_KAPSUL[0]]
    i = int(np.argmax(np.diff(batas)))  # ruang terlebar antar sekat
    xc = (batas[i] + batas[i + 1]) / 2
    cy, _ = data.plan_y(xc)
    zc = (jz0 + jz1) / 2
    pr = mesh_obj("_probe", [(mm(xc + dx), mm(cy + dy), mm(zc + dz)) for dx in (-1.5, 1.5) for dy in (-1.5, 1.5)
                            for dz in (-1.5, 1.5)],
                 [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)], validasi=False)
    em = bpy.data.materials.new("_probe_emisi")
    b = bsdf(em)
    b.inputs["Emission Color"].default_value, b.inputs["Emission Strength"].default_value = (1, 1, 1, 1), 40.0
    pr.data.materials.append(em)
    jx, jz = (v / 1000 for v in data.model("tampak", "jendela_xz_mm", [216.3, 19.0]))
    cam = kamera("CAM_makro", (jx - 0.0113, 0.17, jz + 0.026), (0, 0, 0), lensa=60)
    hadap_ke(cam, Vector((jx, 0.045, jz)))
    den, sc.cycles.use_denoising = sc.cycles.use_denoising, False
    L = []
    for tampil in (False, True):
        pr.hide_render = not tampil
        p = render_gambar(cam, os.path.join(folder, f"kapsul_probe_{int(tampil)}.png"), 320, 210, 32, False)
        L.append(baca_png(p) @ np.array([0.2126, 0.7152, 0.0722], "f"))
    pr.hide_render = True
    sc.cycles.use_denoising = den
    # piksel kapsul: sinar pertama kena kapsul (probe disembunyikan dari ray_cast dengan menghapusnya dulu)
    bpy.data.objects.remove(pr)
    bpy.data.materials.remove(em)
    px = []
    dg = bpy.context.evaluated_depsgraph_get()
    for x, y, o, d in sinar(cam, 320, 210, 1):
        ok, _, _, _, ob, _ = sc.ray_cast(dg, o, d)
        if ok and ob is not None and ob.name == "kapsul_air":
            px.append((y, x))
    if len(px) < 30:
        return cek("AM-17", "kapsul_tembus_luma", 0.0, False, f">= {a}", f"piksel kapsul {len(px)}"), p
    ii, jj = np.array(px).T
    dL = float((L[1][ii, jj] - L[0][ii, jj]).mean())
    kaca = qc_kaca()
    rongga = bool(kaca) and all(c["lulus"] for c in kaca)
    return cek("AM-17", "kapsul_tembus_luma", dL, dL >= a and rongga, f">= {a} dan QC-11 berongga lulus",
               f"{len(px)} px kapsul, probe 3 mm di x {xc:.1f} mm; QC-11 " + ("lulus" if rongga else "GAGAL/tidak ada")), p


def qc_slot_material():
    """AM-18: tiap objek produk punya material peran non-default: tidak ada slot kosong, setiap material bernama
    peran, bertanda hex P3 peran itu (material_am1), dan bukan BSDF abu bawaan (Base Color 0,8 tanpa tautan)."""
    salah = []
    n = 0
    for ob in objek_produk():
        if not ob.data.materials:
            salah.append(f"{ob.name}: tanpa slot")
        for i, m in enumerate(ob.data.materials):
            n += 1
            if m is None:
                salah.append(f"{ob.name}[{i}]: slot kosong")
                continue
            if m.name not in P3() or m.get("hex_p3") != P3()[m.name][0]:
                salah.append(f"{ob.name}[{i}]: {m.name} tanpa hex P3")
                continue
            b = next((x for x in m.node_tree.nodes if x.type == "BSDF_PRINCIPLED"), None) if m.node_tree else None
            bc = b.inputs["Base Color"] if b else None
            if bc is None or (not bc.links and all(abs(c - 0.8) < 1e-3 for c in bc.default_value[:3])):
                salah.append(f"{ob.name}[{i}]: {m.name} abu default")
    return cek("AM-18", "slot_material_non_default", len(salah), not salah, "= 0 slot salah",
               f"{n} slot di {len(objek_produk())} objek; " + ("; ".join(salah[:5]) if salah else "semua material peran P3"))
