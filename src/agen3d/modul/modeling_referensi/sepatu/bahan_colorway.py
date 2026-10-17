"""Resep sepatu M3 GENERIK: material colorway dari palet proyek [palet.peran] = [hex, sumber, jenis] (Tugas 11).

Jenis bahan (satu fungsi per jenis, bukan per sepatu): kulit, kulit_bergaris (rib horizontal, mis. eyestay AM90),
tpu (plakat/tab, mengilap), busa, busa_bergaris (kaset bercat bergaris), mesh, karet, kapsul, tali, lembut, suede.
Hex [F-foto] = median piksel terang panel di foto (ekstraksi/kelas.py warna_terang). Material menyimpan `peran` +
`hex_p3` seperti bahan_p3 (dibaca AM-15/AM-18). Proyek tanpa `jenis` (AM1) tetap memakai bahan_p3 (data.palet_berjenis).
"""
import bpy
import numpy as np

from ....inti.material import bahan, bsdf, matematika
from ....inti.warna import lin
from . import data
from .bahan_p3 import _bump, _hadap_bawah, _koord, _noise, _tandai, _variasi_warna, busa, kapsul, karet, lembut, \
    mesh_rajut, suede, tali_anyam

RIB = {"kulit_bergaris": (1.6, 0.25), "busa_bergaris": (2.5, 0.6)}  # (pitch mm, kekuatan bump) [D] dari foto makro
TINT_KAPSUL = 0.7  # [D] film kapsul jauh lebih bening dari warna yang terlihat melalui jendela


def kulit(peran, hexa):
    """Kulit sintetis halus: kasar 0,42, sheen tipis, coat tipis (kilap kulit baru), butir halus 0,15 mm."""
    m = bahan(peran, lin(hexa), 0.42)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Sheen Weight"].default_value, b.inputs["Coat Weight"].default_value = 0.15, 0.12
    t.links.new(_variasi_warna(t, b, hexa, 0.03, 60.0), b.inputs["Base Color"])
    _bump(t, b, _noise(t, 3200.0, 5.0, 0.65).outputs["Fac"], 0.18, 0.00015)
    return _tandai(m, peran, hexa)


def tpu(peran, hexa):
    """TPU cetak (plakat, tab tumit): kasar 0,22 + coat 0,4, nyaris tanpa tekstur."""
    m = bahan(peran, lin(hexa), 0.22)
    b = bsdf(m)
    b.inputs["Coat Weight"].default_value, b.inputs["Coat Roughness"].default_value = 0.4, 0.15
    return _tandai(m, peran, hexa)


def _rib(m, pitch_mm, kuat):
    """Rib horizontal (alur sejajar tanah) lewat bump Wave BANDS arah Z objek, periode pitch_mm."""
    t, b = m.node_tree, bsdf(m)
    w = t.nodes.new("ShaderNodeTexWave")
    w.wave_type, w.bands_direction, w.wave_profile = "BANDS", "Z", "SIN"
    w.inputs["Scale"].default_value = 1000.0 / pitch_mm  # koordinat objek dalam meter
    t.links.new(_koord(t), w.inputs["Vector"])
    _bump(t, b, w.outputs["Fac"], kuat, 0.0004)
    return m


def karet_foto(peran, hexa, tapak="waffle"):
    """Outsole karet + tapak dari PETA ALUR foto sol (data turunan, ekstraksi/tapak.py): bump hanya di muka menghadap
    bawah, alur sedikit lebih gelap. tapak selain bawaan (polos/gelombang/voronoi) = resep AM1 (uji negatif AM-07)."""
    if tapak != "waffle" or data.TAPAK is None:
        return karet(peran, hexa, tapak)
    m = bahan(peran, lin(hexa), 0.8)
    t, b = m.node_tree, bsdf(m)
    info = data.TAPAK["alur"]
    img = bpy.data.images.load(data.path_data("tapak_alur"), check_existing=True)
    img.colorspace_settings.name = "Non-Color"
    tex = t.nodes.new("ShaderNodeTexImage")
    tex.image, tex.extension, tex.interpolation = img, "CLIP", "Linear"
    xyz = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(_koord(t), xyz.inputs[0])
    p = np.array(data.DATA["profil_plan_sol"], float)
    c = (p[:, 1].min() + p[:, 2].max() + data.PX) / 2  # konvensi plan_y: Y model = c - y foto
    u = matematika(t, "DIVIDE", matematika(t, "MULTIPLY", xyz.outputs[0], 1000.0), info["lebar_mm"])
    y_foto = matematika(t, "SUBTRACT", c, matematika(t, "MULTIPLY", xyz.outputs[1], 1000.0))
    v = matematika(t, "SUBTRACT", 1.0, matematika(t, "DIVIDE", y_foto, info["tinggi_mm"]))
    gab = t.nodes.new("ShaderNodeCombineXYZ")
    t.links.new(u, gab.inputs[0])
    t.links.new(v, gab.inputs[1])
    t.links.new(gab.outputs[0], tex.inputs["Vector"])
    bw = t.nodes.new("ShaderNodeRGBToBW")
    t.links.new(tex.outputs["Color"], bw.inputs[0])
    alur = matematika(t, "MULTIPLY", bw.outputs[0], _hadap_bawah(t))
    _bump(t, b, matematika(t, "SUBTRACT", 1.0, alur), 1.0, 0.0012)
    warna = t.nodes.new("ShaderNodeMix")
    warna.data_type = "RGBA"
    t.links.new(alur, warna.inputs["Factor"])
    warna.inputs["A"].default_value = (*lin(hexa), 1)
    warna.inputs["B"].default_value = (*[c_ * 0.45 for c_ in lin(hexa)], 1)
    t.links.new(warna.outputs["Result"], b.inputs["Base Color"])
    return _tandai(m, peran, hexa)


JENIS = {
    "kulit": kulit, "tpu": tpu, "busa": busa, "mesh": mesh_rajut, "tali": tali_anyam, "lembut": lembut, "suede": suede,
    "kulit_bergaris": lambda p, h: _rib(kulit(p, h), *RIB["kulit_bergaris"]),
    "busa_bergaris": lambda p, h: _rib(busa(p, h), *RIB["busa_bergaris"]),
}


def bahan_colorway(tapak="waffle", kapsul_mode="translusen", hex_salah=None, ior_kapsul=1.5):
    """{peran: material} dari palet proyek berjenis. Parameter selain default hanya untuk uji negatif QC."""
    m = {}
    for peran, v in data.palet().items():
        hexa = (hex_salah or {}).get(peran, v[0])
        jenis = v[2] if len(v) > 2 else "kulit"
        if jenis == "karet":
            m[peran] = karet(peran, hexa, tapak)
        elif jenis == "karet_foto":
            m[peran] = karet_foto(peran, hexa, tapak)
        elif jenis == "kapsul":
            # hex foto = yang TERLIHAT melalui jendela (isi rongga + jendela seberang), bukan tint film; tint film [D] =
            # hex dicerahkan 70 % ke putih (AM90-C12: tint = hex foto -> kapsul gelap, AM-17 0,0083 < 0,01)
            r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
            tint = "#" + "".join("%02X" % round(c + (255 - c) * TINT_KAPSUL) for c in (r, g, b))
            m[peran] = kapsul(peran, tint, ior_kapsul, opak=(kapsul_mode == "opak"))
            m[peran]["hex_p3"] = hexa
        else:
            m[peran] = JENIS[jenis](peran, hexa)
        m[peran].name = peran
    m["upper"] = m["upper_mesh"]
    return m
