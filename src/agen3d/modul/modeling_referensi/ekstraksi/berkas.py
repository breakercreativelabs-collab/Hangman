"""Tulis JSON data turunan secara ringkas: dict berindentasi, daftar angka (titik, baris profil, poligon) satu baris.

Format indent=0/1 menulis satu angka per baris: poligon panel AM90 (ribuan titik [x, z]) menjadi 44 ribu baris diff
(PR tidak bisa ditinjau). Isi identik (json.load sama); hanya tata letak teks.
"""
import json
import numbers


def _angka_saja(v):
    return isinstance(v, numbers.Number) or (isinstance(v, list) and all(_angka_saja(x) for x in v))


def _fmt(v, ind):
    if isinstance(v, dict):
        if not v:
            return "{}"
        isi = [" " * (ind + 1) + json.dumps(k, ensure_ascii=False) + ": " + _fmt(x, ind + 1) for k, x in v.items()]
        return "{\n" + ",\n".join(isi) + "\n" + " " * ind + "}"
    if isinstance(v, list) and v and not _angka_saja(v):
        return "[\n" + ",\n".join(" " * (ind + 1) + _fmt(x, ind + 1) for x in v) + "\n" + " " * ind + "]"
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False, default=float)


def tulis_json_ringkas(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_fmt(json.loads(json.dumps(obj, default=float)), 0) + "\n")
