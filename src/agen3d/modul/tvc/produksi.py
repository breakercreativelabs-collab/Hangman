"""Produksi TVC dari konfigurasi proyek: scene (model + exploded + studio + props + animasi + kamera + teks +
compositor), render frame, encode MP4 (FFmpeg bawaan Blender: sama di Windows dan Linux).

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- tvc render [--proyek am1]
      [--rasio 9x16|16x9] [--kualitas uji|final] [--frame 1-375] [--out <folder>] [--blend 1] [--model <file.blend>]
Bawaan: 9x16, uji (animatic 270 x 480, 12 spp, Cycles CPU). final = resolusi penuh, 256 spp, motion blur (laptop RTX,
OptiX lewat inti.render.pilih_perangkat). Keluaran (bawaan artefak/<proyek>/tvc): render/<rasio>_<kualitas>/f_####.png
+ <nama_berkas>_<rasio>_<kualitas>.mp4. Model: .blend hasil `modeling_referensi qc|bangun` (proyek.toml [keluaran]).
QC TV-xx + uji negatif + storyboard: `tvc qc`.
"""
import math
import os

import bpy
from mathutils import Matrix, Vector

from ...inti import io
from ...inti.render import pilih_perangkat
from ...inti.scene import control, koleksi
from ..modeling_referensi import api as model_api
from . import konfig
from .kamera import pasang_kamera
from .kompositor import compositor
from .kunci import kunci, kunci_vektor
from .props import gelembung, podium
from .props_neon import PROPS_NEON, kontak_lantai
from .teks import teks

PROPS = {"gelembung": gelembung, "podium": podium, **PROPS_NEON}


def muat_model(sumber):
    """Buka .blend model, buang kamera/lampu/lantai review, sisakan PRODUCT + CONTROL."""
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(sumber))
    for o in list(bpy.data.objects):
        if o.type in ("CAMERA", "LIGHT") or o.name in konfig.K["tvc"]["buang_objek"]:
            bpy.data.objects.remove(o)
    for w in list(bpy.data.worlds):
        bpy.data.worlds.remove(w)
    bpy.data.orphans_purge(do_local_ids=True, do_recursive=True)


def bagian():
    """{nama bagian: (objek, offset mm, rotasi z deg, tunda frame)} dari [exploded.bagian]."""
    return {b["nama"]: (tuple(b["objek"]), tuple(b["offset"]), b["rz"], b["tunda"])
            for b in konfig.K["exploded"]["bagian"]}


def susun_bagian():
    """Collection per bagian (anak PRODUCT): XP_<bagian> + empty XP_<bagian> (anak PRODUCT_ROOT, identitas) sebagai
    induk objek bagian. Animasi exploded = transform empty; world objek saat rakit = identik dengan model."""
    pk, root = koleksi("PRODUCT"), bpy.data.objects["PRODUCT_ROOT"]
    for nama, (obs, *_r) in bagian().items():
        k = bpy.data.collections.new("XP_" + nama)
        pk.children.link(k)
        e = bpy.data.objects.new("XP_" + nama, None)
        e.empty_display_size = 0.02
        k.objects.link(e)
        e.parent = root
        for n in obs:
            ob = bpy.data.objects[n]
            for kol in list(ob.users_collection):
                kol.objects.unlink(ob)
            k.objects.link(ob)
            ob.parent = e
            ob.matrix_parent_inverse = Matrix.Identity(4)
    sisa = [o.name for o in pk.objects if o.type == "MESH"]
    if sisa:
        raise RuntimeError(f"objek produk tanpa bagian exploded: {sisa}")


def studio():
    """Studio palet proyek (modeling_referensi, tanpa lantai): latar gradasi hanya untuk sinar kamera, ambien redup,
    softbox key, rim + kicker dari belakang. Plus lampu tambahan [[lampu]] (mis. glow kapsul, ikut bagian exploded)."""
    model_api.studio_palet()
    lt = bpy.data.objects.get("P3_lantai")
    if lt:
        bpy.data.objects.remove(lt)
    for o in bpy.data.objects:
        if o.name.startswith("P3_"):
            o.hide_render = False
    for L in konfig.K.get("lampu", []):
        d = bpy.data.lights.new(L["nama"], L["tipe"])
        d.energy, d.shadow_soft_size, d.color = L["energi"], L["ukuran"], tuple(L["warna"])
        if L["tipe"] == "AREA":
            d.size = L["ukuran"]
        ob = bpy.data.objects.new(L["nama"], d)
        koleksi("LIGHTS").objects.link(ob)
        if L.get("induk"):
            ob.parent = bpy.data.objects[L["induk"]]
        ob.location = tuple(L["lokasi"])
        if L["tipe"] in ("AREA", "SPOT"):  # menghadap pusat produk
            ob.rotation_euler = (konfig.C - ob.location).to_track_quat("-Z", "Y").to_euler()


