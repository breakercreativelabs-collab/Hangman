"""Product shot verb tests + negative QC tests (QC must FAIL on deliberately broken scenes).

  blender -b --factory-startup -P blender_cli.py -- product_shot test [--out <folder>]
Exit code 1 if any test failed. Summary is written to <out>/test_verbs.json (default output/tests/product_shot).
"""
import math
import os
import tempfile

import bpy
from mathutils import Matrix, Vector

from ...core import io, sheets
from ...core.material import bsdf
from ...core.qc import Logger
from ...core.render import QUALITY, setup_render, select_device
from ...core.scene import control, collection, product_object, root, prepare_scene, product_points
from . import profile as pf, qc_image as qcg, qc_scene as qcs, specification
from .framing import ratio_camera, render_variants
from .light import LIGHT_PRESETS, studio_lighting
from .verbs import RATIO, COLOR, import_product, material_variant, normalize, turntable, color_to_linear

P = Logger()
TMP = ""


def test(name, condition, detail=""):
    P.test(name, condition, detail)


def product_scene(name="can", easing="ease_in_out"):
    prepare_scene()
    setup_render("mini")
    import_product("sample:" + name)
    normalize()
    studio_lighting("softbox")
    turntable(4.0, easing)
    material_variant("red")
    return ratio_camera("1:1", 0.70)


def render_1x1(prefix):
    return render_variants(TMP, prefix, ["1:1"])[0]["file"]


def one(entries, id_):
    return next(c for c in entries if c["id"] == id_)


def messy_export(fmt):
    """Export the test can in mm, front facing +X, offset & floating: mimics a client file."""
    product_scene("can")
    obs = product_object()
    for o in obs:
        o.parent = None
        o.matrix_world = (Matrix.Translation((300, -200, 50)) @ Matrix.Rotation(math.pi / 2, 4, "Z")
                          @ Matrix.Scale(1000, 4))
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    path = os.path.join(TMP, "client_can." + fmt)
    if fmt == "obj":
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True, apply_modifiers=True)
    else:
        bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_format="GLB")
    return path


