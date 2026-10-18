"""I/O: repo paths (always absolute, C-10), CLI options, PNG/JPG read/write, numpy resize, JSON."""
import json
import os

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def path_repo(*part):
    """Absolute path inside the repo (C-10: bpy silently fails to write to relative paths)."""
    return os.path.join(ROOT, *part)


def artifact(*part):
    """Path in output/ (git-ignored): .blend, raw renders, MP4. Everything can be regenerated via the CLI."""
    return path_repo("output", *part)


def project(name, *part):
    """Path in projects/<name>/ (configuration + reference data + QC_RULES + small results)."""
    return path_repo("projects", name, *part)


def options(argv, defaults):
    """'--key value' pairs -> dict (starting from a copy of `defaults`). Values are always strings, as in the old scripts."""
    o = dict(defaults)
    for i in range(0, len(argv) - 1, 2):
        o[argv[i].lstrip("-")] = argv[i + 1]
    return o


def read_rgba(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, "f")
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)  # bottom row first (Blender convention)


def read_png(path):
    """RGB (H, W, 3), bottom row first (Blender convention)."""
    return read_rgba(path)[:, :, :3]


def resize(img, height, width=None):
    """Simple bilinear resize (numpy). Without `width`, the aspect ratio is kept."""
    h, w = img.shape[:2]
    width = width or max(1, round(w * height / h))
    ys, xs = np.linspace(0, h - 1, height), np.linspace(0, w - 1, width)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)
    wy = (ys - y0).reshape(-1, 1, *([1] * (img.ndim - 2)))
    wx = (xs - x0).reshape(1, -1, *([1] * (img.ndim - 2)))
    a = img[y0][:, x0] * (1 - wx) + img[y0][:, x1] * wx
    b = img[y1][:, x0] * (1 - wx) + img[y1][:, x1] * wx
    return a * (1 - wy) + b * wy


def save_image(path, rgb, name="image", jpg_quality=85):
    """rgb: (H, W, 3) display values, row 0 = bottom. Format from the extension: .png or .jpg/.jpeg (quality 85).
    C-10: Image.save() with a relative path reports success but writes nothing, so the path is made absolute and
    the file's existence is checked."""
    H, W, _ = rgb.shape
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = bpy.data.images.new(name, W, H, alpha=False)
    img.pixels.foreach_set(np.concatenate([np.clip(rgb, 0, 1), np.ones((H, W, 1), "f")], 2).astype("f").ravel())
    jpg = path.lower().endswith((".jpg", ".jpeg"))
    img.filepath_raw, img.file_format = path, "JPEG" if jpg else "PNG"
    if jpg:
        img.save(quality=jpg_quality)
    else:
        img.save()
    bpy.data.images.remove(img)
    if not os.path.isfile(path):
        raise RuntimeError(f"image was not written: {path}")
    return path


def write_json(path, data, indent=1):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent, default=float)
    return path
