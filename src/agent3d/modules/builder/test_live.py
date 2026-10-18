"""Live-mode test without a GUI: build a piece with the recorder, then run the add-on LOADER (addon/agent3d) step
by step, like the watcher tick in an open Blender. QC KT-01..04 + negative tests. What can only be checked in the GUI
(timer ticking, viewport refresh, visible grow effect) still has to be watched on the laptop (docs/LIVE_PREVIEW.md)."""
import importlib.util
import json
import os
import shutil

from ...core import io, log, qc


def load_addon():
    path = io.path_repo("addon", "agent3d", "live.py")
    spec = importlib.util.spec_from_file_location("agent3d_live", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def qc_live(manifest, step_points, final_points, handover_points, end_scale):
    """manifest dict; step_points = [point count per step (None = failed to load)]; final_points/handover = point
    arrays of the final mesh in the add-on vs the headless model.glb (m); end_scale = object scale after the grow effect."""
    import numpy as np
    n = len(manifest.get("step", []))
    ends_with_glb = n > 0 and manifest["step"][-1]["file"] == "model.glb"
    same = final_points is not None and handover_points is not None and final_points.shape == handover_points.shape and \
        float(np.abs(np.sort(final_points, 0) - np.sort(handover_points, 0)).max()) < 1e-6
    load_failed = [i for i, t in enumerate(step_points) if not t]
    return [
        qc.check("KT-01", "all steps + final = model.glb + done", n, n >= 2 and ends_with_glb and
               bool(manifest.get("done")) and len(step_points) == n, ">= 2 steps, last is model.glb, done"),
        qc.check("KT-02", "final mesh in the open Blender identical to the headless handover mesh", "identical" if same else
               "diff", same, "same points (difference < 1e-6 m)"),
        qc.check("KT-03", "every step loads (mesh not empty)", load_failed or "all", not load_failed,
               "all steps"),
        qc.check("KT-04", "grow effect ends at scale 1", round(end_scale, 4), abs(end_scale - 1.0) < 1e-6, "1.0"),
    ]


def run(out):
    from . import builder
    if os.path.isdir(out):
        shutil.rmtree(out)
    folder = os.path.join(out, "live", "chess_pawn")
    code = builder.assemble(io.project("chess_pawn", "design.toml"), os.path.join(out, "model"), render=False,
                         mode="preview", live=folder)
    import bpy
    import numpy as np
    a = load_addon()
    m = a.read_manifest(folder)
    count, ob = [], None
    for item in m["step"]:
        me = a.load_step(folder, item)
        count.append(len(me.vertices) if me else None)
        if me:
            ob = a.display(me)
            a.grow(ob, a._state["grow_start"] + 10.0)

    def points(me):
        t = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", t)
        return t.reshape(-1, 3)
    end = points(ob.data) if ob else None
    handover = a.mesh_glb(os.path.join(out, "model", "model.glb"), "handover")
    handover_t = points(handover) if handover else None
    first = a.load_step(folder, m["step"][0])
    check = qc_live(m, count, end, handover_t, ob.scale.z if ob else 0.0)
    # loader robustness against half-written files (the next tick retries; must not raise)
    corrupt = os.path.join(out, "corrupt")
    os.makedirs(corrupt)
    with open(os.path.join(corrupt, "live.json"), "w") as f:
        f.write('{"step": [')
    with open(os.path.join(corrupt, "step_00.npz"), "wb") as f:
        f.write(b"PK\x03\x04setengah")
    hold = a.read_manifest(corrupt) is None and a.mesh_npz(os.path.join(corrupt, "step_00.npz"), "x") is None
    check.append(qc.check("KT-05", "loader survives half-written manifest/npz", hold, hold, "None, no error"))
    for c in check:
        print(f"  {c['id']} {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['value']} ({c['threshold']})")
    m_short = dict(m, step=m["step"][:-1])
    corrupt_tests = [
        ("final step missing", (m_short, count[:-1], end, handover_t, 1.0), "KT-01"),
        ("final = first step (not the handover mesh)", (m, count, points(first), handover_t, 1.0), "KT-02"),
        ("one step fails to load", (m, [None] + count[1:], end, handover_t, 1.0), "KT-03"),
        ("grow stops halfway", (m, count, end, handover_t, 0.6), "KT-04"),
    ]
    neg = []
    for name, argument, required in corrupt_tests:
        ok, failed = qc.caught(qc_live(*argument), [required])
        neg.append(dict(name=name, required=[required], failed=failed, caught=ok))
        print(f"  negative live {'OK ' if ok else 'LEAK'} {name}: failed {failed}")
    bpy.data.meshes.remove(first)
    rpt = dict(step=[i["name"] for i in m["step"]], points=count, check=check, negative=neg, build_code=code,
               **qc.summarize(check, neg))
    io.write_json(os.path.join(out, "test_live.json"), rpt)
    log.info(f"live: {len(m['step'])} steps; passed {rpt['passed']}; negative "
             f"{rpt['caught_negatives']}/{rpt['negative_count']}")
    return 0 if code == 0 and rpt["passed"] and rpt["caught_negatives"] == rpt["negative_count"] else 1
