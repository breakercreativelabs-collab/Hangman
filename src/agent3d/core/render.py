"""Render: device selection (GPU -> CPU), standard Cycles test/final settings, still renders to absolute paths (C-10)."""
import os

import bpy

QUALITY = {  # test = cloud CPU (<= 800 px, low samples); final = RTX laptop. Modules may add keys (e.g. "mini")
    "test": dict(scale=1 / 3, sample=24),
    "final": dict(scale=1.0, sample=256),
}


def select_device(order=("OPTIX", "CUDA", "HIP", "ONEAPI")):
    """GPU if available (OptiX -> CUDA -> HIP -> oneAPI), otherwise CPU. HEGEMONI_DEVICE=CPU forces CPU."""
    sc = bpy.context.scene
    prefs = bpy.context.preferences.addons["cycles"].preferences
    if os.environ.get("HEGEMONI_DEVICE", "").upper() != "CPU":
        for t in order:
            try:
                prefs.compute_device_type = t
            except TypeError:
                continue
            prefs.get_devices()
            if any(d.type == t for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == t
                sc.cycles.device = "GPU"
                return t
    try:
        prefs.compute_device_type = "NONE"
    except TypeError:
        pass
    sc.cycles.device = "CPU"
    return "CPU"


def setup_render(quality="test"):
    """Standard Cycles settings (product shot, model QC). Returns the device used."""
    sc, q = bpy.context.scene, QUALITY[quality]
    sc.cycles.samples = q["sample"]
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces, sc.cycles.glossy_bounces = 10, 4
    sc.cycles.transmission_bounces, sc.cycles.transparent_max_bounces = 10, 8
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc["quality"] = quality
    return select_device()


def render_image(cam, path, w, h, sample, transparent):
    """Render a still from camera `cam` to PNG (w x h, `sample`, optional transparent film). Fails hard if not written."""
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    sc.cycles.samples = sample
    sc.render.filepath = os.path.abspath(path)  # C-10
    bpy.ops.render.render(write_still=True)
    if not os.path.isfile(sc.render.filepath):
        raise RuntimeError(f"render was not written: {path}")
    return sc.render.filepath


def render_frame(path, frame):
    """Render frame `frame` with the current scene camera & settings (markers switch the camera)."""
    sc = bpy.context.scene
    sc.frame_set(frame)
    sc.render.filepath = os.path.abspath(path)  # C-10
    bpy.ops.render.render(write_still=True)
    if not os.path.isfile(sc.render.filepath):
        raise RuntimeError(f"render was not written: {path}")
    return sc.render.filepath
