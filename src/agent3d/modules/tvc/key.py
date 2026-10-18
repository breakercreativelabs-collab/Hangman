"""Keyframes with per-key easing (for the segment to the next key) and visibility per frame span."""
from ...core.scene import fcurves


def key(target, path, frame, value, interp="BEZIER", easing="AUTO", index=-1):
    """Set the value and insert a keyframe, then set that key's interpolation (segment to the next key)."""
    if index >= 0:
        getattr(target, path)[index] = value
        target.keyframe_insert(path, index=index, frame=frame)
    else:
        setattr(target, path, value)
        target.keyframe_insert(path, frame=frame)
    idb = target.id_data
    for fc in fcurves(idb):
        if fc.data_path.endswith(path) and (index < 0 or fc.array_index == index):
            for k in fc.keyframe_points:
                if abs(k.co.x - frame) < 1e-6:
                    k.interpolation, k.easing = interp, easing
                    k.handle_left_type = k.handle_right_type = "AUTO_CLAMPED"


def key_vector(ob, path, frame, v, interp="BEZIER", easing="AUTO"):
    for i, x in enumerate(v):
        key(ob, path, frame, x, interp, easing, i)


def show(ob, span):
    """hide_render keyed per frame: visible only within the spans [(f0, f1)]."""
    key(ob, "hide_render", 1, True, "CONSTANT")
    for f0, f1 in span:
        key(ob, "hide_render", f0, False, "CONSTANT")
        key(ob, "hide_render", f1 + 1, True, "CONSTANT")
