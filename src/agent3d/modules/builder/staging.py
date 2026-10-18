"""Blender side of the builder: mesh from points/quads, mesh data (mm), .blend/.glb export, 5-view contact sheet."""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from ...core import camera, sheets, material, render, scene, color

MM = 0.001
VIEWPOINTS = (  # (name, azimuth, elevation, material, zoom, target height / height)  az 0 = from -Y (muzzle to the right)
    ("side_view", 0, 4, "bright", 1.0, 0.48), ("front", 90, 4, "bright", 1.0, 0.48),
    ("three quarter", 35, 18, "bright", 1.0, 0.48), ("back", -120, 14, "bright", 1.0, 0.48),
    ("face", 40, 12, "bright", 1.7, 0.70), ("black", -35, 18, "dark", 1.0, 0.48))
MATERIAL = {"bright": ("#7C776F", 0.55), "dark": ("#1C1612", 0.30)}  # grey clay (to read the shape) vs satin ebony


def wood_material(name, bright_hex, dark_hex, scale=260.0, coarse=0.42):
    """Procedural grained wood: growth rings along Z (seen as vertical grain on the sides) + noise distortion,
    bright->dark color ramp, soft bump. Scale in 1/m (object coordinates)."""
    m = material.make_material(name, color.lin(bright_hex), coarse=coarse, **{"Coat Weight": 0.3, "Coat Roughness": 0.2})
    t, b = m.node_tree, material.bsdf(m)
    ko = material.new_node(t, "ShaderNodeTexCoord")
    wave_tex = material.new_node(t, "ShaderNodeTexWave", wave_type="RINGS", rings_direction="Z", wave_profile="SIN")
    wave_tex.inputs["Scale"].default_value, wave_tex.inputs["Distortion"].default_value = scale, 4.5
    wave_tex.inputs["Detail"].default_value, wave_tex.inputs["Detail Scale"].default_value = 4.0, 1.5
    mapping = material.new_node(t, "ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0, 1.0, 0.08)  # distortion stretched along Z = vertical grain
    mapping.inputs["Location"].default_value = (0.09, 0.03, 0.0)  # ring center far outside the piece = nearly parallel grain
    t.links.new(ko.outputs["Object"], mapping.inputs["Vector"])
    t.links.new(mapping.outputs["Vector"], wave_tex.inputs["Vector"])
    fiber_color = material.ramp(t, wave_tex.outputs["Fac"], color.lin(bright_hex), color.lin(dark_hex))
    fiber_color.node.color_ramp.elements[0].position = 0.6  # thin dark grain over bright wood
    t.links.new(fiber_color, b.inputs["Base Color"])
    bump = material.new_node(t, "ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.12, 0.0002
    t.links.new(wave_tex.outputs["Fac"], bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mesh_object(name, points_mm, quad, target_triangles=None):
    scene.prepare_scene()
    me = bpy.data.meshes.new(name)
    me.from_pydata((np.asarray(points_mm) * MM).tolist(), [], np.asarray(quad).tolist())
    me.validate()
    ob = bpy.data.objects.new(name, me)
    scene.collection("PRODUCT").objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    n_seg = 2 * len(me.polygons)
    if target_triangles and n_seg > target_triangles:
        mod = ob.modifiers.new("decimate", "DECIMATE")
        mod.ratio = target_triangles / n_seg
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def data_mesh(ob):
    """(points mm Nx3, triangle faces Mx3) from the object's mesh."""
    me = ob.data
    me.calc_loop_triangles()
    t = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", t)
    f = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", f)
    return t.reshape(-1, 3) / MM, f.reshape(-1, 3)


def export(ob, out, blend=True):
    """Always writes model.glb (QC, comparison, and the way into an open Blender); model.blend only when asked."""
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, "model.glb"), use_selection=True, export_apply=True)
    if blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "model.blend"))


def _studio(scale=1.0, floor_z=0.0):
    """Clay studio: floor + 3 area lights. `scale` enlarges light distance/size (energy x scale^2) for staging larger
    than one piece (a set on a board)."""
    w = bpy.context.scene.world or bpy.data.worlds.new("world")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.18, 0.18, 0.19, 1)
    bg.inputs["Strength"].default_value = 0.35
    bpy.context.scene.view_settings.exposure = -1.0  # rev 2: lights too bright -> brown wood looked peach
    bpy.ops.mesh.primitive_plane_add(size=4.0 * scale, location=(0, 0, floor_z))
    floor = bpy.context.active_object
    floor.data.materials.append(material.make_material("floor", color.lin("#8A8C90"), coarse=0.6))
    for name, hit_loc, energy, size in (("key", (-0.18, -0.22, 0.26), 9.0, 0.16),
                                      ("contents", (0.25, -0.12, 0.10), 3.0, 0.20),
                                      ("edge", (0.05, 0.25, 0.22), 6.0, 0.10)):
        li = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        li.data.energy, li.data.size = energy * scale ** 2, size * scale
        li.location = Vector(hit_loc) * scale
        camera.look_at(li, Vector((0, 0, 0.03)))
        scene.collection("LIGHTS").objects.link(li)


