"""Resep sepatu dari DATA referensi, non-generatif: M1 bagian bawah + perakitan M2 (upper.py) + M3 (bahan_p3.py).

M1: outsole (karet 5,7 mm, tapak prosedural di material) · midsole (loft penampang per stasiun x) ·
jendela Air kedua sisi (boolean dari `jendela_air_lateral`) · kapsul Air bening berongga + sekat internal (QC-11).
M2 (upper.py, data panel): upper halus berlapis (badan/lining, panel mesh, mudguard, eyestay, overlay tumit, swoosh),
bukaan kerah, lidah, 7 pasang lubang + eyelet, tali, jahitan. upper="blok" = blok kasar M1.
Slot material = nama peran palet (PERAN). M3 (bahan_p3.py): material prosedural palet proyek per peran, tapak waffle;
palet="netral" = material netral M1/M2 (bahan_netral.py). Konvensi sumbu: data.py. Data & palet: proyek/<id>/.
"""
import math

import bmesh
import bpy
import numpy as np

from ....inti.scene import control, koleksi, objek_produk, root, siapkan_scene
from ..geometri import boolean, loft, mm, prisma_xz, rapikan_slot, terapkan
from ..penyaring import median5, selubung_bawah
from . import data
from .bahan_netral import bahan_netral
from .bahan_p3 import bahan_p3

# Parameter bentuk [D] (pilihan modeling, bukan data). Semua mm.
BENGKAK = 0.05          # sisi midsole menggembung: lebar di tepi atas/bawah = (1 - 0,05) x lebar maks (plan)
FILLET_MID = (0.3, 1.0)  # (bawah, atas) jari-jari tepi midsole
FILLET_OUT = (1.5, 0.2)  # (bawah, atas) tepi outsole
UPPER_MASUK = 1.5       # upper duduk 1,5 mm di dalam bibir atas midsole (kesan cupsole)
DINDING_MID = 2.0       # tebal dinding midsole di samping rongga kapsul
CELAH_KAPSUL = 0.4      # rongga = kapsul + 0,4 mm
KAPSUL_DINDING = 1.0    # film PU kapsul [D]
MARGIN_KAPSUL = (3.0, 2.5)  # kapsul melebihi bbox jendela (x, z)


# ---------------- geometri ----------------
def cincin_kotak(cy, a, zlo, zhi, r_bawah, r_atas, n_datar=6, n_fillet=5, n_sisi=12):
    """Penampang midsole/outsole di bidang YZ: sisi menggembung (lebar 2a di tengah tinggi, (1-BENGKAK)a di tepi),
    sudut bawah/atas difillet. Urutan titik tetap (jumlah sama untuk semua stasiun)."""
    h = zhi - zlo
    rb, ra = min(r_bawah, 0.45 * h), min(r_atas, 0.45 * h)
    zc, b = (zlo + zhi) / 2, h / 2
    sisi = lambda z: a * (1 - BENGKAK * ((z - zc) / b) ** 2)
    kanan = []
    yb = sisi(zlo + rb) - rb  # pusat fillet bawah
    for t in np.linspace(0, 1, n_datar, endpoint=False):
        kanan.append((t * yb, zlo))
    for f in np.linspace(-math.pi / 2, 0, n_fillet, endpoint=False):
        kanan.append((yb + rb * math.cos(f), zlo + rb + rb * math.sin(f)))
    for z in np.linspace(zlo + rb, zhi - ra, n_sisi, endpoint=False):
        kanan.append((sisi(z), z))
    ya = sisi(zhi - ra) - ra
    for f in np.linspace(0, math.pi / 2, n_fillet, endpoint=False):
        kanan.append((ya + ra * math.cos(f), zhi - ra + ra * math.sin(f)))
    for t in np.linspace(1, 0, n_datar):
        kanan.append((t * ya, zhi))
    kiri = [(-y, z) for y, z in kanan[-2:0:-1]]
    return [(cy + y, z) for y, z in kanan + kiri]


