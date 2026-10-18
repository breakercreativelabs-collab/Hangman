"""Extract panel DATA from photos with alpha via COLOR CLASSES (generic for any colorway; photos stay in references/).

The AM1 luma thresholds (dark < 0.35 / mudguard < 0.45 / bright >= 0.6) only work for a black/white colorway: on AM90
the sky-blue mudguard has luma 0.57 (not "dark") and the pale Hydrogen is almost as bright as white. Here each pixel
is classified by ORDERED rules in project.toml `[[extraction.classes]]` (CIELAB L*, C*, a*, b*; the first matching
rule wins). C* (chroma) and b* barely change under shadow, so white/pale/saturated separate cleanly; L* is only used
to split two saturated blues or black.

  blender -b --factory-startup -P blender_cli.py -- reference_modeling extract_class --ref <folder> [--project am90]

Output `projects/<id>/<data.classes>` (mm, same axes as contour: x from the toe tip, z from the ground):
- per side: `midsole_top_line` [x, z], `window` [x, z_bottom, z_top] (longest contiguous run), `component`
  {classes: [{area_mm2, bbox, center, polygon {outer, hole}}]} (components split by `separation_mm` erosion, polygon.py)
- the midsole line + window are also merged into the contour reference JSON (key `line_mudguard_bottom_<side>` = top
  midsole line, and `window_air_<side>`; same key names as AM1 so the sole recipe works unchanged).
The class map + line overlay (for a one-time eye check) is saved in the photo folder (references/), not the repo.
"""
import json
import os

import numpy as np

from .file import write_json_compact
from .photo import read_photo
from .panel import box_mean
from .polygon import polygon_mm

STEP = 2  # 3144 px -> 1572 px (~0.19 mm/px)


