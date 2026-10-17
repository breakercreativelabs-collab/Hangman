"""Resep sepatu M3: MATERIAL prosedural palet proyek (P3 Aqua Holo untuk AM1, eksperimen/selera.md), non-generatif.

Satu fungsi per peran (slot M2, data.PERAN). Setiap material menyimpan `peran` dan `hex_p3` (dibaca QC AM-15/AM-18).
Hex + sumber per peran ada di proyek.toml [palet.peran] ([F] keputusan pengguna di selera.md; [D] dugaan).

Variasi untuk uji negatif QC (bukan untuk dipakai):
  swoosh="polos"        swoosh diffuse polos (AM-16)
  kapsul="opak"         kapsul tanpa transmisi (AM-17)
  hex_salah={peran: hex} warna peran salah (AM-15)
  tapak="voronoi|gelombang|polos" tapak lama/negatif (AM-07); default "waffle"
Dipanggil oleh sol.bangun_sepatu(palet="p3").
"""
import math

from ....inti.material import bahan, bayangan_tembus, bsdf, matematika
from ....inti.warna import lin
from . import data


def P3():
    """{peran: (hex, sumber)} palet proyek aktif."""
    return data.palet()


# Tapak waffle [D] (tanpa foto): forefoot kotak 6,5 mm, tumit sel memanjang 13 x 6,5 mm, alur 1,2 mm, kisi diputar
# 15 deg. C-A7: kisi sejajar sumbu (0 deg) = alur melintang selebar sol = garis koheren yang memang dicari AM-07
# (banding 0,077 > 0,010); 10-30 deg -> 0,000; 45 deg -> 0,021 (kisi diagonal kembali periodik sama di kedua separuh).
WAFFLE = dict(x_tumit=168.0, kotak=6.5, tumit=(13.0, 6.5), alur=1.2, sudut=15.0, tepi=0.35)
# Holo swoosh [D]: urutan hue terhadap sudut pandang (facing 0 = tegak lurus = hex P3). Mirip foil holografik Y2K.
HOLO_RAMP = ((0.00, "#2FD0B6"), (0.12, "#2FD0B6"), (0.40, "#3FA9F5"), (0.62, "#9A7BFF"), (0.80, "#FF8AD8"),
             (1.00, "#C8F56A"))


def _tandai(m, peran, hexa):
    m["peran"], m["hex_p3"] = peran, hexa
    return m


def _bump(t, b, tinggi, kekuatan, jarak):
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = kekuatan, jarak
    t.links.new(tinggi, bump.inputs["Height"])
    if b.inputs["Normal"].links:  # rantai bump: normal sebelumnya jadi masukan
        t.links.new(b.inputs["Normal"].links[0].from_socket, bump.inputs["Normal"])
    t.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return bump


def _koord(t):
    return t.nodes.new("ShaderNodeTexCoord").outputs["Object"]


def _noise(t, skala, detail=4.0, kasar=0.6):
    n = t.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value, n.inputs["Detail"].default_value = skala, detail
    n.inputs["Roughness"].default_value = kasar
    t.links.new(_koord(t), n.inputs["Vector"])
    return n


def _variasi_warna(t, b, hexa, amp, skala):
    """Warna dasar x (1 +- amp) dari noise lembut: ketidaksempurnaan halus (selera.md: pastel steril = usang)."""
    n = _noise(t, skala, 2.0, 0.5)
    mr = t.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 1 - amp, 1 + amp
    t.links.new(n.outputs["Fac"], mr.inputs["Value"])
    kali = t.nodes.new("ShaderNodeMix")
    kali.data_type, kali.blend_type = "RGBA", "MULTIPLY"
    kali.inputs["Factor"].default_value = 1.0
    kali.inputs["A"].default_value = (*lin(hexa), 1)
    t.links.new(mr.outputs["Result"], kali.inputs["B"])
    return kali.outputs["Result"]


