"""Material produk uji: label prosedural (logo + garis + WARNA_VARIAN di-drive CONTROL) + bahan per produk."""
import math

from ...inti.material import bahan, bayangan_tembus, bening, bsdf, matematika, simpul
from ...inti.scene import drive
from . import spesifikasi


def bahan_label(nama, z_logo, z_garis, logam=0.0, kasar=0.35, **input_lain):
    """Label prosedural di UV: warna varian (node WARNA_VARIAN, di-drive CONTROL) + logo putih di sisi depan
    + garis gelap melingkar. Logo hanya di depan, jadi arah produk terbaca mata di contact sheet."""
    m = bahan(nama, (0.5, 0.5, 0.5), kasar, logam, **input_lain)
    t = m.node_tree
    b = bsdf(m)
    xyz = simpul(t, "ShaderNodeSeparateXYZ")
    t.links.new(simpul(t, "ShaderNodeTexCoord").outputs["UV"], xyz.inputs[0])
    u, z, _ = xyz.outputs  # UV label: u = 0,5 di depan, v = tinggi (m)
    di_depan = matematika(t, "LESS_THAN", matematika(t, "ABSOLUTE", matematika(t, "SUBTRACT", u, 0.5)),
                          0.42 / (2 * math.pi))
    pita = lambda z0, z1: matematika(t, "MULTIPLY", matematika(t, "GREATER_THAN", z, z0),
                                     matematika(t, "LESS_THAN", z, z1))
    logo = matematika(t, "MULTIPLY", di_depan, pita(*z_logo))
    garis = pita(*z_garis)
    rgb = simpul(t, "ShaderNodeRGB", name="WARNA_VARIAN", label="WARNA_VARIAN")
    rgb.outputs[0].default_value = (0.5, 0.5, 0.5, 1)
    gelap = simpul(t, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    gelap.inputs["Factor"].default_value = 1.0
    t.links.new(garis, gelap.inputs["Factor"])
    t.links.new(rgb.outputs[0], gelap.inputs["A"])
    gelap.inputs["B"].default_value = (0.3, 0.3, 0.3, 1)
    putih = simpul(t, "ShaderNodeMix", data_type="RGBA")
    t.links.new(logo, putih.inputs["Factor"])
    t.links.new(gelap.outputs["Result"], putih.inputs["A"])
    putih.inputs["B"].default_value = (0.85, 0.85, 0.85, 1)
    kertas = simpul(t, "ShaderNodeMix", data_type="RGBA")  # C-11: sisi belakang label = kertas, bukan cetakan
    t.links.new(simpul(t, "ShaderNodeNewGeometry").outputs["Backfacing"], kertas.inputs["Factor"])
    t.links.new(putih.outputs["Result"], kertas.inputs["A"])
    kertas.inputs["B"].default_value = (0.78, 0.76, 0.70, 1)
    t.links.new(kertas.outputs["Result"], b.inputs["Base Color"])
    for i in range(3):
        drive(t, 'nodes["WARNA_VARIAN"].outputs[0].default_value', "warna_varian", indeks=i)
    return m


def bahan_produk(nama):
    s = spesifikasi.SPEC[nama]
    mm = lambda k: tuple(v / 1000 for v in s[k])
    label = lambda **kw: bahan_label("LABEL_" + nama, mm("logo_mm"), mm("garis_mm"), **kw)
    if nama in ("kaleng", "kaleng_slim"):
        # C-14: cat kaleng = tinta opak + clearcoat di atas aluminium. Metallic 0,7 memantulkan studio gelap
        # (dramatis) sehingga putih tampil abu (QC-10 0,36); 0,3 + coat 1,0 -> <= 0,13 di semua preset
        return {"LABEL": label(logam=0.3, kasar=0.28, **{"Coat Weight": 1.0}),
                "logam": bahan("logam_aluminium", (0.80, 0.80, 0.82), 0.22, 1.0)}
    if nama == "kotak_susu":
        return {"LABEL": label(kasar=0.5),  # karton bercetak (seluruh kotak)
                "foil": bahan("foil_sedotan", (0.85, 0.85, 0.86), 0.3, 1.0)}
    if nama == "tube":
        return {"LABEL": label(kasar=0.3),  # tube PE bercetak (seluruh badan)
                "tutup": bahan("tutup_putih", (0.85, 0.85, 0.83), 0.35)}
    if nama == "jar_selai":
        return {"LABEL": label(kasar=0.45),
                "kaca": bening("kaca_flint", (0.95, 0.98, 0.96), 1.52),
                "isi": bahan("isi_selai", (0.30, 0.02, 0.04), 0.25),
                "tutup": bahan("tutup_lug", (0.72, 0.58, 0.30), 0.3, 1.0)}
    if nama == "botol_pet":
        return {"LABEL": label(kasar=0.25),
                "pet": bening("plastik_pet", (0.96, 0.98, 1.0), 1.57, 0.03),
                "air": bening("air", (0.97, 0.99, 1.0), 1.33, 0.0),
                "tutup": bahan("tutup_pp", (0.88, 0.88, 0.88), 0.4)}
    return {"LABEL": label(),
            # C-11: kaca berongga dilewati 4 antarmuka (bukan 2), jadi warna per antarmuka lebih terang
            "kaca": bayangan_tembus(bahan("kaca_cokelat", (0.70, 0.40, 0.12), 0.02, 0.0,
                                          **{"Transmission Weight": 1.0, "IOR": 1.52})),
            "cairan": bayangan_tembus(bahan("cairan_bir", (0.92, 0.58, 0.16), 0.0, 0.0,
                                            **{"Transmission Weight": 1.0, "IOR": 1.33})),
            "tutup": bahan("tutup_logam", (0.78, 0.62, 0.28), 0.3, 1.0)}
