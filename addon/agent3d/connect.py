"""One-click install from inside Blender: copy the package contents to the workspace, unpack the Python wheels for the
connector, then register the MCP connector with Claude Desktop (and show the Claude Code command). No system Python, no
uv: the connector runs on Blender's bundled Python. This module does not use bpy (testable outside the GUI)."""
import glob
import json
import os
import shutil
import sys
import time
import zipfile

CODE = ("src", "docs", "tests", "tools", "blender_cli.py", "mcp_connector.py", "identity.toml", "LICENSE", "README.md",
        "release.toml")  # overwritten on install/update
DATA = ("projects",)    # only missing files are copied (user projects are never overwritten)


def default_workspace_folder(name):
    home = os.path.expanduser("~")
    doc = os.path.join(home, "Documents")
    return os.path.join(doc if os.path.isdir(doc) else home, name)


def install(payload, work, wheels):
    """Copy payload -> workspace; unpack wheels -> work/lib. Returns a summary."""
    os.makedirs(work, exist_ok=True)
    for n in CODE:
        a, b = os.path.join(payload, n), os.path.join(work, n)
        if os.path.isdir(a):
            shutil.rmtree(b, ignore_errors=True)
            shutil.copytree(a, b)
        elif os.path.isfile(a):
            shutil.copyfile(a, b)
    new = 0
    for n in DATA:
        for root, _, fs in os.walk(os.path.join(payload, n)):
            for f in fs:
                target = os.path.join(work, os.path.relpath(os.path.join(root, f), payload))
                if not os.path.exists(target):
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copyfile(os.path.join(root, f), target)
                    new += 1
    for n in ("output", "references"):
        os.makedirs(os.path.join(work, n), exist_ok=True)
    lib = os.path.join(work, "lib")
    entries = sorted(os.path.basename(w) for w in glob.glob(os.path.join(wheels, "*.whl")))
    mark = os.path.join(lib, ".wheel.json")
    already = json.load(open(mark, encoding="utf-8")) if os.path.isfile(mark) else None
    if already != entries:  # wheels changed (new version): unpack again from scratch
        shutil.rmtree(lib, ignore_errors=True)
        os.makedirs(lib)
        for w in entries:
            with zipfile.ZipFile(os.path.join(wheels, w)) as z:
                z.extractall(lib)
        with open(mark, "w", encoding="utf-8") as f:
            json.dump(entries, f)
    return dict(work=work, new_project=new, wheel=len(entries))


def mcp_entry(work, blender_bin, python_bin=None):
    """mcpServers entry: Blender's bundled Python runs mcp_connector.py in the workspace."""
    return {"command": python_bin or sys.executable, "args": [os.path.join(work, "mcp_connector.py")],
            "env": {"PYTHONUTF8": "1", "PYTHONNOUSERSITE": "1", "AGENT3D_BLENDER": blender_bin, "AGENT3D_LIVE": "1"}}


def claude_config_path():
    """claude_desktop_config.json location per OS (Windows: also the Microsoft Store/MSIX version if present)."""
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        candidate = [os.path.join(os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming")), "Claude")]
        candidate += glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages", "Claude_*", "LocalCache",
                                        "Roaming", "Claude"))
    elif sys.platform == "darwin":
        candidate = [os.path.join(home, "Library", "Application Support", "Claude")]
    else:
        candidate = [os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config")), "Claude")]
    return [os.path.join(c, "claude_desktop_config.json") for c in candidate]


def write_config(path, slug, entry):
    """Merge the entry into the Claude Desktop config (other servers untouched); .bak backup before writing."""
    data = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        data = json.loads(text) if text.strip() else {}
        shutil.copyfile(path, f"{path}.{time.strftime('%Y%m%d-%H%M%S')}.bak")
    data.setdefault("mcpServers", {})[slug] = entry
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def claude_code_command(slug, entry):
    env = " ".join(f"-e {k}={v}" for k, v in entry["env"].items() if " " not in v)
    env += "".join(f' -e "{k}={v}"' for k, v in entry["env"].items() if " " in v)
    return f'claude mcp add --scope user {slug} {env} -- "{entry["command"]}" "{entry["args"][0]}"'
