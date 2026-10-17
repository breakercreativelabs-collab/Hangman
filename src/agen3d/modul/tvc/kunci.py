"""Keyframe dengan easing per kunci (segmen menuju kunci berikutnya) dan visibilitas per rentang frame."""
from ...inti.scene import fcurves


def kunci(target, path, frame, nilai, interp="BEZIER", easing="AUTO", indeks=-1):
    """Set nilai + keyframe, lalu atur interpolasi key itu (segmen menuju key berikutnya)."""
    if indeks >= 0:
        getattr(target, path)[indeks] = nilai
        target.keyframe_insert(path, index=indeks, frame=frame)
    else:
        setattr(target, path, nilai)
        target.keyframe_insert(path, frame=frame)
    idb = target.id_data
    for fc in fcurves(idb):
        if fc.data_path.endswith(path) and (indeks < 0 or fc.array_index == indeks):
            for k in fc.keyframe_points:
                if abs(k.co.x - frame) < 1e-6:
                    k.interpolation, k.easing = interp, easing
                    k.handle_left_type = k.handle_right_type = "AUTO_CLAMPED"


def kunci_vektor(ob, path, frame, v, interp="BEZIER", easing="AUTO"):
    for i, x in enumerate(v):
        kunci(ob, path, frame, x, interp, easing, i)


def tampil(ob, rentang):
    """hide_render/viewport dikunci per frame: tampil hanya di rentang [(f0, f1)]."""
    kunci(ob, "hide_render", 1, True, "CONSTANT")
    for f0, f1 in rentang:
        kunci(ob, "hide_render", f0, False, "CONSTANT")
        kunci(ob, "hide_render", f1 + 1, True, "CONSTANT")
