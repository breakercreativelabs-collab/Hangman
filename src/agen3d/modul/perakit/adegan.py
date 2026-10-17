"""Bagian Blender perakit: mesh dari titik/quad, data mesh (mm), ekspor .blend/.glb, lembar kontak 5 tampak."""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from ...inti import kamera, lembar, material, render, scene, warna

MM = 0.001
TAMPAK = (  # (nama, azimut, elevasi, bahan, zoom, tinggi target / tinggi)  az 0 = dari -Y (moncong ke kanan)
    ("samping", 0, 4, "terang", 1.0, 0.48), ("depan", 90, 4, "terang", 1.0, 0.48),
    ("tiga perempat", 35, 18, "terang", 1.0, 0.48), ("belakang", -120, 14, "terang", 1.0, 0.48),
    ("wajah", 40, 12, "terang", 1.7, 0.70), ("hitam", -35, 18, "gelap", 1.0, 0.48))
BAHAN = {"terang": ("#7C776F", 0.55), "gelap": ("#1C1612", 0.30)}  # clay abu (baca bentuk) vs eboni satin


def bahan_kayu(nama, hex_terang, hex_gelap, skala=260.0, kasar=0.42):
    """Kayu berserat prosedural: cincin tahun searah Z (tampak sebagai serat tegak di sisi) + distorsi noise,
    warna ramp terang->gelap, bump halus. Skala dalam 1/m (koordinat objek)."""
    m = material.bahan(nama, warna.lin(hex_terang), kasar=kasar, **{"Coat Weight": 0.3, "Coat Roughness": 0.2})
    t, b = m.node_tree, material.bsdf(m)
    ko = material.simpul(t, "ShaderNodeTexCoord")
    gel = material.simpul(t, "ShaderNodeTexWave", wave_type="RINGS", rings_direction="Z", wave_profile="SIN")
    gel.inputs["Scale"].default_value, gel.inputs["Distortion"].default_value = skala, 4.5
    gel.inputs["Detail"].default_value, gel.inputs["Detail Scale"].default_value = 4.0, 1.5
    peta = material.simpul(t, "ShaderNodeMapping")
    peta.inputs["Scale"].default_value = (1.0, 1.0, 0.08)  # distorsi memanjang searah Z = serat tegak
    peta.inputs["Location"].default_value = (0.09, 0.03, 0.0)  # pusat cincin jauh di luar bidak = serat hampir sejajar
    t.links.new(ko.outputs["Object"], peta.inputs["Vector"])
    t.links.new(peta.outputs["Vector"], gel.inputs["Vector"])
    warna_serat = material.ramp(t, gel.outputs["Fac"], warna.lin(hex_terang), warna.lin(hex_gelap))
    warna_serat.node.color_ramp.elements[0].position = 0.6  # serat gelap tipis di atas kayu terang
    t.links.new(warna_serat, b.inputs["Base Color"])
    bump = material.simpul(t, "ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.12, 0.0002
    t.links.new(gel.outputs["Fac"], bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def objek_mesh(nama, titik_mm, quad, target_segitiga=None):
    scene.siapkan_scene()
    me = bpy.data.meshes.new(nama)
    me.from_pydata((np.asarray(titik_mm) * MM).tolist(), [], np.asarray(quad).tolist())
    me.validate()
    ob = bpy.data.objects.new(nama, me)
    scene.koleksi("PRODUCT").objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    n_seg = 2 * len(me.polygons)
    if target_segitiga and n_seg > target_segitiga:
        mod = ob.modifiers.new("decimate", "DECIMATE")
        mod.ratio = target_segitiga / n_seg
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def data_mesh(ob):
    """(titik mm Nx3, muka segitiga Mx3) dari mesh objek."""
    me = ob.data
    me.calc_loop_triangles()
    t = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", t)
    f = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", f)
    return t.reshape(-1, 3) / MM, f.reshape(-1, 3)


def ekspor(ob, out):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, "model.glb"), use_selection=True, export_apply=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "model.blend"))


def _studio(skala=1.0, lantai_z=0.0):
    """Studio clay: lantai + 3 lampu area. `skala` membesarkan jarak/ukuran lampu (energi x skala^2) untuk adegan
    lebih besar dari satu bidak (set di papan)."""
    w = bpy.context.scene.world or bpy.data.worlds.new("dunia")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.18, 0.18, 0.19, 1)
    bg.inputs["Strength"].default_value = 0.35
    bpy.context.scene.view_settings.exposure = -1.0  # rev 2: lampu terlalu terang -> kayu cokelat tampak peach
    bpy.ops.mesh.primitive_plane_add(size=4.0 * skala, location=(0, 0, lantai_z))
    lantai = bpy.context.active_object
    lantai.data.materials.append(material.bahan("lantai", warna.lin("#8A8C90"), kasar=0.6))
    for nama, lok, energi, ukuran in (("kunci", (-0.18, -0.22, 0.26), 9.0, 0.16),
                                      ("isi", (0.25, -0.12, 0.10), 3.0, 0.20),
                                      ("tepi", (0.05, 0.25, 0.22), 6.0, 0.10)):
        li = bpy.data.objects.new(nama, bpy.data.lights.new(nama, "AREA"))
        li.data.energy, li.data.size = energi * skala ** 2, ukuran * skala
        li.location = Vector(lok) * skala
        kamera.hadap(li, Vector((0, 0, 0.03)))
        scene.koleksi("LIGHTS").objects.link(li)


