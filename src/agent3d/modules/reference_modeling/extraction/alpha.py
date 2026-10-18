"""Alpha channel analysis of reference photos (in references/<project>, not in the repo).

The product photos (AM1: brand CDN) contain a semi-transparent shadow rectangle behind the shoe, so
alpha > 0 is not the same as the shoe. This script prints the alpha distribution and saves
test masks (to the reference folder, not the repo) for a one-time eye check.
  blender -b --factory-startup -P blender_cli.py -- reference_modeling alpha_analysis --ref <folder_reference>
"""
import os

import bpy
import numpy as np

from .photo import read_photo


def save(REF, name, mask):
    h, w = mask.shape
    rgba = np.zeros((h, w, 4), np.float32)
    rgba[..., :3] = mask[..., None]
    rgba[..., 3] = 1
    im = bpy.data.images.new(name, w, h)
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw, im.file_format = os.path.join(REF, name + ".png"), "PNG"
    im.save()


def alpha_analysis(REF):
    for name in ("lateral", "medial", "top", "heel", "sole"):
        p = read_photo(REF, name, 3, top_first=False)  # row 0 = bottom
        a = p[..., 3]
        q = np.quantile(a[a > 0.01], [0.05, 0.25, 0.5, 0.75, 0.95]) if (a > 0.01).any() else []
        hist = np.histogram(a, bins=[0, 0.01, 0.2, 0.4, 0.6, 0.8, 0.95, 0.99, 1.01])[0] / a.size
        print(f"ALPHA {name}: quantile(a>0.01)={np.round(q, 3).tolist()} hist={np.round(hist, 3).tolist()}")
        save(REF, f"_mask_{name}_a099", (a > 0.99).astype(np.float32))
