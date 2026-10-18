"""Procedural tree generator (space colonization) for Blender 5.2.

Claude only holds the PARAMETERS in PRESET; the algorithm grows the trunk, branches and leaves. Numeric QC is in the
build() report (QC_points_stacked, QC_clump_leaf_max_x_median, QC_leaf_in_bottom_ground, branch radius); rules and
defect history: this module's QC_RULES.md. Commands: `procedural tree` (example scene + render) and `procedural test`.
"""
import json
import math
import os
import random

import bpy
from mathutils import Vector, kdtree

from ...core.material import make_material, math_node, ramp, new_node
from ...core.render import select_device

# ---------------- PARAMETERS (the only thing Claude needs to "reason" about) ----------------
PRESET = {
    "lush": dict(shape="ellipsoid", crown_height=5.2, crown_radius=3.6, crown_thickness=2.6,
                    attraction_points=1400, reach=1.6, kill_distance=0.35, step=0.22,
                    stem_radius=0.32, tropism=0.08, leaves_per_tip=10, leaf_size=0.34,
                    leaf_color=(0.10, 0.32, 0.06)),
    "cone": dict(shape="cone", crown_height=4.4, crown_radius=2.4, crown_thickness=5.0,
                    attraction_points=1200, reach=1.3, kill_distance=0.30, step=0.2,
                    stem_radius=0.24, tropism=0.02, leaves_per_tip=12, leaf_size=0.24,
                    leaf_color=(0.05, 0.20, 0.07)),
}
TREE = [("lush", 7, -9.0), ("lush", 21, 0.0), ("cone", 7, 9.0)]  # (preset, seed, x position)


def crown_points(p, rng):
    """Scatter attraction points inside the crown volume (ellipsoid or cone)."""
    pts = []
    while len(pts) < p["attraction_points"]:
        x, y, z = (rng.uniform(-1, 1) for _ in range(3))
        if p["shape"] == "ellipsoid":
            if x * x + y * y + z * z > 1:
                continue
            pts.append(Vector((x * p["crown_radius"], y * p["crown_radius"], p["crown_height"] + z * p["crown_thickness"])))
        else:  # cone: narrower toward the top
            t = (z + 1) / 2  # 0 = base, 1 = apex
            if x * x + y * y > (1 - t) ** 2:
                continue
            pts.append(Vector((x * p["crown_radius"], y * p["crown_radius"], p["crown_height"] - p["crown_thickness"] / 2 + t * p["crown_thickness"] * 1.2)))
    return pts


STAT = {"duplicate_prevented": 0}


def grow(p, seed, prevent_duplicate=True):
    """Space colonization: branches grow toward the attraction points in the crown.
    prevent_duplicate=False only for the QC-001 negative test (v1 behavior)."""
    rng = random.Random(seed)
    pull = crown_points(p, rng)
    node, parent = [Vector((0, 0, 0))], [-1]
    # trunk grows straight up until it reaches the crown's influence
    while min((a - node[-1]).length for a in pull) > p["reach"]:
        node.append(node[-1] + Vector((rng.uniform(-.02, .02), rng.uniform(-.02, .02), p["step"])))
        parent.append(len(node) - 2)
    for _ in range(400):
        kd = kdtree.KDTree(len(node))
        for i, v in enumerate(node):
            kd.insert(v, i)
        kd.balance()
        direction = {}
        for a in pull:
            _, i, d = kd.find(a)
            if d < p["reach"]:
                direction[i] = direction.get(i, Vector()) + (a - node[i]).normalized()
        if not direction:
            break
        new = 0
        for i, d in direction.items():
            d = (d.normalized() + Vector((0, 0, p["tropism"]))).normalized()
            candidate = node[i] + d * p["step"]
            if prevent_duplicate and kd.find(candidate)[2] < p["step"] * 0.4:  # a point already exists there -> do not grow a duplicate
                STAT["duplicate_prevented"] += 1
                continue
            node.append(candidate)
            parent.append(i)
            new += 1
        if not new:
            break
        kd = kdtree.KDTree(len(node))
        for i, v in enumerate(node):
            kd.insert(v, i)
        kd.balance()
        pull = [a for a in pull if kd.find(a)[2] > p["kill_distance"]]
        if not pull:
            break
    # branch radius: Leonardo pipe model (r_parent^n = sum of r_child^n)
    child = [[] for _ in node]
    for i, j in enumerate(parent):
        if j >= 0:
            child[j].append(i)
    r = [0.0] * len(node)
    for i in reversed(range(len(node))):
        r[i] = 0.01 if not child[i] else sum(r[c] ** 2.5 for c in child[i]) ** (1 / 2.5)
    # v3: natural branch taper (not mean-scaled) -> slimmer mid branches
    tip_r = 0.012
    r = [tip_r + (p["stem_radius"] - tip_r) * (x / r[0]) ** 1.5 for x in r]
    # distance from each point to the nearest twig tip (to place leaves along the twigs)
    to_tip = [0] * len(node)
    for i in reversed(range(len(node))):
        to_tip[i] = 0 if not child[i] else min(to_tip[c] for c in child[i]) + 1
    return node, parent, child, r, rng, to_tip


