"""Public (open source) release package: zip of the tracked files selected by release.toml + a README from
docs/README_PUBLIC.md + the live-preview add-on zip, after passing the KR-01..07 audit. System Python (no Blender).

  python3 tools/release.py [--out output/release] [--test 1] [--platform linux-x64,windows-x64,...]
      --test 1: audit + negative tests only, no zip written.
Output: <slug>-<version>-<platform>.zip = ONE Blender extension file per OS (add-on + code + example projects + the
connector's Python packages; in Blender: Install from Disk -> Install & connect to Claude), and <slug>-<version>-source.zip.

Exit code 0 = clean package + every negative test caught. Product name/version come from identity.toml.
"""
import fnmatch
import glob
import os
import re
import subprocess
import sys
import tomllib
import urllib.parse
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERN = {
    "KR-03": ("email address", re.compile(rb"[\w.+-]+@[\w-]+\.[a-z]{2,}(?![\w.-]*\()", re.I)),
    "KR-04": ("secret token/key", re.compile(rb"(?:ghp_|github_pat_|sk-ant-|AKIA|xox[bp]-)[A-Za-z0-9_\-]{10,}|"
                                                rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    "KR-05": ("user home path", re.compile(rb"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+|/home/[a-z_][\w-]*/|/Users/[\w.-]+/")),
}
EMAIL_PERMISSION = (b"noreply@anthropic.com",)  # commit attribution line, not personal data
BINARY = (".jpg", ".jpeg", ".png", ".glb", ".npz", ".blend", ".zip")  # not scanned as text
BRAND_DEFINITION = ("release.toml",)  # the file that legitimately lists the forbidden brands


def read_toml(name):
    with open(os.path.join(ROOT, name), "rb") as f:
        return tomllib.load(f)


def tracked_file():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def select(entries, m):
    def matches(p, pattern):  # "a/" = folder; "a/*/b/" = folder glob pattern; anything else = exact file
        return any(p == x or (x.endswith("/") and (p.startswith(x) or ("*" in x and fnmatch.fnmatch(p, x + "*"))))
                   for x in pattern)
    return [p for p in entries if matches(p, m["include"]) and not matches(p, m["exclude"])]


def audit(contents, m):
    """contents = {path: bytes}. Returns the KR check entries (dict id, name, value = findings, passed)."""
    findings = {k: [] for k in ("KR-01", "KR-02", "KR-03", "KR-04", "KR-05")}
    for p, b in contents.items():
        if any(p == t or (t.endswith("/") and p.startswith(t)) or p.endswith("/" + t) for t in m["forbidden"]):
            findings["KR-01"].append(p)
        if p.lower().endswith(BINARY):
            continue
        low = b.lower()
        if p not in BRAND_DEFINITION:
            findings["KR-02"] += [f"{p}: {w}" for w in m["brand"] if w.encode() in low]
        for k, (_, pattern) in PATTERN.items():
            for x in pattern.findall(b):
                if x not in EMAIL_PERMISSION:
                    findings[k].append(f"{p}: {x[:60].decode('utf-8', 'replace')}")
    name = {"KR-01": "no forbidden files (private ideas, client files, artifacts)", "KR-02": "no third-party brands",
            "KR-03": "no email addresses", "KR-04": "no tokens/keys", "KR-05": "no user home paths"}
    check = [dict(id=k, name=name[k], value=v[:10], passed=not v) for k, v in findings.items()]
    lic = contents.get("LICENSE", b"")
    check.append(dict(id="KR-06", name="LICENSE GPL v3 present", value=len(lic), passed=b"GNU GENERAL PUBLIC LICENSE" in lic
                    and b"Version 3" in lic))
    check.append(dict(id="KR-07", name="README.md + add-on + entry point present",
                    value=sorted(x for x in ("README.md", "blender_cli.py", "addon/agent3d/__init__.py") if x in contents),
                    passed=all(x in contents for x in ("README.md", "blender_cli.py", "addon/agent3d/__init__.py"))))
    # the Worker name is a deployed host: a rename must never point telemetry at a host that does not exist.
    # Expected name lives in release.toml (shipped publicly); the private repo also cross-checks wrangler.toml.
    url = tomllib.loads(contents.get("identity.toml", b"").decode("utf-8")).get("telemetry_url", "")
    expected = m.get("telemetry_worker", "")
    wrangler = os.path.join(ROOT, "services", "telemetry", "wrangler.toml")
    deployed = tomllib.load(open(wrangler, "rb"))["name"] if os.path.isfile(wrangler) else expected
    host = urllib.parse.urlparse(url).hostname or ""
    check.append(dict(id="KR-09", name="telemetry_url points at the deployed Worker (release.toml telemetry_worker)",
                      value=dict(host=host, expected=expected, deployed=deployed),
                      passed=not url or (bool(expected) and host.split(".")[0] == expected == deployed)))
    return check


def negative_tests(contents, m):
    corrupt = [
        ("private idea notes included", {"01-ide/secret.md": b"ide"}, "KR-01"),
        ("client file included", {"references/brand/a.jpg": b"x"}, "KR-01"),
        ("brand in a document", {"docs/x.md": b"shoe " + m["brand"][0].upper().encode() + b" new"}, "KR-02"),
        ("personal email", {"docs/y.md": b"hubungi budi.santoso" + b"@" + b"example.co.id"}, "KR-03"),
        ("GitHub token", {"src/z.py": b"T = 'gh" + b"p_ABCDEFGHIJKLMNOPQRST'"}, "KR-04"),
        ("Windows home path", {"projects/p/result/l.json": b'"C:\\' + b'Users\\budi\\Desktop\\a.png"'}, "KR-05"),
        ("Linux home path", {"projects/p/result/l.json": b'"/ho' + b'me/sari/repo/a.png"'}, "KR-05"),
        ("LICENSE missing", {"LICENSE": b""}, "KR-06"),
        ("README missing", {"README.md": None}, "KR-07"),
        ("telemetry host renamed", {"identity.toml": contents.get("identity.toml", b"").replace(b"telemetri.", b"telemetry.")},
         "KR-09"),
    ]
    result = []
    for name, change, required in corrupt:
        contents2 = dict(contents)
        for k, v in change.items():
            if v is None:
                contents2.pop(k, None)
            else:
                contents2[k] = v
        failed = sorted(c["id"] for c in audit(contents2, m) if not c["passed"])
        ok = required in failed
        result.append((name, ok, failed))
        print(f"  negative release {'OK ' if ok else 'LEAK'} {name}: failed {failed}")
    return result


PLATFORM = {  # Blender extension platform -> pip wheel tags (Python 3.13 = Blender 5.2)
    "windows-x64": ["win_amd64"],
    "linux-x64": ["manylinux2014_x86_64", "manylinux_2_17_x86_64", "manylinux_2_28_x86_64"],
    "macos-arm64": ["macosx_11_0_arm64", "macosx_12_0_arm64", "macosx_14_0_arm64"],
    "macos-x64": ["macosx_10_12_x86_64", "macosx_10_13_x86_64", "macosx_11_0_x86_64"],
}
PY = "3.13"
REQUIREMENT = "mcp>=2,<3"


TARGET = {  # marker environment (PEP 508) per platform: pip download evaluates markers for the OS that RUNS pip
    "windows-x64": dict(sys_platform="win32", platform_system="Windows", os_name="nt", platform_machine="AMD64"),
    "linux-x64": dict(sys_platform="linux", platform_system="Linux", os_name="posix", platform_machine="x86_64"),
    "macos-arm64": dict(sys_platform="darwin", platform_system="Darwin", os_name="posix", platform_machine="arm64"),
    "macos-x64": dict(sys_platform="darwin", platform_system="Darwin", os_name="posix", platform_machine="x86_64"),
}


def _package_name(n):
    return re.sub(r"[-_.]+", "-", n).lower()


def missing_requirements(platform, whl):
    """Requires-Dist entries (markers evaluated for the TARGET platform) not yet in the wheel set. KR-08."""
    from pip._vendor.packaging.requirements import Requirement
    env = dict(TARGET[platform], python_version=PY, python_full_version=PY + ".0", implementation_name="cpython",
               platform_python_implementation="CPython", extra="")
    exists = {_package_name(os.path.basename(w).split("-")[0]) for w in whl}
    subtract = set()
    for w in whl:
        with zipfile.ZipFile(w) as z:
            meta = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
            for row in z.read(meta).decode("utf-8", "replace").splitlines():
                if not row.startswith("Requires-Dist:"):
                    continue
                r = Requirement(row.split(":", 1)[1].strip())
                if (r.marker is None or r.marker.evaluate(env)) and _package_name(r.name) not in exists:
                    subtract.add(str(r).split(";")[0].strip())
    return sorted(subtract)


def wheels(platform, cache):
    """Download the connector wheels for one platform (cached per platform), then add the dependencies whose markers
    only apply on the target OS (e.g. pywin32 for mcp on Windows). Returns the list of .whl paths."""
    d = os.path.join(cache, platform)

    def download(requirement, without_dep=False):
        arg = [sys.executable, "-m", "pip", "download", *requirement, "--only-binary=:all:", "--python-version", PY,
               "--implementation", "cp", "-d", d, "-q"] + (["--no-deps"] if without_dep else [])
        for t in PLATFORM[platform]:
            arg += ["--platform", t]
        subprocess.run(arg, check=True)
    if not glob.glob(os.path.join(d, "mcp-*.whl")):
        download([REQUIREMENT])
    for _ in range(10):  # close the dependency set under the target OS markers
        subtract = missing_requirements(platform, glob.glob(os.path.join(d, "*.whl")))
        if not subtract:
            break
        download(subtract)
    return sorted(glob.glob(os.path.join(d, "*.whl")))


def extension_manifest(ident_info, platform, m):
    return "\n".join([
        'schema_version = "1.0.0"', 'id = "agent3d"', f'version = "{ident_info["version"]}"', f'name = "{ident_info["name"]}"',
        f'tagline = "{m.get("tagline", "Blender agent for Claude with numeric QC, non-generative")[:63]}"',
        f'maintainer = "{m.get("manager", ident_info["name"])}"', 'type = "add-on"', f'blender_version_min = "{m["blender_min"]}"',
        f'license = ["SPDX:{m["license_name"]}"]', f'platforms = ["{platform}"]', 'tags = ["3D View", "Modeling", "Render"]',
        '[permissions]', 'files = "Copy to workspace, write Claude config, read live preview"',
        ""])


def write_extension(path, ident_info, platform, m, contents, whl):
    """Extension zip: add-on at the root, package contents in payload/, wheels in wheels/."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("blender_manifest.toml", extension_manifest(ident_info, platform, m))
        for p, b in sorted(contents.items()):
            if p.startswith("addon/agent3d/"):
                z.writestr(p[len("addon/agent3d/"):], b)
            elif not p.startswith(("addon/", ".github/", ".claude/")):
                z.writestr(f"payload/{p}", b)
        for w in whl:
            z.write(w, f"wheels/{os.path.basename(w)}")


def main():
    a = sys.argv[1:]
    o = dict(out=os.path.join(ROOT, "output", "release"), test="0", platform=",".join(PLATFORM))
    for i in range(0, len(a) - 1, 2):
        o[a[i].lstrip("-")] = a[i + 1]
    ident_info, m = read_toml("identity.toml"), read_toml("release.toml")["release"]
    zip_root = f"{ident_info['slug']}-{ident_info['version']}"
    contents = {}
    for p in select(tracked_file(), m):
        with open(os.path.join(ROOT, p), "rb") as f:
            contents[p] = f.read()
    template = os.path.join(ROOT, "docs", "README_PUBLIC.md")
    if os.path.isfile(template):  # developer repo: README generated from the template; public repo: README.md is final
        with open(template, encoding="utf-8") as f:
            contents["README.md"] = f.read().format(name=ident_info["name"], slug=ident_info["slug"], version=ident_info["version"],
                                               repo=ident_info.get("public_repo") or "<owner>/<repo>").encode("utf-8")
    check = audit(contents, m)
    for c in check:
        print(f"  {c['id']} {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['value']}")
    neg = negative_tests(contents, m)
    passed = all(c["passed"] for c in check) and all(ok for _, ok, _ in neg)
    if passed and o["test"] != "1":
        os.makedirs(o["out"], exist_ok=True)
        package = os.path.join(o["out"], f"{zip_root}-source.zip")
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
            for p, b in sorted(contents.items()):
                z.writestr(f"{zip_root}/{p}", b)
        print(f"source: {package} ({len(contents)} files, {os.path.getsize(package) // 1024} KB)")
        for pf in [x for x in o["platform"].split(",") if x]:
            exp_prev = os.path.join(o["out"], f"{zip_root}-{pf}.zip")
            whl = wheels(pf, os.path.join(o["out"], "wheels"))
            subtract = missing_requirements(pf, whl)
            print(f"  KR-08 {'PASS' if not subtract else 'FAIL'} dependencies complete for {pf}: {subtract or 'complete'}")
            if subtract:
                return 1
            if pf == "windows-x64" and not missing_requirements(pf, [w for w in whl if "pywin32" not in w]):
                print("  negative KR-08 LEAK: still considered complete without pywin32")  # defect in 0.2.2-0.2.4 (Windows test)
                return 1
            write_extension(exp_prev, ident_info, pf, m, contents, whl)
            print(f"extension {pf}: {exp_prev} ({os.path.getsize(exp_prev) // 1024} KB)")
    print(f"release {'PASS' if passed else 'FAIL'}: {sum(c['passed'] for c in check)}/{len(check)} checks, negative "
          f"{sum(ok for _, ok, _ in neg)}/{len(neg)}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
