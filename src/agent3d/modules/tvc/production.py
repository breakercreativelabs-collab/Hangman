"""TVC production from project config: scene (model + exploded view + studio + props + animation + cameras + text +
compositor), frame render, MP4 encode (Blender's built-in FFmpeg: same on Windows and Linux).

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- tvc render [--project am1]
      [--ratio 9x16|16x9] [--quality test|final] [--frame 1-375] [--out <folder>] [--blend 1] [--model <file.blend>]
Defaults: 9x16, test (animatic 270 x 480, 12 spp, Cycles CPU). final = full resolution, 256 spp, motion blur (RTX laptop,
OptiX via core.render.select_device). Output (default output/<project>/tvc): render/<ratio>_<quality>/f_####.png
+ <file_name>_<ratio>_<quality>.mp4. Model: the .blend from `reference_modeling qc|build` (project.toml [output]).
QC TV-xx + negative tests + storyboard: `tvc qc`.
"""
import math
import os

import bpy
from mathutils import Matrix, Vector

from ...core import io
from ...core.render import select_device
from ...core.scene import control, collection
from ..reference_modeling import api as model_api
from . import config
from .camera import place_camera
from .compositor import compositor
from .key import key, key_vector
from .props import bubble, podium
from .props_neon import PROPS_NEON, floor_contact
from .text import text

PROPS = {"bubble": bubble, "podium": podium, **PROPS_NEON}


def load_model(source):
    """Open the model .blend, drop the review cameras/lights/floor, keep PRODUCT + CONTROL."""
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(source))
    for o in list(bpy.data.objects):
        if o.type in ("CAMERA", "LIGHT") or o.name in config.K["tvc"]["drop_objects"]:
            bpy.data.objects.remove(o)
    for w in list(bpy.data.worlds):
        bpy.data.worlds.remove(w)
    bpy.data.orphans_purge(do_local_ids=True, do_recursive=True)


def part():
    """{part name: (entities, offset mm, z rotation deg, delay frames)} from [exploded.part]."""
    return {b["name"]: (tuple(b["entity"]), tuple(b["offset"]), b["rz"], b["defer"])
            for b in config.K["exploded"]["part"]}


def arrange_parts():
    """One collection per part (child of PRODUCT): XP_<part> + empty XP_<part> (child of PRODUCT_ROOT, identity) as the
    parent of the part's entities. Exploded animation = empty transform; when assembled, entity world = model exactly."""
    pk, root = collection("PRODUCT"), bpy.data.objects["PRODUCT_ROOT"]
    for name, (obs, *_r) in part().items():
        k = bpy.data.collections.new("XP_" + name)
        pk.children.link(k)
        e = bpy.data.objects.new("XP_" + name, None)
        e.empty_display_size = 0.02
        k.objects.link(e)
        e.parent = root
        for n in obs:
            ob = bpy.data.objects[n]
            for coll in list(ob.users_collection):
                coll.objects.unlink(ob)
            k.objects.link(ob)
            ob.parent = e
            ob.matrix_parent_inverse = Matrix.Identity(4)
    rest = [o.name for o in pk.objects if o.type == "MESH"]
    if rest:
        raise RuntimeError(f"product entities without an exploded part: {rest}")


def studio():
    """Project palette studio (reference_modeling, no floor): gradient background for camera rays only, dim ambient,
    softbox key, rim + kicker from behind. Plus extra [[lamp]] lights (e.g. capsule glow, follows its exploded part)."""
    model_api.studio_palette()
    lt = bpy.data.objects.get("P3_floor")
    if lt:
        bpy.data.objects.remove(lt)
    for o in bpy.data.objects:
        if o.name.startswith("P3_"):
            o.hide_render = False
    for L in config.K.get("lamp", []):
        d = bpy.data.lights.new(L["name"], L["value_type"])
        d.energy, d.shadow_soft_size, d.color = L["energy"], L["size"], tuple(L["color"])
        if L["value_type"] == "AREA":
            d.size = L["size"]
        ob = bpy.data.objects.new(L["name"], d)
        collection("LIGHTS").objects.link(ob)
        if L.get("parent"):
            ob.parent = bpy.data.objects[L["parent"]]
        ob.location = tuple(L["location"])
        if L["value_type"] in ("AREA", "SPOT"):  # aim at the product center
            ob.rotation_euler = (config.C - ob.location).to_track_quat("-Z", "Y").to_euler()