def suede(peran, hexa):
    """Suede/nubuck: sangat kasar + sheen (bulu halus menangkap cahaya landai), bump bulu 0,3 mm, belang tipis."""
    m = bahan(peran, lin(hexa), 0.92)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Sheen Weight"].default_value, b.inputs["Sheen Roughness"].default_value = 0.6, 0.35
    b.inputs["Sheen Tint"].default_value = (1.0, 1.0, 1.0, 1)
    b.inputs["Specular IOR Level"].default_value = 0.3
    t.links.new(_variasi_warna(t, b, hexa, 0.05, 90.0), b.inputs["Base Color"])
    _bump(t, b, _noise(t, 2500.0, 6.0, 0.7).outputs["Fac"], 0.25, 0.0003)
    return _tandai(m, peran, hexa)


def mesh_rajut(peran, hexa):
    """Mesh toe box/quarter: kisi lubang ~2 mm (Voronoi tanpa acak = kisi teratur), lubang lebih gelap (lining di
    bawahnya) + cekung; benang rajut halus di antara lubang."""
    m = bahan(peran, lin(hexa), 0.85)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Sheen Weight"].default_value, b.inputs["Sheen Roughness"].default_value = 0.3, 0.5
    vor = t.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value, vor.inputs["Randomness"].default_value = 650.0, 0.0  # 1/650 m ~ 1,5 mm
    t.links.new(_koord(t), vor.inputs["Vector"])
    lubang = t.nodes.new("ShaderNodeMapRange")  # pusat sel (jarak < 0,22) = lubang
    lubang.interpolation_type = "SMOOTHSTEP"
    lubang.inputs["From Min"].default_value, lubang.inputs["From Max"].default_value = 0.26, 0.19
    t.links.new(vor.outputs["Distance"], lubang.inputs["Value"])
    warna = t.nodes.new("ShaderNodeMix")
    warna.data_type = "RGBA"
    t.links.new(lubang.outputs["Result"], warna.inputs["Factor"])
    t.links.new(_variasi_warna(t, b, hexa, 0.03, 120.0), warna.inputs["A"])
    warna.inputs["B"].default_value = (*[c * 0.45 for c in lin(hexa)], 1)
    t.links.new(warna.outputs["Result"], b.inputs["Base Color"])
    inv = t.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    t.links.new(lubang.outputs["Result"], inv.inputs[1])
    _bump(t, b, inv.outputs[0], 0.7, 0.0004)
    wav = t.nodes.new("ShaderNodeTexWave")  # benang rajut
    wav.inputs["Scale"].default_value, wav.inputs["Distortion"].default_value = 2200.0, 3.0
    t.links.new(_koord(t), wav.inputs["Vector"])
    _bump(t, b, wav.outputs["Fac"], 0.15, 0.0001)
    return _tandai(m, peran, hexa)


def holo(peran, hexa, polos=False):
    """Swoosh iridescent: warna dasar bergeser hue menurut sudut pandang (Layer Weight facing -> ramp holo; tegak
    lurus = hex P3), plus thin-film di lapisan spekular (interferensi nyata Principled) dan clearcoat.
    polos=True: diffuse teal polos (uji negatif AM-16)."""
    m = bahan(peran, lin(hexa), 0.5 if polos else 0.28, 0.0)
    if polos:
        return _tandai(m, peran, hexa)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Coat Weight"].default_value, b.inputs["Coat Roughness"].default_value = 0.6, 0.08
    b.inputs["Thin Film Thickness"].default_value, b.inputs["Thin Film IOR"].default_value = 520.0, 1.45
    lw = t.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    ramp = t.nodes.new("ShaderNodeValToRGB")
    el = ramp.color_ramp.elements
    for i, (pos, h) in enumerate(HOLO_RAMP):
        h = hexa if h == P3()["swoosh"][0] else h  # facing ~0 = warna peran (hex_salah ikut, uji negatif AM-15)
        e = el[i] if i < len(el) else el.new(pos)
        e.position, e.color = pos, (*lin(h), 1)
    t.links.new(lw.outputs["Facing"], ramp.inputs["Fac"])
    t.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return _tandai(m, peran, hexa)


