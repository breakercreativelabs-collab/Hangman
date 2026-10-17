"""Material: SATU-SATUNYA tempat node helper (bsdf, bahan, simpul, matematika, ramp, bayangan_tembus).
Modul lain wajib memakai helper ini (uji struktur c: tidak ada helper duplikat)."""
import bpy


def bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def bahan(nama, warna, kasar=0.4, logam=0.0, **input_lain):
    """Material Principled baru: warna linear (r, g, b), kekasaran, metallic, input Principled lain per nama."""
    m = bpy.data.materials.new(nama)
    b = bsdf(m)
    b.inputs["Base Color"].default_value = (*warna, 1)
    b.inputs["Roughness"].default_value = kasar
    b.inputs["Metallic"].default_value = logam
    for k, v in input_lain.items():
        b.inputs[k].default_value = v
    return m


def simpul(t, tipe, **kw):
    """Node baru di node tree `t` + atribut node."""
    n = t.nodes.new(tipe)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def matematika(t, op, a=None, b=None):
    """Node Math: input angka = default_value, input socket = ditautkan. Mengembalikan socket keluaran."""
    n = simpul(t, "ShaderNodeMath", operation=op)
    for i, x in enumerate((a, b)):
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        elif x is not None:
            t.links.new(x, n.inputs[i])
    return n.outputs[0]


def ramp(t, fac, c0, c1):
    """Color ramp 2 warna (linear) dari socket fac. Mengembalikan socket warna."""
    cr = simpul(t, "ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color, cr.color_ramp.elements[1].color = (*c0, 1), (*c1, 1)
    t.links.new(fac, cr.inputs[0])
    return cr.outputs[0]


def bayangan_tembus(m):
    """C-11: caustics dimatikan, jadi shadow ray terhalang kaca/cairan dan isi botol + sisi dalam label jadi hitam.
    Untuk shadow ray, material bening dibuat Transparent BSDF berwarna (teknik standar product render)."""
    t = m.node_tree
    out = next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL")
    asli = out.inputs["Surface"].links[0].from_socket
    tembus = simpul(t, "ShaderNodeBsdfTransparent")
    tembus.inputs["Color"].default_value = bsdf(m).inputs["Base Color"].default_value
    campur = simpul(t, "ShaderNodeMixShader")
    t.links.new(simpul(t, "ShaderNodeLightPath").outputs["Is Shadow Ray"], campur.inputs[0])
    t.links.new(asli, campur.inputs[1])
    t.links.new(tembus.outputs[0], campur.inputs[2])
    t.links.new(campur.outputs[0], out.inputs["Surface"])
    return m


def bening(nama, warna, ior, kasar=0.02):
    """Kaca/plastik/cairan bening + bayangan tembus (C-11)."""
    return bayangan_tembus(bahan(nama, warna, kasar, 0.0, **{"Transmission Weight": 1.0, "IOR": ior}))
