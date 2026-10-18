"""Learning from many users (user decision 2026-10-17: public open source, submissions via GitHub Issue).

Flow: the user (or Claude on the user's behalf) runs `record` for a defect/taste -> saved LOCALLY (notes.jsonl) ->
`export --approve 1` builds an anonymous submission (paths, emails, user names, client files, tokens removed),
audited by KB-01..06 -> the user attaches it to an Issue -> the maintainer turns it into rules + negative tests -> release.
Nothing is sent automatically; without explicit approval only a preview is written.
"""
import getpass
import json
import os
import platform
import re
import time

from ... import identity
from ...core import qc

KIND = ("defect", "taste")
PATTERN = {  # (ID, name, regex that must NOT appear in a submission, replacement)
    "KB-01": ("absolute path", re.compile(r"[A-Za-z]:[\\/][^\s\"',;]+|/(?:home|Users|root|mnt|tmp|var|opt|media)/[^\s\"',;]+"),
              "<path>"),
    "KB-02": ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    "KB-03": ("client file", re.compile(r"(?:references|klien)[\\/][^\s\"',;]*"), "<klien>"),
    "KB-04": ("secret token/key", re.compile(r"(?:ghp_|github_pat_|sk-ant-|sk-|AKIA|xox[bp]-)[A-Za-z0-9_\-]{8,}|-----BEGIN [A-Z ]+-----"),
              "<secret>"),
}
MAX_BYTE = 200_000


def _user_name():
    name = {os.environ.get(k, "") for k in ("USER", "USERNAME", "LOGNAME")}
    try:
        name.add(getpass.getuser())
    except Exception:  # noqa: BLE001 - environment without a user name
        pass
    return sorted((n for n in name if len(n) >= 3), key=len, reverse=True)


def cleanup(value, user=None):
    """Recursively clean all text: secrets, client files, paths, emails, OS user names."""
    user = _user_name() if user is None else user
    if isinstance(value, dict):
        return {k: cleanup(v, user) for k, v in value.items()}
    if isinstance(value, list):
        return [cleanup(v, user) for v in value]
    if not isinstance(value, str):
        return value
    for key in ("KB-04", "KB-03", "KB-01", "KB-02"):  # secrets & client files first (they can sit inside a path)
        value = PATTERN[key][1].sub(PATTERN[key][2], value)
    for n in user:
        value = re.sub(re.escape(n), "<user>", value, flags=re.IGNORECASE)
    return value


def summarize_report(path):
    """QC numbers from a JSON report (id, name, value, passed) without any other content; None if missing."""
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    check = d.get("check", [])
    return dict(passed=d.get("passed"), check=[{k: c.get(k) for k in ("id", "name", "value", "passed")} for c in check][:80])


def record(save, kind, module, project, text, report=""):
    if kind not in KIND:
        raise ValueError(f"kind must be one of {KIND}")
    if not text.strip():
        raise ValueError("empty text: describe the defect/taste in 1-3 sentences")
    os.makedirs(save, exist_ok=True)
    e = dict(timings=time.strftime("%Y-%m-%dT%H:%M:%S"), kind=kind, module=module, project=project, text=text.strip(),
             qc=summarize_report(report))
    with open(os.path.join(save, "notes.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def read_notes(save):
    path = os.path.join(save, "notes.jsonl")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(b) for b in f if b.strip()]


def submission(notes, approve):
    """Submission bundle (already cleaned)."""
    environment = dict(version=identity.version(), os=platform.system(), python=platform.python_version())
    try:
        import bpy
        environment["blender"] = bpy.app.version_string
    except ImportError:
        pass
    return dict(format="submission-feedback/1", approve=bool(approve), environment=environment, notes=cleanup(notes))


def audit(bundle):
    """KB-01..06: a submission must not contain personal data/references/secrets; it must be approved; reasonable size."""
    text = json.dumps(bundle, ensure_ascii=False)
    check = [qc.check(k, f"no {name}", len(pattern.findall(text)), not pattern.search(text), "0 findings")
           for k, (name, pattern, _) in PATTERN.items()]
    check.append(qc.check("KB-05", "explicit user approval", bundle.get("approve"), bundle.get("approve") is True,
                      "--approve 1"))
    n = len(text.encode("utf-8"))
    check.append(qc.check("KB-06", "submission size (bytes)", n, n <= MAX_BYTE, f"<= {MAX_BYTE}"))
    return check


def url_issue():
    repo = identity.public_repo()
    return f"https://github.com/{repo}/issues/new?template=feedback-submission.yml" if repo else ""


def submission_negative_tests():
    """A dirty submission without cleaning MUST be rejected by the audit; after cleaning it must pass."""
    win, lin, mail, tok = "C:" + "\\Users\\budi\\Desktop\\job.blend", "/ho" + "me/sari/projects/a.glb", \
        "budi" + "@" + "example.com", "gh" + "p_ABCDEFGHIJKLMNOP1234"  # split up so this source file itself passes the release audit
    dirty = [dict(kind="defect", module="builder", project="x", qc=None,
                  text=f"render di {win} dan {lin} wrong; hubungi {mail}; photo references/brand-x/product.jpg; token {tok} leak")]
    corrupt = [
        ("absolute path not cleaned", dict(submission([], True), notes=[dict(text=win)]),
         "KB-01"),
        ("email not cleaned", dict(submission([], True), notes=[dict(text=mail)]), "KB-02"),
        ("client file not cleaned", dict(submission([], True), notes=[dict(text="references/brand-x/a.jpg")]), "KB-03"),
        ("token not cleaned", dict(submission([], True), notes=[dict(text=tok)]), "KB-04"),
        ("no approval", submission(dirty, False), "KB-05"),
        ("huge submission", submission([dict(text="x" * (MAX_BYTE + 10))], True), "KB-06"),
    ]
    result = []
    for name, b, required in corrupt:
        ok, failed = qc.caught(audit(b), [required])
        result.append(dict(name=name, required=[required], failed=failed, caught=ok))
        print(f"  negative feedback {'OK ' if ok else 'LEAK'} {name}: failed {failed}")
    clean = submission(dirty, True)
    rest = [c["id"] for c in audit(clean) if not c["passed"]]
    text = clean["notes"][0]["text"]
    missing_name = "budi" not in text and "sari" not in text
    result.append(dict(name="dirty submission passes the audit after cleaning + user name in paths removed", required=[],
                      failed=rest, caught=not rest and missing_name))
    print(f"  cleaning {'OK ' if not rest and missing_name else 'LEAK'}: {text}")
    return result
