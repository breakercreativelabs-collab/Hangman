"""Data proyek untuk resep sepatu: referensi JSON (mm) + proyek.toml (palet, label, keluaran).

Konvensi sumbu (sama dengan ekstraksi/kontur.py): meter di scene, X = panjang (0 = ujung toe, + ke tumit),
Y = lebar (+ = sisi lateral), Z = tinggi (0 = tanah). Lateral di +Y dengan toe di -X = sepatu KANAN.
Atribut modul (DATA, PANEL, KONFIG, LAB, PX, PANJANG, OUTSOLE) diisi oleh muat_data(); baca sebagai data.ATRIBUT.
"""
import json
import os
import tomllib

import numpy as np

from ....inti import io

# Slot material = nama peran palet (proyek.toml [palet.peran]; eksperimen/selera.md). Warna netral sampai M3.
PERAN = ("mudguard", "outsole", "upper_mesh", "swoosh", "midsole", "kapsul_air", "overlay_suede", "lining", "tali",
         "aksen_chrome")
PROYEK = None
DIR = None
KONFIG = DATA = PANEL = LAB = KELAS = TAPAK = None
PX = PANJANG = OUTSOLE = None


def muat_data(proyek="am1", tanpa_referensi=False):
    """Muat proyek/<proyek>/proyek.toml + data referensinya (sekali; panggil ulang untuk ganti proyek).
    tanpa_referensi=True: hanya proyek.toml (ekstraksi, sebelum data referensi ada)."""
    global PROYEK, DIR, KONFIG, DATA, PANEL, LAB, PX, PANJANG, OUTSOLE, KELAS, TAPAK
    if PROYEK == proyek and DATA is not None:
        return KONFIG
    DIR = io.proyek(proyek)
    with open(os.path.join(DIR, "proyek.toml"), "rb") as f:
        KONFIG = tomllib.load(f)
    if tanpa_referensi:
        return KONFIG
    with open(os.path.join(DIR, KONFIG["data"]["referensi"]), encoding="utf-8") as f:
        DATA = json.load(f)
    p_panel = os.path.join(DIR, KONFIG["data"].get("panel", ""))
    PANEL = json.load(open(p_panel, encoding="utf-8")) if os.path.isfile(p_panel) else None
    p_kelas = os.path.join(DIR, KONFIG["data"].get("kelas", ""))
    KELAS = json.load(open(p_kelas, encoding="utf-8")) if os.path.isfile(p_kelas) else None
    p_tapak = os.path.join(DIR, KONFIG["data"].get("tapak", ""))
    TAPAK = json.load(open(p_tapak, encoding="utf-8")) if os.path.isfile(p_tapak) else None
    LAB = DATA.get("lab") or DATA["lab_runrepeat_us9"]
    PX = DATA["kalibrasi"]["mm_per_px_sol"]          # 1 piksel foto sol (mm)
    PANJANG = DATA["kalibrasi"]["panjang_luar_mm"]   # 293,7 mm [D] +-2%
    OUTSOLE = LAB["outsole_mm"]                      # 5,7 mm [F] lab
    PROYEK = proyek
    return KONFIG


def model(bagian, kunci, bawaan):
    """Parameter resep per proyek dari proyek.toml [model.<bagian>] (Tugas 11: angka [D] yang dikalibrasi pada AM1
    pindah ke proyek bila sepatu lain butuh nilai berbeda). Tanpa entri = nilai AM1 (bawaan), sehingga AM1 identik."""
    return KONFIG.get("model", {}).get(bagian, {}).get(kunci, bawaan)


def peta_x(x):
    """Peta posisi x resep AM1 -> sepatu proyek lewat landmark [model.landmark] (am1 = [...], proyek = [...], mm,
    piecewise-linear; dari data siluet: ujung toe, lubang tali depan, puncak lidah, kerah terendah, puncak tumit,
    panjang). Tanpa landmark = identitas (AM1 identik). [D]: fitur desain dianggap berposisi relatif landmark."""
    lm = KONFIG.get("model", {}).get("landmark")
    if not lm:
        return x
    return float(np.interp(x, lm["am1"], lm["proyek"]))


def daftar_peran():
    """Peran (slot material) proyek: [model.umum] peran, bawaan PERAN AM1."""
    return tuple(model("umum", "peran", PERAN))


def panel_kelas(nama, sisi):
    """Poligon panel data kelas warna sisi itu: list {luar: [[x, z]], lubang: [[[x, z]]]} (mm)."""
    return KELAS[sisi]["panel"][nama]["poligon"] if KELAS and nama in KELAS[sisi]["panel"] else []


def _pusat_poligon(P):
    P = np.array(P, float)
    x, z = P[:, 0], P[:, 1]
    c = x * np.roll(z, -1) - np.roll(x, -1) * z
    A = 0.5 * c.sum()
    return float(((x + np.roll(x, -1)) * c).sum() / (6 * A)), float(((z + np.roll(z, -1)) * c).sum() / (6 * A)), abs(A)


def plan_xy(poli):
    """Poligon plan foto sol (x, y_foto mm; y dari tepi atas foto) -> (x, Y model mm), konvensi plan_y."""
    p = np.array(DATA["profil_plan_sol"], float)
    c = (p[:, 1].min() + p[:, 2].max() + PX) / 2
    return [(x, c - y) for x, y in poli]


