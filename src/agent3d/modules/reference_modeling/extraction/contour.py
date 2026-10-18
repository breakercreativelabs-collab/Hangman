"""Extract shoe reference DATA from product photos (photos stay in references/, never in the repo).

The output `reference_am1.json` holds only derived numbers (mm): side_view silhouette profiles,
the top-view width profile, panel lines from color segmentation, and the scale calibration.
Principle: Python computes, Claude decides. The 3D model is built from these numbers, then
checked with a per-view silhouette IoU QC.

  blender -b --factory-startup -P blender_cli.py -- reference_modeling extract_contour --ref <folder> [--project am1]
      [--out <json>]   (default: projects/<id>/<data.reference>; settings & lab sizes: project.toml [extraction])

Axis convention (same as product_shot): X = length (0 = toe tip, + toward the heel),
Y = width (+ = the side visible in the 'lateral' photo), Z = height (0 = ground).
"""
import json
import os

import numpy as np

from .photo import read_photo


def extract_contour(REF, OUT, ek):
    """REF: photo folder (lateral/medial/top/heel/sole .png with alpha); OUT: output JSON; ek: project.toml [extraction]."""
    STEP = 2  # 3144 px -> 1572 px

    # Independent lab sizes from project.toml [extraction.lab] (AM1: RunRepeat US M 9)
    LAB = dict(ek["lab"])


    def read(name):
        return read_photo(REF, name, STEP)  # row 0 = image top

    def box(m):
        ys, xs = np.nonzero(m)
        return xs.min(), xs.max(), ys.min(), ys.max()


    def split_pair(m):
        """The top/heel views show a pair of shoes: split at the middle of the longest run of empty columns."""
        coll = m.sum(0)
        x0, x1, _, _ = box(m)
        empty = np.nonzero(coll[x0:x1] == 0)[0] + x0
        if not len(empty):
            raise RuntimeError("pair not separable")
        middle = int(np.median(empty))
        left, right = m.copy(), m.copy()
        left[:, middle:] = False
        right[:, :middle] = False
        return left, right


    # ---------- 1. Scale calibration from the SOLE photo (sole plane ~parallel to the camera, minimal perspective) ----------
    # The top-view photo is NOT used for scale: collar/heel are closer to the camera and appear larger
    # (test: heel width 95.9 mm vs lab 81.8; length 313 mm vs an estimated ~297).
    # Heel/forefoot silhouette ratio = 0.89 in both sole AND top, lab 0.758 -> the lab heel width is measured at a
    # different point, so only the forefoot width (widest point of the shoe = midsole) is used. Status: [D] +-2%.
    sole = read("sole")
    m_sole = sole[..., 3] > 0.99
    x0, x1, y0, y1 = box(m_sole)  # toe on the left, heel on the right
    length_px = x1 - x0 + 1
    col_width = np.array([m_sole[:, x].sum() for x in range(x0, x1 + 1)], np.float32)
    sole_scale = LAB["forefoot_width_mm"] / col_width[: length_px // 2].max()
    length_mm = length_px * sole_scale
    heel_width_mm = float(col_width[length_px // 2:].max() * sole_scale)

    # bottom-view profile (= outer plan line): x from the toe (mm), y_min/y_max from the top image edge (mm)
    top_profile = []
    for k in range(0, length_px, max(1, int(round(2.0 / sole_scale)))):
        ys = np.nonzero(m_sole[:, x0 + k])[0]
        if len(ys):
            top_profile.append([round(k * sole_scale, 2), round((ys.min() - y0) * sole_scale, 2), round((ys.max() - y0) * sole_scale, 2)])

    # ---------- 2. side_view: silhouette top/bottom per column ----------
    def side_profile(name, toe_left=True):
        p = read(name)
        m = p[..., 3] > 0.99
        x0, x1, y0, y1 = box(m)
        sk = length_mm / (x1 - x0 + 1)  # scale from the top-view length
        ground = y1  # lowest silhouette point = ground
        result = []
        for k in range(0, x1 - x0 + 1, max(1, int(round(2.0 / sk)))):
            x = x0 + k if toe_left else x1 - k
            ys = np.nonzero(m[:, x])[0]
            if not len(ys):
                continue
            result.append([round(k * sk, 2), round((ground - ys.max()) * sk, 2), round((ground - ys.min()) * sk, 2)])
        return p, m, (x0, x1, y0, y1), sk, result


    p_lat, m_lat, bb_lat, sk_lat, prof_lat = side_profile("lateral", toe_left=True)
    p_med, m_med, bb_med, sk_med, prof_med = side_profile("medial", toe_left=False)
    heel_height_mm = max(z for x, _, z in prof_lat if x > 0.7 * length_mm)

    # ---------- 3. Panel lines from color (colorway FD9082-107: black = mudguard/swoosh, white = midsole) ----------
    def panel_line(p, m, bb, sk, toe_left=True):
        """Scan each column from the ground up: outsole -> bright midsole -> dark mudguard.
        v1 (luma threshold < 0.08) caught only the stitching, not the black suede -> v2 uses the layer order.
        Returns the mudguard top/bottom limits and the Air window extent (non-bright pixels inside the midsole)."""
        x0, x1, y0, y1 = bb
        rgb, ground = p[..., :3], y1
        luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        mm = lambda n: max(1, int(round(n / sk)))
        mud_top, mud_bottom, window = [], [], []
        for k in range(0, x1 - x0 + 1, mm(2.0)):
            x = x0 + k if toe_left else x1 - k
            coll, msk = luma[:, x], m[:, x]
            base = np.nonzero(msk)[0]
            if not len(base):
                continue
            y = base.max() - mm(LAB["outsole_mm"])     # base per column (toe spring), then skip the outsole
            while y > y0 and msk[y] and coll[y] < 0.6:   # remaining dark outsole
                y -= 1
            if not msk[y] or coll[y] < 0.6:
                continue
            mid_bottom = y
            while y > y0 and msk[y] and not (coll[y - mm(3.0):y + 1] < 0.35).all():  # midsole (window gap allowed)
                y -= 1
            mid_top = y
            while y > y0 and msk[y] and coll[y] < 0.45:  # dark mudguard
                y -= 1
            if mid_top - y < mm(3.0):
                continue
            z = lambda yy: round((ground - yy) * sk, 2)
            mud_bottom.append([round(k * sk, 2), z(mid_top)])
            mud_top.append([round(k * sk, 2), z(y)])
            gap = np.nonzero(coll[mid_top + mm(2.0):mid_bottom - mm(2.0)] < 0.6)[0]
            if len(gap) >= mm(3.0):
                window.append([round(k * sk, 2), z(mid_top + mm(2.0) + gap.max()), z(mid_top + mm(2.0) + gap.min())])
        return mud_top, mud_bottom, window


    if ek.get("luma_line", True):  # AM1 (black/white): lines from a luma threshold; other colorways: extract_class
        mud_top_lat, mud_bottom_lat, window_lat = panel_line(p_lat, m_lat, bb_lat, sk_lat, True)

    calib = dict(method="[D] forefoot width of SOLE silhouette = %s mm (lab midsole); +-2%%" % ("%g" % LAB["forefoot_width_mm"]).replace(".", ","),
               mm_per_px_sole=round(float(sole_scale), 4), outer_length_mm=round(float(length_mm), 1),
               heel_width_silhouette_mm=round(heel_width_mm, 1))
    if "internal_length_mm" in LAB:  # AM1
        calib.update(lab_heel_width_notes="81.8 mm measured at a different point (silhouette ratio 0.89 vs lab 0.758 in 2 photos)",
                   check_outer_vs_internal_length_mm=round(float(length_mm - LAB["internal_length_mm"]), 1))
    else:  # cross-scale check: heel/forefoot width ratio, sole silhouette vs lab (two independent lab sizes)
        r_silhouette = heel_width_mm / LAB["forefoot_width_mm"]
        r_lab = LAB["heel_width_mm"] / LAB["forefoot_width_mm"]
        calib.update(heel_forefoot_ratio_silhouette=round(float(r_silhouette), 4), heel_forefoot_ratio_lab=round(float(r_lab), 4),
                   ratio_delta_pct=round(float(100 * (r_silhouette / r_lab - 1)), 2))
    calib["heel_max_height_mm"] = round(float(heel_height_mm), 1)
    data = dict(
        version=ek["contour_version"], date=ek["date"],
        notes=ek["contour_notes"],
        photo_source={k: ek["photo_source_pattern"].format(v) for k, v in ek["photo_source"].items()},
        calibration=calib,
        convention="x = mm from toe tip; z = mm from ground; sole_plan_profile: [x, y_min, y_max] mm (bottom view)",
        side_profile_lateral=prof_lat,   # [x, z_bottom, z_top]
        side_profile_medial=prof_med,
        sole_plan_profile=top_profile,       # [x, y_min, y_max] from the sole photo
    )
    # lab key: AM1 uses the old name (data.py reads both)
    data["lab_runrepeat_us9" if "internal_length_mm" in LAB else "lab"] = LAB
    if ek.get("luma_line", True):
        data.update(mudguard_top_line_lateral=mud_top_lat,    # [x, z] top limit of the lower black panel
                    mudguard_bottom_line_lateral=mud_bottom_lat,  # [x, z] = top of the white midsole
                    air_window_lateral=window_lat)  # [x, z_bottom, z_top] non-bright pixels inside the midsole
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1, default=float)
    print("CALIBRATION", json.dumps(data["calibration"]))
    print("COUNT", len(prof_lat), len(prof_med), len(top_profile))