def cincin_kubah(cy, a, zlo, zw, zhi, n=48, e_bawah=4.0, e_atas=2.4):
    """Penampang blok upper: superelips, terlebar (2a) di zw, kubah ke zhi, dasar membulat ke zlo."""
    pts = []
    for t in np.linspace(-math.pi / 2, 3 * math.pi / 2, n, endpoint=False):
        c, s = math.cos(t), math.sin(t)
        e = e_atas if s > 0 else e_bawah
        y = a * math.copysign(abs(c) ** (2 / e), c)
        z = zw + (zhi - zw if s > 0 else zw - zlo) * math.copysign(abs(s) ** (2 / e), s)
        pts.append((cy + y, z))
    return pts


def cincin_super(cy, a, zc, b, n=40, e=6.0):
    pts = []
    for t in np.linspace(-math.pi / 2, 3 * math.pi / 2, n, endpoint=False):
        c, s = math.cos(t), math.sin(t)
        pts.append((cy + a * math.copysign(abs(c) ** (2 / e), c), zc + b * math.copysign(abs(s) ** (2 / e), s)))
    return pts


# ---------------- bangun ----------------
def bangun_sepatu(geser_jendela_mm=0.0, skala=1.0, midsole_tambah_mm=0.0, kapsul_pejal=False, tanpa_jendela=False,
           dasar="selubung", tapak=None, upper="m2", peran_hilang=None, palet="p3", bahan_param=None,
           tukar_peran=None, slot_kosong=None, bahan_default=None, **upper_param):
    """Bangun model di collection PRODUCT: bagian bawah M1 + upper M2 (upper.py) + material M3 (bahan_p3.py,
    palet P3; palet="netral" = material M2). upper="blok" = blok kasar M1 (uji negatif C-A3).
    Parameter selain default hanya untuk uji negatif QC: bahan_param (swoosh/kapsul_mode/hex_salah, bahan_p3),
    tukar_peran=(a, b) material dua peran tertukar di objeknya, slot_kosong=<objek> slot material dikosongkan,
    bahan_default=<peran> material peran itu diganti material baru default (abu) bernama sama."""
    siapkan_scene()
    c = control()
    c["produk"], c["proyek"] = data.KONFIG["proyek"]["produk"], data.KONFIG["proyek"]["label"]
    pk, r0 = koleksi("PRODUCT"), root()
    if palet == "p3":
        if any(len(v) > 2 for v in data.palet().values()):  # palet berjenis (colorway foto, Tugas 11)
            from .bahan_colorway import bahan_colorway
            bp = {k: v for k, v in (bahan_param or {}).items() if k != "swoosh"}
            mat = bahan_colorway(tapak=tapak or "waffle", **bp)
        else:
            mat = bahan_p3(tapak=tapak or "waffle", **(bahan_param or {}))
        c["palet"] = data.KONFIG["palet"]["nama"]
    else:
        mat = bahan_netral(tapak or "voronoi")
    if tukar_peran:
        a_, b_ = tukar_peran
        mat[a_], mat[b_] = mat[b_], mat[a_]

    xs_s, zb_raw, zt_raw = data.profil_samping("lateral")
    mid, _ = data.garis_midsole()
    # selubung hanya di rentang sol: sampel ujung tumit (z 46 di x 292,6) = counter tumit, bukan dasar sol
    n1 = int(np.nonzero(zb_raw < mid[-1, 1] - data.OUTSOLE)[0].max())
    zb_hal = zb_raw.copy()
    zb_hal[:n1 + 1] = selubung_bawah(xs_s[:n1 + 1], zb_raw[:n1 + 1])
    if dasar == "median5":  # v1 (uji negatif C-A2)
        zb_hal = median5(zb_raw)
    x_last = xs_s[-1]
    xs = np.unique(np.r_[np.arange(0.0, x_last, 1.0), x_last, np.linspace(x_last, data.PANJANG, 4)])

    def samping(x):
        zb, zt, zh = (np.interp(x, xs_s, v) for v in (zb_raw, zt_raw, zb_hal))
        if x > x_last:  # ekor 1 px terakhir (tepi piksel s.d. 293,7): menyempit ke tengah
            f = 1 - 0.9 * (x - x_last) / (data.PANJANG - x_last)
            m = (zb + zt) / 2
            zb, zt, zh = m - (m - zb) * f, m + (zt - m) * f, m - (m - zh) * f
        return zb, zt, zh

    def plan(x):
        cy, a = data.plan_y(x)
        if x > x_last:
            a *= 1 - 0.9 * (x - x_last) / (data.PANJANG - x_last)
        return cy, a

    # rentang sol: dari titik pertama garis midsole s.d. sampel siluet terakhir yang alasnya masih di bawah midsole
    xs0 = mid[0, 0]
    xs1 = max(x for x, zb in zip(xs_s, zb_raw) if zb < mid[-1, 1] - data.OUTSOLE)
    mt = lambda x: float(np.interp(x, mid[:, 0], mid[:, 1])) + midsole_tambah_mm
    st_sol = [x for x in xs if xs0 <= x <= xs1]
    st_sol = sorted(set(st_sol) | {xs0, xs1})

    c_out, c_mid = [], []
    for x in st_sol:
        _, _, zh = samping(x)
        cy, a = plan(x)
        c_out.append(cincin_kotak(cy, a * (1 - BENGKAK) - 0.2, zh, zh + data.OUTSOLE, *FILLET_OUT))
        c_mid.append(cincin_kotak(cy, a, zh + data.OUTSOLE, max(mt(x), zh + data.OUTSOLE + 0.4), *FILLET_MID))
    outsole = loft("outsole", st_sol, c_out, pk)
    midsole = loft("midsole", st_sol, c_mid, pk)

    if upper == "blok":  # M1: volume tertutup dari siluet atas + plan (bergelombang, C-A3)
        c_up = []
        for x in xs:
            zb, zt, _ = samping(x)
            cy, a = plan(x)
            di_sol = xs0 <= x <= xs1
            w = float(np.clip(min(x - xs0, xs1 - x) / 6.0, 0, 1)) if di_sol else 0.0
            if di_sol:
                m = mt(x)
                zlo_s, zw_s, a_s = max(m - 4.0, zb + 1.0), m + 1.5, a * (1 - BENGKAK) - UPPER_MASUK
            else:
                zlo_s, zw_s, a_s = zb, zb, a
            zlo = zb + w * (zlo_s - zb)
            zw = max(zb + 0.3 * (zt - zb) + w * (zw_s - (zb + 0.3 * (zt - zb))), zlo + 0.2)
            aa = a + w * (a_s - a)
            c_up.append(cincin_kubah(cy, aa, zlo, min(zw, zt - 0.5), zt))
        upper_obs = {"upper_blok": loft("upper_blok", list(xs), c_up, pk)}
        upper_obs["upper_blok"].data.materials.append(mat["upper"])
        info_upper = {}
    else:
        from .upper import bangun_upper
        ctx = dict(xs_s=xs_s, zb_raw=zb_raw, zt_raw=zt_raw, x_last=x_last, xs0=xs0, xs1=xs1, mid=mid,
                   midsole_tambah=midsole_tambah_mm,
                   panel=data.PANEL if data.PANEL is not None else data.lubang_kelas())
        upper_obs, B_up, info_upper = bangun_upper(ctx, mat, pk, halus=(upper == "m2"), **upper_param)

    # rongga + kapsul Air (tumit), dari bbox jendela data
    jx0, jx1, jz0, jz1 = data.bbox_jendela_data()
    jx0, jx1 = jx0 + geser_jendela_mm, jx1 + geser_jendela_mm
    kx0, kx1 = jx0 - MARGIN_KAPSUL[0], jx1 + MARGIN_KAPSUL[0]
    kz0, kz1 = jz0 - MARGIN_KAPSUL[1], jz1 + MARGIN_KAPSUL[1]
    kzc, kb = (kz0 + kz1) / 2, (kz1 - kz0) / 2
    kxc, kxa = (kx0 + kx1) / 2, (kx1 - kx0) / 2

    def kapsul_cincin(x, tambah=0.0, susut=0.0):
        cy, a = plan(x)
        _, _, zh = samping(x)
        zlo, zhi = zh + data.OUTSOLE, mt(x)
        zcm, bm = (zlo + zhi) / 2, (zhi - zlo) / 2
        u2 = max(((kz0 - zcm) / bm) ** 2, ((kz1 - zcm) / bm) ** 2)
        hw = a * (1 - BENGKAK * u2) - DINDING_MID - CELAH_KAPSUL  # muka kapsul 2,4 mm di dalam dinding midsole
        e = (1 - min(abs((x - kxc) / kxa), 1.0) ** 6) ** (1 / 6)  # ujung membulat
        return cincin_super(cy, hw * (0.6 + 0.4 * e) + tambah - susut, kzc, kb * e + tambah - susut)

    u = np.sin(np.linspace(-math.pi / 2, math.pi / 2, 41)) * 0.995
    xk = list(kxc + kxa * u)
    if not tanpa_jendela:
        xr = list(kxc + (kxa + CELAH_KAPSUL) * u)
        rongga = loft("_rongga", xr, [kapsul_cincin(x, CELAH_KAPSUL) for x in xr])
        boolean(midsole, rongga, hapus=True)
        boolean(midsole, prisma_xz("_jendela", data.poligon_jendela(geser_jendela_mm)), hapus=True)
    kapsul = loft("kapsul_air", xk, [kapsul_cincin(x) for x in xk], pk)
    if not kapsul_pejal:
        s = kapsul.modifiers.new("dinding", "SOLIDIFY")
        s.thickness, s.offset, s.use_even_offset = mm(KAPSUL_DINDING), -1.0, True
        terapkan(kapsul)
        # sekat internal [D]: di takik tepi atas data jendela (x 201,9 / 221,5 / 227,7 mm) = dinding sekat terlihat
        x, _, zt = data.jendela_data()
        lok = [x[i] for i in range(1, len(x) - 1) if zt[i] < zt[i - 1] and zt[i] <= zt[i + 1]]
        tambah_sekat(kapsul, [xi + geser_jendela_mm for xi in lok], kapsul_cincin, KAPSUL_DINDING + 0.1)

    for ob, k in ((outsole, "outsole"), (midsole, "midsole"), (kapsul, "kapsul_air")):
        ob.data.materials.append(mat[k])
    if upper != "blok" and data.KELAS is not None:  # wilayah cat midsole (kaset) dari data: setelah boolean midsole
        from .panel_data import bangun_panel_alas
        bangun_panel_alas(B_up, mat)
        for p in ob.data.polygons:
            p.use_smooth = True
    for ob in [outsole, midsole, kapsul] + list(upper_obs.values()):
        ob.parent = r0
    for ob in [outsole, midsole, kapsul] + list(upper_obs.values()):
        rapikan_slot(ob)
    if peran_hilang:  # uji negatif AM-14
        bpy.data.materials[peran_hilang].name = peran_hilang + "_tanpa_peran"
    if slot_kosong:  # uji negatif AM-18
        bpy.data.objects[slot_kosong].data.materials[0] = None
    if bahan_default:  # uji negatif AM-18: material baru tanpa isi (abu default) dengan nama peran yang benar
        lama = bpy.data.materials[bahan_default]
        lama.name = bahan_default + "_lama"
        baru = bpy.data.materials.new(bahan_default)
        for ob in objek_produk():
            for i, m_ in enumerate(ob.data.materials):
                if m_ == lama:
                    ob.data.materials[i] = baru
    r0.scale = (skala,) * 3
    r0["spec_panjang_mm"], r0["spec_lebar_forefoot_mm"] = data.PANJANG, data.LAB["lebar_forefoot_mm"]
    r0["sumber"] = data.sumber_data()
    bpy.context.view_layer.update()
    return dict(outsole=outsole, midsole=midsole, kapsul=kapsul, root=r0, info_upper=info_upper, **upper_obs)


def tambah_sekat(kapsul, xs, cincin_fn, susut, tebal=1.0):
    bm = bmesh.new()
    bm.from_mesh(kapsul.data)
    for xc in xs:
        st = [xc - tebal / 2, xc + tebal / 2]
        ob = loft("_sekat", st, [cincin_fn(x, susut=susut) for x in st])
        bm.from_mesh(ob.data)  # from_mesh menambahkan (tidak mengganti) geometri
        lama = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(lama)
    bm.to_mesh(kapsul.data)
    bm.free()
    kapsul["sekat_x_mm"] = [round(float(v), 2) for v in xs]