def path_data(kunci):
    """Path file data proyek [data].<kunci> (mis. tapak_alur)."""
    return os.path.join(DIR, KONFIG["data"][kunci])


def lubang_kelas():
    """Lubang tali data dari lubang poligon panel [model.lubang] sumber (mis. eyestay): {sisi: {lubang_tali:
    [[x, z, luas]]}} (format panel AM1, dipakai Bentuk)."""
    out = {}
    for sisi in ("lateral", "medial"):
        lub = []
        for nama in model("lubang", "sumber", []):
            for pg in panel_kelas(nama, sisi):
                lub += [[round(v, 2) for v in _pusat_poligon(h)] for h in pg["lubang"]]
        out[sisi] = dict(lubang_tali=sorted(lub))
    return out


def path_keluaran(kunci):
    """Path keluaran dari [keluaran]: 'artefak/...' relatif akar repo, selain itu relatif folder proyek."""
    p = KONFIG["keluaran"][kunci]
    return io.path_repo(p) if p.startswith("artefak/") else os.path.join(DIR, p)


def palet():
    """{peran: (hex, sumber)} urut peran palet proyek."""
    return {k: tuple(v) for k, v in KONFIG["palet"]["peran"].items()}


def sumber_data():
    """Teks sumber data untuk PRODUCT_ROOT['sumber'] dan laporan QC."""
    d = KONFIG["data"]
    if PANEL is None:  # proyek kelas warna (am90): panel di JSON kelas
        return "%s v%d + %s" % (d["referensi"], DATA["versi"], d.get("kelas", "-"))
    return "%s v%d + %s v%d" % (d["referensi"], DATA["versi"], d["panel"], PANEL["versi"])


# ---------------- data turunan (dipakai bangun dan QC) ----------------
def profil_samping(sisi="lateral"):
    a = np.array(DATA[f"profil_samping_{sisi}"], float)
    return a[:, 0], a[:, 1], a[:, 2]


def garis_midsole():
    """`garis_mudguard_bawah_lateral` = garis atas midsole. Pencilan dibuang dengan aturan tetap:
    |z - median 6 tetangga| > 5 mm (titik terakhir x 292,6 z 71,2 = tepi counter tumit, bukan midsole)."""
    a = np.array(DATA["garis_mudguard_bawah_lateral"], float)
    z, ok = a[:, 1], np.ones(len(a), bool)
    for i in range(len(a)):
        tet = np.r_[z[max(0, i - 3):i], z[i + 1:i + 4]]
        ok[i] = abs(z[i] - np.median(tet)) <= 5.0
    return a[ok], a[~ok]


def plan_y(x):
    """Plan tampak bawah -> Y model (mm). Sisi y_min foto = LATERAL [D]: sisi y_max punya pinggang cekung
    10,5 mm (lengkung medial) dan titik terlebar lebih depan (bola jempol); sisi y_min hampir lurus.
    Konvensi tepi piksel: lebar = y_max - y_min + 1 px (lebar forefoot 107,9 = lab)."""
    p = np.array(DATA["profil_plan_sol"], float)
    c = (p[:, 1].min() + p[:, 2].max() + PX) / 2
    ymin, ymax = np.interp(x, p[:, 0], p[:, 1]), np.interp(x, p[:, 0], p[:, 2]) + PX
    return c - (ymin + ymax) / 2, (ymax - ymin) / 2  # pusat Y, setengah lebar


def plan_data_y():
    """Poligon plan mentah dalam Y model: (x, Y_bawah, Y_atas) untuk QC AM-02."""
    p = np.array(DATA["profil_plan_sol"], float)
    c = (p[:, 1].min() + p[:, 2].max() + PX) / 2
    return p[:, 0], c - p[:, 2], c - p[:, 1]


def jendela_data():
    a = np.array(DATA["jendela_air_lateral"], float)
    return a[:, 0], a[:, 1], a[:, 2]


def bbox_jendela_data():
    x, zb, zt = jendela_data()
    return float(x.min()), float(x.max()), float(zb.min()), float(zt.max())


def poligon_jendela(geser=0.0):
    """Garis luar jendela (x, z) dari data: tepi bawah mentah; tepi atas = maks dalam +-4 mm (takik 19,7-21,8 mm
    di x 200-204/220-229 adalah sekat kapsul yang terlihat, bukan tepi jendela); celah data x 206-216 diinterpolasi;
    ujung ditutup 1 mm di luar kolom data (kolom < 3 mm tidak terdeteksi oleh ekstraksi)."""
    x, zb, zt = jendela_data()
    atas = np.array([zt[np.abs(x - xi) <= 4.0].max() for xi in x])
    atas[0], atas[-1] = zt[0], zt[-1]  # kolom ujung = sudut membulat
    bawah = list(zip(x, zb))
    tutup = lambda i, d: (x[i] + d, (zb[i] + zt[i]) / 2)
    poli = [tutup(0, -1.0)] + bawah + [tutup(-1, 1.0)] + list(zip(x[::-1], atas[::-1]))
    return [(px + geser, pz) for px, pz in poli]


def poligon_swoosh(sisi):
    a = np.array(PANEL[sisi]["swoosh"], float)
    return a[:, 0], a[:, 1], a[:, 2]
