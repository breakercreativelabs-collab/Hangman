"""Uji verbs + uji negatif QC product shot (QC harus GAGAL pada scene yang sengaja dirusak).

  blender -b --factory-startup -P blender_cli.py -- product_shot uji [--out <folder>]
Kode keluar 1 jika ada uji gagal. Ringkasan ditulis ke <out>/uji_verbs.json (bawaan artefak/uji/product_shot).
"""
import math
import os
import tempfile

import bpy
from mathutils import Matrix, Vector

from ...inti import io, lembar
from ...inti.material import bsdf
from ...inti.qc import Pencatat
from ...inti.render import KUALITAS, atur_render, pilih_perangkat
from ...inti.scene import control, koleksi, objek_produk, root, siapkan_scene, titik_produk
from . import profil as pf, qc_gambar as qcg, qc_scene as qcs, spesifikasi
from .bingkai import kamera_rasio, render_variants
from .cahaya import PRESET_CAHAYA, studio_lighting
from .verbs import RASIO, WARNA, import_product, material_variant, normalize, turntable, warna_ke_linear

P = Pencatat()
TMP = ""


def uji(nama, kondisi, detail=""):
    P.uji(nama, kondisi, detail)


def scene_produk(nama="kaleng", easing="ease_in_out"):
    siapkan_scene()
    atur_render("mini")
    import_product("uji:" + nama)
    normalize()
    studio_lighting("softbox")
    turntable(4.0, easing)
    material_variant("merah")
    return kamera_rasio("1:1", 0.70)


def render_1x1(awalan):
    return render_variants(TMP, awalan, ["1:1"])[0]["file"]


def satu(daftar, id_):
    return next(c for c in daftar if c["id"] == id_)


def ekspor_berantakan(fmt):
    """Ekspor kaleng uji dalam mm, depan menghadap +X, tergeser & melayang: meniru file klien."""
    scene_produk("kaleng")
    obs = objek_produk()
    for o in obs:
        o.parent = None
        o.matrix_world = (Matrix.Translation((300, -200, 50)) @ Matrix.Rotation(math.pi / 2, 4, "Z")
                          @ Matrix.Scale(1000, 4))
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    path = os.path.join(TMP, "klien_kaleng." + fmt)
    if fmt == "obj":
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True, apply_modifiers=True)
    else:
        bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_format="GLB")
    return path


