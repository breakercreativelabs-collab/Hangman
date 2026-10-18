"""Write derived-data JSON compactly: dicts indented, numeric entries (points, profile rows, polygons) on one line.

indent=0/1 writes one number per line: the AM90 panel polygons (thousands of [x, z] points) became a 44k-line diff
(unreviewable PR). Content is identical (json.load gives the same result); only the text layout differs.
"""
import json
import numbers


def _digits_only(v):
    return isinstance(v, numbers.Number) or (isinstance(v, list) and all(_digits_only(x) for x in v))


def _fmt(v, indent):
    if isinstance(v, dict):
        if not v:
            return "{}"
        contents = [" " * (indent + 1) + json.dumps(k, ensure_ascii=False) + ": " + _fmt(x, indent + 1) for k, x in v.items()]
        return "{\n" + ",\n".join(contents) + "\n" + " " * indent + "}"
    if isinstance(v, list) and v and not _digits_only(v):
        return "[\n" + ",\n".join(" " * (indent + 1) + _fmt(x, indent + 1) for x in v) + "\n" + " " * indent + "]"
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False, default=float)


def write_json_compact(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_fmt(json.loads(json.dumps(obj, default=float)), 0) + "\n")
