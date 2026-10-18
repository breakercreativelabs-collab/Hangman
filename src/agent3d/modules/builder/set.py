"""Chess set on a board: 6 piece kinds (each from a builder design) placed in the starting position, SET QC
(KS-01..06) + negative tests, renders from several viewpoints -> sheet_set.jpg. Config: projects/<id>/set.toml.

Piece models come from output/builder/<piece project>/model.glb; if missing or older than the design, they are built
first (preview mode, no render). Pieces of the same kind share one mesh (instances), not copies.
"""
import math
import os
import time
import tomllib

import numpy as np

from ...core import io, log, qc

ORDER = ("king", "queen", "bishop", "knight", "rook", "pawn")  # Staunton set height order (tallest -> shortest)
COUNT = {"king": 1, "queen": 1, "bishop": 2, "knight": 2, "rook": 2, "pawn": 8}  # per color
BACK = ("rook", "knight", "bishop", "queen", "king", "bishop", "knight", "rook")  # tile a..h row 1 / 8


def load_set(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def start_position():
    """[(tile 'e1', color, kind)] for the 32 pieces of the standard starting position."""
    result = []
    for color, row_b, row_p in (("white", 1, 2), ("black", 8, 7)):
        for i, j in enumerate(BACK):
            result.append((f"{'abcdefgh'[i]}{row_b}", color, j))
            result.append((f"{'abcdefgh'[i]}{row_p}", color, "pawn"))
    return result


def piece_model(design):
    """(glb path, QC report) for one piece kind; builds it first (preview, no render) if missing or stale."""
    design = io.path_repo(design)
    out = io.artifact("builder", os.path.basename(os.path.dirname(design)))
    glb, rpt = os.path.join(out, "model.glb"), os.path.join(out, "report_qc.json")
    if not (os.path.isfile(glb) and os.path.isfile(rpt)) or os.path.getmtime(glb) < os.path.getmtime(design):
        from . import builder
        log.info(f"set: building {os.path.relpath(design, io.path_repo())} (missing / stale)")
        builder.assemble(design, out, render=False, mode="preview")
    import json
    with open(rpt, encoding="utf-8") as f:
        return glb, json.load(f)


def qc_set(box, size, passed_pieces, arrangement):
    """SET QC (builder QC_RULES, KS). size = {kind: (height mm, base diameter mm)}; passed_pieces = {kind: bool};
    arrangement = [(tile, color, kind)]."""
    t = [size[j][0] for j in ORDER]
    sort = all(a > b for a, b in zip(t, t[1:]))
    king_ratio = size["king"][1] / box
    ratio_max = max(a for _, a in size.values()) / box
    tile = [p for p, _, _ in arrangement]
    compute = {(w, j): sum(1 for _, ww, jj in arrangement if (ww, jj) == (w, j)) for w in ("white", "black") for j in ORDER}
    king_queen = {(p, j) for p, _, j in arrangement if j in ("king", "queen")} == {("e1", "king"), ("d1", "queen"),
                                                                          ("e8", "king"), ("d8", "queen")}
    valid = len(tile) == 32 and len(set(tile)) == 32 and all(compute[(w, j)] == COUNT[j] for w, j in compute) and king_queen
    failed_pieces = [j for j in ORDER if not passed_pieces.get(j)]
    return [
        qc.check("KS-01", "height order king > queen > bishop > knight > rook > pawn",
               dict(zip(ORDER, [round(x, 1) for x in t])), sort, "strictly decreasing"),
        qc.check("KS-02", "king base / tile side", king_ratio, 0.68 <= king_ratio <= 0.80,
               "0.68-0.80 (guideline 75-78%, sources range 68-85%)"),
        qc.check("KS-03", "tile side (mm)", box, 50.0 <= box <= 60.0, "50-60 mm (FIDE, tournament)"),
        qc.check("KS-04", "largest base / tile side", ratio_max, ratio_max <= 0.80, "<= 0.80 (gap between pieces)"),
        qc.check("KS-05", "valid starting position", "valid" if valid else "invalid", valid,
               "32 pieces, unique tiles, count per kind, king e / queen d"),
        qc.check("KS-06", "every piece passes its own QC (KC/KA)", failed_pieces or "all", not failed_pieces,
               "report_qc of each kind passed"),
    ]


def set_negative_tests(box, size, passed_pieces, arrangement):
    swap = [(p, w, {"king": "queen", "queen": "king"}.get(j, j)) for p, w, j in arrangement]
    corrupt = [
        ("pawn 2x as tall", box, dict(size, pawn=(size["pawn"][0] * 2, size["pawn"][1])), passed_pieces, arrangement,
         ["KS-01"]),
        ("tile 40 mm", 40.0, size, passed_pieces, arrangement, ["KS-02", "KS-03", "KS-04"]),
        ("tile 70 mm", 70.0, size, passed_pieces, arrangement, ["KS-02", "KS-03"]),
        ("knight base 50 mm", box, dict(size, knight=(size["knight"][0], 50.0)), passed_pieces, arrangement, ["KS-04"]),
        ("king and queen swapped", box, size, passed_pieces, swap, ["KS-05"]),
        ("two pieces on one tile", box, size, passed_pieces, arrangement[:-1] + [("e1",) + arrangement[-1][1:]], ["KS-05"]),
        ("knight fails its own QC", box, size, dict(passed_pieces, knight=False), arrangement, ["KS-06"]),
    ]
    result = []
    for name, k, u, lb, s, required in corrupt:
        ok, failed = qc.caught(qc_set(k, u, lb, s), required)
        result.append(dict(name=name, required=required, failed=failed, caught=ok))
        print(f"  negative set {'OK ' if ok else 'LEAK'} {name}: failed {failed}")
    return result


def _import(glb):
    """Import glb -> (mesh data, height mm, base diameter mm). Imported objects are removed; the mesh is shared."""
    import bpy
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    new = [o for o in bpy.data.objects if o not in before]
    ob = next(o for o in new if o.type == "MESH")
    me = ob.data.copy()
    me.transform(ob.matrix_world)
    for o in new:
        bpy.data.objects.remove(o)
    t = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", t)
    t = t.reshape(-1, 3) * 1000.0
    bottom = t[t[:, 2] < t[:, 2].min() + 1.0]
    return me, float(np.ptp(t[:, 2])), float(2 * np.hypot(bottom[:, 0], bottom[:, 1]).max())


def _board(s, box):
    """Board: 64 tiles (thin boxes, top at z = 0) + a framed board body underneath. Units: meters."""
    import bpy
    from ...core import material, color
    mm = 0.001
    bright = material.make_material("bright_tile", color.lin(s.get("bright_tile", "#B9A586")), coarse=0.5)
    dark = material.make_material("dark_tile", color.lin(s.get("dark_tile", "#4A3A2C")), coarse=0.5)
    side = 8 * box + 2 * s.get("frame_mm", 20.0)
    thickness = s.get("board_thickness_mm", 14.0)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, -(thickness / 2 + 0.6) * mm))
    body = bpy.context.active_object
    body.scale = (side * mm, side * mm, thickness * mm)
    body.data.materials.append(material.make_material("framing", color.lin(s.get("framing", "#2E241C")), coarse=0.45))
    for f in range(8):
        for r in range(8):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=((f - 3.5) * box * mm, (r - 3.5) * box * mm,
                                                                -0.3 * mm))
            p = bpy.context.active_object
            p.scale = (box * mm * 0.999, box * mm * 0.999, 0.6 * mm)
            p.data.materials.append(dark if (f + r) % 2 == 0 else bright)  # a1 dark
    return side, thickness