def _semua():
    print("== perangkat")
    uji("pilih_perangkat mengembalikan tipe yang dikenal", pilih_perangkat() in ("OPTIX", "CUDA", "HIP", "ONEAPI", "CPU"),
        pilih_perangkat())

    print("== import_product + normalize (file klien berantakan)")
    for fmt in ("obj", "glb"):
        path = ekspor_berantakan(fmt)
        siapkan_scene()
        atur_render("mini")
        import_product(path)
        root()["logo_u"], root()["logo_z"] = 0.5, 0.0575  # posisi logo di UV, info dari klien
        n = normalize(satuan="mm", depan="+X")
        d = n["dimensi_mm"]
        uji(f"{fmt}: dimensi nyata 66,2 x 66,2 x 115,2 mm", all(abs(x - y) < 0.1 for x, y in zip(d, (66.2, 66.2, 115.2))), d)
        p = titik_produk()
        uji(f"{fmt}: berdiri di lantai, origin di tengah dasar",
            abs(p[:, 2].min()) < 1e-5 and abs(p[:, 0].max() + p[:, 0].min()) < 1e-5 and abs(p[:, 1].max() + p[:, 1].min()) < 1e-5,
            f"z_min {p[:, 2].min():.2e}")
        studio_lighting("softbox")
        turntable(4.0)
        cam = kamera_rasio("1:1", 0.70)
        uji(f"{fmt}: depan menghadap kamera setelah normalize(depan=+X)", qcs.qc_depan(cam)[0]["lulus"], qcs.qc_depan(cam)[0]["nilai"])
        uji(f"{fmt}: semua objek di PRODUCT di bawah PRODUCT_ROOT",
            all(o.parent and o.parent.name in ("PRODUCT_ROOT",) for o in objek_produk()))
    siapkan_scene()
    import_product(path)
    root()["logo_u"], root()["logo_z"] = 0.5, 0.0575
    normalize(satuan="mm")  # sengaja lupa depan=+X
    studio_lighting("softbox")
    cam = kamera_rasio("1:1", 0.70)
    c = qcs.qc_depan(cam)[0]
    uji("NEGATIF QC-04: depan salah (lupa depan=+X) tertangkap", not c["lulus"], f"{c['nilai']} deg")

    cam = scene_produk("kaleng")
    for o in objek_produk():
        o.rotation_euler.z = math.pi
    c = qcs.qc_depan(cam)[0]
    uji("NEGATIF QC-04: label menghadap belakang (mesh diputar 180) tertangkap", not c["lulus"], f"{c['nilai']:.1f} deg")

    print("== studio_lighting")
    cam = scene_produk("kaleng")
    for p, isi in PRESET_CAHAYA.items():
        studio_lighting(p)
        lampu = list(koleksi("LIGHTS").objects)
        n = len(isi["lampu"]) + len(isi.get("refleksi", []))
        uji(f"preset {p}: {n} lampu di LIGHTS + backdrop", len(lampu) == n
            and len(koleksi("BACKDROP").objects) == 1)
    L = koleksi("LIGHTS").objects[0]
    energi = lambda: L.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.energy  # driver hidup di salinan depsgraph
    e1 = energi()
    control()["intensitas_cahaya"] = 0.5
    control().update_tag()
    bpy.context.view_layer.update()
    uji("CONTROL.intensitas_cahaya men-drive energi lampu", abs(energi() - e1 * 0.5) < 1e-4, f"{e1:.3f} -> {energi():.3f}")
    control()["intensitas_cahaya"] = 1.0

    print("== turntable")
    for e in ("ease_in_out", "cubic", "expo", "bezier"):
        scene_produk("kaleng", e)
        sc = bpy.context.scene
        sc.frame_set(sc.frame_end)
        z = root().parent.rotation_euler.z
        uji(f"{e}: 101 frame, 360 derajat, QC-06 lulus", sc.frame_end - sc.frame_start == 100 and abs(z - 2 * math.pi) < 1e-4
            and qcs.qc_keyframe()[0]["lulus"], qcs.qc_keyframe()[0]["nilai"])
    scene_produk("kaleng", "linear")
    c = qcs.qc_keyframe()[0]
    uji("NEGATIF QC-06: keyframe linear tertangkap", not c["lulus"], c["nilai"])

    print("== material_variant")
    cam = scene_produk("kaleng")
    material_variant("#1F4E9C")
    n = bpy.data.materials["LABEL_kaleng"].node_tree.nodes["WARNA_VARIAN"]
    uji("warna hex -> CONTROL + node WARNA_VARIAN (linear)",
        all(abs(x - y) < 1e-4 for x, y in zip(n.outputs[0].default_value[:3], warna_ke_linear("#1F4E9C")))
        and control()["warna_hex"] == "#1F4E9C")
    n.outputs[0].default_value = (1.0, 0.0, 0.0, 1)  # node sengaja dibiarkan merah: hanya driver yang boleh mengubahnya
    control()["warna_varian"] = [0.0, 1.0, 0.0]
    control().update_tag()
    c = qcg.qc_warna(render_1x1("driver_hijau"), cam, "#00FF00")
    uji("driver: CONTROL.warna_varian (tanpa sentuh node) -> render hijau", c["lulus"], c["konteks"][:60])
    material_variant("merah")
    f = render_1x1("warna_ok")
    c = qcg.qc_warna(f, cam, "#C8102E")
    uji("QC-10 lulus pada cahaya terkalibrasi", c["lulus"], c["nilai"])
    control()["intensitas_cahaya"] = 30.0  # setara energi v1 (sebelum kalibrasi): merah jadi pink
    f = render_1x1("warna_pudar")
    c = qcg.qc_warna(f, cam, "#C8102E")
    uji("NEGATIF QC-10: warna pudar/overexposed tertangkap", not c["lulus"], c["nilai"])
    control()["intensitas_cahaya"] = 1.0

    print("== regresi warna: semua palet x preset x produk (QC-10)")
    for prod in spesifikasi.PRODUK:
        cam = scene_produk(prod)
        for p in PRESET_CAHAYA:
            studio_lighting(p)
            gagal = []
            for w in WARNA:
                material_variant(w)
                c = qcg.qc_warna(render_1x1(f"pal_{prod}_{p}_{w}"), cam, WARNA[w])
                if not c["lulus"]:
                    gagal.append(f"{w} {c['nilai']:.2f}")
            uji(f"{prod} {p}: {len(WARNA)} warna palet terbaca", not gagal, ", ".join(gagal))

    cam = scene_produk("kaleng_slim")  # C-14: label logam 0,7 tanpa coat (sebelum perbaikan) harus tertangkap QC-10
    b = bsdf(bpy.data.materials["LABEL_kaleng_slim"])
    b.inputs["Metallic"].default_value, b.inputs["Coat Weight"].default_value = 0.7, 0.0
    studio_lighting("dramatis")
    bpy.data.objects.remove(bpy.data.objects["L_kartu_depan"])  # kondisi asli sebelum C-14 & C-15 (tanpa kartu pantulan)
    material_variant("putih")
    c = qcg.qc_warna(render_1x1("c14_logam"), cam, WARNA["putih"])
    uji("NEGATIF C-14: label kaleng metallic 0,7 (tanpa kartu C-15) -> putih abu di dramatis tertangkap", not c["lulus"],
        c["nilai"])

    print("== QC-12 logam tidak hitam pekat (C-15)")
    for prod in ("kaleng_slim", "kaleng"):
        cam = scene_produk(prod)
        studio_lighting("dramatis")
        c = qcg.qc_logam(render_1x1(f"c15_{prod}"), cam)
        uji(f"QC-12 {prod} dramatis (dengan kartu pantulan) lulus", c["lulus"], c["nilai"])
    cam = scene_produk("kaleng_slim")
    studio_lighting("dramatis")
    bpy.data.objects.remove(bpy.data.objects["L_kartu_depan"])  # preset dramatis sebelum C-15
    c = qcg.qc_logam(render_1x1("c15_tanpa_kartu"), cam)
    uji("NEGATIF QC-12: leher kaleng slim hitam pekat tanpa kartu pantulan tertangkap", not c["lulus"], c["nilai"])
    cam = scene_produk("kotak_susu")
    c = qcg.qc_logam(render_1x1("c15_tanpa_logam"), cam)
    uji("QC-12 n/a pada produk tanpa logam terlihat (kotak susu: foil di atas, tak terlihat)", c["lulus"], c["konteks"])

    print("== render_variants + bingkai")
    for prod in ("kaleng", "botol"):
        scene_produk(prod)
        for r in RASIO:
            cam = kamera_rasio(r, 0.70)
            hasil = qcs.qc_kamera(cam)
            uji(f"{prod} {r}: isi 0,70 +-0,01, tidak terpotong, kamera di luar",
                abs(satu(hasil, "QC-02")["nilai"] - 0.70) < 0.01 and all(x["lulus"] for x in hasil), satu(hasil, "QC-02")["nilai"])
    cam = scene_produk("kaleng")
    f = render_1x1("normal")
    uji("render_variants menulis PNG ukuran mini", os.path.isfile(f) and tuple(bpy.data.images.load(f).size) == (180, 180))
    rel = os.path.relpath(os.path.join(TMP, "sheet_rel.png"))  # C-10: path relatif dulu gagal senyap
    lembar.buat([("UJI", [(f, "UJI", True)])], rel, "UJI")
    uji("C-10: contact sheet tertulis walau path relatif", os.path.isfile(os.path.abspath(rel)), rel)
    c = qcg.qc_histogram(f, cam)
    uji("QC-05 lulus pada frame normal", c["lulus"], c["nilai"]["luma_rata"])
    cam.location = cam.location * 0.55 + Vector((0, 0, 0.026))
    hasil = qcs.qc_kamera(cam)
    uji("NEGATIF QC-02/03: kamera terlalu dekat -> terpotong", not satu(hasil, "QC-03")["lulus"] and not satu(hasil, "QC-02")["lulus"],
        satu(hasil, "QC-03")["nilai"])
    cam.location = Vector((0, -3.0, 0.4))
    uji("NEGATIF QC-02: kamera terlalu jauh -> produk kecil", not satu(qcs.qc_kamera(cam), "QC-02")["lulus"])
    cam.location = Vector((0, 0, 0.05))
    uji("NEGATIF QC-08: kamera di dalam produk", not satu(qcs.qc_kamera(cam), "QC-08")["lulus"])

    print("== QC-01 kontak lantai")
    for dz, kata in ((0.005, "melayang"), (-0.005, "tenggelam")):
        scene_produk("botol")
        root().location.z = dz
        c = qcs.qc_kontak_lantai()
        uji(f"NEGATIF QC-01: produk {kata} 5 mm tertangkap", not c["lulus"] and kata in c["konteks"], c["nilai"])
    scene_produk("botol")
    uji("QC-01 lulus setelah normalize", qcs.qc_kontak_lantai()["lulus"])

    print("== QC-05 frame gelap / kosong")
    cam = scene_produk("kaleng")
    control()["intensitas_cahaya"] = 0.0
    bpy.context.scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.0
    c = qcg.qc_histogram(render_1x1("gelap"), cam)
    uji("NEGATIF QC-05: frame gelap tertangkap", not c["lulus"], c["nilai"]["luma_rata"])
    cam = scene_produk("kaleng")
    for o in objek_produk():
        for k in ("camera", "diffuse", "glossy", "transmission", "volume_scatter", "shadow"):
            setattr(o, "visible_" + k, False)
    c = qcg.qc_histogram(render_1x1("kosong"), cam)
    uji("NEGATIF QC-05: frame kosong (produk tak terlihat) tertangkap", not c["lulus"], c["nilai"]["kontras_produk"])

    print("== QC-07 dimensi, QC-09 standar")
    scene_produk("botol")
    uji("QC-07 botol sesuai spec", all(c["lulus"] for c in qcs.qc_dimensi()), [c["nilai"] for c in qcs.qc_dimensi()])
    root().scale = (1.05, 1.05, 1.05)
    uji("NEGATIF QC-07: skala salah 5% tertangkap", not all(c["lulus"] for c in qcs.qc_dimensi()))
    scene_produk("kaleng")
    uji("QC-09 standar .blend lengkap", qcs.qc_standar()[0]["lulus"])
    del control()["easing"]
    uji("NEGATIF QC-09: property CONTROL hilang tertangkap", not qcs.qc_standar()[0]["lulus"], qcs.qc_standar()[0]["konteks"])

    print("== QC-11 kaca berongga (C-11), tab kaleng (C-12)")
    scene_produk("botol")
    c = qcs.qc_kaca()
    uji("QC-11 botol uji berongga lulus (cairan IOR 1,33 tidak dicek)", len(c) == 1 and c[0]["lulus"],
        c[0]["konteks"] if c else "tidak ada objek kaca")
    kaca = bpy.data.objects["botol_kaca"]
    mat = kaca.data.materials[0]
    kaca.data = pf.putar_profil("botol_pejal", pf.profil_botol(spesifikasi.SPEC["botol"]))
    kaca.data.materials.append(mat)
    c = qcs.qc_kaca()
    uji("NEGATIF QC-11: botol kaca pejal tertangkap", len(c) == 1 and not c[0]["lulus"], c[0]["nilai"] if c else "-")
    scene_produk("kaleng")
    H = spesifikasi.SPEC["kaleng"]["tinggi_mm"] / 1000
    zs = [z for n in ("kaleng_tab", "kaleng_rivet") for z in (bpy.data.objects[n].matrix_world @ v.co for v in
          bpy.data.objects[n].data.vertices)]
    uji("C-12: tab + rivet ada di panel tutup, di bawah bibir kaleng",
        zs and min(v.z for v in zs) > H - 0.0062 and max(v.z for v in zs) < H, f"{min(v.z for v in zs) * 1000:.2f}-"
        f"{max(v.z for v in zs) * 1000:.2f} mm")

    print("== kurikulum Tugas 4: 5 produk baru (QC scene), QC-07 kotak/pipih, QC-11 jar/PET")
    for prod in spesifikasi.BARU:
        cam = scene_produk(prod)
        c = qcs.qc_scene([cam])
        uji(f"{prod}: QC scene lulus (01/02/03/04/06/07/08/09/11)", all(x["lulus"] for x in c),
            [x["id"] for x in c if not x["lulus"]] or list(root()["dimensi_mm"]))
    scene_produk("kotak_susu")
    for o in objek_produk():  # mesh diputar 90 derajat: lebar dan tebal tertukar (depan salah)
        o.data.transform(Matrix.Rotation(math.pi / 2, 4, "Z"))
    c = [x for x in qcs.qc_dimensi() if not x["lulus"]]
    uji("NEGATIF QC-07: kotak diputar 90 derajat (lebar/tebal tertukar) tertangkap",
        {x["nama"] for x in c} == {"selisih_lebar_mm", "selisih_tebal_mm"}, [x["nilai"] for x in c])
    scene_produk("tube")
    root().scale = (1.0, 1.05, 1.0)  # tube 5% lebih tebal
    c = [x for x in qcs.qc_dimensi() if not x["lulus"]]
    uji("NEGATIF QC-07: tube tebal salah 5% tertangkap", [x["nama"] for x in c] == ["selisih_tebal_mm"], [x["nilai"] for x in c])
    s = spesifikasi.SPEC["tube"]
    scene_produk("tube")
    p = titik_produk()
    seal = p[p[:, 2] > (s["tinggi_mm"] - 1.0) / 1000]
    uji("tube: ujung atas dipipihkan (tebal seal <= 1,2 mm, lebar = setengah keliling)",
        (seal[:, 1].max() - seal[:, 1].min()) * 1000 <= s["seal_tebal_mm"] + 1e-6
        and abs((seal[:, 0].max() - seal[:, 0].min()) * 1000 - s["lebar_mm"]) < 0.01,
        f"{(seal[:, 1].max() - seal[:, 1].min()) * 1000:.2f} x {(seal[:, 0].max() - seal[:, 0].min()) * 1000:.2f} mm")


    def lebar_logo_mm(me, z_mm, setengah=0.42 / (2 * math.pi) / 1):
        """Lebar fisik logo (mm, sepanjang permukaan) di cincin vertex setinggi z: busur dengan |u - 0,5| < setengah."""
        u = {}
        for lp, d in zip(me.loops, me.uv_layers.active.data):
            u.setdefault(lp.vertex_index, d.uv.x)
        ring = sorted((v for v in me.vertices if abs(v.co.z * 1000 - z_mm) < 1e-3 and v.co.xy.length > 1e-6),
                      key=lambda v: math.atan2(v.co.x, -v.co.y))
        di = [v for v in ring if abs(u[v.index] - 0.5) < setengah]
        return sum((a.co - b.co).length for a, b in zip(di, di[1:])) * 1000


    s = spesifikasi.SPEC["tube"]
    z0, z1 = s["logo_mm"]
    zs = [z for _, z in pf.profil_tube(s) if z0 <= z <= z1]
    for busur in (True, False):
        me = pf.putar_profil("tube_uv", pf.profil_tube(s), penampang=pf.penampang_tube(s),
                                     uv_busur=busur)
        l0, l1 = lebar_logo_mm(me, zs[0]), lebar_logo_mm(me, zs[-1])
        r = max(l0, l1) / min(l0, l1)
        if busur:
            uji("C-13: logo tube persegi (lebar maks/min bawah-atas logo <= 1,10)", r <= 1.10, f"{l0:.1f} -> {l1:.1f} mm")
        else:
            uji("NEGATIF C-13: UV per sudut membuat logo tube trapesium (> 1,10)", r > 1.10, f"{l0:.1f} -> {l1:.1f} mm")
    for prod, ob_kaca, luar in (("jar_selai", "jar_kaca", lambda s: pf.profil_jar(s)[0]),
                                ("botol_pet", "pet_badan", lambda s: pf.profil_pet(s)[0])):
        scene_produk(prod)
        kaca = bpy.data.objects[ob_kaca]
        mat = kaca.data.materials[0]
        profil = luar(spesifikasi.SPEC[prod])
        kaca.data = pf.putar_profil(ob_kaca + "_pejal", profil + [(0, profil[-1][1])])
        kaca.data.materials.append(mat)
        c = qcs.qc_kaca()
        uji(f"NEGATIF QC-11: {prod} pejal tertangkap", len(c) == 1 and not c[0]["lulus"], c[0]["nilai"] if c else "-")
    for prod, isi, wadah in (("jar_selai", "jar_isi", "jar_kaca"), ("botol_pet", "pet_air", "pet_badan")):
        scene_produk(prod)
        dg = bpy.context.evaluated_depsgraph_get()
        w = bpy.data.objects[wadah]
        vi = [bpy.data.objects[isi].matrix_world @ v.co for v in bpy.data.objects[isi].data.vertices]
        keluar = 0
        for v in vi[::7]:  # sinar horizontal dari titik isi ke luar: harus menembus dinding dalam + luar (2 permukaan)
            if v.x ** 2 + v.y ** 2 < 1e-8:
                continue
            arah = Vector((v.x, v.y, 0)).normalized()
            n, asal = 0, v
            for _ in range(4):
                ok, loc, *_ = w.ray_cast(w.matrix_world.inverted() @ asal, arah, depsgraph=dg)
                if not ok:
                    break
                n, asal = n + 1, w.matrix_world @ loc + arah * 1e-5
            keluar += n != 2
        uji(f"{prod}: isi berada di dalam rongga wadah (tidak menembus dinding)", keluar == 0, f"{keluar} titik bermasalah")


def main(argv):
    global P, TMP
    out = os.path.abspath(io.opsi(argv, dict(out=io.artefak("uji", "product_shot")))["out"])
    TMP = tempfile.mkdtemp(prefix="ps_uji_")
    KUALITAS["mini"] = dict(skala=1 / 6, sampel=8)  # render uji 180-320 px
    P = Pencatat()
    _semua()
    print(f"UJI {'LULUS' if P.semua_lulus else 'GAGAL'} {P.lulus}/{len(P.hasil)} ({P.durasi:.0f} s)")
    P.tulis(os.path.join(out, "uji_verbs.json"), blender=bpy.app.version_string)
    return 0 if P.semua_lulus else 1
