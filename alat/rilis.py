"""Paket rilis publik (open source): zip berkas ter-track yang dipilih rilis.toml + README dari docs/README_PUBLIK.md
+ zip add-on mode tonton, setelah lolos audit KR-01..07. Python sistem (tanpa Blender).

  python3 alat/rilis.py [--out artefak/rilis] [--uji 1] [--platform linux-x64,windows-x64,...]
      --uji 1: hanya audit + uji negatif, tanpa menulis zip.
Keluaran: <slug>-<versi>-<platform>.zip = SATU berkas ekstensi Blender per OS (add-on + kode + contoh proyek + paket
Python konektor, Blender: Install from Disk -> Pasang & hubungkan ke Claude), dan <slug>-<versi>-source.zip.

Kode keluar 0 = paket bersih + semua uji negatif tertangkap. Nama/versi produk dari identitas.toml.
"""
import fnmatch
import glob
import os
import re
import subprocess
import sys
import tomllib
import zipfile

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLA = {
    "KR-03": ("alamat email", re.compile(rb"[\w.+-]+@[\w-]+\.[a-z]{2,}(?![\w.-]*\()", re.I)),
    "KR-04": ("token/kunci rahasia", re.compile(rb"(?:ghp_|github_pat_|sk-ant-|AKIA|xox[bp]-)[A-Za-z0-9_\-]{10,}|"
                                                rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    "KR-05": ("path rumah pengguna", re.compile(rb"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+|/home/[a-z_][\w-]*/|/Users/[\w.-]+/")),
}
IZIN_EMAIL = (b"noreply@anthropic.com",)  # baris atribusi commit, bukan data pribadi
BINER = (".jpg", ".jpeg", ".png", ".glb", ".npz", ".blend", ".zip")  # tidak dipindai sebagai teks
DEFINISI_MEREK = ("rilis.toml",)  # berkas yang memang berisi daftar merek terlarang


def baca_toml(nama):
    with open(os.path.join(AKAR, nama), "rb") as f:
        return tomllib.load(f)


def berkas_tertrack():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=AKAR, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def pilih(daftar, m):
    def cocok(p, pola):  # "a/" = folder; "a/*/b/" = pola glob folder; lainnya = berkas persis
        return any(p == x or (x.endswith("/") and (p.startswith(x) or ("*" in x and fnmatch.fnmatch(p, x + "*"))))
                   for x in pola)
    return [p for p in daftar if cocok(p, m["sertakan"]) and not cocok(p, m["kecualikan"])]


def audit(isi, m):
    """isi = {path: bytes}. Kembalikan daftar cek KR (dict id, nama, nilai = temuan, lulus)."""
    temuan = {k: [] for k in ("KR-01", "KR-02", "KR-03", "KR-04", "KR-05")}
    for p, b in isi.items():
        if any(p == t or (t.endswith("/") and p.startswith(t)) or p.endswith("/" + t) for t in m["terlarang"]):
            temuan["KR-01"].append(p)
        if p.lower().endswith(BINER):
            continue
        rendah = b.lower()
        if p not in DEFINISI_MEREK:
            temuan["KR-02"] += [f"{p}: {w}" for w in m["merek"] if w.encode() in rendah]
        for k, (_, pola) in POLA.items():
            for x in pola.findall(b):
                if x not in IZIN_EMAIL:
                    temuan[k].append(f"{p}: {x[:60].decode('utf-8', 'replace')}")
    nama = {"KR-01": "tidak ada berkas terlarang (ide pribadi, klien, artefak)", "KR-02": "tidak ada merek pihak ketiga",
            "KR-03": "tidak ada alamat email", "KR-04": "tidak ada token/kunci", "KR-05": "tidak ada path rumah pengguna"}
    cek = [dict(id=k, nama=nama[k], nilai=v[:10], lulus=not v) for k, v in temuan.items()]
    lis = isi.get("LICENSE", b"")
    cek.append(dict(id="KR-06", nama="LICENSE GPL v3 ada", nilai=len(lis), lulus=b"GNU GENERAL PUBLIC LICENSE" in lis
                    and b"Version 3" in lis))
    cek.append(dict(id="KR-07", nama="README.md + add-on + titik masuk ada",
                    nilai=sorted(x for x in ("README.md", "blender_cli.py", "addon/agen3d/__init__.py") if x in isi),
                    lulus=all(x in isi for x in ("README.md", "blender_cli.py", "addon/agen3d/__init__.py"))))
    return cek


def uji_negatif(isi, m):
    rusak = [
        ("catatan ide pribadi ikut", {"01-ide/rahasia.md": b"ide"}, "KR-01"),
        ("berkas klien ikut", {"klien/merek/a.jpg": b"x"}, "KR-01"),
        ("merek di dokumen", {"docs/x.md": b"sepatu " + m["merek"][0].upper().encode() + b" baru"}, "KR-02"),
        ("email pribadi", {"docs/y.md": b"hubungi budi.santoso" + b"@" + b"contoh.co.id"}, "KR-03"),
        ("token GitHub", {"src/z.py": b"T = 'gh" + b"p_ABCDEFGHIJKLMNOPQRST'"}, "KR-04"),
        ("path rumah Windows", {"proyek/p/hasil/l.json": b'"C:\\' + b'Users\\budi\\Desktop\\a.png"'}, "KR-05"),
        ("path rumah Linux", {"proyek/p/hasil/l.json": b'"/ho' + b'me/sari/repo/a.png"'}, "KR-05"),
        ("LICENSE hilang", {"LICENSE": b""}, "KR-06"),
        ("README hilang", {"README.md": None}, "KR-07"),
    ]
    hasil = []
    for nama, ubah, wajib in rusak:
        isi2 = dict(isi)
        for k, v in ubah.items():
            if v is None:
                isi2.pop(k, None)
            else:
                isi2[k] = v
        gagal = sorted(c["id"] for c in audit(isi2, m) if not c["lulus"])
        ok = wajib in gagal
        hasil.append((nama, ok, gagal))
        print(f"  negatif rilis {'OK ' if ok else 'BOCOR'} {nama}: gagal {gagal}")
    return hasil


PLATFORM = {  # platform ekstensi Blender -> tag wheel pip (Python 3.13 = Blender 5.2)
    "windows-x64": ["win_amd64"],
    "linux-x64": ["manylinux2014_x86_64", "manylinux_2_17_x86_64", "manylinux_2_28_x86_64"],
    "macos-arm64": ["macosx_11_0_arm64", "macosx_12_0_arm64", "macosx_14_0_arm64"],
    "macos-x64": ["macosx_10_12_x86_64", "macosx_10_13_x86_64", "macosx_11_0_x86_64"],
}
PY = "3.13"
SYARAT = "mcp>=2,<3"


def wheels(platform, cache):
    """Unduh wheel konektor untuk satu platform (cache per platform). Daftar path .whl."""
    d = os.path.join(cache, platform)
    if not glob.glob(os.path.join(d, "mcp-*.whl")):
        arg = [sys.executable, "-m", "pip", "download", SYARAT, "--only-binary=:all:", "--python-version", PY,
               "--implementation", "cp", "-d", d, "-q"]
        for t in PLATFORM[platform]:
            arg += ["--platform", t]
        subprocess.run(arg, check=True)
    return sorted(glob.glob(os.path.join(d, "*.whl")))


def manifest_ekstensi(idn, platform, m):
    return "\n".join([
        'schema_version = "1.0.0"', 'id = "agen3d"', f'version = "{idn["versi"]}"', f'name = "{idn["nama"]}"',
        f'tagline = "{m.get("tagline", "Agen Blender untuk Claude: QC angka, non-generatif")[:63]}"',
        f'maintainer = "{m.get("pengelola", idn["nama"])}"', 'type = "add-on"', f'blender_version_min = "{m["blender_min"]}"',
        f'license = ["SPDX:{m["lisensi"]}"]', f'platforms = ["{platform}"]', 'tags = ["3D View", "Modeling", "Render"]',
        '[permissions]', 'files = "Pasang ke folder kerja, tulis config Claude, baca tonton"',
        ""])


def tulis_ekstensi(path, idn, platform, m, isi, whl):
    """Zip ekstensi: add-on di akar, isi paket di payload/, wheel di wheels/."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("blender_manifest.toml", manifest_ekstensi(idn, platform, m))
        for p, b in sorted(isi.items()):
            if p.startswith("addon/agen3d/"):
                z.writestr(p[len("addon/agen3d/"):], b)
            elif not p.startswith(("addon/", ".github/", ".claude/")):
                z.writestr(f"payload/{p}", b)
        for w in whl:
            z.write(w, f"wheels/{os.path.basename(w)}")


def main():
    a = sys.argv[1:]
    o = dict(out=os.path.join(AKAR, "artefak", "rilis"), uji="0", platform=",".join(PLATFORM))
    for i in range(0, len(a) - 1, 2):
        o[a[i].lstrip("-")] = a[i + 1]
    idn, m = baca_toml("identitas.toml"), baca_toml("rilis.toml")["rilis"]
    akar_zip = f"{idn['slug']}-{idn['versi']}"
    isi = {}
    for p in pilih(berkas_tertrack(), m):
        with open(os.path.join(AKAR, p), "rb") as f:
            isi[p] = f.read()
    templat = os.path.join(AKAR, "docs", "README_PUBLIK.md")
    if os.path.isfile(templat):  # repo pengembang: README dibuat dari templat; repo publik: README.md sudah jadi
        with open(templat, encoding="utf-8") as f:
            isi["README.md"] = f.read().format(nama=idn["nama"], slug=idn["slug"], versi=idn["versi"],
                                               repo=idn.get("repo_publik") or "<pemilik>/<repo>").encode("utf-8")
    cek = audit(isi, m)
    for c in cek:
        print(f"  {c['id']} {'LULUS' if c['lulus'] else 'GAGAL'} {c['nama']}: {c['nilai']}")
    neg = uji_negatif(isi, m)
    lulus = all(c["lulus"] for c in cek) and all(ok for _, ok, _ in neg)
    if lulus and o["uji"] != "1":
        os.makedirs(o["out"], exist_ok=True)
        paket = os.path.join(o["out"], f"{akar_zip}-source.zip")
        with zipfile.ZipFile(paket, "w", zipfile.ZIP_DEFLATED) as z:
            for p, b in sorted(isi.items()):
                z.writestr(f"{akar_zip}/{p}", b)
        print(f"sumber: {paket} ({len(isi)} berkas, {os.path.getsize(paket) // 1024} KB)")
        for pf in [x for x in o["platform"].split(",") if x]:
            eks = os.path.join(o["out"], f"{akar_zip}-{pf}.zip")
            tulis_ekstensi(eks, idn, pf, m, isi, wheels(pf, os.path.join(o["out"], "wheels")))
            print(f"ekstensi {pf}: {eks} ({os.path.getsize(eks) // 1024} KB)")
    print(f"rilis {'LULUS' if lulus else 'GAGAL'}: {sum(c['lulus'] for c in cek)}/{len(cek)} cek, negatif "
          f"{sum(ok for _, ok, _ in neg)}/{len(neg)}")
    return 0 if lulus else 1


if __name__ == "__main__":
    sys.exit(main())
