"""QC TV bagian gambar/berkas: TV-03 frame hitam/putih/rata + flash tercatat di ketukan, TV-06 kontras WCAG teks,
TV-07 berkas video (fps, resolusi, jumlah frame; ffprobe bila ada sebagai cek silang)."""
import json
import math
import os
import shutil
import subprocess
from fractions import Fraction

import bpy
import numpy as np

from ...inti.io import baca_png
from ...inti.kamera import proyeksi
from ...inti.render import render_frame
from ...inti.scene import koleksi
from ...inti.warna import lum_relatif, luma as luma_inti
from . import konfig
from ...inti.qc import cek
from .qc_scene import AMBANG, _vertex_teks

# ---------------- gambar ----------------
def luma_frame(rgb):
    return luma_inti(rgb, None)


def res_uji(rasio, skala=None):
    """Resolusi uji per rasio: skala kualitas 'uji' (animatic 270 x 480) atau skala lain (kontras 0,375 = 405 x 720)."""
    w, h = konfig.K["resolusi"][rasio]
    s = konfig.K["kualitas"]["uji"]["skala"] if skala is None else skala
    return round(w * s), round(h * s)


KONTRAS_SKALA = 0.375  # render kontras TV-06: 405 x 720 / 720 x 405 (<= 800 px, aturan render cloud)


def statistik_frame(paths):
    L = []
    for p in paths:
        y = luma_frame(baca_png(p))
        L.append((float(y.mean()), float(y.std())))
    return np.array(L)


def qc_frame(stat, flash, rasio):
    """TV-03 (piksel): tidak ada frame hitam/putih (aturan QC-05) atau rata (std luma), kecuali flash tercatat;
    setiap lonjakan luma (flash) harus tercatat dan berawal di ketukan."""
    A = AMBANG
    m, s = stat[:, 0], stat[:, 1]
    salah, lonjak = [], []
    for i in range(len(m)):
        f = i + 1
        tetangga = np.r_[m[max(0, i - 3):i], m[i + 1:i + 4]]
        if m[i] - np.median(tetangga) > A["flash_lonjak"]:
            lonjak.append(f)
            if f not in flash:
                salah.append(f"f{f} flash tak tercatat")
        if f in flash:
            continue
        if m[i] < A["luma_min"]:
            salah.append(f"f{f} hitam {m[i]:.3f}")
        elif m[i] > A["luma_maks"]:
            salah.append(f"f{f} putih {m[i]:.3f}")
        elif s[i] < A["std_min"]:
            salah.append(f"f{f} rata std {s[i]:.4f}")
    awal = [f for f in flash if f - 1 not in flash]
    for f in awal:
        if abs((f - 1) - round((f - 1) / konfig.KETUKAN) * konfig.KETUKAN) > AMBANG["ketukan_frame"]:
            salah.append(f"flash f{f} tidak di ketukan")
    bukan_flash = np.array([i for i in range(len(m)) if i + 1 not in flash])
    return cek("TV-03", f"frame_hitam_kosong_{rasio}", len(salah), not salah, "= 0 frame salah",
               f"{len(m)} frame; luma {m[bukan_flash].min():.3f}..{m[bukan_flash].max():.3f}, std min "
               f"{s[bukan_flash].min():.4f}; lonjakan {lonjak}; flash tercatat {sorted(flash)}"
               + ("; " + "; ".join(salah[:5]) if salah else ""))


def render_kontras(folder, rasio, frame=None):
    """Render frame `frame` (bawaan: terakhir) dengan dan tanpa teks (seed & grain sama), resolusi kontras."""
    frame = frame or konfig.FRAME_AKHIR
    sc = bpy.context.scene
    w0, h0 = sc.render.resolution_x, sc.render.resolution_y
    sc.render.resolution_x, sc.render.resolution_y = res_uji(rasio, KONTRAS_SKALA)
    teks = list(koleksi("TEKS").objects)
    a = render_frame(os.path.join(folder, f"kontras_{rasio}_teks.png"), frame)
    for o in teks:
        o.hide_render = True
    sc.frame_set(frame)
    simpan = {o.name: o.animation_data.action for o in teks}
    for o in teks:
        o.animation_data.action = None  # hide_render dikunci: lepas action supaya tetap tersembunyi
        o.hide_render = True
    b = render_frame(os.path.join(folder, f"kontras_{rasio}_latar.png"), frame)
    for o in teks:
        o.animation_data.action = simpan[o.name]
    sc.render.resolution_x, sc.render.resolution_y = w0, h0
    sc.frame_set(frame)
    return a, b


