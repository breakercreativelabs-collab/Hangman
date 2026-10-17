"""Perintah CLI modul perakit (kontrak cli: def _set(argv):
    from . import set as set_
    o = io.opsi(argv, dict(set=io.proyek("set_catur", "set.toml"), out="", render="1", sampel="24"))
    out = os.path.abspath(o["out"] or io.artefak("perakit", "set_catur"))
    return set_.susun(os.path.abspath(o["set"]), out, o["render"] == "1", int(o["sampel"]))


def _uji_tonton(argv):
    from . import uji_tonton
    o = io.opsi(argv, dict(out=io.artefak("uji", "tonton")))
    return uji_tonton.jalankan(os.path.abspath(o["out"]))


PERINTAH = {nama: (fungsi(argv) -> kode keluar, ringkasan)})."""
import os

from ...inti import io


def _bangun(argv):
    from . import perakit
    o = io.opsi(argv, dict(rancangan=io.proyek("kuda_catur", "rancangan.toml"), out="", render="1", sampel="32",
                                   mode="penuh", tonton=os.environ.get("AGEN3D_TONTON", "0")))  # ekstensi Blender: 1
    nama = os.path.basename(os.path.dirname(os.path.abspath(o["rancangan"])))
    out = os.path.abspath(o["out"] or io.artefak("perakit", nama))
    tonton = {"0": "", "1": io.artefak("tonton", nama)}.get(o["tonton"], o["tonton"])  # 1 = artefak/tonton/<proyek>
    return perakit.rakit(os.path.abspath(o["rancangan"]), out, o["render"] == "1", int(o["sampel"]), o["mode"],
                         os.path.abspath(tonton) if tonton else "")


def _set(argv):
    from . import set as set_
    o = io.opsi(argv, dict(set=io.proyek("set_catur", "set.toml"), out="", render="1", sampel="24"))
    out = os.path.abspath(o["out"] or io.artefak("perakit", "set_catur"))
    return set_.susun(os.path.abspath(o["set"]), out, o["render"] == "1", int(o["sampel"]))


def _uji_tonton(argv):
    from . import uji_tonton
    o = io.opsi(argv, dict(out=io.artefak("uji", "tonton")))
    return uji_tonton.jalankan(os.path.abspath(o["out"]))


PERINTAH = {
    "bangun": (_bangun, "rancangan bentuk (TOML dari prompt) -> SDF -> mesh + QC KC + negatif + lembar kontak (--mode pratinjau: cepat)"),
    "uji_tonton": (_uji_tonton, "uji mode tonton tanpa GUI: perekam langkah + pemuat add-on (KT-01..05 + negatif)"),
    "set": (_set, "set bidak (set.toml) di papan posisi awal: QC set KS-01..06 + negatif + lembar_set (bidak dibangun bila perlu)"),
}
