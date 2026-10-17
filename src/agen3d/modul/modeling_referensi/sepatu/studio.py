"""Studio resep sepatu: review netral (QC warna, cek bentuk) dan studio palet proyek (P3: gradasi aqua -> violet)."""
import bpy
from mathutils import Vector

from ....inti.kamera import hadap
from ....inti.material import bahan, matematika
from ....inti.scene import koleksi
from ....inti.warna import lin
from ..geometri import mesh_obj
from . import data


# ---------------- studio ----------------
def pakai_studio(nama):
    """review = cahaya netral QC (studio_review); p3 = studio review P3 (gradasi aqua -> violet, softbox + rim)."""
    sc = bpy.context.scene
    lantai = None
    if nama == "review":
        w = bpy.data.worlds.get("dunia_review") or bpy.data.worlds.new("dunia_review")
        sc.world = w
        lantai = studio_review()
    else:
        studio_p3()
    for ob in bpy.data.objects:
        if ob.name in ("L_key", "L_fill", "L_rim", "L_bawah", "lantai"):
            ob.hide_render = nama != "review"
        elif ob.name.startswith("P3_"):
            ob.hide_render = nama != "p3"
    return lantai


def studio_p3():
    """Studio review palet proyek (cek mata, bukan QC warna): latar gradasi proyek.toml (P3: aqua -> violet) (hanya sinar kamera, diagonal layar),
    ambien sangat redup bertint violet, softbox key putih, rim aqua + kicker violet dari belakang (glow Y2K),
    lantai penangkap bayangan."""
    sc = bpy.context.scene
    w = bpy.data.worlds.get("dunia_p3")
    if w is None:
        gradasi = data.KONFIG["palet"]["gradasi"]  # selera.md P3: latar aqua -> violet
        w = bpy.data.worlds.new("dunia_p3")
        w.use_nodes = True
        t = w.node_tree
        bg = next(n for n in t.nodes if n.type == "BACKGROUND")
        out = next(n for n in t.nodes if n.type == "OUTPUT_WORLD")
        koord = t.nodes.new("ShaderNodeTexCoord")
        xyz = t.nodes.new("ShaderNodeSeparateXYZ")
        t.links.new(koord.outputs["Window"], xyz.inputs[0])
        diag = matematika(t, "MULTIPLY", matematika(t, "ADD", xyz.outputs[0], matematika(t, "SUBTRACT", 1.0, xyz.outputs[1])), 0.5)
        ramp = t.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*lin(gradasi[0]), 1)
        ramp.color_ramp.elements[1].color = (*lin(gradasi[1]), 1)
        t.links.new(diag, ramp.inputs["Fac"])
        latar = t.nodes.new("ShaderNodeBackground")
        latar.inputs["Strength"].default_value = 1.41  # eksposur render P3 -0,5: latar tetap pada hex selera.md
        t.links.new(ramp.outputs["Color"], latar.inputs["Color"])
        bg.inputs["Color"].default_value, bg.inputs["Strength"].default_value = (0.80, 0.78, 0.95, 1), 0.03
        mix = t.nodes.new("ShaderNodeMixShader")
        t.links.new(t.nodes.new("ShaderNodeLightPath").outputs["Is Camera Ray"], mix.inputs[0])
        t.links.new(bg.outputs[0], mix.inputs[1])
        t.links.new(latar.outputs[0], mix.inputs[2])
        t.links.new(mix.outputs[0], out.inputs["Surface"])
        kl = koleksi("LIGHTS")
        pusat = Vector((0.147, 0.0, 0.05))
        for nama, lok, energi, ukuran, warna in (
                ("P3_softbox", (-0.05, 0.40, 0.45), 11.0, 0.7, (1, 1, 1)),
                # rim dari BELAKANG (berlawanan kamera hero): rim di sisi kamera meratakan bentuk (lihat ATURAN_QC M3)
                ("P3_rim_aqua", (0.42, -0.30, 0.32), 6.0, 0.25, tuple(lin(gradasi[0]))),
                ("P3_rim_violet", (-0.12, -0.38, 0.20), 3.0, 0.25, tuple(lin(gradasi[1])))):
            d = bpy.data.lights.new(nama, "AREA")
            d.energy, d.size, d.color = energi, ukuran, warna
            ob = bpy.data.objects.new(nama, d)
            kl.objects.link(ob)
            ob.location = lok
            hadap(ob, pusat)
        lt = mesh_obj("P3_lantai", [(-1, -1, 0), (1.5, -1, 0), (1.5, 1, 0), (-1, 1, 0)], [(0, 1, 2, 3)],
                     koleksi("BACKDROP"), validasi=False)
        lt.is_shadow_catcher = True
    sc.world = w


# ---------------- render tampak (cek mata) ----------------
def studio_review():
    """Cahaya review netral (bukan preset product shot: model belum di-normalize, M1 hanya cek bentuk)."""
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("dunia")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value, bg.inputs["Strength"].default_value = (0.55, 0.57, 0.60, 1), 0.35
    if bpy.data.objects.get("lantai"):
        return bpy.data.objects["lantai"]
    kl = koleksi("LIGHTS")
    # L_bawah: menyinari sol dari bawah dengan sudut landai (alur tapak terbaca); terhalang lantai di tampak lain
    for nama, lok, energi, ukuran in (("L_key", (0.05, 0.45, 0.55), 18.0, 0.5), ("L_fill", (0.25, -0.5, 0.25), 6.0, 0.8),
                                      ("L_rim", (0.55, 0.1, 0.35), 8.0, 0.3), ("L_bawah", (-0.15, 0.25, -0.30), 5.0, 0.5)):
        d = bpy.data.lights.new(nama, "AREA")
        d.energy, d.size = energi, ukuran
        ob = bpy.data.objects.new(nama, d)
        kl.objects.link(ob)
        ob.location = lok
        hadap(ob, Vector((0.147, 0.0, 0.05)))
    lantai = mesh_obj("lantai", [(-1, -1, 0), (1.5, -1, 0), (1.5, 1, 0), (-1, 1, 0)], [(0, 1, 2, 3)],
                     koleksi("BACKDROP"), validasi=False)
    lantai.data.materials.append(bahan("lantai", (0.16, 0.16, 0.17), 0.6))
    return lantai