# ---------------- color ----------------
def srgb_lab(rgb):
    """sRGB 0..1 (display values) -> CIELAB (D65)."""
    c = np.clip(rgb, 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def classification(rgb, m, rules):
    """rules: list of dicts {name, L=[lo, hi], C=[..], a=[..], b=[..]} (limits optional). Returns the index map
    (-1 = background, len(rules) = 'other') and the list of names."""
    lab = srgb_lab(rgb[m])
    fit = dict(L=lab[:, 0], a=lab[:, 1], b=lab[:, 2], C=np.hypot(lab[:, 1], lab[:, 2]))
    class_idx = np.full(len(lab), len(rules), np.int32)
    free = np.ones(len(lab), bool)
    for i, a in enumerate(rules):
        ok = free.copy()
        for k in ("L", "C", "a", "b"):
            if k in a:
                lo, hi = a[k]
                ok &= (fit[k] >= lo) & (fit[k] < hi)
        class_idx[ok] = i
        free &= ~ok
    mapping = np.full(m.shape, -1, np.int32)
    mapping[m] = class_idx
    return mapping, [a["name"] for a in rules] + ["other"]


def majority(mapping, n, r):
    """Box majority filter (2r+1)^2: stitching, highlights and small shadow edges take the surrounding class."""
    score = np.stack([box_mean((mapping == k).astype(np.float32), r) for k in range(n)])
    out = score.argmax(0).astype(np.int32)
    out[mapping < 0] = -1
    return out


# ---------------- connected components (numpy, no scipy) ----------------
def label_components(m):
    """4-neighbor labeling via minimum propagation + pointer jumping. Returns (label, n); 0 = background."""
    h, w = m.shape
    idx = np.arange(h * w, dtype=np.int64).reshape(h, w)
    BIG = h * w
    lab = np.where(m, idx, BIG)
    while True:
        old = lab
        t = lab.copy()
        for sl_a, sl_b in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                           ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                           ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                           ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
            t[sl_a] = np.minimum(t[sl_a], lab[sl_b])
        t = np.where(m, t, BIG)
        flat = t.ravel()
        contents = flat < BIG
        for _ in range(4):  # pointer jumping: label = label of label
            flat[contents] = flat[flat[contents]]
        lab = flat.reshape(h, w)
        if np.array_equal(lab, old):
            break
    u, inv = np.unique(lab[m], return_inverse=True)
    out = np.zeros((h, w), np.int32)
    out[m] = inv + 1
    return out, len(u)


def split_components(mk, r):
    """Components after a box erosion of r px (breaks thin bridges < 2r, e.g. a swoosh touching a same-colored mudguard),
    then labels are grown back inside the original mask (r + 1 steps, 4-neighbor)."""
    er = box_mean(mk.astype(np.float32), r) > 0.999 if r > 0 else mk
    lab, n = label_components(er)
    for _ in range(r + 2):
        t = lab.copy()
        for a, b in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                     ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                     ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                     ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
            t[a] = np.maximum(t[a], lab[b])
        lab = np.where(mk & (lab == 0), t, lab)
    return lab, n


def bright_color(rgb, mk):
    """Panel base color from the photo [F-photo]: sRGB median of pixels whose L* lies in the panel's 50-90 percentile (the
    key-lit side, without inner shadows or specular highlights). Display hex, compared by AM-15 in the neutral render."""
    if mk.sum() < 50:
        return None
    px = rgb[mk]
    L = srgb_lab(px)[:, 0]
    lo, hi = np.percentile(L, [50, 90])
    med = np.median(px[(L >= lo) & (L <= hi)], 0)
    return "#" + "".join("%02X" % int(round(float(np.clip(c, 0, 1)) * 255)) for c in med)


def longest_run(row, gap_mm):
    """Rows [x, ...] sorted by x: keep the longest contiguous run (x spacing <= gap_mm). Small false windows
    (warm shadows at the toe) are dropped."""
    if not row:
        return row
    runs, cur = [], [row[0]]
    for r in row[1:]:
        if r[0] - cur[-1][0] <= gap_mm:
            cur.append(r)
        else:
            runs.append(cur)
            cur = [r]
    runs.append(cur)
    return max(runs, key=lambda u: u[-1][0] - u[0][0])


# ---------------- extraction per side ----------------
def class_process(REF, LENGTH, name, toe_left, ek):
    p = read_photo(REF, name, STEP)  # row 0 = top
    m = p[..., 3] > 0.99
    ys, xs = np.nonzero(m)
    x0, x1, ground = xs.min(), xs.max(), ys.max()
    sk = LENGTH / (x1 - x0 + 1)  # mm/px (same as contour.side_profile)
    to_x = (lambda X: (X - x0) * sk) if toe_left else (lambda X: (x1 - X) * sk)
    to_z = lambda Y: (ground - Y) * sk
    px = lambda mm_: max(1, int(round(mm_ / sk)))
    cfg = ek["class_cfg"]
    rules = ek["classes"]
    map0, name_k = classification(p[..., :3], m, rules)
    mapping = majority(map0, len(name_k), px(cfg.get("majority_mm", 0.6)))
    k_id = {n: i for i, n in enumerate(name_k)}
    ids = lambda entries: [k_id[n] for n in entries if n in k_id]
    k_out, k_mid, k_window_mask = ids(cfg["outsole"]), ids(cfg["midsole"]), ids(cfg["window"])

    # top midsole line + window: scan the layers up from the base of each column (per-column base = toe spring)
    line, window, OUT = [], [], ek["lab"]["outsole_mm"]
    gap_max = px(cfg.get("gap_mm", 1.5))
    for k in range(0, x1 - x0 + 1, px(1.0)):
        X = x0 + k if toe_left else x1 - k
        coll, msk = mapping[:, X], m[:, X]
        base = np.nonzero(msk)[0]
        if not len(base):
            continue
        y = base.max() - px(OUT)  # skip the outsole (lab thickness), then the remaining outsole-colored pixels
        while y > 0 and msk[y] and coll[y] in k_out and coll[y] not in k_mid:
            y -= 1
        if not msk[y] or coll[y] not in k_mid + k_window_mask:
            continue
        mid_bottom, y_top, gap = y, y, 0
        while y > 0 and msk[y]:
            if coll[y] in k_mid or coll[y] in k_window_mask:
                y_top, gap = y, 0
            else:
                gap += 1
                if gap > gap_max:
                    break
            y -= 1
        if (mid_bottom - y_top) * sk < cfg.get("midsole_min_mm", 3.0):
            continue
        line.append([round(to_x(X), 2), round(to_z(y_top), 2)])
        band = coll[y_top:mid_bottom + 1]
        jj = np.nonzero(np.isin(band, k_window_mask))[0]
        if len(jj) * sk >= cfg.get("column_window_mm", 3.0):
            window.append([round(to_x(X), 2), round(to_z(y_top + jj.max()), 2), round(to_z(y_top + jj.min()), 2)])

    if not toe_left:
        window.sort()
    window = longest_run(window, cfg.get("gap_window_mm", 2.5))

    # components per class (split by separation_mm erosion): summary for panel selection; area >= area_min_mm2
    xmm, zmm = to_x(np.arange(m.shape[1])), to_z(np.arange(m.shape[0]))
    comps, mask_k = {}, {}
    for nk in cfg.get("class_panels", []):
        if nk not in k_id:
            continue
        lab_k, n = split_components(mapping == k_id[nk], int(round(cfg.get("separation_mm", 0.0) / sk)))
        area = np.bincount(lab_k.ravel(), minlength=n + 1)[1:] * sk * sk
        entries = []
        for i in np.nonzero(area >= cfg.get("area_min_mm2", 20.0))[0]:
            Ys, Xs = np.nonzero(lab_k == i + 1)
            xa, za = to_x(Xs), to_z(Ys)
            entries.append(dict(id=int(i + 1), area_mm2=round(float(area[i]), 1),
                               bbox=[round(float(xa.min()), 1), round(float(xa.max()), 1),
                                     round(float(za.min()), 1), round(float(za.max()), 1)],
                               center=[round(float(xa.mean()), 1), round(float(za.mean()), 1)]))
        comps[nk] = sorted(entries, key=lambda d: -d["area_mm2"])
        mask_k[nk] = lab_k

    # panel = union of selected components (project.toml [[extraction.panel]]): classes, component center zone, area range,
    # optional box cut, morphological closing, hole filling -> polygon per resulting component (mm)
    def box(b):
        return (((xmm >= b[0]) & (xmm <= b[1]))[None, :]) & (((zmm >= b[2]) & (zmm <= b[3]))[:, None])
    panel = {}
    side = "lateral" if toe_left else "medial"
    for sp in ek.get("panel", []):
        zone = sp.get(f"zone_{side}", sp["zone"])
        lo, hi = sp.get("area", [0.0, 1e9])
        mk = np.zeros(m.shape, bool)
        for nk in sp["classes"]:
            for c in comps.get(nk, []):
                if zone[0] <= c["center"][0] <= zone[1] and zone[2] <= c["center"][1] <= zone[3] and lo <= c["area_mm2"] <= hi:
                    mk |= mask_k[nk] == c["id"]
        if "cuts" in sp:
            mk &= box(sp.get(f"cuts_{side}", sp["cuts"]))
        r = px(sp["cap_mm"]) if sp.get("cap_mm") else 0
        if r:
            mk = box_mean((box_mean(mk.astype(np.float32), r) > 0).astype(np.float32), r) > 0.999
        rb = px(sp["opening_mm"]) if sp.get("opening_mm") else 0
        if rb:  # opening: narrow spikes (< 2 r) removed
            mk = box_mean((box_mean(mk.astype(np.float32), rb) > 0.999).astype(np.float32), rb) > 0
        outer = sp.get("outer_mm", cfg.get("outer_mm", 0.0))
        if outer:  # panels at the silhouette edge are grown into the background: the prism covers curved edges (toe, heel)
            r_l = px(outer)
            mk |= (box_mean(mk.astype(np.float32), r_l) > 0) & ~m
        if sp.get("fill_holes"):
            outer, _ = label_components(~mk)
            edge = np.unique(np.r_[outer[0], outer[-1], outer[:, 0], outer[:, -1]])
            mk |= ~np.isin(outer, edge[edge > 0]) & (outer > 0)
        lab_p, n = label_components(mk)
        poly_set = []
        for i in range(1, n + 1):
            mi = lab_p == i
            if mi.sum() * sk * sk >= cfg.get("area_min_mm2", 20.0):
                poly_set.append(polygon_mm(mi, to_x, to_z, cfg.get("eps_mm", 0.15), sk, sp.get("hole_min_mm2", 4.0),
                                      cfg.get("chaikin", 0)))
        Ys, Xs = np.nonzero(mk)
        panel[sp["name"]] = dict(role=sp["role"], area_mm2=round(float(mk.sum() * sk * sk), 1), polygon=poly_set,
                                 color=bright_color(p[..., :3], mk & m),
                                 bbox=[round(float(to_x(Xs).min()), 1), round(float(to_x(Xs).max()), 1),
                                       round(float(to_z(Ys).min()), 1), round(float(to_z(Ys).max()), 1)] if len(Xs) else None)
    portion = {n: round(float((mapping == i).sum() / m.sum()), 4) for i, n in enumerate(name_k)}
    zz = to_z(np.arange(m.shape[0]))[:, None] * np.ones((1, m.shape[1]))
    g = np.array(line) if line else np.zeros((0, 2))
    xx = to_x(np.arange(m.shape[1]))[None, :] * np.ones((m.shape[0], 1))
    z_mid = np.interp(xx, g[:, 0], g[:, 1]) if len(g) else np.zeros_like(xx)
    class_color = {n: bright_color(p[..., :3], mapping == i) for i, n in enumerate(name_k)}
    class_color["upper_white"] = bright_color(p[..., :3], (mapping == k_id.get("white", -9)) & (zz > z_mid + 5.0))
    class_color["midsole_white"] = bright_color(p[..., :3], (mapping == k_id.get("white", -9)) & (zz < z_mid - 2.0)
                                                & (zz > OUT + 1.0))
    vis = dict(p=p, m=m, mapping=mapping, to_x=to_x, to_z=to_z, sk=sk, x0=x0, x1=x1, ground=ground, toe_left=toe_left)
    return dict(scale_mm_per_px=round(float(sk), 4), class_portion=portion, class_color=class_color,
                midsole_top_line=line, window=window, component=comps, panel=panel), vis


# ---------------- eye-check overlay ----------------
MAP_COLOR = np.array([[0.90, 0.10, 0.30], [0.24, 0.70, 0.30], [1.00, 0.88, 0.10], [0.00, 0.51, 0.78],
                       [0.96, 0.51, 0.19], [0.57, 0.12, 0.71], [0.27, 0.94, 0.94], [0.94, 0.20, 0.90],
                       [0.82, 0.96, 0.24], [0.98, 0.75, 0.83], [0.00, 0.50, 0.50], [0.67, 0.43, 0.16]])


def overlay(REF, name, result, vis, n_classes):
    """Top: photo + midsole line (red) + window (yellow). Bottom: class map. PNG goes to the photo folder (references/)."""
    import bpy
    p, m, mapping, sk = vis["p"], vis["m"], vis["mapping"], vis["sk"]
    h, w = m.shape
    photo = np.where(m[..., None], p[..., :3], 0.12)
    pk = np.full((h, w, 3), 0.12)
    for i in range(n_classes):
        pk[mapping == i] = MAP_COLOR[i % len(MAP_COLOR)]

    def X_from(x):
        return int(round(vis["x0"] + x / sk)) if vis["toe_left"] else int(round(vis["x1"] - x / sk))

    def Y_from(z):
        return int(round(vis["ground"] - z / sk))

    def points(img, x, z, c, r=2):
        X, Y = X_from(x), Y_from(z)
        img[max(0, Y - r):Y + r + 1, max(0, X - r):X + r + 1] = c
    for x, z in result["midsole_top_line"]:
        points(photo, x, z, (1, 0, 0))
        points(pk, x, z, (1, 1, 1))
    for x, zb, zt in result["window"]:
        for z in (zb, zt):
            points(photo, x, z, (1, 0.9, 0))
    for i, pn in enumerate(result["panel"].values()):  # panel polygon contours on the photo (color per panel; holes black)
        c = MAP_COLOR[(i + 6) % len(MAP_COLOR)]
        for pg in pn["polygon"]:
            for loop, color in [(pg["outer"], c)] + [(L, (0, 0, 0)) for L in pg["hole"]]:
                P = np.array(loop + loop[:1])
                for a, b in zip(P[:-1], P[1:]):
                    for t in np.linspace(0, 1, max(2, int(np.hypot(*(b - a)) / sk))):
                        points(photo, *(a + (b - a) * t), color, 1)
    combined = np.concatenate([photo, pk], 0)[::-1]  # Blender: row 0 = bottom
    rgba = np.concatenate([combined, np.ones(combined.shape[:2] + (1,))], -1).astype(np.float32)
    im = bpy.data.images.new(f"_class_{name}", w, 2 * h)
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw, im.file_format = os.path.join(REF, f"_overlay_class_{name}.png"), "PNG"
    im.save()
    bpy.data.images.remove(im)


def extract_class(REF, DATA_JSON, OUT, ek):
    """REF: photo folder; DATA_JSON: contour reference (length; midsole line + window merged in); OUT: classes JSON."""
    DATA = json.load(open(DATA_JSON, encoding="utf-8"))
    LENGTH = DATA["calibration"]["outer_length_mm"]
    out = dict(version=ek["class_version"], date=ek["date"], notes=ek["class_notes"], rules=ek["classes"],
               settings=ek["class_cfg"])
    n_classes = len(ek["classes"]) + 1
    for name, toe_left in (("lateral", True), ("medial", False)):
        result, vis = class_process(REF, LENGTH, name, toe_left, ek)
        out[name] = result
        overlay(REF, name, result, vis, n_classes)
        DATA[f"line_mudguard_bottom_{name}"] = result["midsole_top_line"]  # = top midsole line (AM1 key name)
        DATA[f"window_air_{name}"] = result["window"]
        print("CLASS", name, "portion", result["class_portion"], "| line midsole", len(result["midsole_top_line"]),
              "| window columns", len(result["window"]),
              "| component", {k: len(v) for k, v in result["component"].items()},
              "| panel", {k: (v["area_mm2"], len(v["polygon"])) for k, v in result["panel"].items()})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    write_json_compact(OUT, out)
    write_json_compact(DATA_JSON, DATA)