def animasi_produk():
    """TURNTABLE (pivot di pusat): kunci dari [[animasi]] (urutan = urutan pemasangan). Exploded: empty XP_* per
    bagian: diam -> keluar (BACK) -> tahan (SINE) -> masuk (BOUNCE, overshoot 6 %) -> rakit tepat (CONSTANT)."""
    C = konfig.C
    tt, root = bpy.data.objects["TURNTABLE"], bpy.data.objects["PRODUCT_ROOT"]
    tt.location, root.location = C, -C
    tt.rotation_mode = "XYZ"
    for a in konfig.K["animasi"]:
        interp, ease = a.get("interp", "BEZIER"), a.get("easing", "AUTO")
        if "relatif_pusat" in a:
            kunci_vektor(tt, a["path"], a["frame"], konfig.relatif_pusat(a["relatif_pusat"]), interp, ease)
        elif "indeks" in a:
            kunci(tt, a["path"], a["frame"], konfig.angka(a["nilai"]), interp, ease, a["indeks"])
        else:
            kunci_vektor(tt, a["path"], a["frame"], tuple(konfig.angka(x) for x in a["nilai"]), interp, ease)
    X = konfig.K["exploded"]
    f_awal, _ = konfig.f_shot(X["shot"])
    for nama, (_, off, rz, tunda) in bagian().items():
        e = bpy.data.objects["XP_" + nama]
        o = Vector(off) / 1000.0
        kunci_vektor(e, "location", f_awal, (0, 0, 0), "CONSTANT")
        kunci_vektor(e, "location", X["keluar"] + tunda, (0, 0, 0), "BACK", "EASE_OUT")
        kunci_vektor(e, "location", X["tahan"] + tunda, o, "SINE", "EASE_IN_OUT")
        kunci_vektor(e, "location", X["masuk"] + tunda // 2, o * 1.06, "BOUNCE", "EASE_OUT")
        kunci_vektor(e, "location", X["rakit"] + tunda // 2, (0, 0, 0), "CONSTANT")
        kunci(e, "rotation_euler", X["keluar"] + tunda, 0.0, "SINE", "EASE_IN_OUT", 2)
        kunci(e, "rotation_euler", X["tahan"] + 12, math.radians(rz), "SINE", "EASE_IN_OUT", 2)
        kunci(e, "rotation_euler", X["masuk"] + tunda // 2, 0.0, "CONSTANT", indeks=2)


def bangun_tvc(rasio="9x16", kualitas="uji", sumber=None):
    """Scene TVC lengkap untuk `rasio`. sumber = .blend model (bawaan: path model proyek)."""
    model_api.muat_proyek(konfig.PROYEK)  # palet studio dari proyek.toml
    muat_model(sumber or model_api.path_model())
    T = konfig.K["tvc"]
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = konfig.FPS, 1.0
    sc.frame_start, sc.frame_end = 1, konfig.FRAME_AKHIR
    w, h = konfig.K["resolusi"][rasio]
    q = konfig.K["kualitas"][kualitas]
    sc.render.resolution_x, sc.render.resolution_y = round(w * q["skala"]), round(h * q["skala"])
    sc.render.resolution_percentage = 100
    susun_bagian()
    studio()
    sc.view_settings.view_transform, sc.view_settings.look, sc.view_settings.exposure = ("Khronos PBR Neutral", "None",
                                                                                         T["eksposur"])
    animasi_produk()
    kontak_lantai()  # [kontak] (opsional): titik produk terendah tepat di lantai pada frame benturan
    for nama in konfig.K["tvc"].get("props", ["gelembung", "podium"]):  # bawaan AM1
        PROPS[nama]()
    cams = pasang_kamera(rasio)
    tx = teks(rasio, cams[konfig.K["teks"]["shot"]])
    compositor(konfig.FLASH)
    c = control()
    c["produk"], c["proyek"] = T["produk"], T["label_control"]
    c["rasio"], c["fps"], c["durasi_detik"], c["bpm"] = rasio, konfig.FPS, konfig.DURASI, konfig.BPM
    c["easing"] = T["easing"]
    c["tagline"] = konfig.K["teks"]["tagline"]
    atur_render_animasi(kualitas)
    sc.frame_set(1)
    return dict(kamera=cams, teks=tx)


def atur_render_animasi(kualitas="uji"):
    sc, q = bpy.context.scene, konfig.K["kualitas"][kualitas]
    perangkat = pilih_perangkat()
    sc.cycles.samples, sc.cycles.use_denoising = q["sampel"], True
    sc.cycles.max_bounces, sc.cycles.glossy_bounces, sc.cycles.diffuse_bounces = 8, 4, 3
    sc.cycles.transmission_bounces, sc.cycles.transparent_max_bounces = 10, 16
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
    sc.cycles.seed, sc.cycles.use_animated_seed = 1, True
    sc.render.use_motion_blur = q["blur"]
    sc.render.motion_blur_shutter = 0.35
    sc.render.use_persistent_data = True
    sc.render.film_transparent = False
    sc.render.image_settings.media_type = "IMAGE"
    sc.render.image_settings.file_format, sc.render.image_settings.color_mode = "PNG", "RGB"
    sc["kualitas"] = kualitas
    sc["perangkat"] = perangkat
    return perangkat


def render_animasi(folder, f0=1, f1=None):
    """PNG per frame f_####.png (marker men-switch kamera per shot). Frame yang sudah ada dilewati (bisa dilanjutkan)."""
    f1 = f1 or konfig.FRAME_AKHIR
    sc = bpy.context.scene
    os.makedirs(folder, exist_ok=True)
    sc.render.use_overwrite, sc.render.use_placeholder = False, True
    sc.frame_start, sc.frame_end = f0, f1
    sc.render.filepath = os.path.join(os.path.abspath(folder), "f_")
    bpy.ops.render.render(animation=True)
    sc.frame_start, sc.frame_end = 1, konfig.FRAME_AKHIR
    return [os.path.join(folder, f"f_{f:04d}.png") for f in range(f0, f1 + 1)]


def encode_mp4(folder_frame, path_mp4, w, h, fps=None, f0=1, f1=None):
    """Encode PNG sequence -> MP4 H.264 lewat sequencer Blender (FFmpeg bawaan Blender: sama di Windows dan Linux)."""
    fps, f1 = fps or konfig.FPS, f1 or konfig.FRAME_AKHIR
    sc = bpy.data.scenes.new("ENKODE")
    sc.render.fps, sc.render.fps_base = fps, 1.0
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    ed = sc.sequence_editor_create()
    berkas = [f"f_{f:04d}.png" for f in range(f0, f1 + 1)]
    st = ed.strips.new_image("frame", os.path.join(os.path.abspath(folder_frame), berkas[0]), 1, 1)
    for b in berkas[1:]:
        st.elements.append(b)
    sc.frame_start, sc.frame_end = 1, len(berkas)
    sc.render.use_sequencer, sc.render.use_compositing = True, False
    sc.view_settings.view_transform = "Standard"  # frame PNG sudah ter-grading; jangan ditransform dua kali
    im = sc.render.image_settings
    im.media_type, im.file_format = "VIDEO", "FFMPEG"
    sc.render.ffmpeg.format, sc.render.ffmpeg.codec = "MPEG4", "H264"
    sc.render.ffmpeg.constant_rate_factor, sc.render.ffmpeg.ffmpeg_preset = "HIGH", "GOOD"
    sc.render.ffmpeg.audio_codec = "NONE"
    sc.render.filepath = os.path.abspath(path_mp4)
    if os.path.isfile(path_mp4):
        os.remove(path_mp4)
    bpy.ops.render.render(animation=True, scene=sc.name)
    bpy.data.scenes.remove(sc)
    keluar = sorted(f for f in os.listdir(os.path.dirname(os.path.abspath(path_mp4)))
                    if f.startswith(os.path.basename(path_mp4).rsplit(".", 1)[0]))
    if not os.path.isfile(path_mp4):  # Blender bisa menambah akhiran rentang frame: rapikan ke nama yang diminta
        kandidat = [f for f in keluar if f.endswith(".mp4")]
        if not kandidat:
            raise RuntimeError(f"MP4 tidak tertulis: {path_mp4}")
        os.replace(os.path.join(os.path.dirname(os.path.abspath(path_mp4)), kandidat[0]), path_mp4)
    return path_mp4


def main(argv):
    o = io.opsi(argv, dict(proyek="am1", rasio="9x16", kualitas="uji", frame="", out="", blend="0", model=""))
    konfig.muat_tvc(o["proyek"])
    if o["rasio"] not in konfig.K["resolusi"] or o["kualitas"] not in konfig.K["kualitas"]:
        raise SystemExit(f"--rasio {list(konfig.K['resolusi'])} --kualitas {list(konfig.K['kualitas'])}")
    out = os.path.abspath(o["out"] or io.artefak(o["proyek"], "tvc"))  # C-10
    bangun_tvc(o["rasio"], o["kualitas"], o["model"] or None)
    sc = bpy.context.scene
    tag = f"{o['rasio']}_{o['kualitas']}"
    nama = konfig.K["tvc"]["nama_berkas"]
    if o["blend"] == "1":  # C-B2: folder dibuat dulu (Blender menulis <file>.blend@ lalu rename; folder harus ada)
        path_blend = os.path.join(out, "render", f"{nama}_{tag}.blend")
        os.makedirs(os.path.dirname(path_blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=path_blend, compress=True)
    f0, f1 = (int(x) for x in (o["frame"] or f"1-{konfig.FRAME_AKHIR}").split("-"))
    folder = os.path.join(out, "render", tag)
    render_animasi(folder, f0, f1)
    if (f0, f1) == (1, konfig.FRAME_AKHIR):
        mp4 = encode_mp4(folder, os.path.join(out, f"{nama}_{tag}.mp4"), sc.render.resolution_x, sc.render.resolution_y)
        print("TVC MP4:", mp4)
    print(f"TVC selesai: {tag}, frame {f0}-{f1}, perangkat {sc.get('perangkat')}")
    return 0