def arrange(path_set, out, render=True, sample=24):
    """Build the set staging + KS QC + negative tests + sheet_set.jpg. Exit code 0 = pass + all negatives caught."""
    t0 = time.time()
    cfg = load_set(path_set)
    s = cfg["set"]
    box = float(s["box_mm"])
    source = {}
    for j in ORDER:  # build first (the builder clears the scene)
        try:
            source[j] = piece_model(cfg["piece"][j])
        except FileNotFoundError as e:  # e.g. a licensed asset not yet downloaded to references/ (public package)
            if j not in cfg.get("backup_pieces", {}) or not os.path.isfile(io.path_repo(cfg["backup_pieces"][j])):
                raise
            log.info(f"set: {j} uses backup {cfg['backup_pieces'][j]} ({e})")
            cfg["piece"][j] = cfg["backup_pieces"][j]
            source[j] = piece_model(cfg["piece"][j])
    import bpy
    from mathutils import Vector
    from ...core import camera, sheets, material, render, scene, color
    from . import staging
    scene.prepare_scene()
    mesh, size = {}, {}
    for j in ORDER:
        mesh[j], height, base_width = _import(source[j][0])
        size[j] = (height, base_width)
        log.info(f"set: {j} height {height:.1f} mm, base_width {base_width:.1f} mm")
    passed_pieces = {j: bool(source[j][1].get("passed")) for j in ORDER}
    arrangement = start_position()
    check = qc_set(box, size, passed_pieces, arrangement)
    for c in check:
        print(f"  {c['id']} {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['value']} ({c['threshold']})")
    neg = set_negative_tests(box, size, passed_pieces, arrangement)
    make_material = {w: material.make_material(f"piece_{w}", color.lin(s[w]), coarse=0.45 if w == "white" else 0.3)
             for w in ("white", "black")}
    copies = {}
    for j in ORDER:  # one mesh per color (the material lives on the mesh data), shared by pieces of the same kind
        for w in ("white", "black"):
            m = mesh[j].copy()
            m.materials.clear()
            m.materials.append(make_material[w])
            for p in m.polygons:
                p.use_smooth = True
            copies[(j, w)] = m
    mm = 0.001
    for tile, w, j in arrangement:
        ob = bpy.data.objects.new(f"{w}_{j}_{tile}", copies[(j, w)])
        f, r = "abcdefgh".index(tile[0]), int(tile[1]) - 1
        ob.location = ((f - 3.5) * box * mm, (r - 3.5) * box * mm, 0.0)
        if j == "knight":  # the model's muzzle points +X -> face the opponent
            ob.rotation_euler.z = math.radians(90 if w == "white" else -90)
        scene.collection("PRODUCT").objects.link(ob)
    side, thickness = _board(s, box)
    os.makedirs(out, exist_ok=True)
    image = []
    if render:
        render.setup_render("test")
        staging._studio(scale=side * mm / 0.12, floor_z=-(thickness + 0.6) * mm)
        bpy.context.scene.view_settings.exposure = s.get("exposure", -1.0)
        for i, (az, el, distance, tz, tx, ty) in enumerate(s["viewpoints"]):
            tgt = Vector((tx * mm, ty * mm, tz * mm))
            cam = camera.camera(f"cam_set_{i}", tgt + camera.direction(az, el) * distance * mm, (0, 0, 0), lens=50)
            camera.look_at(cam, tgt)
            image.append((render.render_image(cam, os.path.join(out, f"set_{i}.png"), 720, 540, sample, False),
                           f"az {az} el {el}", all(c["passed"] for c in check)))
        sheets.make([("SET", image[:2]), ("CLOSE-UP", image[2:])], os.path.join(out, "sheet_set.jpg"),
                    s.get("name", "SET"), cell_height=360)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "set.blend"))
    report = dict(set=os.path.relpath(path_set, io.path_repo()), box_mm=box,
                   size={j: [round(a, 2), round(b, 2)] for j, (a, b) in size.items()},
                   piece={j: cfg["piece"][j] for j in ORDER}, check=check, negative=neg,
                   seconds=round(time.time() - t0, 1), **qc.summarize(check, neg))
    io.write_json(os.path.join(out, "report_set.json"), report)
    log.info(f"done {report['seconds']} s; passed {report['passed']}; negative "
             f"{report['caught_negatives']}/{report['negative_count']}")
    return 0 if report["passed"] and report["caught_negatives"] == report["negative_count"] else 1
