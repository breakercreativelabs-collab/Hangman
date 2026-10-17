"""I/O: path repo (selalu absolut, C-10), opsi CLI, baca/tulis PNG-JPG, resize numpy, JSON."""
import json
import os

import bpy
import numpy as np

AKAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def path_repo(*bagian):
    """Path absolut di dalam repo (C-10: bpy gagal senyap menulis ke path relatif)."""
    return os.path.join(AKAR, *bagian)


def artefak(*bagian):
    """Path di artefak/ (di-ignore): .blend, render mentah, MP4. Semua bisa dibuat ulang lewat CLI."""
    return path_repo("artefak", *bagian)


def proyek(nama, *bagian):
    """Path di proyek/<nama>/ (konfigurasi + data referensi + ATURAN_QC + hasil kecil)."""
    return path_repo("proyek", nama, *bagian)


def opsi(argv, bawaan):
    """Pasangan '--kunci nilai' -> dict (dimulai dari salinan `bawaan`). Nilai selalu string, seperti skrip lama."""
    o = dict(bawaan)
    for i in range(0, len(argv) - 1, 2):
        o[argv[i].lstrip("-")] = argv[i + 1]
    return o


def baca_rgba(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, "f")
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)  # baris bawah dulu (konvensi Blender)


def baca_png(path):
    """RGB (H, W, 3), baris bawah dulu (konvensi Blender)."""
    return baca_rgba(path)[:, :, :3]


def ubah_ukuran(img, tinggi, lebar=None):
    """Resize bilinear sederhana (numpy). Tanpa `lebar`, rasio dijaga."""
    h, w = img.shape[:2]
    lebar = lebar or max(1, round(w * tinggi / h))
    ys, xs = np.linspace(0, h - 1, tinggi), np.linspace(0, w - 1, lebar)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)
    wy = (ys - y0).reshape(-1, 1, *([1] * (img.ndim - 2)))
    wx = (xs - x0).reshape(1, -1, *([1] * (img.ndim - 2)))
    a = img[y0][:, x0] * (1 - wx) + img[y0][:, x1] * wx
    b = img[y1][:, x0] * (1 - wx) + img[y1][:, x1] * wx
    return a * (1 - wy) + b * wy


def simpan_gambar(path, rgb, nama="gambar", kualitas_jpg=85):
    """rgb: (H, W, 3) nilai tampilan, baris 0 = bawah. Format dari ekstensi: .png atau .jpg/.jpeg (kualitas 85).
    C-10: Image.save() dengan path relatif melapor sukses tetapi tidak menulis file, jadi path dibuat absolut dan
    keberadaan file dicek."""
    H, W, _ = rgb.shape
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = bpy.data.images.new(nama, W, H, alpha=False)
    img.pixels.foreach_set(np.concatenate([np.clip(rgb, 0, 1), np.ones((H, W, 1), "f")], 2).astype("f").ravel())
    jpg = path.lower().endswith((".jpg", ".jpeg"))
    img.filepath_raw, img.file_format = path, "JPEG" if jpg else "PNG"
    if jpg:
        img.save(quality=kualitas_jpg)
    else:
        img.save()
    bpy.data.images.remove(img)
    if not os.path.isfile(path):
        raise RuntimeError(f"gambar tidak tertulis: {path}")
    return path


def tulis_json(path, data, indent=1):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent, default=float)
    return path
