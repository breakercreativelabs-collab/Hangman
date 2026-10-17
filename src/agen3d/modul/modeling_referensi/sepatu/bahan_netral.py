"""Material netral M1/M2 (sebelum palet M3): outsole bertapak, mesh rajut, peran lain polos."""
from ....inti.material import bahan, bayangan_tembus, bsdf

KAPSUL_IOR = 1.50       # [D] poliuretan/TPU


def bahan_outsole(tapak="voronoi"):
    """Karet outsole + tapak prosedural (bump, bukan geometri: siluet & QC tidak berubah).
    C-A1: v1 memakai Wave (pita sepanjang X) = garis vertikal di tampak bawah. Kini sel Voronoi 2D (lug ~6 mm,
    tepi sel = alur), tanpa arah dominan, sehingga rata-rata per kolom tidak bergaris. tapak: voronoi | gelombang | polos."""
    m = bahan("outsole", (0.32, 0.32, 0.33), 0.85)
    if tapak == "polos":
        return m
    t = m.node_tree
    b = bsdf(m)
    koord = t.nodes.new("ShaderNodeTexCoord")
    bump = t.nodes.new("ShaderNodeBump")
    if tapak == "gelombang":  # v1 (uji negatif C-A1)
        tex = t.nodes.new("ShaderNodeTexWave")
        tex.inputs["Scale"].default_value = 25.0
        bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.3, 0.0008
        t.links.new(koord.outputs["Object"], tex.inputs["Vector"])
        t.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    else:
        tex = t.nodes.new("ShaderNodeTexVoronoi")
        tex.feature = "DISTANCE_TO_EDGE"
        tex.inputs["Scale"].default_value = 160.0  # 1/160 m ~ 6 mm per sel
        alur = t.nodes.new("ShaderNodeMapRange")  # tepi sel (< 0,08) = alur 1 mm, isi sel = lug datar
        alur.inputs["From Min"].default_value, alur.inputs["From Max"].default_value = 0.0, 0.08
        bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 1.0, 0.001
        t.links.new(koord.outputs["Object"], tex.inputs["Vector"])
        t.links.new(tex.outputs["Distance"], alur.inputs["Value"])
        t.links.new(alur.outputs["Result"], bump.inputs["Height"])
        warna = t.nodes.new("ShaderNodeMix")  # alur sedikit lebih gelap (kotoran/AO murah)
        warna.data_type = "RGBA"
        warna.inputs["A"].default_value, warna.inputs["B"].default_value = (0.12, 0.12, 0.13, 1), (0.32, 0.32, 0.33, 1)
        t.links.new(alur.outputs["Result"], warna.inputs["Factor"])
        t.links.new(warna.outputs["Result"], b.inputs["Base Color"])
    t.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def bahan_mesh(nama, warna):
    """Mesh rajut toe box/quarter: bump sel kecil (~1,3 mm) supaya terbaca sebagai mesh, warna tetap netral."""
    m = bahan(nama, warna, 0.8)
    t = m.node_tree
    koord = t.nodes.new("ShaderNodeTexCoord")
    tex = t.nodes.new("ShaderNodeTexVoronoi")
    tex.inputs["Scale"].default_value = 750.0
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.6, 0.0003
    t.links.new(koord.outputs["Object"], tex.inputs["Vector"])
    t.links.new(tex.outputs["Distance"], bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], bsdf(m).inputs["Normal"])
    return m


def bahan_netral(tapak="voronoi"):
    m = {
        "midsole": bahan("midsole", (0.86, 0.86, 0.84), 0.55),
        "outsole": bahan_outsole(tapak),
        "kapsul_air": bayangan_tembus(bahan("kapsul_air", (0.93, 0.96, 1.0), 0.04, 0.0,
                                                        **{"Transmission Weight": 1.0, "IOR": KAPSUL_IOR})),
        "upper_mesh": bahan_mesh("upper_mesh", (0.62, 0.62, 0.63)),
        "mudguard": bahan("mudguard", (0.30, 0.30, 0.31), 0.9),
        "overlay_suede": bahan("overlay_suede", (0.42, 0.42, 0.43), 0.95),
        "swoosh": bahan("swoosh", (0.12, 0.12, 0.13), 0.5),
        "lining": bahan("lining", (0.05, 0.05, 0.055), 0.9),
        "tali": bahan("tali", (0.80, 0.80, 0.78), 0.85),
        "aksen_chrome": bahan("aksen_chrome", (0.83, 0.86, 0.91), 0.2, 1.0),
    }
    m["outsole"].name = "outsole"
    m["upper"] = m["upper_mesh"]  # blok M1 (uji negatif C-A3)
    return m
