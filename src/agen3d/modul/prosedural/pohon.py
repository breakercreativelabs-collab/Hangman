"""Generator pohon prosedural (space colonization) untuk Blender 5.2.

Claude hanya memegang PARAMETER di PRESET; algoritma yang menumbuhkan batang, cabang, dan daun. QC angka di laporan
bangun() (QC_titik_menumpuk, QC_gumpalan_daun_maks_x_median, QC_daun_di_bawah_tanah, radius cabang), aturan dan
riwayat cacat: ATURAN_QC.md modul ini. Perintah: `prosedural pohon` (scene contoh + render) dan `prosedural uji`.
"""
import json
import math
import os
import random

import bpy
from mathutils import Vector, kdtree

from ...inti.material import bahan, matematika, ramp, simpul
from ...inti.render import pilih_perangkat

# ---------------- PARAMETER (satu-satunya yang perlu "dinalar" Claude) ----------------
PRESET = {
    "rindang": dict(bentuk="elipsoid", tinggi_tajuk=5.2, radius_tajuk=3.6, tebal_tajuk=2.6,
                    titik_tarik=1400, jangkau=1.6, jarak_hapus=0.35, langkah=0.22,
                    radius_batang=0.32, tropisme=0.08, daun_per_ujung=10, ukuran_daun=0.34,
                    warna_daun=(0.10, 0.32, 0.06)),
    "kerucut": dict(bentuk="kerucut", tinggi_tajuk=4.4, radius_tajuk=2.4, tebal_tajuk=5.0,
                    titik_tarik=1200, jangkau=1.3, jarak_hapus=0.30, langkah=0.2,
                    radius_batang=0.24, tropisme=0.02, daun_per_ujung=12, ukuran_daun=0.24,
                    warna_daun=(0.05, 0.20, 0.07)),
}
POHON = [("rindang", 7, -9.0), ("rindang", 21, 0.0), ("kerucut", 7, 9.0)]  # (preset, seed, posisi x)


def titik_tajuk(p, rng):
    """Sebar titik-tarik di dalam volume tajuk (elipsoid atau kerucut)."""
    pts = []
    while len(pts) < p["titik_tarik"]:
        x, y, z = (rng.uniform(-1, 1) for _ in range(3))
        if p["bentuk"] == "elipsoid":
            if x * x + y * y + z * z > 1:
                continue
            pts.append(Vector((x * p["radius_tajuk"], y * p["radius_tajuk"], p["tinggi_tajuk"] + z * p["tebal_tajuk"])))
        else:  # kerucut: makin ke atas makin sempit
            t = (z + 1) / 2  # 0 = dasar, 1 = puncak
            if x * x + y * y > (1 - t) ** 2:
                continue
            pts.append(Vector((x * p["radius_tajuk"], y * p["radius_tajuk"], p["tinggi_tajuk"] - p["tebal_tajuk"] / 2 + t * p["tebal_tajuk"] * 1.2)))
    return pts


STAT = {"duplikat_dicegah": 0}


def tumbuh(p, seed, cegah_duplikat=True):
    """Space colonization: cabang tumbuh mendekati titik-titik tarik di tajuk.
    cegah_duplikat=False hanya untuk uji negatif QC-001 (perilaku v1)."""
    rng = random.Random(seed)
    tarik = titik_tajuk(p, rng)
    node, induk = [Vector((0, 0, 0))], [-1]
    # batang naik lurus sampai menyentuh pengaruh tajuk
    while min((a - node[-1]).length for a in tarik) > p["jangkau"]:
        node.append(node[-1] + Vector((rng.uniform(-.02, .02), rng.uniform(-.02, .02), p["langkah"])))
        induk.append(len(node) - 2)
    for _ in range(400):
        kd = kdtree.KDTree(len(node))
        for i, v in enumerate(node):
            kd.insert(v, i)
        kd.balance()
        arah = {}
        for a in tarik:
            _, i, d = kd.find(a)
            if d < p["jangkau"]:
                arah[i] = arah.get(i, Vector()) + (a - node[i]).normalized()
        if not arah:
            break
        baru = 0
        for i, d in arah.items():
            d = (d.normalized() + Vector((0, 0, p["tropisme"]))).normalized()
            calon = node[i] + d * p["langkah"]
            if cegah_duplikat and kd.find(calon)[2] < p["langkah"] * 0.4:  # sudah ada titik di situ -> jangan tumbuh dobel
                STAT["duplikat_dicegah"] += 1
                continue
            node.append(calon)
            induk.append(i)
            baru += 1
        if not baru:
            break
        kd = kdtree.KDTree(len(node))
        for i, v in enumerate(node):
            kd.insert(v, i)
        kd.balance()
        tarik = [a for a in tarik if kd.find(a)[2] > p["jarak_hapus"]]
        if not tarik:
            break
    # radius cabang: model pipa Leonardo (r_induk^n = jumlah r_anak^n)
    anak = [[] for _ in node]
    for i, j in enumerate(induk):
        if j >= 0:
            anak[j].append(i)
    r = [0.0] * len(node)
    for i in reversed(range(len(node))):
        r[i] = 0.01 if not anak[i] else sum(r[c] ** 2.5 for c in anak[i]) ** (1 / 2.5)
    # v3: cabang meruncing alami (bukan diskala rata) -> cabang tengah lebih ramping
    ujung_r = 0.012
    r = [ujung_r + (p["radius_batang"] - ujung_r) * (x / r[0]) ** 1.5 for x in r]
    # jarak tiap titik ke ujung ranting terdekat (untuk menaruh daun di sepanjang ranting)
    ke_ujung = [0] * len(node)
    for i in reversed(range(len(node))):
        ke_ujung[i] = 0 if not anak[i] else min(ke_ujung[c] for c in anak[i]) + 1
    return node, induk, anak, r, rng, ke_ujung


