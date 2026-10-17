"""SATU pintu CLI semua modul:

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- <modul> <perintah> [--opsi nilai ...]
  blender -b --factory-startup -P blender_cli.py -- bantuan        (daftar modul + perintah)

Kontrak modul: agen3d/modul/<modul>/perintah.py berisi PERINTAH = {nama: (fungsi(argv) -> kode keluar, ringkasan)}.
"""
import importlib
import sys

from . import identitas
from .inti import log

MODUL = ("product_shot", "modeling_referensi", "tvc", "prosedural", "perakit", "belajar")


def perintah_modul(nama):
    return importlib.import_module(f"agen3d.modul.{nama}.perintah").PERINTAH


def bantuan():
    print(f"{identitas.judul()}: {identitas.deskripsi()}")
    print("Pakai: blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- <modul> <perintah> [--opsi nilai]")
    for m in MODUL:
        for p, (_, ringkas) in perintah_modul(m).items():
            print(f"  {m} {p:<16} {ringkas}")


class _OpsiDitangkap(Exception):
    def __init__(self, bawaan):
        super().__init__("opsi")
        self.bawaan = bawaan


def katalog():
    """[{modul, perintah, ringkasan, opsi}] tanpa menjalankan perintah: `io.opsi` dicegat sehingga fungsi perintah
    berhenti tepat saat membaca opsinya. opsi = {nama: nilai bawaan} (None bila perintah tidak memakai io.opsi).
    Dipakai konektor MCP untuk membuat satu alat per perintah, lengkap dengan parameternya."""
    from .inti import io
    asli = io.opsi

    def cegat(argv, bawaan):
        raise _OpsiDitangkap({k: str(v) for k, v in bawaan.items()})

    hasil = []
    io.opsi = cegat
    try:
        for m in MODUL:
            for p, (fungsi, ringkas) in perintah_modul(m).items():
                galat = None
                try:
                    fungsi([])
                    opsi, galat = None, "perintah berjalan tanpa membaca opsi lewat io.opsi (melanggar kontrak)"
                except _OpsiDitangkap as e:
                    opsi = e.bawaan
                except (Exception, SystemExit) as e:  # noqa: BLE001 - perintah yang gagal sebelum membaca opsi
                    opsi, galat = None, f"{type(e).__name__}: {e}"[:300]
                hasil.append(dict(modul=m, perintah=p, ringkasan=ringkas, opsi=opsi, galat=galat))
    finally:
        io.opsi = asli
    return hasil


def main(argv=None):
    a = argv if argv is not None else (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if a and a[0] in ("__kode__", "__diagnosa__"):  # perintah meta konektor MCP (tidak tercantum di bantuan)
        from .konektor import eksekusi
        return int(getattr(eksekusi, a[0].strip("_"))(a[1:]) or 0)
    if a[:2] == ["bantuan", "--json"] and len(a) == 3:  # katalog mesin-baca (konektor MCP), ditulis ke berkas
        import json
        with open(a[2], "w", encoding="utf-8", newline="\n") as f:
            json.dump(dict(judul=identitas.judul(), deskripsi=identitas.deskripsi(), perintah=katalog()), f,
                      ensure_ascii=False, indent=1)
        return 0
    if not a or a[0] in ("bantuan", "-h", "--help"):
        bantuan()
        return 0
    if a[0] == "--versi":
        print(identitas.judul())
        return 0
    if a[0] not in MODUL or len(a) < 2:
        print(f"modul tidak dikenal atau perintah kosong: {a[:2]}; modul: {', '.join(MODUL)}")
        return 2
    daftar = perintah_modul(a[0])
    if a[1] not in daftar:
        print(f"perintah '{a[1]}' tidak ada di {a[0]}; tersedia: {', '.join(daftar)}")
        return 2
    log.banner(a[0], a[1])
    import time
    from . import telemetri
    t0 = time.time()
    try:
        kode = int(daftar[a[1]][0](a[2:]) or 0)
    except BaseException as e:  # galat tetap dilempar; telemetri hanya mencatat JENISNYA (tanpa pesan/path)
        telemetri.catat_job(a[0], a[1], 1, t0, type(e).__name__.lower())
        raise
    telemetri.catat_job(a[0], a[1], kode, t0)
    return kode
