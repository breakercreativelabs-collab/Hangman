"""Automatic telemetry (user decision 2026-10-17: on by default, no prompt; the agent learns from real usage).

Hard limits (feedback QC_RULES, KM-01..08):
- ONLY numbers + short IDs from a whitelisted schema: version, OS, module/command, exit code, duration, QC check results
  (ID, passed, numeric value), negative-test counts, recipes used, error type, verdict 👍/👎. No free text, file/project
  names, paths, images, models or prompts.
- Disclosed (README + Blender panel) and can be turned off in one click: file `output/telemetry/MATI`, env
  AGENT3D_TELEMETRY=0 (our test runner sets it), or the panel button.
- Never slows down or fails a job: events are queued to a file, sent with a 3 s timeout, errors are swallowed.
"""
import json
import os
import platform
import re
import time
import urllib.request
import uuid

from . import identity

FOLDER = os.path.join(identity.ROOT, "output", "telemetry")
MAX_QUEUE = 500
RETRY_PAUSE = 600  # seconds to wait after a failed send before retrying
ID_PATTERN = re.compile(r"^[A-Za-z]{1,4}-\d{1,3}$")          # KC-01, KA-08, QC-11, TV-03, ...
PATTERN_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")         # module/command/recipe/error names (code, not user data)
KEY = {"job": {"v", "kind", "install_id", "version", "os", "blender", "module", "command", "code", "seconds", "check",
                 "negative", "recipe", "error"},
         "verdict": {"v", "kind", "install_id", "version", "os", "module", "command", "value"}}


def active():
    off = "0" in (os.environ.get("AGENT3D_TELEMETRY", "1"), os.environ.get("AGENT3D_TELEMETRI", "1"))  # old 0.2.x name kept
    return not off and not os.path.exists(os.path.join(FOLDER, "MATI"))


def configure(enable):
    """One-click switch (used by the Blender panel)."""
    os.makedirs(FOLDER, exist_ok=True)
    p = os.path.join(FOLDER, "MATI")
    if enable and os.path.exists(p):
        os.remove(p)
    elif not enable:
        open(p, "w").close()


def install_id():
    """Random UUID per installation (not a person's identity): detects a single installation flooding the data (poisoning)."""
    p = os.path.join(FOLDER, "install_id")
    if not os.path.isfile(p):
        os.makedirs(FOLDER, exist_ok=True)
        with open(p, "w") as f:
            f.write(uuid.uuid4().hex)
    with open(p) as f:
        return f.read().strip()[:32]


def _name(x):
    return x if isinstance(x, str) and PATTERN_NAME.match(x) else None


