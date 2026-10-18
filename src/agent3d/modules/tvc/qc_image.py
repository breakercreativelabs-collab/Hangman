"""QC TV, image/file part: TV-03 black/white/flat frames + listed flashes on the beat, TV-06 WCAG text contrast,
TV-07 video file (fps, resolution, frame count; ffprobe as a cross-check when available)."""
import json
import math
import os
import shutil
import subprocess
from fractions import Fraction

import bpy
import numpy as np

from ...core.io import read_png
from ...core.camera import projection
from ...core.render import render_frame
from ...core.scene import collection
from ...core.color import relative_lum, luma as core_luma
from . import config
from ...core.qc import check
from .qc_scene import THRESHOLD, _text_vertices

# ---------------- image ----------------
def luma_frame(rgb):
    return core_luma(rgb, None)


def test_res(ratio, scale=None):
    """Test resolution per ratio: the 'test' quality scale (animatic 270 x 480) or another scale (contrast 0.375 = 405 x 720)."""
    w, h = config.K["resolution"][ratio]
    s = config.K["quality"]["test"]["scale"] if scale is None else scale
    return round(w * s), round(h * s)


CONTRAST_SCALE = 0.375  # TV-06 contrast render: 405 x 720 / 720 x 405 (<= 800 px, cloud render rule)


def frame_stats(paths):
    L = []
    for p in paths:
        y = luma_frame(read_png(p))
        L.append((float(y.mean()), float(y.std())))
    return np.array(L)


def qc_frame(stat, flash, ratio):
    """TV-03 (pixel): no black/white frame (QC-05 rule) or flat frame (luma std), except listed flashes;
    every luma spike (flash) must be listed and start on the beat."""
    A = THRESHOLD
    m, s = stat[:, 0], stat[:, 1]
    wrong, spike = [], []
    for i in range(len(m)):
        f = i + 1
        neighbor = np.r_[m[max(0, i - 3):i], m[i + 1:i + 4]]
        if m[i] - np.median(neighbor) > A["flash_spike"]:
            spike.append(f)
            if f not in flash:
                wrong.append(f"f{f} unlisted flash")
        if f in flash:
            continue
        if m[i] < A["luma_min"]:
            wrong.append(f"f{f} black {m[i]:.3f}")
        elif m[i] > A["luma_max"]:
            wrong.append(f"f{f} white {m[i]:.3f}")
        elif s[i] < A["std_min"]:
            wrong.append(f"f{f} flat std {s[i]:.4f}")
    initial = [f for f in flash if f - 1 not in flash]
    for f in initial:
        if abs((f - 1) - round((f - 1) / config.BEAT) * config.BEAT) > THRESHOLD["beat_frames"]:
            wrong.append(f"flash f{f} not on the beat")
    non_flash = np.array([i for i in range(len(m)) if i + 1 not in flash])
    return check("TV-03", f"frame_black_empty_{ratio}", len(wrong), not wrong, "= 0 bad frames",
               f"{len(m)} frames; luma {m[non_flash].min():.3f}..{m[non_flash].max():.3f}, std min "
               f"{s[non_flash].min():.4f}; spikes {spike}; listed flashes {sorted(flash)}"
               + ("; " + "; ".join(wrong[:5]) if wrong else ""))


def render_contrast(folder, ratio, frame=None):
    """Render frame `frame` (default: the last) with and without text (same seed & grain), at contrast resolution."""
    frame = frame or config.END_FRAME
    sc = bpy.context.scene
    w0, h0 = sc.render.resolution_x, sc.render.resolution_y
    sc.render.resolution_x, sc.render.resolution_y = test_res(ratio, CONTRAST_SCALE)
    text = list(collection("TEXT").objects)
    a = render_frame(os.path.join(folder, f"contrast_{ratio}_text.png"), frame)
    for o in text:
        o.hide_render = True
    sc.frame_set(frame)
    save = {o.name: o.animation_data.action for o in text}
    for o in text:
        o.animation_data.action = None  # hide_render is keyed: detach the action so the text stays hidden
        o.hide_render = True
    b = render_frame(os.path.join(folder, f"contrast_{ratio}_background.png"), frame)
    for o in text:
        o.animation_data.action = save[o.name]
    sc.render.resolution_x, sc.render.resolution_y = w0, h0
    sc.frame_set(frame)
    return a, b