def preview(ob, out, sample=12, viewpoints=((35, 18),), r=None):
    """Fast render (clay, 480x560, low samples). One viewpoint -> preview.png; several viewpoints ([az, el], from
    [entity] preview) -> preview.jpg side by side. For iteration, not handover."""
    render.setup_render("test")
    _studio()
    ob.data.materials.append(material.make_material("plain_preview", color.lin(MATERIAL["bright"][0]), coarse=MATERIAL["bright"][1]))
    zmax = max(v.co.z for v in ob.data.vertices)
    distance = zmax * 0.62 / math.tan(math.radians(11.5))
    result = []
    for i, tp in enumerate(viewpoints):  # [az, el] or [az, el, zoom, target height / height] (face close-up)
        az, el = tp[0], tp[1]
        zoom, ft = (tp[2], tp[3]) if len(tp) > 2 else (1.0, 0.48)
        target = Vector((0, 0, zmax * ft))
        cam = camera.camera(f"cam_preview_{i}", target + camera.direction(az, el) * distance / zoom, (0, 0, 0), lens=85)
        camera.look_at(cam, target)
        name = "preview.png" if len(viewpoints) == 1 else f"preview_{i}.png"
        result.append(render.render_image(cam, os.path.join(out, name), 480, 560, sample, False))
    if r:
        compare_3d(ob, r, out, sample)
    if len(result) == 1:
        return result[0]
    path, _ = sheets.make([("PREVIEW", [(p, f"az {tp[0]}" + (f" x{tp[2]}" if len(tp) > 2 else ""), True)
                                          for p, tp in zip(result, viewpoints)])],
                          os.path.join(out, "preview.jpg"), "PREVIEW", cell_height=420)
    return path


def build_contact_sheet(ob, r, check, out, sample):
    """Render 5 viewpoints + summary into build_contact_sheet.jpg (green/red bar = overall QC)."""
    render.setup_render("test")
    _studio()
    wood = r.get("make_material", {})
    if wood.get("kind") == "wood":
        make_material = {k: wood_material(f"wood_{k}", *wood[k], scale=wood.get("fiber_scale", 260.0)) for k in ("bright", "dark")}
    else:
        make_material = {k: material.make_material(f"plain_{k}", color.lin(h), coarse=ks, **{"Coat Weight": 0.25})
                 for k, (h, ks) in MATERIAL.items()}
    ob.data.materials.append(make_material["bright"])
    zmax = max(v.co.z for v in ob.data.vertices)
    distance0 = zmax * 0.62 / math.tan(math.radians(11.5))
    passed = all(c["passed"] for c in check)
    cell = []
    for name, az, el, b, zoom, ft in VIEWPOINTS:
        ob.data.materials[0] = make_material[b]
        target, distance = Vector((0.007 * (zoom > 1), 0, zmax * ft)), distance0 / zoom
        cam = camera.camera(f"kam_{name}", target + camera.direction(az, el) * distance, (0, 0, 0), lens=85)
        camera.look_at(cam, target)
        p = render.render_image(cam, os.path.join(out, f"viewpoints_{name.replace(' ', '_')}.png"), 520, 620, sample,
                                 False)
        cell.append((p, name, passed))
    ob.data.materials[0] = make_material["bright"]
    for pb in r.get("comparison", []):
        compare(ob, pb, out, sample, zmax)
    summarize = " ".join(f"{c['id']}:{c['value']}" for c in check[:2])
    path, _ = sheets.make([(f"QC {'PASS' if passed else 'FAIL'} {summarize} MM", cell)],
                          os.path.join(out, "build_contact_sheet.jpg"), r["entity"]["name"], cell_height=380)
    return path


