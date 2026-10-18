"""Project data for the shoe recipe: reference JSON (mm) + project.toml (palette, labels, output).

Axis convention (same as extraction/contour.py): meters in the scene, X = length (0 = toe tip, + toward the heel),
Y = width (+ = lateral side), Z = height (0 = ground). Lateral at +Y with the toe at -X = RIGHT shoe.
Module attributes (DATA, PANEL, CONFIG, LAB, PX, LENGTH, OUTSOLE) are filled by load_data(); read them as data.ATTRIBUTE.
"""
import json
import os
import tomllib

import numpy as np

from ....core import io

# Material slot = palette role name (project.toml [palette.role]; experiment/taste.md). Neutral colors until M3.
ROLE = ("mudguard", "outsole", "upper_mesh", "swoosh", "midsole", "air_capsule", "overlay_suede", "lining", "lace",
         "chrome_accent")
PROJECT = None
DIR = None
CONFIG = DATA = PANEL = LAB = CLASS = TREAD = None
PX = LENGTH = OUTSOLE = None


def load_data(project="am1", without_reference=False):
    """Load projects/<project>/project.toml + its reference data (once; call again to switch project).
    without_reference=True: project.toml only (extraction, before the reference data exists)."""
    global PROJECT, DIR, CONFIG, DATA, PANEL, LAB, PX, LENGTH, OUTSOLE, CLASS, TREAD
    if PROJECT == project and DATA is not None:
        return CONFIG
    DIR = io.project(project)
    with open(os.path.join(DIR, "project.toml"), "rb") as f:
        CONFIG = tomllib.load(f)
    if without_reference:
        return CONFIG
    with open(os.path.join(DIR, CONFIG["data"]["reference"]), encoding="utf-8") as f:
        DATA = json.load(f)
    p_panel = os.path.join(DIR, CONFIG["data"].get("panel", ""))
    PANEL = json.load(open(p_panel, encoding="utf-8")) if os.path.isfile(p_panel) else None
    p_class = os.path.join(DIR, CONFIG["data"].get("classes", ""))
    CLASS = json.load(open(p_class, encoding="utf-8")) if os.path.isfile(p_class) else None
    p_tread = os.path.join(DIR, CONFIG["data"].get("tread", ""))
    TREAD = json.load(open(p_tread, encoding="utf-8")) if os.path.isfile(p_tread) else None
    LAB = DATA.get("lab") or DATA["lab_runrepeat_us9"]
    PX = DATA["calibration"]["mm_per_px_sole"]          # 1 sole-photo pixel (mm)
    LENGTH = DATA["calibration"]["outer_length_mm"]   # 293.7 mm [D] +-2%
    OUTSOLE = LAB["outsole_mm"]                      # 5.7 mm [F] lab
    PROJECT = project
    return CONFIG


def model(part, key, defaults):
    """Per-project recipe parameter from project.toml [model.<part>] (Task 11: [D] numbers calibrated on AM1 move to the
    project when another shoe needs a different value). No entry = AM1 value (default), so AM1 stays identical."""
    return CONFIG.get("model", {}).get(part, {}).get(key, defaults)


def map_x(x):
    """Map an AM1 recipe x position -> project shoe via [model.landmark] (am1 = [...], project = [...], mm,
    piecewise-linear; from silhouette data: toe tip, front lace hole, tongue peak, lowest collar point, heel peak,
    length). No landmark = identity (AM1 identical). [D]: design features are assumed to sit relative to landmarks."""
    lm = CONFIG.get("model", {}).get("landmark")
    if not lm:
        return x
    return float(np.interp(x, lm["am1"], lm["project"]))


def role_list():
    """Project roles (material slots): [model.common] role, default = AM1 ROLE."""
    return tuple(model("common", "role", ROLE))


def class_panels(name, side):
    """Color-class panel polygons for that side: list of {outer: [[x, z]], hole: [[[x, z]]]} (mm)."""
    return CLASS[side]["panel"][name]["polygon"] if CLASS and name in CLASS[side]["panel"] else []


def _polygon_center(P):
    P = np.array(P, float)
    x, z = P[:, 0], P[:, 1]
    c = x * np.roll(z, -1) - np.roll(x, -1) * z
    A = 0.5 * c.sum()
    return float(((x + np.roll(x, -1)) * c).sum() / (6 * A)), float(((z + np.roll(z, -1)) * c).sum() / (6 * A)), abs(A)


def plan_xy(poly):
    """Sole-photo plan polygon (x, y_photo mm; y from the photo top edge) -> (x, model Y mm), plan_y convention."""
    p = np.array(DATA["sole_plan_profile"], float)
    c = (p[:, 1].min() + p[:, 2].max() + PX) / 2
    return [(x, c - y) for x, y in poly]