def pratinjau(ob, out, sampel=12, tampak=((35, 18),), r=None):
    """Render cepat (clay, 480x560, sampel rendah). Satu tampak -> pratinjau.png; beberapa tampak ([az, el], dari
    [objek] pratinjau) -> pratinjau.jpg berjajar. Untuk iterasi, bukan serah."""
    render.atur_render("uji")
    _studio()
    ob.data.materials.append(material.bahan("polos_pratinjau", warna.lin(BAHAN["terang"][0]), kasar=BAHAN["terang"][1]))
    zmax = max(v.co.z for v in ob.data.vertices)
    jarak = zmax * 0.62 / math.tan(math.radians(11.5))
    hasil = []
    for i, tp in enumerate(tampak):  # [az, el] atau [az, el, zoom, tinggi target / tinggi] (close-up wajah)
        az, el = tp[0], tp[1]
        zoom, ft = (tp[2], tp[3]) if len(tp) > 2 else (1.0, 0.48)
        target = Vector((0, 0, zmax * ft))
        cam = kamera.kamera(f"kam_pratinjau_{i}", target + kamera.arah(az, el) * jarak / zoom, (0, 0, 0), lensa=85)
        kamera.hadap(cam, target)
        nama = "pratinjau.png" if len(tampak) == 1 else f"pratinjau_{i}.png"
        hasil.append(render.render_gambar(cam, os.path.join(out, nama), 480, 560, sampel, False))
    if r:
        banding_3d(ob, r, out, sampel)
    if len(hasil) == 1:
        return hasil[0]
    path, _ = lembar.buat([("PRATINJAU", [(p, f"az {tp[0]}" + (f" x{tp[2]}" if len(tp) > 2 else ""), True)
                                          for p, tp in zip(hasil, tampak)])],
                          os.path.join(out, "pratinjau.jpg"), "PRATINJAU", tinggi_sel=420)
    return path


def lembar_kontak(ob, r, cek, out, sampel):
    """Render 5 tampak + rangkum ke lembar_kontak.jpg (bilah hijau/merah = QC keseluruhan)."""
    render.atur_render("uji")
    _studio()
    kayu = r.get("bahan", {})
    if kayu.get("jenis") == "kayu":
        bahan = {k: bahan_kayu(f"kayu_{k}", *kayu[k], skala=kayu.get("skala_serat", 260.0)) for k in ("terang", "gelap")}
    else:
        bahan = {k: material.bahan(f"polos_{k}", warna.lin(h), kasar=ks, **{"Coat Weight": 0.25})
                 for k, (h, ks) in BAHAN.items()}
    ob.data.materials.append(bahan["terang"])
    zmax = max(v.co.z for v in ob.data.vertices)
    jarak0 = zmax * 0.62 / math.tan(math.radians(11.5))
    lulus = all(c["lulus"] for c in cek)
    sel = []
    for nama, az, el, b, zoom, ft in TAMPAK:
        ob.data.materials[0] = bahan[b]
        target, jarak = Vector((0.007 * (zoom > 1), 0, zmax * ft)), jarak0 / zoom
        cam = kamera.kamera(f"kam_{nama}", target + kamera.arah(az, el) * jarak, (0, 0, 0), lensa=85)
        kamera.hadap(cam, target)
        p = render.render_gambar(cam, os.path.join(out, f"tampak_{nama.replace(' ', '_')}.png"), 520, 620, sampel,
                                 False)
        sel.append((p, nama, lulus))
    ob.data.materials[0] = bahan["terang"]
    for pb in r.get("pembanding", []):
        banding(ob, pb, out, sampel, zmax)
    ringkas = " ".join(f"{c['id']}:{c['nilai']}" for c in cek[:2])
    path, _ = lembar.buat([(f"QC {'LULUS' if lulus else 'GAGAL'} {ringkas} MM", sel)],
                          os.path.join(out, "lembar_kontak.jpg"), r["objek"]["nama"], tinggi_sel=380)
    return path