def product_animation():
    """TURNTABLE (pivot at the center): keys from [[animation]] (in insertion order). Exploded: one XP_* empty per
    part: still -> out (BACK) -> hold (SINE) -> in (BOUNCE, 6 % overshoot) -> exact assembly (CONSTANT)."""
    C = config.C
    tt, root = bpy.data.objects["TURNTABLE"], bpy.data.objects["PRODUCT_ROOT"]
    tt.location, root.location = C, -C
    tt.rotation_mode = "XYZ"
    for a in config.K["animation"]:
        interp, ease = a.get("interp", "BEZIER"), a.get("easing", "AUTO")
        if "relative_to_center" in a:
            key_vector(tt, a["path"], a["frame"], config.relative_to_center(a["relative_to_center"]), interp, ease)
        elif "index" in a:
            key(tt, a["path"], a["frame"], config.number(a["value"]), interp, ease, a["index"])
        else:
            key_vector(tt, a["path"], a["frame"], tuple(config.number(x) for x in a["value"]), interp, ease)
    X = config.K["exploded"]
    f_start, _ = config.f_shot(X["shot"])
    for name, (_, off, rz, defer) in part().items():
        e = bpy.data.objects["XP_" + name]
        o = Vector(off) / 1000.0
        key_vector(e, "location", f_start, (0, 0, 0), "CONSTANT")
        key_vector(e, "location", X["exit_code"] + defer, (0, 0, 0), "BACK", "EASE_OUT")
        key_vector(e, "location", X["hold"] + defer, o, "SINE", "EASE_IN_OUT")
        key_vector(e, "location", X["enter"] + defer // 2, o * 1.06, "BOUNCE", "EASE_OUT")
        key_vector(e, "location", X["assemble"] + defer // 2, (0, 0, 0), "CONSTANT")
        key(e, "rotation_euler", X["exit_code"] + defer, 0.0, "SINE", "EASE_IN_OUT", 2)
        key(e, "rotation_euler", X["hold"] + 12, math.radians(rz), "SINE", "EASE_IN_OUT", 2)
        key(e, "rotation_euler", X["enter"] + defer // 2, 0.0, "CONSTANT", index=2)


def build_tvc(ratio="9x16", quality="test", source=None):
    """Full TVC scene for `ratio`. source = model .blend (default: the project model path)."""
    model_api.load_project(config.PROJECT)  # studio palette from project.toml
    load_model(source or model_api.path_model())
    T = config.K["tvc"]
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = config.FPS, 1.0
    sc.frame_start, sc.frame_end = 1, config.END_FRAME
    w, h = config.K["resolution"][ratio]
    q = config.K["quality"][quality]
    sc.render.resolution_x, sc.render.resolution_y = round(w * q["scale"]), round(h * q["scale"])
    sc.render.resolution_percentage = 100
    arrange_parts()
    studio()
    sc.view_settings.view_transform, sc.view_settings.look, sc.view_settings.exposure = ("Khronos PBR Neutral", "None",
                                                                                         T["exposure"])
    product_animation()
    floor_contact()  # [contact] (optional): lowest product point exactly on the floor at the impact frame
    for name in config.K["tvc"].get("props", ["bubble", "podium"]):  # AM1 default
        PROPS[name]()
    cams = place_camera(ratio)
    tx = text(ratio, cams[config.K["text"]["shot"]])
    compositor(config.FLASH)
    c = control()
    c["product"], c["project"] = T["product"], T["label_control"]
    c["ratio"], c["fps"], c["duration_seconds"], c["bpm"] = ratio, config.FPS, config.DURATION, config.BPM
    c["easing"] = T["easing"]
    c["tagline"] = config.K["text"]["tagline"]
    setup_animation_render(quality)
    sc.frame_set(1)
    return dict(camera=cams, text=tx)


def setup_animation_render(quality="test"):
    sc, q = bpy.context.scene, config.K["quality"][quality]
    device = select_device()
    sc.cycles.samples, sc.cycles.use_denoising = q["sample"], True
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
    sc["quality"] = quality
    sc["device"] = device
    return device


def render_animation(folder, f0=1, f1=None):
    """One PNG per frame, f_####.png (markers switch the camera per shot). Existing frames are skipped (resumable)."""
    f1 = f1 or config.END_FRAME
    sc = bpy.context.scene
    os.makedirs(folder, exist_ok=True)
    sc.render.use_overwrite, sc.render.use_placeholder = False, True
    sc.frame_start, sc.frame_end = f0, f1
    sc.render.filepath = os.path.join(os.path.abspath(folder), "f_")
    bpy.ops.render.render(animation=True)
    sc.frame_start, sc.frame_end = 1, config.END_FRAME
    return [os.path.join(folder, f"f_{f:04d}.png") for f in range(f0, f1 + 1)]


def encode_mp4(folder_frame, path_mp4, w, h, fps=None, f0=1, f1=None):
    """Encode a PNG sequence to H.264 MP4 via the Blender sequencer (built-in FFmpeg: same on Windows and Linux)."""
    fps, f1 = fps or config.FPS, f1 or config.END_FRAME
    sc = bpy.data.scenes.new("ENKODE")
    sc.render.fps, sc.render.fps_base = fps, 1.0
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    ed = sc.sequence_editor_create()
    file = [f"f_{f:04d}.png" for f in range(f0, f1 + 1)]
    st = ed.strips.new_image("frame", os.path.join(os.path.abspath(folder_frame), file[0]), 1, 1)
    for b in file[1:]:
        st.elements.append(b)
    sc.frame_start, sc.frame_end = 1, len(file)
    sc.render.use_sequencer, sc.render.use_compositing = True, False
    sc.view_settings.view_transform = "Standard"  # PNG frames are already graded; do not transform twice
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
    exit_code = sorted(f for f in os.listdir(os.path.dirname(os.path.abspath(path_mp4)))
                    if f.startswith(os.path.basename(path_mp4).rsplit(".", 1)[0]))
    if not os.path.isfile(path_mp4):  # Blender may append a frame-range suffix: rename to the requested name
        candidates = [f for f in exit_code if f.endswith(".mp4")]
        if not candidates:
            raise RuntimeError(f"MP4 not written: {path_mp4}")
        os.replace(os.path.join(os.path.dirname(os.path.abspath(path_mp4)), candidates[0]), path_mp4)
    return path_mp4


def main(argv):
    o = io.options(argv, dict(project="am1", ratio="9x16", quality="test", frame="", out="", blend="0", model=""))
    config.load_tvc(o["project"])
    if o["ratio"] not in config.K["resolution"] or o["quality"] not in config.K["quality"]:
        raise SystemExit(f"--ratio {list(config.K['resolution'])} --quality {list(config.K['quality'])}")
    out = os.path.abspath(o["out"] or io.artifact(o["project"], "tvc"))  # C-10
    build_tvc(o["ratio"], o["quality"], o["model"] or None)
    sc = bpy.context.scene
    tag = f"{o['ratio']}_{o['quality']}"
    name = config.K["tvc"]["file_name"]
    if o["blend"] == "1":  # C-B2: create the folder first (Blender writes <file>.blend@ then renames; the folder must exist)
        path_blend = os.path.join(out, "render", f"{name}_{tag}.blend")
        os.makedirs(os.path.dirname(path_blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=path_blend, compress=True)
    f0, f1 = (int(x) for x in (o["frame"] or f"1-{config.END_FRAME}").split("-"))
    folder = os.path.join(out, "render", tag)
    render_animation(folder, f0, f1)
    if (f0, f1) == (1, config.END_FRAME):
        mp4 = encode_mp4(folder, os.path.join(out, f"{name}_{tag}.mp4"), sc.render.resolution_x, sc.render.resolution_y)
        print("TVC MP4:", mp4)
    print(f"TVC done: {tag}, frame {f0}-{f1}, device {sc.get('device')}")
    return 0

