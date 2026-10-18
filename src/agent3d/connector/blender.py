"""Find Blender, build CLI command lines, command catalog (cached), and path fence (no bpy; system Python)."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LAUNCHER = os.path.join(ROOT, "blender_cli.py")
ENV_BLENDER = "AGENT3D_BLENDER"  # path to blender.exe / blender if not found automatically
CATALOG_CACHE = os.path.join(ROOT, "output", "connector", "catalog.json")
ZONE = ("output", "projects", "references")  # the only folders tools may read/write through path options
PATH_OPTIONS = {"out", "artifact", "ref", "data", "source", "model", "save", "path"}  # option names that are always paths
PROJECT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _version_from_path(p):
    m = re.search(r"blender[ _-]?(\d+)\.(\d+)", p, re.IGNORECASE)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def find_blender():
    """Absolute Blender path: env AGENT3D_BLENDER -> standard install (highest version) -> PATH. None if not found."""
    p = os.environ.get(ENV_BLENDER, "").strip().strip('"')
    if p and os.path.isfile(p):
        return os.path.abspath(p)
    pattern = []
    if sys.platform == "win32":
        for root in {os.environ.get("ProgramFiles", r"C:\Program Files"), r"C:\Program Files"}:
            pattern.append(os.path.join(root, "Blender Foundation", "Blender*", "blender.exe"))
    elif sys.platform == "darwin":
        pattern.append("/Applications/Blender*.app/Contents/MacOS/Blender")
    else:
        pattern += ["/opt/blender*/blender", os.path.expanduser("~/blender*/blender"), "/snap/bin/blender"]
    candidate = [c for pl in pattern for c in glob.glob(pl) if os.path.isfile(c)]
    if candidate:
        return max(candidate, key=_version_from_path)
    p = shutil.which("blender")  # the launcher sets cwd = repo + NoDefaultCurrentDirectoryInExePath (no cwd planting)
    return os.path.abspath(p) if p and os.path.isabs(p) else None


def argv_cli(blender, *argument, blend=None):
    """Command line for one headless Blender process running the single CLI (opens blend first if given)."""
    a = [blender, "-b"]
    if blend:
        a.append(blend)
    return a + ["--factory-startup", "--python-exit-code", "1", "-P", LAUNCHER, "--", *argument]


def _cache_key(blender):
    """Catalog fingerprint: Blender path + mtime of all .py in src/agent3d (option defaults are read from module code)."""
    mt = 0.0
    for d, _, fs in os.walk(os.path.join(ROOT, "src", "agent3d")):
        for f in fs:
            if f.endswith(".py"):
                mt = max(mt, os.path.getmtime(os.path.join(d, f)))
    return f"{blender}|{mt:.3f}"


def read_catalog(blender, limit_seconds=25):
    """{title, description, command: [{module, command, summary, options, error}]} from `help --json`.
    Cached in output/connector/catalog.json (instant server start); Blender only runs when the code changed."""
    key = _cache_key(blender)
    try:
        with open(CATALOG_CACHE, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("key") == key:
            return c["catalog"]
    except (OSError, ValueError, KeyError):
        pass
    with tempfile.TemporaryDirectory(prefix="agent3d_catalog_") as d:
        path = os.path.join(d, "catalog.json")
        r = subprocess.run(argv_cli(blender, "help", "--json", path), cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=limit_seconds, stdin=subprocess.DEVNULL)
        if r.returncode != 0 or not os.path.isfile(path):
            raise RuntimeError(f"catalog failed (code {r.returncode}): {(r.stdout + r.stderr)[-800:]}")
        with open(path, encoding="utf-8") as f:
            cat_data = json.load(f)
    os.makedirs(os.path.dirname(CATALOG_CACHE), exist_ok=True)
    with open(CATALOG_CACHE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(key=key, catalog=cat_data), f, ensure_ascii=False)
    return cat_data


def _is_under(p, root):
    nc = os.path.normcase
    try:
        return nc(os.path.commonpath([p, root])) == nc(root)
    except ValueError:  # different drive on Windows
        return False


def looks_like_path(value):
    v = str(value)
    return bool(v) and (os.path.isabs(v) or "/" in v or "\\" in v or ".." in v or bool(os.path.splitdrive(v)[0]))


def safe_path(name, value):
    """Resolved absolute path (realpath) that must lie in the repo's output/, projects/ or references/ zone. ValueError
    if outside the zone, drive-relative ('C:..', 'D:x'), or escaping via '..' / symlink / junction."""
    v = str(value).strip()
    drive = os.path.splitdrive(v)[0]
    if drive and not os.path.isabs(v):
        raise ValueError(f"{name}={v!r}: drive-relative paths are not allowed; use a path inside {', '.join(ZONE)}/")
    p = os.path.realpath(os.path.join(ROOT, v))
    if not any(_is_under(p, os.path.realpath(os.path.join(ROOT, z))) for z in ZONE):
        raise ValueError(f"{name}={v!r} -> {p}: di outer folder work ({', '.join(z + '/' for z in ZONE)} di {ROOT}). "
                         f"Salin reference ke references/, save biner ke output/.")
    return p


def option_values(name, value):
    """Safe CLI option value: paths are resolved + fenced; project = id of an existing project folder; others as-is."""
    if isinstance(value, bool):
        return "1" if value else "0"
    v = str(value)
    if name == "project":
        if not PROJECT_PATTERN.match(v) or not os.path.isdir(os.path.join(ROOT, "projects", v)):
            raise ValueError(f"project={v!r} is unknown; existing projects: {', '.join(sorted(os.listdir(os.path.join(ROOT, 'projects'))))}")
        return v
    if name in PATH_OPTIONS or looks_like_path(v):
        return safe_path(name, v)
    return v  # io.options reads --key value pairs by position, so values starting with '-' (e.g. front=-Y) are safe


def valid_option_names(name):
    """CLI option names that may be sent (prevents argument injection via other_options)."""
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,40}", str(name)))