def banding(ob, pb, out, sampel, zmax):
    """Juri banding: gambar referensi hasil riset (klien/, tidak di repo) berdampingan dengan render model dari sudut
    kamera yang sama ([[pembanding]] az, el, lensa, isi = tinggi objek / tinggi gambar). Untuk menilai, bukan dijiplak."""
    from ...inti import io
    sumber = io.path_repo(pb["gambar"])
    if not os.path.isfile(sumber):
        print(f"  banding LEWAT: {pb['gambar']} tidak ada (referensi hanya di laptop/klien)")
        return None
    img = bpy.data.images.load(sumber, check_existing=False)
    w, h = img.size
    ref = os.path.join(out, f"ref_{pb['nama']}.png")
    img.filepath_raw, img.file_format = ref, "PNG"
    img.save()
    lensa = pb.get("lensa", 135.0)
    jarak = zmax / pb.get("isi", 0.88) * lensa / 36.0
    target = Vector((pb.get("geser_x_mm", 0.0) * MM, 0, zmax * 0.5))
    cam = kamera.kamera(f"kam_banding_{pb['nama']}", target + kamera.arah(pb["az"], pb["el"]) * jarak, (0, 0, 0),
                        lensa=lensa)
    kamera.hadap(cam, target)
    tinggi = 620
    lebar = int(round(tinggi * w / h))
    hasil = render.render_gambar(cam, os.path.join(out, f"model_{pb['nama']}.png"), lebar, tinggi, sampel, False)
    path, _ = lembar.buat([("REFERENSI RISET VS MODEL (SUDUT SAMA)", [(ref, "referensi", True), (hasil, "model", True)])],
                          os.path.join(out, f"banding_{pb['nama']}.jpg"), f"BANDING {pb['nama']}", tinggi_sel=620)
    print(f"  banding: {path}")
    return path


def muat_referensi_3d(ref, tinggi_mm):
    """Impor model 3D referensi hasil riset (glTF, klien/; tidak di repo), ambil satu objek, alas di titik asal,
    skala ke tinggi rancangan, putar Z (`putar_z`) agar moncong/arah depan = +X. Untuk menilai, bukan disalin."""
    from ...inti import io
    sumber = io.path_repo(ref["model"])
    if not os.path.isfile(sumber):
        print(f"  referensi 3D LEWAT: {ref['model']} tidak ada")
        return None
    sebelum = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=sumber)
    baru = [o for o in bpy.data.objects if o not in sebelum]
    target = next(o for o in baru if o.name == ref["objek"])
    for o in baru:
        if o is not target:
            bpy.data.objects.remove(o)
    me = target.data.copy()
    me.transform(target.matrix_world)
    target.matrix_world.identity()
    target.data = me
    t = np.array([v.co[:] for v in me.vertices])
    pusat = np.array([(t[:, 0].min() + t[:, 0].max()) / 2, (t[:, 1].min() + t[:, 1].max()) / 2, t[:, 2].min()])
    k = tinggi_mm * MM / (t[:, 2].max() - t[:, 2].min())
    a = math.radians(ref.get("putar_z", 0.0))
    c, s_ = math.cos(a), math.sin(a)
    for v in me.vertices:
        x, y, z = (np.array(v.co[:]) - pusat) * k
        v.co = (x * c - y * s_, x * s_ + y * c, z)
    target.data.materials.clear()
    for p in me.polygons:
        p.use_smooth = True
    return target


def banding_3d(ob, r, out, sampel=12):
    """Juri banding 3D: referensi 3D vs model, sudut kamera & bahan clay sama, baris atas referensi, bawah model."""
    ref = r.get("referensi_3d")
    obr = muat_referensi_3d(ref, r["objek"]["tinggi_mm"]) if ref else None
    if obr is None:
        return None
    obr.data.materials.append(ob.data.materials[0])
    zmax = max(v.co.z for v in ob.data.vertices)
    target = Vector((0, 0, zmax * 0.48))
    jarak = zmax * 0.62 / math.tan(math.radians(11.5))
    tampak = ref.get("tampak", [[0, 4], [35, 18], [90, 4], [180, 4], [-90, 4], [0, 89]])
    baris = []
    for judul, tampil, sembunyi in (("REFERENSI 3D RISET", obr, ob), ("MODEL", ob, obr)):
        tampil.hide_render, sembunyi.hide_render = False, True
        sel = []
        for i, tp in enumerate(tampak):  # [az, el] atau [az, el, zoom, tinggi target / tinggi] (close-up)
            az, el = tp[0], tp[1]
            zoom, ft = (tp[2], tp[3]) if len(tp) > 2 else (1.0, 0.48)
            tgt = Vector((0, 0, zmax * ft))
            cam = kamera.kamera(f"kam_b3d_{i}", tgt + kamera.arah(az, el) * jarak / zoom, (0, 0, 0), lensa=85)
            kamera.hadap(cam, tgt)
            nama = f"b3d_{'ref' if tampil is obr else 'mdl'}_{i}.png"
            sel.append((render.render_gambar(cam, os.path.join(out, nama), 360, 420, sampel, False),
                        f"az {az} el {el}" + (f" x{zoom}" if zoom != 1.0 else ""), True))
        baris.append((judul, sel))
    ob.hide_render, obr.hide_render = False, True
    path, _ = lembar.buat(baris, os.path.join(out, "banding_3d.jpg"), "BANDING 3D: REFERENSI VS MODEL", tinggi_sel=300)
    print(f"  banding 3D: {path}")
    return path
