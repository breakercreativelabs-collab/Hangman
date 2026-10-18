"""Read a reference photo (PNG with alpha) as a float RGBA array, with a sampling step."""
import os

import bpy
import numpy as np


def read_photo(folder, name, step=2, top_first=True):
    """<folder>/<name>.png -> array (h, w, 4) sampled every `step` px. top_first: row 0 = image top
    (contour/panel extraction convention); False: row 0 = bottom (Blender convention)."""
    im = bpy.data.images.load(os.path.join(folder, name + ".png"))
    w, h = im.size
    p = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(p)
    bpy.data.images.remove(im)
    p = p.reshape(h, w, 4)
    return (p[::-1] if top_first else p)[::step, ::step]