def qc_contrast(pa, pb, ratio, frame=None):
    """TV-06 (b): WCAG contrast per text group (title, tagline, label): core text pixels = |luma difference between the
    render with and without text| >= 0.5 x p95 of that difference in the text bbox; L text = median of the render with
    text, L background = median of the render without text on the same pixels (after the compositor: grain, vignette)."""
    frame = frame or config.END_FRAME
    sc = bpy.context.scene
    sc.frame_set(frame)
    A, B = read_png(pa), read_png(pb)
    h, w = A.shape[:2]
    dg = bpy.context.evaluated_depsgraph_get()
    cam = bpy.data.objects["CAM_" + config.K["text"]["shot"]]
    grp = {"title": ["TX_title"], "tagline": [o.name for o in collection("TEXT").objects if o.name.startswith("TX_tag")],
           "label": ["TX_label"]}
    dif = np.abs(luma_frame(A) - luma_frame(B))
    result, value = True, {}
    for k, name in grp.items():
        u, v, _ = projection(cam, np.concatenate([_text_vertices(bpy.data.objects[n], dg) for n in name]))
        c0, c1 = max(0, int(u.min() * w) - 2), min(w, int(math.ceil(u.max() * w)) + 2)
        r0, r1 = max(0, int(v.min() * h) - 2), min(h, int(math.ceil(v.max() * h)) + 2)
        reg = dif[r0:r1, c0:c1]
        if reg.size == 0 or reg.max() < 0.02:
            value[k], result = 0.0, False
            continue
        core = reg >= 0.5 * np.percentile(reg, 95)
        lt = float(np.median(relative_lum(A[r0:r1, c0:c1][core])))
        lb = float(np.median(relative_lum(B[r0:r1, c0:c1][core])))
        kr = (max(lt, lb) + 0.05) / (min(lt, lb) + 0.05)
        value[k] = round(kr, 2)
        result &= kr >= THRESHOLD["contrast_min"]
    return check("TV-06", f"contrast_text_min_{ratio}", min(value.values()), result, f">= {THRESHOLD['contrast_min']}:1 (WCAG AA)",
               f"frame {frame} {w}x{h}: " + ", ".join(f"{k} {v}" for k, v in value.items()))


def info_video(path):
    """fps, (w, h), frame count of a video file (Blender MovieClip; ffprobe as a cross-check when available)."""
    clip = bpy.data.movieclips.load(os.path.abspath(path), check_existing=False)
    fps, size, n = float(clip.fps), tuple(clip.size), int(clip.frame_duration)
    bpy.data.movieclips.remove(clip)
    probe = None
    if shutil.which("ffprobe"):
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                            "stream=r_frame_rate,width,height,nb_read_frames,codec_name", "-of", "json", path],
                           capture_output=True, text=True)
        try:
            probe = json.loads(r.stdout)["streams"][0]
        except (ValueError, KeyError, IndexError):
            probe = None
    return fps, size, n, probe


def qc_video(path, res, ratio):
    """TV-07: video file: fps and resolution = plan, duration = planned frame count (tvc.toml)."""
    if not os.path.isfile(path):
        return check("TV-07", f"video_{ratio}", "missing", False, "exists", path)
    fps, size, n, probe = info_video(path)
    n_target = round(config.DURATION * config.FPS)
    ok = abs(fps - config.FPS) < 1e-3 and size == tuple(res) and n == n_target
    if probe:
        pf = float(Fraction(probe["r_frame_rate"]))
        ok &= abs(pf - config.FPS) < 1e-3 and (probe["width"], probe["height"]) == tuple(res) and int(probe["nb_read_frames"]) == n_target
    return check("TV-07", f"video_{ratio}", f"{fps:g} fps {size[0]}x{size[1]} {n} f", ok,
               f"{config.FPS} fps, {res[0]}x{res[1]}, {n_target} frames ({config.DURATION:g} s)",
               f"{os.path.basename(path)} {os.path.getsize(path) / 1e6:.2f} MB, {n / max(fps, 1e-6):.2f} s"
               + (f"; ffprobe {probe['codec_name']} {probe['r_frame_rate']} {probe['width']}x{probe['height']} "
                  f"{probe['nb_read_frames']} f" if probe else "; ffprobe not available"))