def leaf_material(name, dark, bright):
    """Procedural leaf: leaf shape from UV (alpha), per-leaf color variation, light transmission."""
    m = make_material(name, dark, 0.45)
    t = m.node_tree
    bsdf = next(n for n in t.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL")
    uv = new_node(t, "ShaderNodeSeparateXYZ")
    t.links.new(new_node(t, "ShaderNodeTexCoord").outputs["UV"], uv.inputs[0])
    u, v = uv.outputs[0], uv.outputs[1]
    width = math_node(t, "MULTIPLY", math_node(t, "POWER", math_node(t, "SINE", math_node(t, "MULTIPLY", u, math.pi)), 0.75), 0.48)
    mid_distance = math_node(t, "ABSOLUTE", math_node(t, "SUBTRACT", v, 0.5))
    shape = math_node(t, "LESS_THAN", mid_distance, width)
    bone = math_node(t, "LESS_THAN", mid_distance, 0.025)
    var = new_node(t, "ShaderNodeAttribute", attribute_name="variation")
    color = ramp(t, math_node(t, "ADD", var.outputs["Fac"], math_node(t, "MULTIPLY", bone, 0.35)), dark, bright)
    t.links.new(color, bsdf.inputs["Base Color"])
    transmission = new_node(t, "ShaderNodeBsdfTranslucent")
    t.links.new(color, transmission.inputs["Color"])
    mix = new_node(t, "ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.3
    t.links.new(bsdf.outputs[0], mix.inputs[1])
    t.links.new(transmission.outputs[0], mix.inputs[2])
    alpha = new_node(t, "ShaderNodeMixShader")
    t.links.new(shape, alpha.inputs[0])
    t.links.new(new_node(t, "ShaderNodeBsdfTransparent").outputs[0], alpha.inputs[1])
    t.links.new(mix.outputs[0], alpha.inputs[2])
    t.links.new(alpha.outputs[0], out.inputs["Surface"])
    return m


def leather_material(name):
    """Procedural bark: vertical grooves (wave) + noise, with bump."""
    m = make_material(name, (0.15, 0.1, 0.06), 0.9)
    t = m.node_tree
    bsdf = next(n for n in t.nodes if n.type == "BSDF_PRINCIPLED")
    obj = new_node(t, "ShaderNodeTexCoord").outputs["Object"]
    wave = new_node(t, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="X")
    for k, v in (("Scale", 9.0), ("Distortion", 7.0), ("Detail", 6.0)):
        if k in wave.inputs:
            wave.inputs[k].default_value = v
    noise = new_node(t, "ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value, noise.inputs["Detail"].default_value = 14.0, 10.0
    t.links.new(obj, wave.inputs["Vector"])
    t.links.new(obj, noise.inputs["Vector"])
    pattern = math_node(t, "MULTIPLY", wave.outputs["Fac"], noise.outputs["Fac"])
    t.links.new(ramp(t, pattern, (0.04, 0.03, 0.02), (0.30, 0.22, 0.14)), bsdf.inputs["Base Color"])
    bump = new_node(t, "ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.7
    t.links.new(pattern, bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def build_tree(preset_name, seed, x0, prevent_duplicate=True):
    p = PRESET[preset_name]
    node, parent, child, r, rng, to_tip = grow(p, seed, prevent_duplicate)
    off = Vector((x0, 0, 0))
    # trunk + branches: edge mesh + Skin modifier (thickness per point)
    me = bpy.data.meshes.new(f"batang_{preset_name}_{seed}")
    me.from_pydata([v + off for v in node], [(j, i) for i, j in enumerate(parent) if j >= 0], [])
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.collection.objects.link(ob)
    ob.modifiers.new("Skin", "SKIN")
    for i, sv in enumerate(me.skin_vertices[0].data):
        sv.radius = (r[i], r[i])
    me.skin_vertices[0].data[0].use_root = True
    sub = ob.modifiers.new("Halus", "SUBSURF")
    sub.levels, sub.render_levels = 0, 1
    ob.data.materials.append(leather_material(f"leather_{seed}"))
    # leaves v3: at the tips AND along the last 3 twig segments, leaning outward from the crown center
    tip = [i for i in range(len(node)) if not child[i]]
    center = Vector((0, 0, p["crown_height"]))
    lv, lf = [], []
    for i in (i for i in range(len(node)) if to_tip[i] <= 3):
        n_leaves = p["leaves_per_tip"] if to_tip[i] == 0 else max(2, p["leaves_per_tip"] // 3)
        for _ in range(n_leaves):
            c = node[i] + off + Vector((rng.uniform(-.3, .3), rng.uniform(-.3, .3), rng.uniform(-.25, .25)))
            exit_code = (node[i] - center).normalized()
            u = (exit_code * 0.7 + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-.4, .2)))).normalized()
            w = u.cross(Vector((0, 0, 1))).normalized() if abs(u.z) < .95 else Vector((1, 0, 0))
            L, W = p["leaf_size"], p["leaf_size"] * .5
            b = len(lv)
            lv += [c - u * L / 2 - w * W / 2, c + u * L / 2 - w * W / 2, c + u * L / 2 + w * W / 2, c - u * L / 2 + w * W / 2]
            lf.append((b, b + 1, b + 2, b + 3))
    dm = bpy.data.meshes.new(f"leaf_{preset_name}_{seed}")
    dm.from_pydata(lv, [], lf)
    uvl = dm.uv_layers.new(name="UVMap")
    angle = ((0, 0), (1, 0), (1, 1), (0, 1))
    for poly in dm.polygons:
        for k, li in enumerate(poly.loop_indices):
            uvl.data[li].uv = angle[k]
    var = dm.attributes.new("variation", "FLOAT", "FACE")
    var.data.foreach_set("value", [rng.random() * 0.8 for _ in lf])
    do = bpy.data.objects.new(dm.name, dm)
    bpy.context.collection.objects.link(do)
    g = p["leaf_color"]
    do.data.materials.append(leaf_material(f"leaf_{seed}", tuple(x * 0.6 for x in g), (g[0] * 2.2, g[1] * 1.5, g[2] * 1.2)))
    kdq = kdtree.KDTree(len(node))
    for i, v in enumerate(node):
        kdq.insert(v, i)
    kdq.balance()
    stack = sum(1 for v in node if len(kdq.find_range(v, 0.01)) > 1)
    vox = {}
    for v in lv[::4]:
        k = (int(v.x // .5), int(v.y // .5), int(v.z // .5))
        vox[k] = vox.get(k, 0) + 1
    contents = sorted(vox.values())
    median = contents[len(contents) // 2]
    zs = [v.z for v in node]
    xy = max(math.hypot(v.x, v.y) for v in node)
    return {"tree": f"{preset_name} seed {seed}", "branch_points": len(node), "twig_tips": len(tip),
            "leaf": len(lf), "height_m": round(max(zs) + p["leaf_size"], 2), "crown_width_m": round(2 * xy, 2),
            "stem_radius_m": p["stem_radius"],
            "QC_points_stacked": stack, "QC_clump_leaf_max_x_median": round(contents[-1] / median, 1),
            "QC_leaf_in_bottom_ground": sum(1 for v in lv[::4] if v.z < 0),
            "branch_radius_min_max_m": [round(min(r), 3), round(max(r), 3)]}


def example_scene(out, render=True, sample=128, res=(1600, 720)):
    """Scene with 3 trees (TREE) + ground + sun + sky, renders tree_render_v3.png + tree.blend into `out`.
    Device: GPU if available (OptiX -> CUDA -> ...), otherwise CPU (the old v3 forced OptiX)."""
    for o in list(bpy.data.objects):
        if o.type != "CAMERA":
            bpy.data.objects.remove(o)
    report = [build_tree(*t) for t in TREE]

    bpy.ops.mesh.primitive_plane_add(size=80)
    bpy.context.active_object.data.materials.append(make_material("ground", (0.16, 0.20, 0.10), 0.95))
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
    sc.cycles.samples = sample
    sc.cycles.transparent_max_bounces = 48  # stacked alpha leaves: keeps leaves from turning black
    select_device()
    sc.render.resolution_x, sc.render.resolution_y = res
    os.makedirs(out, exist_ok=True)
    if render:
        sc.render.filepath = os.path.join(os.path.abspath(out), "tree_render_v3.png")  # C-10
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(out), "tree.blend"))
    print("REPORT " + json.dumps(report, ensure_ascii=False))
    print("STAT", STAT)
    return report
