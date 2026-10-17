"""Peluncur konektor MCP (di luar src/; Python SISTEM/venv dengan paket `mcp`, bukan Python Blender):

  .venv/Scripts/python konektor_mcp.py             server MCP stdio (dipanggil aplikasi Claude, jangan dijalankan manual)
  .venv/Scripts/python konektor_mcp.py --config    cetak konfigurasi Claude Desktop + perintah `claude mcp add`

Seperti blender_cli.py, peluncur ini yang menambahkan src/ ke sys.path (di dalam src/ dilarang, uji struktur b).
Panduan pemasangan: docs/KONEKTOR.md.
"""
import json
import os
import sys

if sys.version_info < (3, 11):  # tomllib (identitas.toml)
    sys.exit("konektor butuh Python 3.11+")
AKAR = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")  # Windows: jangan jalankan program dari cwd
os.chdir(AKAR)  # cwd = repo (klien bisa memulai server dari folder proyek lain)
sys.path.insert(0, os.path.join(AKAR, "src"))
if os.path.isdir(os.path.join(AKAR, "lib")):  # paket Python (mcp, ...) dibuka ekstensi Blender: Python bawaan Blender cukup
    import site
    sys.path.insert(0, os.path.join(AKAR, "lib"))
    site.addsitedir(os.path.join(AKAR, "lib"))  # jalankan .pth (pywin32 di Windows memuat DLL-nya lewat .pth)
from agen3d import identitas  # noqa: E402


def config():
    skrip = os.path.join(AKAR, "konektor_mcp.py")
    desktop = {"mcpServers": {identitas.slug(): {"command": sys.executable, "args": [skrip],
                                                 "env": {"PYTHONUTF8": "1"}}}}
    print("Claude Desktop (gabungkan ke claude_desktop_config.json, lalu tutup penuh & buka ulang Claude):")
    print(json.dumps(desktop, indent=2))
    print("\nClaude Code (satu kali, semua folder):")
    print(f'claude mcp add --scope user {identitas.slug()} -e PYTHONUTF8=1 -- "{sys.executable}" "{skrip}"')


if __name__ == "__main__":
    if "--config" in sys.argv:
        config()
    else:
        from agen3d.konektor.server import main
        main()