def bahan_daun(nama, gelap, terang):
    """Daun prosedural: bentuk daun dari UV (alfa), variasi warna per daun, tembus cahaya."""
    m = bahan(nama, gelap, 0.45)
    t = m.node_tree
    bsdf = next(n for n in t.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL")
    uv = simpul(t, "ShaderNodeSeparateXYZ")
    t.links.new(simpul(t, "ShaderNodeTexCoord").outputs["UV"], uv.inputs[0])
    u, v = uv.outputs[0], uv.outputs[1]
    lebar = matematika(t, "MULTIPLY", matematika(t, "POWER", matematika(t, "SINE", matematika(t, "MULTIPLY", u, math.pi)), 0.75), 0.48)
    jarak_tengah = matematika(t, "ABSOLUTE", matematika(t, "SUBTRACT", v, 0.5))
    bentuk = matematika(t, "LESS_THAN", jarak_tengah, lebar)
    tulang = matematika(t, "LESS_THAN", jarak_tengah, 0.025)
    var = simpul(t, "ShaderNodeAttribute", attribute_name="variasi")
    warna = ramp(t, matematika(t, "ADD", var.outputs["Fac"], matematika(t, "MULTIPLY", tulang, 0.35)), gelap, terang)
    t.links.new(warna, bsdf.inputs["Base Color"])
    tembus = simpul(t, "ShaderNodeBsdfTranslucent")
    t.links.new(warna, tembus.inputs["Color"])
    campur = simpul(t, "ShaderNodeMixShader")
    campur.inputs[0].default_value = 0.3
    t.links.new(bsdf.outputs[0], campur.inputs[1])
    t.links.new(tembus.outputs[0], campur.inputs[2])
    alfa = simpul(t, "ShaderNodeMixShader")
    t.links.new(bentuk, alfa.inputs[0])
    t.links.new(simpul(t, "ShaderNodeBsdfTransparent").outputs[0], alfa.inputs[1])
    t.links.new(campur.outputs[0], alfa.inputs[2])
    t.links.new(alfa.outputs[0], out.inputs["Surface"])
    return m


def bahan_kulit(nama):
    """Kulit batang prosedural: alur vertikal (wave) + noise, dengan bump."""
    m = bahan(nama, (0.15, 0.1, 0.06), 0.9)
    t = m.node_tree
    bsdf = next(n for n in t.nodes if n.type == "BSDF_PRINCIPLED")
    obj = simpul(t, "ShaderNodeTexCoord").outputs["Object"]
    wave = simpul(t, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="X")
    for k, v in (("Scale", 9.0), ("Distortion", 7.0), ("Detail", 6.0)):
        if k in wave.inputs:
            wave.inputs[k].default_value = v
    noise = simpul(t, "ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value, noise.inputs["Detail"].default_value = 14.0, 10.0
    t.links.new(obj, wave.inputs["Vector"])
    t.links.new(obj, noise.inputs["Vector"])
    pola = matematika(t, "MULTIPLY", wave.outputs["Fac"], noise.outputs["Fac"])
    t.links.new(ramp(t, pola, (0.04, 0.03, 0.02), (0.30, 0.22, 0.14)), bsdf.inputs["Base Color"])
    bump = simpul(t, "ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.7
    t.links.new(pola, bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def bangun_pohon(nama_preset, seed, x0, cegah_duplikat=True):
    p = PRESET[nama_preset]
    node, induk, anak, r, rng, ke_ujung = tumbuh(p, seed, cegah_duplikat)
    off = Vector((x0, 0, 0))
    # batang + cabang: mesh garis + Skin modifier (ketebalan per titik)
    me = bpy.data.meshes.new(f"batang_{nama_preset}_{seed}")
    me.from_pydata([v + off for v in node], [(j, i) for i, j in enumerate(induk) if j >= 0], [])
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.collection.objects.link(ob)
    ob.modifiers.new("Skin", "SKIN")
    for i, sv in enumerate(me.skin_vertices[0].data):
        sv.radius = (r[i], r[i])
    me.skin_vertices[0].data[0].use_root = True
    sub = ob.modifiers.new("Halus", "SUBSURF")
    sub.levels, sub.render_levels = 0, 1
    ob.data.materials.append(bahan_kulit(f"kulit_{seed}"))
    # daun v3: di ujung DAN sepanjang 3 ruas terakhir ranting, condong keluar dari pusat tajuk
    ujung = [i for i in range(len(node)) if not anak[i]]
    pusat = Vector((0, 0, p["tinggi_tajuk"]))
    lv, lf = [], []
    for i in (i for i in range(len(node)) if ke_ujung[i] <= 3):
        n_daun = p["daun_per_ujung"] if ke_ujung[i] == 0 else max(2, p["daun_per_ujung"] // 3)
        for _ in range(n_daun):
            c = node[i] + off + Vector((rng.uniform(-.3, .3), rng.uniform(-.3, .3), rng.uniform(-.25, .25)))
            keluar = (node[i] - pusat).normalized()
            u = (keluar * 0.7 + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-.4, .2)))).normalized()
            w = u.cross(Vector((0, 0, 1))).normalized() if abs(u.z) < .95 else Vector((1, 0, 0))
            L, W = p["ukuran_daun"], p["ukuran_daun"] * .5
            b = len(lv)
            lv += [c - u * L / 2 - w * W / 2, c + u * L / 2 - w * W / 2, c + u * L / 2 + w * W / 2, c - u * L / 2 + w * W / 2]
            lf.append((b, b + 1, b + 2, b + 3))
    dm = bpy.data.meshes.new(f"daun_{nama_preset}_{seed}")
    dm.from_pydata(lv, [], lf)
    uvl = dm.uv_layers.new(name="UVMap")
    sudut = ((0, 0), (1, 0), (1, 1), (0, 1))
    for poly in dm.polygons:
        for k, li in enumerate(poly.loop_indices):
            uvl.data[li].uv = sudut[k]
    var = dm.attributes.new("variasi", "FLOAT", "FACE")
    var.data.foreach_set("value", [rng.random() * 0.8 for _ in lf])
    do = bpy.data.objects.new(dm.name, dm)
    bpy.context.collection.objects.link(do)
    g = p["warna_daun"]
    do.data.materials.append(bahan_daun(f"daun_{seed}", tuple(x * 0.6 for x in g), (g[0] * 2.2, g[1] * 1.5, g[2] * 1.2)))
    kdq = kdtree.KDTree(len(node))
    for i, v in enumerate(node):
        kdq.insert(v, i)
    kdq.balance()
    tumpuk = sum(1 for v in node if len(kdq.find_range(v, 0.01)) > 1)
    vox = {}
    for v in lv[::4]:
        k = (int(v.x // .5), int(v.y // .5), int(v.z // .5))
        vox[k] = vox.get(k, 0) + 1
    isi = sorted(vox.values())
    median = isi[len(isi) // 2]
    zs = [v.z for v in node]
    xy = max(math.hypot(v.x, v.y) for v in node)
    return {"pohon": f"{nama_preset} seed {seed}", "titik_cabang": len(node), "ujung_ranting": len(ujung),
            "daun": len(lf), "tinggi_m": round(max(zs) + p["ukuran_daun"], 2), "lebar_tajuk_m": round(2 * xy, 2),
            "radius_batang_m": p["radius_batang"],
            "QC_titik_menumpuk": tumpuk, "QC_gumpalan_daun_maks_x_median": round(isi[-1] / median, 1),
            "QC_daun_di_bawah_tanah": sum(1 for v in lv[::4] if v.z < 0),
            "radius_cabang_min_max_m": [round(min(r), 3), round(max(r), 3)]}


def scene_contoh(out, render=True, sampel=128, res=(1600, 720)):
    """Scene 3 pohon (POHON) + tanah + matahari + langit, render pohon_render_v3.png + pohon.blend di `out`.
    Perangkat: GPU bila ada (OptiX -> CUDA -> ...), selain itu CPU (v3 lama memaksa OptiX)."""
    for o in list(bpy.data.objects):
        if o.type != "CAMERA":
            bpy.data.objects.remove(o)
    laporan = [bangun_pohon(*t) for t in POHON]

    bpy.ops.mesh.primitive_plane_add(size=80)
    bpy.context.active_object.data.materials.append(bahan("tanah", (0.16, 0.20, 0.10), 0.95))
    sun = bpy.data.objects.new("Matahari", bpy.data.lights.new("Matahari", "SUN"))
    sun.data.energy, sun.data.angle = 4.0, math.radians(3)
    sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    bpy.context.collection.objects.link(sun)
    w = bpy.context.scene.world
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value, bg.inputs[1].default_value = (0.55, 0.70, 0.95, 1), 0.9

    cam = bpy.context.scene.camera
    cam.location = (0, -30, 6.5)
    cam.rotation_euler = (math.radians(86), 0, 0)
    cam.data.lens = 35

    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = sampel
    sc.cycles.transparent_max_bounces = 48  # daun beralfa bertumpuk: cegah daun jadi hitam
    pilih_perangkat()
    sc.render.resolution_x, sc.render.resolution_y = res
    os.makedirs(out, exist_ok=True)
    if render:
        sc.render.filepath = os.path.join(os.path.abspath(out), "pohon_render_v3.png")  # C-10
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(out), "pohon.blend"))
    print("LAPORAN " + json.dumps(laporan, ensure_ascii=False))
    print("STAT", STAT)
    return laporan
