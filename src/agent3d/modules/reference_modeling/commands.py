"""CLI commands of the reference_modeling module (cli contract: COMMANDS = {name: (function(argv) -> exit code, summary)})."""
import os

from ...core import io


def _qc(argv):
    from .shoe import report
    return report.main(argv)


def _build(argv):
    """Build the model from project data and save the .blend (same as the old model_am1.py, no QC)."""
    from . import api
    o = io.options(argv, dict(project="am1", out=""))
    api.load_project(o["project"])
    obs = api.build_model()
    out = api.save_model(os.path.abspath(o["out"]) if o["out"] else None)
    print("MODEL saved:", out, {k: len(v.data.vertices) for k, v in obs.items() if getattr(v, "type", "") == "MESH"})
    return 0 if os.path.isfile(out) else 1


def _extract_contour(argv):
    from .extraction import contour
    from .shoe import data
    o = io.options(argv, dict(project="am1", ref="", out=""))
    k = data.load_data(o["project"], without_reference=True)
    out = os.path.abspath(o["out"] or io.project(o["project"], k["data"]["reference"]))
    contour.extract_contour(os.path.abspath(o["ref"]), out, k["extraction"])
    return 0


def _extract_panel(argv):
    from .extraction import panel
    from .shoe import data
    o = io.options(argv, dict(project="am1", ref="", data="", out=""))
    k = data.load_data(o["project"], without_reference=True)
    baseline = os.path.abspath(o["data"] or io.project(o["project"], k["data"]["reference"]))
    out = os.path.abspath(o["out"] or io.project(o["project"], k["data"]["panel"]))
    panel.extract_panel(os.path.abspath(o["ref"]), baseline, out, k["extraction"])
    return 0


def _extract_class(argv):
    from .extraction import classes
    from .shoe import data
    o = io.options(argv, dict(project="am1", ref="", data="", out=""))
    k = data.load_data(o["project"], without_reference=True)
    baseline = os.path.abspath(o["data"] or io.project(o["project"], k["data"]["reference"]))
    out = os.path.abspath(o["out"] or io.project(o["project"], k["data"]["classes"]))
    classes.extract_class(os.path.abspath(o["ref"]), baseline, out, k["extraction"])
    return 0


def _target(o, d, key):
    """Path of data file `key` ([data] in project.toml): in the --out folder when given (tests / MCP: tracked project
    data stays untouched), otherwise in the project folder (old behavior)."""
    if o.get("out"):
        os.makedirs(os.path.abspath(o["out"]), exist_ok=True)
        return os.path.join(os.path.abspath(o["out"]), os.path.basename(d[key]))
    return io.project(o["project"], d[key])


def _extract_tread(argv):
    from .extraction import tread
    from .shoe import data
    o = io.options(argv, dict(project="am1", ref="", data="", out=""))
    k = data.load_data(o["project"], without_reference=True)
    d = k["data"]
    baseline = os.path.abspath(o["data"]) if o["data"] else io.project(o["project"], d["reference"])
    tread.extract_tread(os.path.abspath(o["ref"]), baseline, _target(o, d, "tread"), _target(o, d, "tread_grooves"),
                        k["extraction"])
    return 0


def _data(argv):
    """One command photo -> data: alpha analysis + contour (sole calibration) + color classes (midsole line, window, panels)
    or luma panels (AM1). Prints the cross-scale check; exits 1 when the ratio delta exceeds [extraction] check_ratio_pct."""
    import json
    from .extraction import alpha
    from .shoe import data
    o = io.options(argv, dict(project="am1", ref="", out=""))
    k = data.load_data(o["project"], without_reference=True)
    d, ref = k["data"], os.path.abspath(o["ref"])
    base = ["--project", o["project"], "--ref", ref]
    baseline = _target(o, d, "reference")
    ke = (lambda key: ["--data", baseline, "--out", _target(o, d, key)]) if o["out"] else (lambda key: [])
    alpha.alpha_analysis(ref)
    _extract_contour(base + (["--out", baseline] if o["out"] else []))
    if k["extraction"].get("luma_line", True):
        _extract_panel(base + ke("panel"))
    else:
        _extract_class(base + ke("classes"))
    if "tread" in d:
        _extract_tread(base + (["--data", baseline, "--out", o["out"]] if o["out"] else []))
    calib = json.load(open(baseline, encoding="utf-8"))["calibration"]
    print("CALIBRATION", json.dumps(calib))
    limit = k["extraction"].get("check_ratio_pct")
    if limit is not None and abs(calib.get("ratio_delta_pct", 0.0)) > limit:
        print(f"FAIL cross-scale check: heel/forefoot ratio delta {calib['ratio_delta_pct']} % > {limit} %")
        return 1
    return 0


def _alpha_analysis(argv):
    from .extraction import alpha
    alpha.alpha_analysis(os.path.abspath(io.options(argv, dict(ref=""))["ref"]))
    return 0


def _test_photo(argv):
    """Synthetic reference photos from the project model (extraction smoke test, cli suite; C-B3)."""
    from . import api
    from .extraction import test_photo
    o = io.options(argv, dict(project="am1", out=""))
    api.load_project(o["project"])
    api.build_model()
    result = test_photo.test_photo(os.path.abspath(o["out"] or io.artifact(o["project"], "test_photo")))
    print("TEST PHOTO:", result)
    return 0


COMMANDS = {
    "qc": (_qc, "build project model + QC AM-01..18 + 25 negative tests + contact sheet (--project am1)"),
    "build": (_build, "build model from project data -> .blend (artifact), no QC"),
    "extract_contour": (_extract_contour, "reference photos (references/) -> JSON silhouette/plan/lines (--ref <folder>)"),
    "extract_panel": (_extract_panel, "reference photos (references/) -> JSON upper panels (--ref <folder>)"),
    "alpha_analysis": (_alpha_analysis, "alpha distribution of reference photos + test masks (--ref <folder>)"),
    "test_photo": (_test_photo, "SYNTHETIC reference photos from the model (flat render per role) for the extraction smoke test (--out)"),
    "extract_class": (_extract_class, "reference photos -> JSON panels per color class + midsole/window lines (--ref <folder>)"),
    "extract_tread": (_extract_tread, "sole photo -> outsole color zones (plan polygons) + tread groove map PNG (--ref <folder>; "
                                      "--out <folder> = do not write to project data)"),
    "data": (_data, "ONE command photo -> data: alpha + contour + classes/panels + tread + cross-scale check (--project <id> "
                    "--ref <folder>; --out <folder> = write there, not to project data)"),
}