def _number(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 1e9 else None


def sanitize(e):
    """Whitelist: drop every key/value outside the schema. The result never contains free text."""
    kind = e.get("kind")
    if kind not in KEY:
        return None
    k = {x: e[x] for x in KEY[kind] if x in e}
    k["module"], k["command"] = _name(k.get("module")), _name(k.get("command"))
    if kind == "verdict":
        k["value"] = k.get("value") if k.get("value") in (1, -1) else None
        return k if k["value"] else None
    k["code"], k["seconds"] = _number(k.get("code")), _number(k.get("seconds"))
    k["check"] = [dict(id=c["id"], passed=bool(c.get("passed")), **({"value": _number(c.get("value"))}
                                                                  if _number(c.get("value")) is not None else {}))
                for c in (k.get("check") or [])[:200] if isinstance(c, dict) and ID_PATTERN.match(str(c.get("id", "")))]
    neg = k.get("negative") or [0, 0]
    k["negative"] = [int(_number(neg[0]) or 0), int(_number(neg[1]) or 0)] if isinstance(neg, list) and len(neg) == 2 else [0, 0]
    k["recipe"] = {n: int(v) for n, v in (k.get("recipe") or {}).items() if _name(n) and _number(v) is not None}
    k["error"] = _name(k.get("error"))
    for x in ("version", "os", "blender"):
        k[x] = str(k.get(x, ""))[:20] if re.match(r"^[\w .\-]*$", str(k.get(x, ""))) else ""
    k["install_id"] = str(k.get("install_id", ""))[:32] if re.match(r"^[0-9a-f]*$", str(k.get("install_id", ""))) else ""
    return k


def _base(kind):
    d = dict(v=1, kind=kind, install_id=install_id(), version=identity.version(), os=platform.system())
    try:
        import bpy
        d["blender"] = bpy.app.version_string.split()[0]
    except ImportError:
        pass
    return d


def summarize_output(t0, root=None):
    """QC checks, negative tests and recipes from the JSON reports this job wrote (mtime >= t0) in output/ and projects/."""
    check, neg, recipe = [], [0, 0], {}
    for a in root or (os.path.join(identity.ROOT, "output"), os.path.join(identity.ROOT, "projects")):
        for d, sub, fs in os.walk(a):
            sub[:] = [s for s in sub if s not in ("telemetry", "connector", "live")]
            for f in fs:
                p = os.path.join(d, f)
                if not f.endswith(".json") or os.path.getmtime(p) < t0 or os.path.getsize(p) > 5_000_000:
                    continue
                try:
                    with open(p, encoding="utf-8") as fh:
                        j = json.load(fh)
                except (OSError, ValueError):
                    continue
                if isinstance(j, dict):
                    check += [c for c in j.get("check", []) if isinstance(c, dict)]
                    neg[0] += sum(1 for n in j.get("negative", []) if isinstance(n, dict) and n.get("caught"))
                    neg[1] += sum(1 for n in j.get("negative", []) if isinstance(n, dict))
                    for b in j.get("recipe_used", []):
                        recipe[b] = recipe.get(b, 0) + 1
    return check, neg, recipe


def record_job(module, command, code, t0, error=None):
    if not active():
        return
    try:
        check, neg, recipe = summarize_output(t0)
        queue(dict(_base("job"), module=module, command=command, code=code, seconds=round(time.time() - t0, 1), check=check,
                   negative=neg, recipe=recipe, error=error))
        send()
    except Exception:  # noqa: BLE001 - telemetry must never fail a job
        pass


def record_verdict(value, module="builder", command="build"):
    if not active():
        return
    try:
        queue(dict(_base("verdict"), module=module, command=command, value=value))
        send()
    except Exception:  # noqa: BLE001
        pass


def queue(e):
    e = sanitize(e)
    if not e:
        return
    os.makedirs(FOLDER, exist_ok=True)
    p = os.path.join(FOLDER, "queue.jsonl")
    row = open(p, encoding="utf-8").read().splitlines()[-(MAX_QUEUE - 1):] if os.path.isfile(p) else []
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(row + [json.dumps(e, ensure_ascii=True)]) + "\n")


def send(url=None, limit=3.0):
    """POST the queue to the endpoint (identity.toml telemetry_url); on success the queue is cleared. Returns the count."""
    url = url if url is not None else identity.read().get("telemetry_url", "")
    p = os.path.join(FOLDER, "queue.jsonl")
    if not url or not os.path.isfile(p):
        return 0
    with open(p, encoding="utf-8") as f:
        contents = [json.loads(b) for b in f if b.strip()]
    if not contents:
        return 0
    pause = os.path.join(FOLDER, "last_failed")
    if os.path.isfile(pause) and time.time() - os.path.getmtime(pause) < RETRY_PAUSE:
        return 0  # just failed: don't hold up the next job another 3 s (KM-05)
    data = json.dumps(dict(events=contents)).encode("utf-8")
    # explicit User-Agent: some edges reject the default "Python-urllib/x.y" signature
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json", "User-Agent": f"{identity.read().get('slug', 'agent3d')}/{identity.version()}"})
    try:
        with urllib.request.urlopen(req, timeout=limit) as r:
            if r.status // 100 != 2:
                raise OSError(f"HTTP {r.status}")
    except Exception as e:  # noqa: BLE001 - offline / server down: retry after RETRY_PAUSE
        with open(pause, "w", encoding="utf-8") as f:  # kept for `diagnose`: the reason is otherwise invisible
            f.write(f"{type(e).__name__}: {e}"[:300])
        return 0
    os.remove(p)
    if os.path.isfile(pause):
        os.remove(pause)
    return len(contents)


def health():
    """For `diagnose`: is telemetry on, how many events wait in the queue, and why the last send failed (if it did)."""
    p, pause = os.path.join(FOLDER, "queue.jsonl"), os.path.join(FOLDER, "last_failed")
    queued = sum(1 for b in open(p, encoding="utf-8") if b.strip()) if os.path.isfile(p) else 0
    error = open(pause, encoding="utf-8").read().strip() if os.path.isfile(pause) else ""
    return dict(active=active(), queued=queued, last_error=error,
                last_error_age_s=round(time.time() - os.path.getmtime(pause)) if error else None)