def path_data(key):
    """Path of project data file [data].<key> (e.g. tread_grooves)."""
    return os.path.join(DIR, CONFIG["data"][key])


def class_holes():
    """Lace holes from the hole polygons of the [model.hole] source panels (e.g. eyestay): {side: {lace_hole:
    [[x, z, area]]}} (AM1 panel format, used by Shape)."""
    out = {}
    for side in ("lateral", "medial"):
        holes = []
        for name in model("hole", "source", []):
            for pg in class_panels(name, side):
                holes += [[round(v, 2) for v in _polygon_center(h)] for h in pg["hole"]]
        out[side] = dict(lace_hole=sorted(holes))
    return out


def output_path(key):
    """Output path from [output]: 'output/...' is relative to the repo root, anything else to the project folder."""
    p = CONFIG["output"][key]
    return io.path_repo(p) if p.startswith("output/") else os.path.join(DIR, p)


def palette():
    """{role: (hex, source)} in project palette role order."""
    return {k: tuple(v) for k, v in CONFIG["palette"]["role"].items()}


def data_source():
    """Data source text for PRODUCT_ROOT['source'] and the QC report."""
    d = CONFIG["data"]
    if PANEL is None:  # color-class project (am90): panels live in the classes JSON
        return "%s v%d + %s" % (d["reference"], DATA["version"], d.get("classes", "-"))
    return "%s v%d + %s v%d" % (d["reference"], DATA["version"], d["panel"], PANEL["version"])


# ---------------- derived data (used by build and QC) ----------------
def side_profile(side="lateral"):
    a = np.array(DATA[f"side_profile_{side}"], float)
    return a[:, 0], a[:, 1], a[:, 2]


def midsole_line():
    """`mudguard_bottom_line_lateral` = top midsole line. Outliers are dropped by a fixed rule:
    |z - median of 6 neighbors| > 5 mm (last point x 292.6 z 71.2 = heel counter edge, not midsole)."""
    a = np.array(DATA["mudguard_bottom_line_lateral"], float)
    z, ok = a[:, 1], np.ones(len(a), bool)
    for i in range(len(a)):
        nbrs = np.r_[z[max(0, i - 3):i], z[i + 1:i + 4]]
        ok[i] = abs(z[i] - np.median(nbrs)) <= 5.0
    return a[ok], a[~ok]


def plan_y(x):
    """Bottom-view plan -> model Y (mm). The photo y_min side = LATERAL [D]: the y_max side has a 10.5 mm concave waist
    (medial arch) and its widest point further forward (big-toe ball); the y_min side is almost straight.
    Pixel edge convention: width = y_max - y_min + 1 px (forefoot width 107.9 = lab)."""
    p = np.array(DATA["sole_plan_profile"], float)
    c = (p[:, 1].min() + p[:, 2].max() + PX) / 2
    ymin, ymax = np.interp(x, p[:, 0], p[:, 1]), np.interp(x, p[:, 0], p[:, 2]) + PX
    return c - (ymin + ymax) / 2, (ymax - ymin) / 2  # center Y, half width


def plan_data_y():
    """Raw plan polygon in model Y: (x, Y_bottom, Y_top) for QC AM-02."""
    p = np.array(DATA["sole_plan_profile"], float)
    c = (p[:, 1].min() + p[:, 2].max() + PX) / 2
    return p[:, 0], c - p[:, 2], c - p[:, 1]


def data_window():
    a = np.array(DATA["air_window_lateral"], float)
    return a[:, 0], a[:, 1], a[:, 2]


def data_window_bbox():
    x, zb, zt = data_window()
    return float(x.min()), float(x.max()), float(zb.min()), float(zt.max())


def window_polygon(shift=0.0):
    """Window outline (x, z) from data: raw bottom edge; top edge = max within +-4 mm (the 19.7-21.8 mm notches
    at x 200-204/220-229 are visible capsule dividers, not the window edge); the data gap at x 206-216 is interpolated;
    ends closed 1 mm outside the data columns (columns < 3 mm are not detected by extraction)."""
    x, zb, zt = data_window()
    top = np.array([zt[np.abs(x - xi) <= 4.0].max() for xi in x])
    top[0], top[-1] = zt[0], zt[-1]  # end columns = rounded corners
    bottom = list(zip(x, zb))
    cap = lambda i, d: (x[i] + d, (zb[i] + zt[i]) / 2)
    poly = [cap(0, -1.0)] + bottom + [cap(-1, 1.0)] + list(zip(x[::-1], top[::-1]))
    return [(px + shift, pz) for px, pz in poly]


def swoosh_polygon(side):
    a = np.array(PANEL[side]["swoosh"], float)
    return a[:, 0], a[:, 1], a[:, 2]
