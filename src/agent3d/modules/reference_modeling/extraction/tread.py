"""Extract tread (outsole) DATA from the SOLE photo with alpha: color zones (plan polygons) + groove map (bump), generic.

Zones: sole pixels are classified by the project's color rules (`[[extraction.classes]]`), classes are mapped to zone
roles (`[extraction.tread] zone = {role: [classes, ...]}`), then majority filter, closing, polygons (mm, sole_plan_profile
system: x from the toe tip, y from the top edge of the sole photo). The recipe builds each zone as a prism along Z that
cuts the outsole (panel `base_width = "outsole"`). Groove map: local L* valleys (3 mm box mean - L*, normalized) on a
0.5 mm grid = dark grooves between lugs; saved as a small greyscale PNG (derived data, not a photo) for the tread
material bump.

  blender -b --factory-startup -P blender_cli.py -- reference_modeling extract_tread --ref <folder> [--project am90]
"""
import json
import os

import numpy as np

from .file import write_json_compact
from .photo import read_photo
from .classes import classification, label_components, majority, srgb_lab
from .panel import box_mean
from .polygon import polygon_mm

STEP = 2  # same as contour (mm_per_px_sole is computed at step 2)


def extract_tread(REF, DATA_JSON, OUT_JSON, OUT_PNG, ek):
    import bpy
    DATA = json.load(open(DATA_JSON, encoding="utf-8"))
    sk = DATA["calibration"]["mm_per_px_sole"]
    cfg = ek["tread"]
    p = read_photo(REF, "sole", STEP)
    m = p[..., 3] > 0.99
    ys, xs = np.nonzero(m)
    x0, y0 = xs.min(), ys.min()
    to_x = lambda X: (X - x0) * sk
    to_y = lambda Y: (Y - y0) * sk
    px = lambda v: max(1, int(round(v / sk)))
    map0, name_k = classification(p[..., :3], m, ek["classes"])
    mapping = majority(map0, len(name_k), px(cfg.get("majority_mm", 1.0)))
    k_id = {n: i for i, n in enumerate(name_k)}
    zone = {}
    for role, classes in cfg["zone"].items():
        mk = np.isin(mapping, [k_id[k] for k in classes if k in k_id]) & m
        r = px(cfg.get("cap_mm", 1.0))
        mk = box_mean((box_mean(mk.astype(np.float32), r) > 0).astype(np.float32), r) > 0.999
        if cfg.get("outer_mm"):  # zones at the plan edge are grown into the background: the prism covers the curved outsole wall
            mk |= (box_mean(mk.astype(np.float32), px(cfg["outer_mm"])) > 0) & ~m
        lab, n = label_components(mk)
        poly_set = []
        for i in range(1, n + 1):
            mi = lab == i
            if mi.sum() * sk * sk >= cfg.get("area_min_mm2", 30.0):
                # polygon_mm maps rows via to_z; here a row = plan y (not height)
                poly_set.append(polygon_mm(mi, to_x, to_y, cfg.get("eps_mm", 0.15), sk, 9e9, cfg.get("chaikin", 2)))
        zone[role] = dict(polygon=poly_set, area_mm2=round(float(mk.sum() * sk * sk), 1))
    # groove map on a 0.5 mm grid (row 0 = plan y 0 = top edge of the sole photo)
    L = srgb_lab(np.clip(p[..., :3], 0, 1))[..., 0]
    Lm = np.where(m, L, np.nan)
    mean = box_mean(np.nan_to_num(Lm, nan=float(np.nanmean(Lm))), px(cfg.get("groove_window_mm", 3.0)))
    grooves = np.clip((mean - L) / cfg.get("groove_scale_L", 8.0), 0.0, 1.0) * m
    for x0h, x1h, y0h, y1h in cfg.get("delete", []):  # regions removed from the groove map (e.g. brand text: model = mirror)
        Xh, Yh = to_x(np.arange(m.shape[1])), to_y(np.arange(m.shape[0]))
        grooves[np.ix_((Yh >= y0h) & (Yh <= y1h), (Xh >= x0h) & (Xh <= x1h))] = 0.0
    g = cfg.get("grid_mm", 0.5)
    W = float(to_x(xs.max()) + sk)
    H = float(to_y(ys.max()) + sk)
    gx, gy = np.arange(0.0, W, g), np.arange(0.0, H, g)
    X = np.clip(np.round(x0 + gx / sk).astype(int), 0, m.shape[1] - 1)
    Y = np.clip(np.round(y0 + gy / sk).astype(int), 0, m.shape[0] - 1)
    a = grooves[Y][:, X]
    img = bpy.data.images.new("_tread_grooves", len(gx), len(gy))
    rgba = np.ones((len(gy), len(gx), 4), np.float32)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = a
    img.pixels.foreach_set(rgba[::-1].ravel())  # Blender: row 0 = bottom
    img.filepath_raw, img.file_format = OUT_PNG, "PNG"
    img.save()
    bpy.data.images.remove(img)
    out = dict(version=1, date=ek["date"], notes=cfg.get("notes", ""), zone=zone,
               grooves=dict(png=os.path.basename(OUT_PNG), grid_mm=g, width_mm=round(W, 2), height_mm=round(H, 2),
                         convention="pixel (i, j) = (plan y = i*grid, x = j*grid); PNG row 0 = y 0 (top edge of the sole photo)"))
    write_json_compact(OUT_JSON, out)
    print("TREAD zone", {k: (v["area_mm2"], len(v["polygon"])) for k, v in zone.items()},
          "| grooves", a.shape, "mean", round(float(a.mean()), 3))
