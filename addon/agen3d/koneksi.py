"""Pasang sekali klik dari dalam Blender: salin isi paket ke folder kerja, buka paket Python (wheel) untuk konektor,
lalu daftarkan konektor MCP ke Claude Desktop (dan tampilkan perintah Claude Code). Tanpa Python sistem, tanpa uv:
konektor berjalan dengan Python bawaan Blender. Modul ini tidak memakai bpy (bisa diuji di luar GUI)."""
import glob
import json
import os
import shutil
import sys
import time
import zipfile

KODE = ("src", "docs", "uji", "alat", "blender_cli.py", "konektor_mcp.py", "identitas.toml", "LICENSE", "README.md",
        "rilis.toml")  # ditimpa saat pasang/perbarui
DATA = ("proyek",)    # hanya berkas yang belum ada yang disalin (proyek pengguna tidak pernah ditimpa)


def folder_kerja_bawaan(nama):
    rumah = os.path.expanduser("~")
    dok = os.path.join(rumah, "Documents")
    return os.path.join(dok if os.path.isdir(dok) else rumah, nama)


def pasang(payload, kerja, wheels):
    """Salin payload -> folder kerja; buka wheel -> kerja/lib. Kembalikan ringkasan."""
    os.makedirs(kerja, exist_ok=True)
    for n in KODE:
        a, b = os.path.join(payload, n), os.path.join(kerja, n)
        if os.path.isdir(a):
            shutil.rmtree(b, ignore_errors=True)
            shutil.copytree(a, b)
        elif os.path.isfile(a):
            shutil.copyfile(a, b)
    baru = 0
    for n in DATA:
        for akar, _, fs in os.walk(os.path.join(payload, n)):
            for f in fs:
                tujuan = os.path.join(kerja, os.path.relpath(os.path.join(akar, f), payload))
                if not os.path.exists(tujuan):
                    os.makedirs(os.path.dirname(tujuan), exist_ok=True)
                    shutil.copyfile(os.path.join(akar, f), tujuan)
                    baru += 1
    for n in ("artefak", "klien"):
        os.makedirs(os.path.join(kerja, n), exist_ok=True)
    lib = os.path.join(kerja, "lib")
    daftar = sorted(os.path.basename(w) for w in glob.glob(os.path.join(wheels, "*.whl")))
    tanda = os.path.join(lib, ".wheel.json")
    sudah = json.load(open(tanda, encoding="utf-8")) if os.path.isfile(tanda) else None
    if sudah != daftar:  # wheel berubah (versi baru): buka ulang dari nol
        shutil.rmtree(lib, ignore_errors=True)
        os.makedirs(lib)
        for w in daftar:
            with zipfile.ZipFile(os.path.join(wheels, w)) as z:
                z.extractall(lib)
        with open(tanda, "w", encoding="utf-8") as f:
            json.dump(daftar, f)
    return dict(kerja=kerja, proyek_baru=baru, wheel=len(daftar))


def entri_mcp(kerja, blender_bin, python_bin=None):
    """Entri mcpServers: Python bawaan Blender menjalankan konektor_mcp.py di folder kerja."""
    return {"command": python_bin or sys.executable, "args": [os.path.join(kerja, "konektor_mcp.py")],
            "env": {"PYTHONUTF8": "1", "PYTHONNOUSERSITE": "1", "AGEN3D_BLENDER": blender_bin, "AGEN3D_TONTON": "1"}}


def jalur_config_claude():
    """Lokasi claude_desktop_config.json per OS (Windows: juga versi Microsoft Store/MSIX bila ada)."""
    rumah = os.path.expanduser("~")
    if sys.platform == "win32":
        calon = [os.path.join(os.environ.get("APPDATA", os.path.join(rumah, "AppData", "Roaming")), "Claude")]
        calon += glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages", "Claude_*", "LocalCache",
                                        "Roaming", "Claude"))
    elif sys.platform == "darwin":
        calon = [os.path.join(rumah, "Library", "Application Support", "Claude")]
    else:
        calon = [os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(rumah, ".config")), "Claude")]
    return [os.path.join(c, "claude_desktop_config.json") for c in calon]


def tulis_config(path, slug, entri):
    """Gabungkan entri ke config Claude Desktop (server lain tidak disentuh); cadangan .bak sebelum menulis."""
    data = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            teks = f.read()
        data = json.loads(teks) if teks.strip() else {}
        shutil.copyfile(path, f"{path}.{time.strftime('%Y%m%d-%H%M%S')}.bak")
    data.setdefault("mcpServers", {})[slug] = entri
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def perintah_claude_code(slug, entri):
    env = " ".join(f"-e {k}={v}" for k, v in entri["env"].items() if " " not in v)
    env += "".join(f' -e "{k}={v}"' for k, v in entri["env"].items() if " " in v)
    return f'claude mcp add --scope user {slug} {env} -- "{entri["command"]}" "{entri["args"][0]}"'