def compare(ob, pb, out, sample, zmax):
    """Comparison judge: a researched reference image (references/, not in the repo) next to a model render from the same
    camera angle ([[comparison]] az, el, lens, contents = object height / image height). For judging, not for tracing."""
    from ...core import io
    source = io.path_repo(pb["image"])
    if not os.path.isfile(source):
        print(f"  compare SKIP: {pb['image']} not found (reference only on the laptop/client)")
        return None
    img = bpy.data.images.load(source, check_existing=False)
    w, h = img.size
    ref = os.path.join(out, f"ref_{pb['name']}.png")
    img.filepath_raw, img.file_format = ref, "PNG"
    img.save()
    lens = pb.get("lens", 135.0)
    distance = zmax / pb.get("contents", 0.88) * lens / 36.0
    target = Vector((pb.get("shift_x_mm", 0.0) * MM, 0, zmax * 0.5))
    cam = camera.camera(f"cam_banding_{pb['name']}", target + camera.direction(pb["az"], pb["el"]) * distance, (0, 0, 0),
                        lens=lens)
    camera.look_at(cam, target)
    height = 620
    width = int(round(height * w / h))
    result = render.render_image(cam, os.path.join(out, f"model_{pb['name']}.png"), width, height, sample, False)
    path, _ = sheets.make([("RESEARCH REFERENCE VS MODEL (SAME ANGLE)", [(ref, "reference", True), (result, "model", True)])],
                          os.path.join(out, f"compare_{pb['name']}.jpg"), f"COMPARE {pb['name']}", cell_height=620)
    print(f"  compare: {path}")
    return path


def load_reference_3d(ref, height_mm):
    """Import a researched 3D reference model (glTF, references/; not in the repo), take one entity, base at the origin,
    scale to the design height, rotate about Z (`rotate_z`) so the muzzle/front faces +X. For judging, not for copying."""
    from ...core import io
    source = io.path_repo(ref["model"])
    if not os.path.isfile(source):
        print(f"  reference 3D SKIP: {ref['model']} not found")
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=source)
    new = [o for o in bpy.data.objects if o not in before]
    target = next(o for o in new if o.name == ref["entity"])
    for o in new:
        if o is not target:
            bpy.data.objects.remove(o)
    me = target.data.copy()
    me.transform(target.matrix_world)
    target.matrix_world.identity()
    target.data = me
    t = np.array([v.co[:] for v in me.vertices])
    center = np.array([(t[:, 0].min() + t[:, 0].max()) / 2, (t[:, 1].min() + t[:, 1].max()) / 2, t[:, 2].min()])
    k = height_mm * MM / (t[:, 2].max() - t[:, 2].min())
    a = math.radians(ref.get("rotate_z", 0.0))
    c, s_ = math.cos(a), math.sin(a)
    for v in me.vertices:
        x, y, z = (np.array(v.co[:]) - center) * k
        v.co = (x * c - y * s_, x * s_ + y * c, z)
    target.data.materials.clear()
    for p in me.polygons:
        p.use_smooth = True
    return target


def compare_3d(ob, r, out, sample=12):
    """3D comparison judge: 3D reference vs model with the same camera angles and clay material; top row reference, bottom model."""
    ref = r.get("reference_3d")
    ref_obj = load_reference_3d(ref, r["entity"]["height_mm"]) if ref else None
    if ref_obj is None:
        return None
    ref_obj.data.materials.append(ob.data.materials[0])
    zmax = max(v.co.z for v in ob.data.vertices)
    target = Vector((0, 0, zmax * 0.48))
    distance = zmax * 0.62 / math.tan(math.radians(11.5))
    viewpoints = ref.get("viewpoints", [[0, 4], [35, 18], [90, 4], [180, 4], [-90, 4], [0, 89]])
    row = []
    for title, show, hide in (("RESEARCH 3D REFERENCE", ref_obj, ob), ("MODEL", ob, ref_obj)):
        show.hide_render, hide.hide_render = False, True
        cell = []
        for i, tp in enumerate(viewpoints):  # [az, el] or [az, el, zoom, target height / height] (close-up)
            az, el = tp[0], tp[1]
            zoom, ft = (tp[2], tp[3]) if len(tp) > 2 else (1.0, 0.48)
            tgt = Vector((0, 0, zmax * ft))
            cam = camera.camera(f"cam_b3d_{i}", tgt + camera.direction(az, el) * distance / zoom, (0, 0, 0), lens=85)
            camera.look_at(cam, tgt)
            name = f"b3d_{'ref' if show is ref_obj else 'mdl'}_{i}.png"
            cell.append((render.render_image(cam, os.path.join(out, name), 360, 420, sample, False),
                        f"az {az} el {el}" + (f" x{zoom}" if zoom != 1.0 else ""), True))
        row.append((title, cell))
    ob.hide_render, ref_obj.hide_render = False, True
    path, _ = sheets.make(row, os.path.join(out, "compare_3d.jpg"), "3D COMPARE: REFERENCE VS MODEL", cell_height=300)
    print(f"  compare 3D: {path}")
    return path
