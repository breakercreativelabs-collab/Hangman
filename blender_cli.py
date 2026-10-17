"""Peluncur CLI (di luar src/): blender -b --factory-startup -P blender_cli.py -- <modul> <perintah> [--opsi nilai ...]

Blender tidak menambahkan folder skrip ke sys.path dan mengabaikan PYTHONPATH, jadi peluncur ini yang menambahkan
src/ (satu-satunya sys.path.insert di repo; di dalam src/ dilarang, uji struktur b). Semua logika ada di agen3d.cli.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from agen3d.cli import main  # noqa: E402

sys.exit(main())