def chrome(peran, hexa):
    """Aksen chrome perak dingin: logam, kasar 0,12, thin-film tipis (hologram shift halus di sorot)."""
    m = bahan(peran, lin(hexa), 0.12, 1.0)
    b = bsdf(m)
    b.inputs["Thin Film Thickness"].default_value, b.inputs["Thin Film IOR"].default_value = 300.0, 1.33
    return _tandai(m, peran, hexa)


def busa(peran, hexa):
    """Midsole busa PU/EVA semi-matte: kasar 0,5, pori halus (bump noise 0,2 mm)."""
    m = bahan(peran, lin(hexa), 0.5)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Specular IOR Level"].default_value = 0.4
    _bump(t, b, _noise(t, 1800.0, 3.0, 0.5).outputs["Fac"], 0.12, 0.0002)
    return _tandai(m, peran, hexa)


def kapsul(peran, hexa, ior, opak=False):
    """Kapsul Air pink translusen: transmisi penuh (berongga, QC-11) + sedikit buram (kasar 0,08) + bayangan tembus
    (C-11). opak=True: tanpa transmisi (uji negatif AM-17)."""
    if opak:
        return _tandai(bahan(peran, lin(hexa), 0.3), peran, hexa)
    m = bahan(peran, lin(hexa), 0.08, 0.0, **{"Transmission Weight": 1.0, "IOR": ior})
    return _tandai(bayangan_tembus(m), peran, hexa)


def _alur(t, a, pitch, lebar, tepi):
    """1 di alur (dekat garis kisi berjarak `pitch` mm sepanjang koordinat a mm), 0 di lug; tepi smoothstep."""
    d = matematika(t, "ABSOLUTE", matematika(t, "SUBTRACT",
                                                  matematika(t, "FRACT", matematika(t, "DIVIDE", a, pitch)), 0.5))
    mr = t.nodes.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    batas = pitch / 2 - lebar / 2
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = batas - tepi, batas + tepi
    t.links.new(matematika(t, "MULTIPLY", d, pitch), mr.inputs["Value"])
    return mr.outputs["Result"]


def _waffle(t, p=WAFFLE):
    """Masker alur waffle [D] di bidang XY objek (mm), kisi diputar `sudut`: forefoot kotak, tumit (x' >= x_tumit)
    sel memanjang searah x'. Kembalikan socket 0..1 (1 = alur)."""
    xyz = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(_koord(t), xyz.inputs[0])
    x, y = (matematika(t, "MULTIPLY", xyz.outputs[i], 1000.0) for i in (0, 1))
    c, s = math.cos(math.radians(p["sudut"])), math.sin(math.radians(p["sudut"]))
    xr = matematika(t, "SUBTRACT", matematika(t, "MULTIPLY", x, c), matematika(t, "MULTIPLY", y, s))
    yr = matematika(t, "ADD", matematika(t, "MULTIPLY", x, s), matematika(t, "MULTIPLY", y, c))
    g, e = p["alur"], p["tepi"]
    depan = matematika(t, "MAXIMUM", _alur(t, xr, p["kotak"], g, e), _alur(t, yr, p["kotak"], g, e))
    belakang = matematika(t, "MAXIMUM", _alur(t, xr, p["tumit"][0], g, e), _alur(t, yr, p["tumit"][1], g, e))
    di_tumit = matematika(t, "GREATER_THAN", xr, p["x_tumit"])
    mix = t.nodes.new("ShaderNodeMix")
    t.links.new(di_tumit, mix.inputs["Factor"])
    t.links.new(depan, mix.inputs["A"])
    t.links.new(belakang, mix.inputs["B"])
    return mix.outputs["Result"]


def _hadap_bawah(t):
    """0..1: permukaan menghadap bawah (normal dunia z < -0,35 .. -0,6). Tapak hanya di dasar, dinding outsole polos
    (pantauan M2: Voronoi 3D ikut tampil di dinding samping)."""
    xyz = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(t.nodes.new("ShaderNodeNewGeometry").outputs["Normal"], xyz.inputs[0])
    mr = t.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.35, 0.6
    t.links.new(matematika(t, "MULTIPLY", xyz.outputs[2], -1.0), mr.inputs["Value"])
    return mr.outputs["Result"]


