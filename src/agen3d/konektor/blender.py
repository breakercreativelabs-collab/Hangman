"""Cari Blender, bangun baris perintah CLI, katalog perintah (bercache), dan pagar path (tanpa bpy; Python sistem)."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

AKAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PELUNCUR = os.path.join(AKAR, "blender_cli.py")
ENV_BLENDER = "AGEN3D_BLENDER"  # path blender.exe / blender bila tidak ditemukan otomatis
CACHE_KATALOG = os.path.join(AKAR, "artefak", "konektor", "katalog.json")
ZONA = ("artefak", "proyek", "klien")  # satu-satunya folder yang boleh dibaca/ditulis alat lewat opsi path
OPSI_PATH = {"out", "artefak", "ref", "data", "sumber", "model", "simpan", "path"}  # nama opsi yang selalu path
POLA_PROYEK = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _versi_dari_path(p):
    m = re.search(r"blender[ _-]?(\d+)\.(\d+)", p, re.IGNORECASE)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def cari_blender():
    """Path absolut Blender: env AGEN3D_BLENDER -> instalasi standar (versi tertinggi) -> PATH. None bila tidak ada."""
    p = os.environ.get(ENV_BLENDER, "").strip().strip('"')
    if p and os.path.isfile(p):
        return os.path.abspath(p)
    pola = []
    if sys.platform == "win32":
        for akar in {os.environ.get("ProgramFiles", r"C:\Program Files"), r"C:\Program Files"}:
            pola.append(os.path.join(akar, "Blender Foundation", "Blender*", "blender.exe"))
    elif sys.platform == "darwin":
        pola.append("/Applications/Blender*.app/Contents/MacOS/Blender")
    else:
        pola += ["/opt/blender*/blender", os.path.expanduser("~/blender*/blender"), "/snap/bin/blender"]
    calon = [c for pl in pola for c in glob.glob(pl) if os.path.isfile(c)]
    if calon:
        return max(calon, key=_versi_dari_path)
    p = shutil.which("blender")  # peluncur menyetel cwd = repo + NoDefaultCurrentDirectoryInExePath (tanpa cwd planting)
    return os.path.abspath(p) if p and os.path.isabs(p) else None


def argv_cli(blender, *argumen, blend=None):
    """Baris perintah satu proses Blender headless menjalankan CLI tunggal (blend dibuka dulu bila diberikan)."""
    a = [blender, "-b"]
    if blend:
        a.append(blend)
    return a + ["--factory-startup", "--python-exit-code", "1", "-P", PELUNCUR, "--", *argumen]


def _kunci_cache(blender):
    """Sidik katalog: path Blender + mtime semua .py di src/agen3d (opsi bawaan dibaca dari kode modul)."""
    mt = 0.0
    for d, _, fs in os.walk(os.path.join(AKAR, "src", "agen3d")):
        for f in fs:
            if f.endswith(".py"):
                mt = max(mt, os.path.getmtime(os.path.join(d, f)))
    return f"{blender}|{mt:.3f}"


def baca_katalog(blender, batas_detik=25):
    """{judul, deskripsi, perintah: [{modul, perintah, ringkasan, opsi, galat}]} dari `bantuan --json`.
    Bercache di artefak/konektor/katalog.json (start server instan); Blender hanya dijalankan bila kode berubah."""
    kunci = _kunci_cache(blender)
    try:
        with open(CACHE_KATALOG, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("kunci") == kunci:
            return c["katalog"]
    except (OSError, ValueError, KeyError):
        pass
    with tempfile.TemporaryDirectory(prefix="agen3d_katalog_") as d:
        path = os.path.join(d, "katalog.json")
        r = subprocess.run(argv_cli(blender, "bantuan", "--json", path), cwd=AKAR, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=batas_detik, stdin=subprocess.DEVNULL)
        if r.returncode != 0 or not os.path.isfile(path):
            raise RuntimeError(f"katalog gagal (kode {r.returncode}): {(r.stdout + r.stderr)[-800:]}")
        with open(path, encoding="utf-8") as f:
            kat = json.load(f)
    os.makedirs(os.path.dirname(CACHE_KATALOG), exist_ok=True)
    with open(CACHE_KATALOG, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(kunci=kunci, katalog=kat), f, ensure_ascii=False)
    return kat


def _di_bawah(p, akar):
    nc = os.path.normcase
    try:
        return nc(os.path.commonpath([p, akar])) == nc(akar)
    except ValueError:  # beda drive di Windows
        return False


def mirip_path(nilai):
    v = str(nilai)
    return bool(v) and (os.path.isabs(v) or "/" in v or "\\" in v or ".." in v or bool(os.path.splitdrive(v)[0]))


def jalur_aman(nama, nilai):
    """Path absolut ter-resolve (realpath) yang wajib berada di zona artefak/, proyek/, atau klien/ repo. ValueError
    bila di luar zona, drive-relatif ('C:..', 'D:x'), atau menembus lewat '..' / symlink / junction."""
    v = str(nilai).strip()
    drive = os.path.splitdrive(v)[0]
    if drive and not os.path.isabs(v):
        raise ValueError(f"{nama}={v!r}: path drive-relatif tidak diizinkan; pakai path di dalam {', '.join(ZONA)}/")
    p = os.path.realpath(os.path.join(AKAR, v))
    if not any(_di_bawah(p, os.path.realpath(os.path.join(AKAR, z))) for z in ZONA):
        raise ValueError(f"{nama}={v!r} -> {p}: di luar folder kerja ({', '.join(z + '/' for z in ZONA)} di {AKAR}). "
                         f"Salin referensi ke klien/, simpan biner ke artefak/.")
    return p


def nilai_opsi(nama, nilai):
    """Nilai opsi CLI yang aman: path diresolve + dipagari; proyek = id folder proyek yang ada; lainnya apa adanya."""
    if isinstance(nilai, bool):
        return "1" if nilai else "0"
    v = str(nilai)
    if nama == "proyek":
        if not POLA_PROYEK.match(v) or not os.path.isdir(os.path.join(AKAR, "proyek", v)):
            raise ValueError(f"proyek={v!r} tidak dikenal; proyek yang ada: {', '.join(sorted(os.listdir(os.path.join(AKAR, 'proyek'))))}")
        return v
    if nama in OPSI_PATH or mirip_path(v):
        return jalur_aman(nama, v)
    return v  # io.opsi membaca pasangan --kunci nilai menurut posisi, jadi nilai berawalan '-' (mis. depan=-Y) aman


def nama_opsi_sah(nama):
    """Nama opsi CLI yang boleh dikirim (mencegah injeksi argumen lewat opsi_lain)."""
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,40}", str(nama)))
