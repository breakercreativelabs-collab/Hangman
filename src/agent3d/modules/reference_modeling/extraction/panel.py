"""Extract shoe upper panel DATA for M2 modeling (photos stay in references/, never in the repo).

Output `reference_am1_panel.json` (mm, same axis system as reference_am1.json):
- `dark_<side>`: per x column (1 mm), the list of dark z spans (mudguard, swoosh, collar, lace holes)
- `swoosh_<side>`: [x, z_bottom, z_top] of the largest dark component above the mudguard line and below the collar
- `edge_line_<side>`: [x, z] points of panel edge/stitching lines (thin luma valleys in bright areas)
- `lace_hole_<side>`: [x, z] centers of small dark blobs in the top band (eyelets)
Grey suede vs white mesh is NOT separated by color (they overlap because of shadows) but by edge lines.

  blender -b --factory-startup -P blender_cli.py -- reference_modeling extract_panel --ref <folder> [--project am1]
      [--data <reference.json>] [--out <json>]   (default: project data files)
"""
import json

import numpy as np

from .photo import read_photo


def box_mean(img, r):
    """Box mean (2r+1)^2 via an integral image."""
    pad = np.pad(img, r + 1, mode="edge")
    ii = pad.cumsum(0).cumsum(1)
    k = 2 * r + 1
    s = ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]
    return s[: img.shape[0], : img.shape[1]] / (k * k)


def label(m):
    """4-connected components (simple BFS, enough for ~1500 px masks)."""
    lab = np.zeros(m.shape, np.int32)
    n = 0
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        n += 1
        stack = [(y0, x0)]
        lab[y0, x0] = n
        while stack:
            y, x = stack.pop()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < m.shape[0] and 0 <= xx < m.shape[1] and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    stack.append((yy, xx))
    return lab, n


def process(REF, LENGTH, name, toe_left, mud_line):
    p = read_photo(REF, name, 2)  # row 0 = top
    m = p[..., 3] > 0.99
    ys, xs = np.nonzero(m)
    x0, x1, ground = xs.min(), xs.max(), ys.max()
    sk = LENGTH / (x1 - x0 + 1)  # mm/px
    luma = 0.2126 * p[..., 0] + 0.7152 * p[..., 1] + 0.0722 * p[..., 2]
    to_x = (lambda X: (X - x0) * sk) if toe_left else (lambda X: (x1 - X) * sk)
    to_z = lambda Y: (ground - Y) * sk
    dark = m & (luma < 0.35)
    bright = m & (luma >= 0.6)
    # edge lines: thin luma valleys (< 1.5 mm local mean - 0.07) inside bright areas
    hit_loc = box_mean(np.where(m, luma, 0.9), max(1, int(round(1.5 / sk))))
    edge = bright & (luma < hit_loc - 0.07)
    # dark spans per 1 mm column
    dark_cols = []
    for xm in np.arange(0, LENGTH, 1.0):
        X = int(round(x0 + xm / sk)) if toe_left else int(round(x1 - xm / sk))
        if not (0 <= X < m.shape[1]):
            continue
        run, start = [], None
        coll = dark[:, X]
        for Y in range(m.shape[0]):
            if coll[Y] and start is None:
                start = Y
            elif not coll[Y] and start is not None:
                if (Y - start) * sk >= 0.8:
                    run.append([round(to_z(Y - 1), 1), round(to_z(start), 1)])
                start = None
        dark_cols.append([round(float(xm), 1), run])
    # swoosh: largest dark component lying fully above the mudguard line (+3 mm) and below 85% of the heel height
    gm = np.array(mud_line, float)
    z_mud = lambda xmm: np.interp(xmm, gm[:, 0], gm[:, 1])
    kand = dark.copy()
    Ys, Xs = np.nonzero(kand)
    for Y, X in zip(Ys, Xs):
        xmm, zmm = to_x(X), to_z(Y)
        if zmm < z_mud(xmm) + 3.0 or zmm > 95.0:
            kand[Y, X] = False
    lab, n = label(kand)
    swoosh = []
    if n:
        size = np.bincount(lab.ravel())[1:]
        sw = lab == (int(np.argmax(size)) + 1)
        for X in np.unique(np.nonzero(sw)[1])[:: max(1, int(round(1.0 / sk)))]:
            zs = np.nonzero(sw[:, X])[0]
            swoosh.append([round(to_x(X), 1), round(to_z(zs.max()), 1), round(to_z(zs.min()), 1)])
        swoosh.sort()
    # lace holes: small dark blobs (2-40 mm^2) in the top band (z > 70 mm)
    small = dark.copy()
    Ys, Xs = np.nonzero(small)
    for Y, X in zip(Ys, Xs):
        if to_z(Y) < 70.0:
            small[Y, X] = False
    lab2, n2 = label(small)
    hole = []
    for i in range(1, n2 + 1):
        Yi, Xi = np.nonzero(lab2 == i)
        area = len(Yi) * sk * sk
        if 2.0 <= area <= 40.0:
            hole.append([round(to_x(Xi.mean()), 1), round(to_z(Yi.mean()), 1), round(area, 1)])
    hole.sort()
    Yt, Xt = np.nonzero(edge)
    cell = np.unique(np.c_[np.round(to_x(Xt)), np.round(to_z(Yt))], axis=0)  # dedup grid 1 mm
    return dict(dark=dark_cols, swoosh=swoosh, edge_line=cell.astype(float).tolist(), lace_hole=hole,
                scale_mm_per_px=round(float(sk), 4))


def extract_panel(REF, DATA_JSON, OUT, ek):
    """REF: photo folder; DATA_JSON: contour reference (mudguard line, length); OUT: panel JSON; ek: [extraction]."""
    DATA = json.load(open(DATA_JSON, encoding="utf-8"))
    LENGTH = DATA["calibration"]["outer_length_mm"]
    lat = process(REF, LENGTH, "lateral", True, DATA["mudguard_top_line_lateral"])
    med = process(REF, LENGTH, "medial", False, DATA["mudguard_top_line_lateral"])  # medial mudguard line ~ lateral [D]
    out = dict(version=ek["panel_version"], date=ek["date"], notes=ek["panel_notes"], lateral=lat, medial=med)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, default=float)
    for k, v in (("lateral", lat), ("medial", med)):
        print("PANEL", k, "swoosh columns", len(v["swoosh"]), "x", v["swoosh"][0][0] if v["swoosh"] else None, "-",
              v["swoosh"][-1][0] if v["swoosh"] else None, "| edge points", len(v["edge_line"]), "| hole", len(v["lace_hole"]))
