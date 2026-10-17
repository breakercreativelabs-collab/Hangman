"""Render: pilih perangkat (GPU -> CPU), pengaturan Cycles standar uji/final, render still ke path absolut (C-10)."""
import os

import bpy

KUALITAS = {  # uji = cloud CPU (<= 800 px, sampel rendah); final = laptop RTX. Modul boleh menambah kunci (mis. "mini")
    "uji": dict(skala=1 / 3, sampel=24),
    "final": dict(skala=1.0, sampel=256),
}


def pilih_perangkat(urutan=("OPTIX", "CUDA", "HIP", "ONEAPI")):
    """GPU jika ada (OptiX -> CUDA -> HIP -> oneAPI), selain itu CPU. HEGEMONI_DEVICE=CPU memaksa CPU."""
    sc = bpy.context.scene
    prefs = bpy.context.preferences.addons["cycles"].preferences
    if os.environ.get("HEGEMONI_DEVICE", "").upper() != "CPU":
        for t in urutan:
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


def atur_render(kualitas="uji"):
    """Pengaturan Cycles standar (product shot, QC model). Mengembalikan perangkat yang dipakai."""
    sc, q = bpy.context.scene, KUALITAS[kualitas]
    sc.cycles.samples = q["sampel"]
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces, sc.cycles.glossy_bounces = 10, 4
    sc.cycles.transmission_bounces, sc.cycles.transparent_max_bounces = 10, 8
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc["kualitas"] = kualitas
    return pilih_perangkat()


def render_gambar(cam, path, w, h, sampel, transparan):
    """Render still kamera `cam` ke PNG (w x h, `sampel`, film transparan opsional). Gagal keras bila tidak tertulis."""
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.render.film_transparent = transparan
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparan else "RGB"
    sc.cycles.samples = sampel
    sc.render.filepath = os.path.abspath(path)  # C-10
    bpy.ops.render.render(write_still=True)
    if not os.path.isfile(sc.render.filepath):
        raise RuntimeError(f"render tidak tertulis: {path}")
    return sc.render.filepath


def render_frame(path, frame):
    """Render frame `frame` dengan kamera & pengaturan scene saat ini (marker men-switch kamera)."""
    sc = bpy.context.scene
    sc.frame_set(frame)
    sc.render.filepath = os.path.abspath(path)  # C-10
    bpy.ops.render.render(write_still=True)
    if not os.path.isfile(sc.render.filepath):
        raise RuntimeError(f"render tidak tertulis: {path}")
    return sc.render.filepath
