"""Konfigurasi TVC proyek (proyek/<id>/tvc.toml) + turunan: frame shot, ketukan, nilai per rasio, ekspresi angka."""
import ast
import math
import operator
import tomllib

from mathutils import Vector

from ...inti import io

K = None          # isi tvc.toml proyek aktif
PROYEK = None
FPS = BPM = KETUKAN = DURASI = FRAME_AKHIR = None
C = None          # pusat produk (m): pivot TURNTABLE
FLASH = {}        # frame: kekuatan

_OP = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.USub: operator.neg, ast.UAdd: operator.pos}


def muat_tvc(proyek="am1"):
    global K, PROYEK, FPS, BPM, KETUKAN, DURASI, FRAME_AKHIR, C, FLASH
    with open(io.proyek(proyek, "tvc.toml"), "rb") as f:
        K = tomllib.load(f)
    t = K["tvc"]
    PROYEK = proyek
    FPS, BPM, DURASI = t["fps"], t["bpm"], t["durasi"]
    KETUKAN = FPS * 60 / BPM                    # 12,5 frame @ 25 fps / 120 BPM
    FRAME_AKHIR = 1 + round(DURASI * FPS) - 1   # 375 frame: 1..375
    C = Vector(t["pusat"])
    FLASH = {int(f): k for f, k in t["flash"]}
    return K


def angka(v):
    """Angka TOML atau ekspresi teks aman: angka, pi, rad(x), + - * / dan tanda kurung."""
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
        raise ValueError(f"ekspresi tidak diizinkan: {v}")
    return ev(ast.parse(v, mode="eval"))


def per_rasio(v, rasio):
    """Nilai konfigurasi yang boleh berbeda per rasio: {"9x16": .., "16x9": ..} atau satu nilai untuk semua."""
    return v[rasio] if isinstance(v, dict) else v


def relatif_pusat(offset):
    """pusat + offset (daftar vektor dijumlah berurutan, sama dengan C + a + b)."""
    v = C
    for o in offset:
        v = v + Vector(o)
    return v if offset else C


def target(spek):
    """Target kamera/kunci: 'titik' absolut atau 'relatif_pusat'."""
    return Vector(spek["titik"]) if "titik" in spek else relatif_pusat(spek["relatif_pusat"])


def frame_dari_detik(s):
    return 1 + round(s * FPS)


def shot():
    return K["shot"]


def rentang_shot():
    """[(id, f0, f1)] inklusif. Durasi = (selesai - mulai) x fps."""
    return [(s["id"], frame_dari_detik(s["mulai"]), frame_dari_detik(s["selesai"]) - 1) for s in K["shot"]]


def shot_di(f):
    for nama, f0, f1 in rentang_shot():
        if f0 <= f <= f1:
            return nama
    return None


def makro(nama):
    return next(s["makro"] for s in K["shot"] if s["id"] == nama)


def f_shot(nama):
    """(f0, f1) shot bernama."""
    return next((f0, f1) for n, f0, f1 in rentang_shot() if n == nama)

