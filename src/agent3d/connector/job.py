"""Connector background jobs: every CLI command / free-form code run = one process with its own job folder.

output/connector/job/<id>/  meta.json · argv.json · log.txt · hidup.lock (held by the wrapper while alive) ·
wrapper.json · cancel_requested · done.json (single writer: the wrapper) · output.json (summary, computed once) ·
for free-form code: code.py, permintaan.json, result.json, preview.png.
Status: starting | running | done | failed | cancelled | disconnected (wrapper died without an exit code, e.g. the Claude
session was closed by a client that kills the whole job object, or the computer restarted).
"""
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time

from . import blender as bl
from . import wrap

FOLDER = os.path.join(bl.ROOT, "output", "connector", "job")
WRAP = os.path.abspath(wrap.__file__)
WAIT_LIMIT = max(0, min(int(os.environ.get("AGENT3D_WAIT_LIMIT", "50")), 3600))  # < Claude Desktop limit ~60 s
START_GRACE = 20                       # seconds: no hidup.lock after this = the wrapper never started
SCAN = ("output", "projects")        # fallback when a job declares no output folder
MAX_SCAN = 20000                   # max file entries per scan
IMAGE = (".jpg", ".jpeg", ".png")
MAX_IMAGE = 700_000                 # raw bytes (base64 ~930 KB, under the client's tool result limit)
IMAGE_PRIORITY = ("contact_sheet", "storyboard", "sheets", "preview", "before_after")
MAX_RESULTS = 8000                     # characters of free-form code HASIL in the response; full version stays in result.json
MAX_TEXT = 4000                      # stdout/error in the response


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def new_folder():
    """(id, folder) unique across server instances (pid + random); the folder is claimed atomically."""
    os.makedirs(FOLDER, exist_ok=True)
    while True:
        ident = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid() % 100000:05d}-{secrets.token_hex(2)}"
        d = os.path.join(FOLDER, ident)
        try:
            os.makedirs(d)
            return ident, d
        except FileExistsError:
            continue


def start(argv, kind, title, ident=None, folder=None, output=()):
    """Run argv in the background via the two-stage wrapper; returns the job id. output = paths the job declares
    (scanned for the result summary; empty = scan output/ + projects/)."""
    if ident is None:
        ident, folder = new_folder()
    meta = dict(id=ident, kind=kind, title=title, argv=argv, start=time.time(), output=list(output))
    wrap.write_atomic(os.path.join(folder, "meta.json"), meta)
    wrap.write_atomic(os.path.join(folder, "argv.json"), dict(argv=argv, cwd=bl.ROOT))
    try:
        r = subprocess.run([sys.executable, "-I", WRAP, "--detach", folder], cwd=bl.ROOT, capture_output=True,
                           text=True, errors="replace", timeout=30, stdin=subprocess.DEVNULL)
        error = None if r.returncode == 0 else (r.stdout + r.stderr)[-800:]
    except (OSError, subprocess.SubprocessError) as e:
        error = str(e)
    if error:
        wrap.write_atomic(os.path.join(folder, "done.json"), dict(code=127, done=time.time(),
                                                                          error=f"wrapper failed to start: {error}"))
    return ident


def _folder(ident):
    d = os.path.join(FOLDER, os.path.basename(str(ident)))
    return d if os.path.isfile(os.path.join(d, "meta.json")) else None


def _end(d):
    """done.json; if the wrapper died without writing it, write the terminal status `disconnected` (once)."""
    end = load_json(os.path.join(d, "done.json"))
    if end is not None:
        return end
    h = wrap.still_alive(d)
    meta = load_json(os.path.join(d, "meta.json")) or {}
    if h or time.time() - meta.get("start", 0) < START_GRACE:  # K-12: window between open and lock while the wrapper starts
        return None
    end = load_json(os.path.join(d, "done.json"))  # K-12: the wrapper writes it RIGHT before releasing the lock
    if end is not None:
        return end
    end = dict(code=None, done=time.time(), disconnected=True,
                 reason="job process stopped without an exit code (Claude session closed, computer restarted, or "
                        "the wrapper never started)")
    wrap.write_atomic(os.path.join(d, "done.json"), end)
    return end


async def wait(ident, seconds):
    """Wait for the job to finish, at most min(seconds, WAIT_LIMIT)."""
    d = _folder(ident)
    t_end = time.monotonic() + max(0, min(int(seconds), WAIT_LIMIT))
    while d and time.monotonic() < t_end:
        if await asyncio.to_thread(_end, d) is not None:
            return True
        await asyncio.sleep(0.5)
    return bool(d) and _end(d) is not None


def log_tail(d, n=20, max_rows=300):
    p = os.path.join(d, "log.txt")
    try:
        with open(p, "rb") as f:
            f.seek(max(0, os.path.getsize(p) - 65536))
            row = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    important = [b.rstrip()[:max_rows] for b in row if b.strip() and not b.lstrip().startswith(("Fra:", "|"))]
    return important[-n:]


def summarize_qc(path):
    j = load_json(path)
    if not isinstance(j, dict) or "passed" not in j:
        return None
    count = len(j["check"]) if isinstance(j.get("check"), list) else j.get("check_count", j.get("count"))
    failed = j.get("failed")
    r = dict(file=os.path.relpath(path, bl.ROOT), passed=j["passed"], check_count=count,
             failed=failed[:15] if isinstance(failed, list) else failed)
    neg = j.get("negative_tests")
    if isinstance(neg, list):
        r["negative_tests"] = f"{sum(bool(n.get('caught')) for n in neg)}/{len(neg)} caught"
    return r