def _all():
    print("== device")
    test("select_device returns a known value", select_device() in ("OPTIX", "CUDA", "HIP", "ONEAPI", "CPU"),
        select_device())

    print("== import_product + normalize (messy client file)")
    for fmt in ("obj", "glb"):
        path = messy_export(fmt)
        prepare_scene()
        setup_render("mini")
        import_product(path)
        root()["logo_u"], root()["logo_z"] = 0.5, 0.0575  # logo position in UV, provided by the client
        n = normalize(unit="mm", front="+X")
        d = n["dimension_mm"]
        test(f"{fmt}: real dimensions 66.2 x 66.2 x 115.2 mm", all(abs(x - y) < 0.1 for x, y in zip(d, (66.2, 66.2, 115.2))), d)
        p = product_points()
        test(f"{fmt}: stands on the floor, origin at bottom center",
            abs(p[:, 2].min()) < 1e-5 and abs(p[:, 0].max() + p[:, 0].min()) < 1e-5 and abs(p[:, 1].max() + p[:, 1].min()) < 1e-5,
            f"z_min {p[:, 2].min():.2e}")
        studio_lighting("softbox")
        turntable(4.0)
        cam = ratio_camera("1:1", 0.70)
        test(f"{fmt}: front faces camera after normalize(front=+X)", qcs.qc_front(cam)[0]["passed"], qcs.qc_front(cam)[0]["value"])
        test(f"{fmt}: all objects in PRODUCT under PRODUCT_ROOT",
            all(o.parent and o.parent.name in ("PRODUCT_ROOT",) for o in product_object()))
    prepare_scene()
    import_product(path)
    root()["logo_u"], root()["logo_z"] = 0.5, 0.0575
    normalize(unit="mm")  # deliberately forget front=+X
    studio_lighting("softbox")
    cam = ratio_camera("1:1", 0.70)
    c = qcs.qc_front(cam)[0]
    test("NEGATIVE QC-04: wrong front (forgot front=+X) caught", not c["passed"], f"{c['value']} deg")

    cam = product_scene("can")
    for o in product_object():
        o.rotation_euler.z = math.pi
    c = qcs.qc_front(cam)[0]
    test("NEGATIVE QC-04: label facing back (mesh rotated 180) caught", not c["passed"], f"{c['value']:.1f} deg")

    print("== studio_lighting")
    cam = product_scene("can")
    for p, contents in LIGHT_PRESETS.items():
        studio_lighting(p)
        lamp = list(collection("LIGHTS").objects)
        n = len(contents["lamp"]) + len(contents.get("reflection", []))
        test(f"preset {p}: {n} lamps in LIGHTS + backdrop", len(lamp) == n
            and len(collection("BACKDROP").objects) == 1)
    L = collection("LIGHTS").objects[0]
    energy = lambda: L.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.energy  # drivers live on the depsgraph copy
    e1 = energy()
    control()["light_intensity"] = 0.5
    control().update_tag()
    bpy.context.view_layer.update()
    test("CONTROL.light_intensity drives lamp energy", abs(energy() - e1 * 0.5) < 1e-4, f"{e1:.3f} -> {energy():.3f}")
    control()["light_intensity"] = 1.0

    print("== turntable")
    for e in ("ease_in_out", "cubic", "expo", "bezier"):
        product_scene("can", e)
        sc = bpy.context.scene
        sc.frame_set(sc.frame_end)
        z = root().parent.rotation_euler.z
        test(f"{e}: 101 frames, 360 degrees, QC-06 passes", sc.frame_end - sc.frame_start == 100 and abs(z - 2 * math.pi) < 1e-4
            and qcs.qc_keyframe()[0]["passed"], qcs.qc_keyframe()[0]["value"])
    product_scene("can", "linear")
    c = qcs.qc_keyframe()[0]
    test("NEGATIVE QC-06: keyframe linear caught", not c["passed"], c["value"])

    print("== material_variant")
    cam = product_scene("can")
    material_variant("#1F4E9C")
    n = bpy.data.materials["LABEL_can"].node_tree.nodes["COLOR_VARIANT"]
    test("color hex -> CONTROL + node COLOR_VARIANT (linear)",
        all(abs(x - y) < 1e-4 for x, y in zip(n.outputs[0].default_value[:3], color_to_linear("#1F4E9C")))
        and control()["hex_color"] == "#1F4E9C")
    n.outputs[0].default_value = (1.0, 0.0, 0.0, 1)  # node deliberately left red: only the driver may change it
    control()["variant_color"] = [0.0, 1.0, 0.0]
    control().update_tag()
    c = qcg.qc_color(render_1x1("green_driver"), cam, "#00FF00")
    test("driver: CONTROL.variant_color (node untouched) -> green render", c["passed"], c["context"][:60])
    material_variant("red")
    f = render_1x1("color_ok")
    c = qcg.qc_color(f, cam, "#C8102E")
    test("QC-10 passes with calibrated lighting", c["passed"], c["value"])
    control()["light_intensity"] = 30.0  # equals v1 energy (before calibration): red turns pink
    f = render_1x1("faded_color")
    c = qcg.qc_color(f, cam, "#C8102E")
    test("NEGATIVE QC-10: washed-out/overexposed color caught", not c["passed"], c["value"])
    control()["light_intensity"] = 1.0

    print("== color regression: full palette x preset x product (QC-10)")
    for prod in specification.PRODUCT:
        cam = product_scene(prod)
        for p in LIGHT_PRESETS:
            studio_lighting(p)
            failed = []
            for w in COLOR:
                material_variant(w)
                c = qcg.qc_color(render_1x1(f"pal_{prod}_{p}_{w}"), cam, COLOR[w])
                if not c["passed"]:
                    failed.append(f"{w} {c['value']:.2f}")
            test(f"{prod} {p}: {len(COLOR)} palette colors readable", not failed, ", ".join(failed))

    cam = product_scene("slim_can")  # C-14: label metallic 0.7 without coat (before the fix) must be caught by QC-10
    b = bsdf(bpy.data.materials["LABEL_slim_can"])
    b.inputs["Metallic"].default_value, b.inputs["Coat Weight"].default_value = 0.7, 0.0
    studio_lighting("dramatic")
    bpy.data.objects.remove(bpy.data.objects["L_front_card"])  # original condition before C-14 & C-15 (no reflection card)
    material_variant("white")
    c = qcg.qc_color(render_1x1("c14_metal"), cam, COLOR["white"])
    test("NEGATIVE C-14: can label metallic 0.7 (no C-15 card) -> grey white in dramatic caught", not c["passed"],
        c["value"])

    print("== QC-12 metal not pitch black (C-15)")
    for prod in ("slim_can", "can"):
        cam = product_scene(prod)
        studio_lighting("dramatic")
        c = qcg.qc_metal(render_1x1(f"c15_{prod}"), cam)
        test(f"QC-12 {prod} dramatic (with reflection card) passes", c["passed"], c["value"])
    cam = product_scene("slim_can")
    studio_lighting("dramatic")
    bpy.data.objects.remove(bpy.data.objects["L_front_card"])  # dramatic preset before C-15
    c = qcg.qc_metal(render_1x1("c15_without_card"), cam)
    test("NEGATIVE QC-12: slim can neck pitch black without reflection card caught", not c["passed"], c["value"])
    cam = product_scene("milk_carton")
    c = qcg.qc_metal(render_1x1("c15_without_metal"), cam)
    test("QC-12 n/a on product without visible metal (milk carton: foil on top, not visible)", c["passed"], c["context"])

    print("== render_variants + framing")
    for prod in ("can", "bottle"):
        product_scene(prod)
        for r in RATIO:
            cam = ratio_camera(r, 0.70)
            result = qcs.qc_camera(cam)
            test(f"{prod} {r}: fill 0.70 +-0.01, not clipped, camera outside",
                abs(one(result, "QC-02")["value"] - 0.70) < 0.01 and all(x["passed"] for x in result), one(result, "QC-02")["value"])
    cam = product_scene("can")
    f = render_1x1("normal")
    test("render_variants writes a mini-size PNG", os.path.isfile(f) and tuple(bpy.data.images.load(f).size) == (180, 180))
    rel = os.path.relpath(os.path.join(TMP, "sheet_rel.png"))  # C-10: relative paths used to fail silently
    sheets.make([("TEST", [(f, "TEST", True)])], rel, "TEST")
    test("C-10: contact sheet written even with relative path", os.path.isfile(os.path.abspath(rel)), rel)
    c = qcg.qc_histogram(f, cam)
    test("QC-05 passes on a normal frame", c["passed"], c["value"]["mean_luma"])
    cam.location = cam.location * 0.55 + Vector((0, 0, 0.026))
    result = qcs.qc_camera(cam)
    test("NEGATIVE QC-02/03: camera too close -> clipped", not one(result, "QC-03")["passed"] and not one(result, "QC-02")["passed"],
        one(result, "QC-03")["value"])
    cam.location = Vector((0, -3.0, 0.4))
    test("NEGATIVE QC-02: camera too far -> product small", not one(qcs.qc_camera(cam), "QC-02")["passed"])
    cam.location = Vector((0, 0, 0.05))
    test("NEGATIVE QC-08: camera inside product", not one(qcs.qc_camera(cam), "QC-08")["passed"])

    print("== QC-01 floor contact")
    for dz, word in ((0.005, "floating"), (-0.005, "sunk")):
        product_scene("bottle")
        root().location.z = dz
        c = qcs.qc_floor_contact()
        test(f"NEGATIVE QC-01: product {word} 5 mm caught", not c["passed"] and word in c["context"], c["value"])
    product_scene("bottle")
    test("QC-01 passes after normalize", qcs.qc_floor_contact()["passed"])

    print("== QC-05 dark / empty frame")
    cam = product_scene("can")
    control()["light_intensity"] = 0.0
    bpy.context.scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.0
    c = qcg.qc_histogram(render_1x1("dark"), cam)
    test("NEGATIVE QC-05: dark frame caught", not c["passed"], c["value"]["mean_luma"])
    cam = product_scene("can")
    for o in product_object():
        for k in ("camera", "diffuse", "glossy", "transmission", "volume_scatter", "shadow"):
            setattr(o, "visible_" + k, False)
    c = qcg.qc_histogram(render_1x1("empty"), cam)
    test("NEGATIVE QC-05: empty frame (product hidden) caught", not c["passed"], c["value"]["product_contrast"])

    print("== QC-07 dimensions, QC-09 standard")
    product_scene("bottle")
    test("QC-07 bottle matches spec", all(c["passed"] for c in qcs.qc_dimension()), [c["value"] for c in qcs.qc_dimension()])
    root().scale = (1.05, 1.05, 1.05)
    test("NEGATIVE QC-07: scale off by 5% caught", not all(c["passed"] for c in qcs.qc_dimension()))
    product_scene("can")
    test("QC-09 standard .blend complete", qcs.qc_standard()[0]["passed"])
    del control()["easing"]
    test("NEGATIVE QC-09: missing CONTROL property caught", not qcs.qc_standard()[0]["passed"], qcs.qc_standard()[0]["context"])

    print("== QC-11 hollow glass (C-11), can tab (C-12)")
    product_scene("bottle")
    c = qcs.qc_glass()
    test("QC-11 hollow test bottle passes (liquid IOR 1.33 not checked)", len(c) == 1 and c[0]["passed"],
        c[0]["context"] if c else "no glass object")
    glass = bpy.data.objects["glass_bottle"]
    mat = glass.data.materials[0]
    glass.data = pf.lathe_profile("solid_bottle", pf.bottle_profile(specification.SPEC["bottle"]))
    glass.data.materials.append(mat)
    c = qcs.qc_glass()
    test("NEGATIVE QC-11: solid glass bottle caught", len(c) == 1 and not c[0]["passed"], c[0]["value"] if c else "-")
    product_scene("can")
    H = specification.SPEC["can"]["height_mm"] / 1000
    zs = [z for n in ("can_tab", "can_rivet") for z in (bpy.data.objects[n].matrix_world @ v.co for v in
          bpy.data.objects[n].data.vertices)]
    test("C-12: tab + rivet on the lid panel, below the can rim",
        zs and min(v.z for v in zs) > H - 0.0062 and max(v.z for v in zs) < H, f"{min(v.z for v in zs) * 1000:.2f}-"
        f"{max(v.z for v in zs) * 1000:.2f} mm")

    print("== Task 4 curriculum: 5 new products (scene QC), QC-07 box/flat, QC-11 jar/PET")
    for prod in specification.NEW:
        cam = product_scene(prod)
        c = qcs.qc_scene([cam])
        test(f"{prod}: scene QC passes (01/02/03/04/06/07/08/09/11)", all(x["passed"] for x in c),
            [x["id"] for x in c if not x["passed"]] or list(root()["dimension_mm"]))
    product_scene("milk_carton")
    for o in product_object():  # mesh rotated 90 degrees: width and thickness swapped (wrong front)
        o.data.transform(Matrix.Rotation(math.pi / 2, 4, "Z"))
    c = [x for x in qcs.qc_dimension() if not x["passed"]]
    test("NEGATIVE QC-07: box rotated 90 degrees (width/thickness swapped) caught",
        {x["name"] for x in c} == {"width_delta_mm", "thickness_delta_mm"}, [x["value"] for x in c])
    product_scene("tube")
    root().scale = (1.0, 1.05, 1.0)  # tube 5% thicker
    c = [x for x in qcs.qc_dimension() if not x["passed"]]
    test("NEGATIVE QC-07: tube thickness off by 5% caught", [x["name"] for x in c] == ["thickness_delta_mm"], [x["value"] for x in c])
    s = specification.SPEC["tube"]
    product_scene("tube")
    p = product_points()
    seal = p[p[:, 2] > (s["height_mm"] - 1.0) / 1000]
    test("tube: top end flattened (seal thickness <= 1.2 mm, width = half the perimeter)",
        (seal[:, 1].max() - seal[:, 1].min()) * 1000 <= s["seal_thickness_mm"] + 1e-6
        and abs((seal[:, 0].max() - seal[:, 0].min()) * 1000 - s["width_mm"]) < 0.01,
        f"{(seal[:, 1].max() - seal[:, 1].min()) * 1000:.2f} x {(seal[:, 0].max() - seal[:, 0].min()) * 1000:.2f} mm")


    def logo_width_mm(me, z_mm, half_size=0.42 / (2 * math.pi) / 1):
        """Physical logo width (mm, along the surface) on the vertex ring at height z: arc where |u - 0.5| < half_size."""
        u = {}
        for lp, d in zip(me.loops, me.uv_layers.active.data):
            u.setdefault(lp.vertex_index, d.uv.x)
        ring = sorted((v for v in me.vertices if abs(v.co.z * 1000 - z_mm) < 1e-3 and v.co.xy.length > 1e-6),
                      key=lambda v: math.atan2(v.co.x, -v.co.y))
        di = [v for v in ring if abs(u[v.index] - 0.5) < half_size]
        return sum((a.co - b.co).length for a, b in zip(di, di[1:])) * 1000


    s = specification.SPEC["tube"]
    z0, z1 = s["logo_mm"]
    zs = [z for _, z in pf.tube_profile(s) if z0 <= z <= z1]
    for arc in (True, False):
        me = pf.lathe_profile("tube_uv", pf.tube_profile(s), section=pf.tube_section(s),
                                     uv_arc=arc)
        l0, l1 = logo_width_mm(me, zs[0]), logo_width_mm(me, zs[-1])
        r = max(l0, l1) / min(l0, l1)
        if arc:
            test("C-13: tube logo is rectangular (logo width max/min bottom-top <= 1.10)", r <= 1.10, f"{l0:.1f} -> {l1:.1f} mm")
        else:
            test("NEGATIVE C-13: UV per angle makes the tube logo trapezoidal (> 1.10)", r > 1.10, f"{l0:.1f} -> {l1:.1f} mm")
    for prod, ob_glass, outer in (("jam_jar", "jar_glass", lambda s: pf.jar_profile(s)[0]),
                                ("pet_bottle", "pet_body", lambda s: pf.pet_profile(s)[0])):
        product_scene(prod)
        glass = bpy.data.objects[ob_glass]
        mat = glass.data.materials[0]
        profile = outer(specification.SPEC[prod])
        glass.data = pf.lathe_profile(ob_glass + "_solid", profile + [(0, profile[-1][1])])
        glass.data.materials.append(mat)
        c = qcs.qc_glass()
        test(f"NEGATIVE QC-11: solid {prod} caught", len(c) == 1 and not c[0]["passed"], c[0]["value"] if c else "-")
    for prod, contents, container in (("jam_jar", "jar_fill", "jar_glass"), ("pet_bottle", "pet_water", "pet_body")):
        product_scene(prod)
        dg = bpy.context.evaluated_depsgraph_get()
        w = bpy.data.objects[container]
        vi = [bpy.data.objects[contents].matrix_world @ v.co for v in bpy.data.objects[contents].data.vertices]
        exit_code = 0
        for v in vi[::7]:  # horizontal ray from a contents point outward: must cross the inner + outer wall (2 surfaces)
            if v.x ** 2 + v.y ** 2 < 1e-8:
                continue
            direction = Vector((v.x, v.y, 0)).normalized()
            n, origin = 0, v
            for _ in range(4):
                ok, loc, *_ = w.ray_cast(w.matrix_world.inverted() @ origin, direction, depsgraph=dg)
                if not ok:
                    break
                n, origin = n + 1, w.matrix_world @ loc + direction * 1e-5
            exit_code += n != 2
        test(f"{prod}: contents sit inside the container cavity (do not cross the wall)", exit_code == 0, f"{exit_code} bad points")


def main(argv):
    global P, TMP
    out = os.path.abspath(io.options(argv, dict(out=io.artifact("test", "product_shot")))["out"])
    TMP = tempfile.mkdtemp(prefix="ps_test_")
    QUALITY["mini"] = dict(scale=1 / 6, sample=8)  # test renders 180-320 px
    P = Logger()
    _all()
    print(f"TEST {'PASS' if P.all_passed else 'FAIL'} {P.passed}/{len(P.result)} ({P.duration:.0f} s)")
    P.write(os.path.join(out, "test_verbs.json"), blender=bpy.app.version_string)
    return 0 if P.all_passed else 1