def karet(peran, hexa, tapak="waffle"):
    """Outsole karet tonal: kasar 0,8 + tapak. waffle (M3) | voronoi (M2) | gelombang (v1, negatif C-A1) | polos."""
    m = bahan(peran, lin(hexa), 0.8)
    t, b = m.node_tree, bsdf(m)
    if tapak == "polos":
        return _tandai(m, peran, hexa)
    if tapak == "waffle":
        alur = matematika(t, "MULTIPLY", _waffle(t), _hadap_bawah(t))
        tinggi = matematika(t, "SUBTRACT", 1.0, alur)
        _bump(t, b, tinggi, 1.0, 0.0012)
    else:
        koord = _koord(t)
        if tapak == "gelombang":
            tex = t.nodes.new("ShaderNodeTexWave")
            tex.inputs["Scale"].default_value = 25.0
            t.links.new(koord, tex.inputs["Vector"])
            _bump(t, b, tex.outputs["Fac"], 0.3, 0.0008)
            return _tandai(m, peran, hexa)
        tex = t.nodes.new("ShaderNodeTexVoronoi")
        tex.feature = "DISTANCE_TO_EDGE"
        tex.inputs["Scale"].default_value = 160.0
        t.links.new(koord, tex.inputs["Vector"])
        mr = t.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.08, 0.0
        t.links.new(tex.outputs["Distance"], mr.inputs["Value"])
        alur = mr.outputs["Result"]
        _bump(t, b, matematika(t, "SUBTRACT", 1.0, alur), 1.0, 0.001)
    warna = t.nodes.new("ShaderNodeMix")  # alur lebih gelap (kotoran/AO murah)
    warna.data_type = "RGBA"
    t.links.new(alur, warna.inputs["Factor"])
    warna.inputs["A"].default_value = (*lin(hexa), 1)
    warna.inputs["B"].default_value = (*[c * 0.4 for c in lin(hexa)], 1)
    t.links.new(warna.outputs["Result"], b.inputs["Base Color"])
    return _tandai(m, peran, hexa)


def tali_anyam(peran, hexa):
    """Tali anyaman: pita gelombang halus terdistorsi (serat) + sheen ringan."""
    m = bahan(peran, lin(hexa), 0.8)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Sheen Weight"].default_value = 0.4
    wav = t.nodes.new("ShaderNodeTexWave")
    wav.inputs["Scale"].default_value, wav.inputs["Distortion"].default_value = 1400.0, 6.0
    t.links.new(_koord(t), wav.inputs["Vector"])
    _bump(t, b, wav.outputs["Fac"], 0.5, 0.0003)
    return _tandai(m, peran, hexa)


def lembut(peran, hexa):
    m = bahan(peran, lin(hexa), 0.9)
    b = bsdf(m)
    b.inputs["Sheen Weight"].default_value = 0.3
    return _tandai(m, peran, hexa)


def bahan_p3(tapak="waffle", swoosh="holo", kapsul_mode="translusen", hex_salah=None, ior_kapsul=1.5):
    hx = {k: v[0] for k, v in P3().items()}
    hx.update(hex_salah or {})
    m = {
        "mudguard": suede("mudguard", hx["mudguard"]),
        "outsole": karet("outsole", hx["outsole"], tapak),
        "upper_mesh": mesh_rajut("upper_mesh", hx["upper_mesh"]),
        "swoosh": holo("swoosh", hx["swoosh"], polos=(swoosh == "polos")),
        "midsole": busa("midsole", hx["midsole"]),
        "kapsul_air": kapsul("kapsul_air", hx["kapsul_air"], ior_kapsul, opak=(kapsul_mode == "opak")),
        "overlay_suede": suede("overlay_suede", hx["overlay_suede"]),
        "lining": lembut("lining", hx["lining"]),
        "tali": tali_anyam("tali", hx["tali"]),
        "aksen_chrome": chrome("aksen_chrome", hx["aksen_chrome"]),
    }
    for k, v in m.items():
        v.name = k  # nama = peran (AM-14); hindari akhiran .001
    m["upper"] = m["upper_mesh"]  # blok M1 (uji negatif C-A3)
    return m
