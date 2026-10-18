"""Tree generator test: QC-001/002/005/006 (QC_RULES.md) on 3 example trees, regression against reference_tree.json
(the generator is deterministic), QC-001 negative test (duplicate-point guard disabled = v1 behavior, must be caught).

  blender -b --factory-startup -P blender_cli.py -- procedural test [--out <folder>]
QC-004 (twig tip <= 0.015 m) is still ⚠ (0.022 m, Task 1 parked): reported, does not fail the test.
"""
import json
import os

import bpy

from ...core import io
from ...core.qc import Logger
from . import tree

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference_tree.json")


def clear():
    for o in list(bpy.data.objects):
        if o.type != "CAMERA":
            bpy.data.objects.remove(o)


def main(argv):
    out = os.path.abspath(io.options(argv, dict(out=io.artifact("test", "procedural")))["out"])
    P = Logger()
    with open(BASELINE, encoding="utf-8") as f:
        baseline = json.load(f)
    clear()
    tree.STAT["duplicate_prevented"] = 0
    rpt = [tree.build_tree(*t) for t in tree.TREE]
    for x in rpt:
        n = x["tree"]
        P.test(f"QC-001 {n}: stacked points = 0", x["QC_points_stacked"] == 0, x["QC_points_stacked"])
        P.test(f"QC-002 {n}: leaf clump <= 8 x median", x["QC_clump_leaf_max_x_median"] <= 8,
              x["QC_clump_leaf_max_x_median"])
        P.test(f"QC-005 {n}: leaves >= 15 x twig tips", x["leaf"] >= 15 * x["twig_tips"],
              f"{x['leaf']} vs {15 * x['twig_tips']}")
        P.test(f"QC-006 {n}: leaves below ground = 0", x["QC_leaf_in_bottom_ground"] == 0, x["QC_leaf_in_bottom_ground"])
        print(f"  NOTE QC-004 {n}: tip radius {x['branch_radius_min_max_m'][0]} m (threshold 0.015; status ⚠)")
    P.test("regression: report of 3 trees = reference_tree.json", rpt == baseline["report"],
          [x["branch_points"] for x in rpt])
    P.test("regression: duplicates prevented = baseline", tree.STAT == baseline["stat"], tree.STAT)
    clear()
    x = tree.build_tree(*tree.TREE[0], prevent_duplicate=False)
    P.test("NEGATIVE QC-001: duplicate-point guard disabled (v1) caught", x["QC_points_stacked"] > 0,
          x["QC_points_stacked"])
    print(f"TREE TEST {'PASS' if P.all_passed else 'FAIL'} {P.passed}/{len(P.result)} ({P.duration:.0f} s)")
    P.write(os.path.join(out, "test_tree.json"), blender=bpy.app.version_string, report=rpt)
    return 0 if P.all_passed else 1