def new_output(scan_root, since, until):
    """Files written within the window [since-1, until+2] under scan_root (job folders are skipped)."""
    new, viewed = [], 0
    stack = [p for p in scan_root if os.path.isdir(p)]
    for p in scan_root:
        if os.path.isfile(p):
            st = os.stat(p)
            if since - 1 <= st.st_mtime <= until + 2:
                new.append((st.st_mtime, st.st_size, p))
    while stack and viewed < MAX_SCAN:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    viewed += 1
                    if e.is_dir(follow_symlinks=False):
                        if e.name != "__pycache__" and os.path.normcase(e.path) != os.path.normcase(FOLDER):
                            stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        st = e.stat()
                        if since - 1 <= st.st_mtime <= until + 2:
                            new.append((st.st_mtime, st.st_size, e.path))
        except OSError:
            continue
    new.sort(reverse=True)
    per_folder = {}
    for _, _, p in new:
        k = os.path.relpath(os.path.dirname(p), bl.ROOT)
        per_folder[k] = per_folder.get(k, 0) + 1
    qc = [r for r in (summarize_qc(p) for _, _, p in new if p.endswith(".json")) if r][:10]
    image = [(t, s, p) for t, s, p in new if p.lower().endswith(IMAGE) and s <= MAX_IMAGE]
    image.sort(key=lambda x: (not any(k in os.path.basename(x[2]).lower() for k in IMAGE_PRIORITY), -x[0]))
    example = [os.path.relpath(p, bl.ROOT) for _, _, p in new if not p.lower().endswith(".png")][:15]
    return dict(file_count=len(new), per_folder=dict(list(per_folder.items())[:15]), example=example, qc=qc,
                image=image[0][2] if image else None, scan_truncated=viewed >= MAX_SCAN)


def _summarize_code_result(d, result):
    r = dict(result)
    for k in ("stdout", "error", "preview_error"):
        if isinstance(r.get(k), str) and len(r[k]) > MAX_TEXT:
            r[k] = "...(clipped)...\n" + r[k][-MAX_TEXT:]
    if "HASIL" in r:
        text = json.dumps(r["HASIL"], ensure_ascii=False, default=str)
        if len(text) > MAX_RESULTS:
            r["HASIL"] = dict(clipped=True, length=len(text), initial=text[:2000],
                              complete_files=os.path.relpath(os.path.join(d, "result.json"), bl.ROOT))
    return r


def status(ident):
    d = _folder(ident)
    if not d:
        return dict(id=ident, status="unknown")
    meta = load_json(os.path.join(d, "meta.json")) or {}
    r = dict(id=meta.get("id", ident), title=meta.get("title"), kind=meta.get("kind"))
    end = _end(d)
    if end is None:
        st = "running" if wrap.still_alive(d) else "starting"
        r.update(status=st, seconds=round(time.time() - meta.get("start", time.time())), log=log_tail(d, 12))
        return r
    st = ("cancelled" if end.get("cancelled") else "disconnected" if end.get("disconnected") else
          "done" if end.get("code") == 0 else "failed")
    r.update(status=st, code=end.get("code"), seconds=round(end["done"] - meta.get("start", end["done"])),
             log=log_tail(d))
    for k in ("reason", "error"):
        if end.get(k):
            r[k] = end[k]
    result = load_json(os.path.join(d, "result.json"))
    if isinstance(result, dict):
        r["code_result"] = _summarize_code_result(d, result)
    grp = load_json(os.path.join(d, "output.json"))
    if grp is None:
        root = [p for p in meta.get("output", []) if p] or [os.path.join(bl.ROOT, a) for a in SCAN]
        grp = new_output(root, meta.get("start", end["done"]), end["done"])
        if meta.get("kind") == "code":
            grp["image"] = (result or {}).get("preview")  # free-form code: only the requested preview
        wrap.write_atomic(os.path.join(d, "output.json"), grp)
    r["output"] = grp
    if meta.get("kind") == "test":
        u = load_json(os.path.join(d, "tests", "summary.json")) or {}
        h = u.get("result", [])
        r["test_summary"] = dict(passed=u.get("passed"), grain=len(h), via=u.get("via"),
                                  failed=[x["name"] for x in h if x.get("passed") is False][:15])
    return r


def cancel(ident):
    d = _folder(ident)
    if not d or _end(d) is not None or not wrap.still_alive(d):
        return dict(id=ident, cancelled=False, reason="unknown job or no longer running")
    with open(os.path.join(d, "cancel_requested"), "w", encoding="utf-8") as f:
        f.write(str(time.time()))
    for _ in range(60):  # the wrapper stops its own child, then writes done.json
        end = load_json(os.path.join(d, "done.json"))
        if end is not None:
            return dict(id=ident, cancelled=bool(end.get("cancelled")), code=end.get("code"))
        time.sleep(0.25)
    return dict(id=ident, cancelled=False, reason="cancel request sent; the job did not stop within 15 s")


def latest_list(n=15):
    if not os.path.isdir(FOLDER):
        return []
    result = []
    for ident in sorted(os.listdir(FOLDER), reverse=True)[:max(1, min(int(n), 100))]:
        d = os.path.join(FOLDER, ident)
        meta = load_json(os.path.join(d, "meta.json")) or {}
        end = load_json(os.path.join(d, "done.json"))
        st = ("running/starting" if end is None else "cancelled" if end.get("cancelled") else
              "disconnected" if end.get("disconnected") else "done" if end.get("code") == 0 else "failed")
        result.append(dict(id=ident, title=str(meta.get("title"))[:120], status=st))
    return result
