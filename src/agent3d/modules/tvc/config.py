"""Project TVC config (projects/<id>/tvc.toml) and derived values: shot frames, beats, per-ratio values, numeric expressions."""
import ast
import math
import operator
import tomllib

from mathutils import Vector

from ...core import io

K = None          # parsed tvc.toml of the active project
PROJECT = None
FPS = BPM = BEAT = DURATION = END_FRAME = None
C = None          # product center (m): TURNTABLE pivot
FLASH = {}        # frame: strength

_OP = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.USub: operator.neg, ast.UAdd: operator.pos}


def load_tvc(project="am1"):
    global K, PROJECT, FPS, BPM, BEAT, DURATION, END_FRAME, C, FLASH
    with open(io.project(project, "tvc.toml"), "rb") as f:
        K = tomllib.load(f)
    t = K["tvc"]
    PROJECT = project
    FPS, BPM, DURATION = t["fps"], t["bpm"], t["duration"]
    BEAT = FPS * 60 / BPM                    # 12.5 frames @ 25 fps / 120 BPM
    END_FRAME = 1 + round(DURATION * FPS) - 1   # 375 frames: 1..375
    C = Vector(t["center"])
    FLASH = {int(f): k for f, k in t["flash"]}
    return K


def number(v):
    """A TOML number or a safe text expression: numbers, pi, rad(x), + - * / and parentheses."""
    if not isinstance(v, str):
        return v

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name) and n.id == "pi":
            return math.pi
        if isinstance(n, ast.BinOp) and type(n.op) in _OP:
            return _OP[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OP:
            return _OP[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "rad" and len(n.args) == 1:
            return math.radians(ev(n.args[0]))
        raise ValueError(f"expression not allowed: {v}")
    return ev(ast.parse(v, mode="eval"))


def per_ratio(v, ratio):
    """A config value that may differ per ratio: {"9x16": .., "16x9": ..} or one value for all ratios."""
    return v[ratio] if isinstance(v, dict) else v


def relative_to_center(offset):
    """center + offset (vectors summed in order, same as C + a + b)."""
    v = C
    for o in offset:
        v = v + Vector(o)
    return v if offset else C


def target(spec):
    """Camera/light target: absolute 'points' or 'relative_to_center'."""
    return Vector(spec["points"]) if "points" in spec else relative_to_center(spec["relative_to_center"])


def frame_from_seconds(s):
    return 1 + round(s * FPS)


def shot():
    return K["shot"]


def shot_span():
    """[(id, f0, f1)], inclusive. Duration = (done - start) x fps."""
    return [(s["id"], frame_from_seconds(s["start"]), frame_from_seconds(s["done"]) - 1) for s in K["shot"]]


def shot_at(f):
    for name, f0, f1 in shot_span():
        if f0 <= f <= f1:
            return name
    return None


def macro(name):
    return next(s["macro"] for s in K["shot"] if s["id"] == name)


def f_shot(name):
    """(f0, f1) of the named shot."""
    return next((f0, f1) for n, f0, f1 in shot_span() if n == name)

