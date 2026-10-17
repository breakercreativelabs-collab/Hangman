"""Produk uji prosedural: membangun objek (dengan material dari bahan.py) dari spesifikasi + profil.

Konvensi: origin di tengah dasar, sisi depan (logo label) menghadap -Y. Produk: spesifikasi.PRODUK.
"""
import math

import bpy
from mathutils import Matrix

from .profil import (cairan_dari, penampang_tube, profil_botol, profil_botol_dalam, profil_cairan, profil_flip_top,
                     profil_jar, profil_kaleng, profil_kotak, profil_pet, profil_tube, profil_tutup, profil_tutup_lug,
                     profil_tutup_pet, putar_profil, superelips, tab_kaleng)
from .spesifikasi import SPEC


def _objek(nama, me, koleksi):
    ob = bpy.data.objects.new(nama, me)
    koleksi.objects.link(ob)
    return ob


def _geser(me, dx, dy):
    me.transform(Matrix.Translation((dx / 1000, dy / 1000, 0)))
    return me


def _label_pita(nama, s, koleksi, bahan):
    z0, z1 = s["label_mm"]
    r = s["diameter_mm"] / 2 + 0.25
    ob = _objek(nama, putar_profil(nama, [(r, z0), (r, z1)]), koleksi)
    ob.data.materials.append(bahan["LABEL"])
    return ob


def bangun_baru(nama, koleksi, bahan):
    """Produk kurikulum Tugas 4. Mengembalikan daftar objek."""
    s = SPEC[nama]
    if nama == "kaleng_slim":
        return bangun_kaleng(nama, s, koleksi, bahan)
    if nama == "kotak_susu":
        a, b = s["lebar_mm"] / 2, s["tebal_mm"] / 2
        H, hs = s["tinggi_mm"], s["sirip_mm"]
        badan = _objek("kotak_badan", putar_profil("kotak_badan", profil_kotak(s), penampang=superelips(a, b)), koleksi)
        sirip = _objek("kotak_sirip", putar_profil("kotak_sirip", [(0, H - hs), (1, H - hs), (1, H), (0, H)],
                                                   penampang=superelips(a - 1.0, 3.5, 6)), koleksi)
        for ob in (badan, sirip):
            ob.data.materials.append(bahan["LABEL"])
        foil = _objek("kotak_foil", _geser(putar_profil("kotak_foil", [(0, H - hs), (3.5, H - hs), (3.5, H - hs + 0.15),
                                                                        (0, H - hs + 0.15)], seg=32), a / 2, b / 2 + 2.0),
                      koleksi)  # lubang sedotan (foil) [D]
        foil.data.materials.append(bahan["foil"])
        return [badan, sirip, foil]
    if nama == "tube":
        badan = _objek("tube_badan", putar_profil("tube_badan", profil_tube(s), penampang=penampang_tube(s)), koleksi)
        badan.data.materials.append(bahan["LABEL"])
        tutup = _objek("tube_tutup", putar_profil("tube_tutup", profil_flip_top(s)), koleksi)
        tutup.data.materials.append(bahan["tutup"])
        return [badan, tutup]
    if nama == "jar_selai":
        luar, dalam = profil_jar(s)
        kaca = _objek("jar_kaca", putar_profil("jar_kaca", luar + dalam), koleksi)
        kaca.data.materials.append(bahan["kaca"])
        isi = _objek("jar_isi", putar_profil("jar_isi", cairan_dari(dalam, s["isi_mm"], 0.15, 6.0)), koleksi)
        isi.data.materials.append(bahan["isi"])
        tutup = _objek("jar_tutup", putar_profil("jar_tutup", profil_tutup_lug(s)), koleksi)
        tutup.data.materials.append(bahan["tutup"])
        return [kaca, isi, _label_pita("jar_label", s, koleksi, bahan), tutup]
    if nama == "botol_pet":
        luar, dalam = profil_pet(s)
        pet = _objek("pet_badan", putar_profil("pet_badan", luar + dalam), koleksi)
        pet.data.materials.append(bahan["pet"])
        air = _objek("pet_air", putar_profil("pet_air", cairan_dari(dalam, s["isi_mm"], 0.1, 6.0)), koleksi)
        air.data.materials.append(bahan["air"])
        flute = lambda t, z: 1.0 + (0.02 * math.cos(60 * t) if z < s["tinggi_mm"] + s["tutup_naik_mm"] - 2.5 else 0.0)
        tutup = _objek("pet_tutup", putar_profil("pet_tutup", profil_tutup_pet(s), seg=120, modulasi=flute), koleksi)
        tutup.data.materials.append(bahan["tutup"])
        return [pet, air, _label_pita("pet_label", s, koleksi, bahan), tutup]
    raise KeyError(nama)


def bangun_kaleng(nama, s, koleksi, bahan):
    badan = _objek(f"{nama}_badan", putar_profil(f"{nama}_badan", profil_kaleng(s)), koleksi)
    badan.data.materials.append(bahan["LABEL"])   # indeks 0: cat + logo (badan)
    badan.data.materials.append(bahan["logam"])   # indeks 1: aluminium polos (leher, tutup, dasar)
    zb = (s["tinggi_mm"] - s["leher_mm"]) / 1000
    for p in badan.data.polygons:
        z = p.center.z
        p.material_index = 0 if 0.0105 < z < zb + 0.0005 else 1
    me_tab, me_rivet = tab_kaleng(s)
    tab, rivet = _objek(f"{nama}_tab", me_tab, koleksi), _objek(f"{nama}_rivet", me_rivet, koleksi)
    for ob in (tab, rivet):
        ob.data.materials.append(bahan["logam"])
    return [badan, tab, rivet]


def bangun_produk(nama, koleksi, bahan):
    """Bangun produk uji. `bahan` = dict nama->material (dibuat oleh verbs). Mengembalikan daftar objek."""
    s = SPEC[nama]
    if nama == "kaleng":
        return bangun_kaleng(nama, s, koleksi, bahan)
    if nama != "botol":
        return bangun_baru(nama, koleksi, bahan)
    # C-11: kaca berongga (dinding luar naik + dinding dalam turun) + cairan, bukan silinder kaca pejal
    kaca = _objek("botol_kaca", putar_profil("botol_kaca", profil_botol(s)[:-1] + profil_botol_dalam(s)), koleksi)
    kaca.data.materials.append(bahan["kaca"])
    cairan = _objek("botol_cairan", putar_profil("botol_cairan", profil_cairan(s)), koleksi)
    cairan.data.materials.append(bahan["cairan"])
    z0, z1 = s["label_mm"]
    r = s["diameter_mm"] / 2 + 0.25
    label = _objek("botol_label", putar_profil("botol_label", [(r, z0), (r, z1)]), koleksi)
    label.data.materials.append(bahan["LABEL"])
    flute = lambda t, z: 1.0 + (0.025 * math.cos(21 * t) if z < s["tinggi_mm"] - 0.5 else 0.0)  # 21 lekuk crown
    tutup = _objek("botol_tutup", putar_profil("botol_tutup", profil_tutup(s), modulasi=flute), koleksi)
    tutup.data.materials.append(bahan["tutup"])
    return [kaca, cairan, label, tutup]