def qc_kontras(pa, pb, rasio, frame=None):
    """TV-06 (b): kontras WCAG per kelompok teks (judul, tagline, label): piksel inti teks = |selisih luma render
    bertek vs tanpa teks| >= 0,5 x p95 selisih di bbox teks; L teks = median render bertek, L latar = median render
    tanpa teks di piksel yang sama (setelah compositor: grain, vignette)."""
    frame = frame or konfig.FRAME_AKHIR
    sc = bpy.context.scene
    sc.frame_set(frame)
    A, B = baca_png(pa), baca_png(pb)
    h, w = A.shape[:2]
    dg = bpy.context.evaluated_depsgraph_get()
    cam = bpy.data.objects["CAM_" + konfig.K["teks"]["shot"]]
    kel = {"judul": ["TX_judul"], "tagline": [o.name for o in koleksi("TEKS").objects if o.name.startswith("TX_tag")],
           "label": ["TX_label"]}
    dif = np.abs(luma_frame(A) - luma_frame(B))
    hasil, nilai = True, {}
    for k, nama in kel.items():
        u, v, _ = proyeksi(cam, np.concatenate([_vertex_teks(bpy.data.objects[n], dg) for n in nama]))
        c0, c1 = max(0, int(u.min() * w) - 2), min(w, int(math.ceil(u.max() * w)) + 2)
        r0, r1 = max(0, int(v.min() * h) - 2), min(h, int(math.ceil(v.max() * h)) + 2)
        reg = dif[r0:r1, c0:c1]
        if reg.size == 0 or reg.max() < 0.02:
            nilai[k], hasil = 0.0, False
            continue
        inti = reg >= 0.5 * np.percentile(reg, 95)
        lt = float(np.median(lum_relatif(A[r0:r1, c0:c1][inti])))
        lb = float(np.median(lum_relatif(B[r0:r1, c0:c1][inti])))
        kr = (max(lt, lb) + 0.05) / (min(lt, lb) + 0.05)
        nilai[k] = round(kr, 2)
        hasil &= kr >= AMBANG["kontras_min"]
    return cek("TV-06", f"kontras_teks_min_{rasio}", min(nilai.values()), hasil, f">= {AMBANG['kontras_min']}:1 (WCAG AA)",
               f"frame {frame} {w}x{h}: " + ", ".join(f"{k} {v}" for k, v in nilai.items()))


def info_video(path):
    """fps, (w, h), jumlah frame dari file video (MovieClip Blender; ffprobe bila ada sebagai cek silang)."""
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


def qc_video(path, res, rasio):
    """TV-07: file video: fps, resolusi = rencana, durasi = jumlah frame rencana (tvc.toml)."""
    if not os.path.isfile(path):
        return cek("TV-07", f"video_{rasio}", "tidak ada", False, "ada", path)
    fps, size, n, probe = info_video(path)
    n_target = round(konfig.DURASI * konfig.FPS)
    ok = abs(fps - konfig.FPS) < 1e-3 and size == tuple(res) and n == n_target
    if probe:
        pf = float(Fraction(probe["r_frame_rate"]))
        ok &= abs(pf - konfig.FPS) < 1e-3 and (probe["width"], probe["height"]) == tuple(res) and int(probe["nb_read_frames"]) == n_target
    return cek("TV-07", f"video_{rasio}", f"{fps:g} fps {size[0]}x{size[1]} {n} f", ok,
               f"{konfig.FPS} fps, {res[0]}x{res[1]}, {n_target} frame ({konfig.DURASI:g} s)",
               f"{os.path.basename(path)} {os.path.getsize(path) / 1e6:.2f} MB, {n / max(fps, 1e-6):.2f} s"
               + (f"; ffprobe {probe['codec_name']} {probe['r_frame_rate']} {probe['width']}x{probe['height']} "
                  f"{probe['nb_read_frames']} f" if probe else "; ffprobe tidak ada"))

