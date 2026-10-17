"""Perintah CLI modul prosedural (kontrak cli: PERINTAH = {nama: (fungsi(argv) -> kode keluar, ringkasan)})."""
import os

from ...inti import io


def _pohon(argv):
    from . import pohon
    o = io.opsi(argv, dict(out=io.artefak("prosedural"), render="1", sampel="128"))
    pohon.scene_contoh(os.path.abspath(o["out"]), o["render"] == "1", int(o["sampel"]))
    return 0


def _cocokkan(argv):
    from . import cocokkan
    cocokkan.cocokkan(os.path.abspath(io.opsi(argv, dict(out=io.artefak("prosedural", "cocok")))["out"]))
    return 0


def _uji(argv):
    from . import uji
    return uji.main(argv)


PERINTAH = {
    "pohon": (_pohon, "3 pohon contoh (preset + seed tetap) -> render + .blend (--render 0 untuk tanpa render)"),
    "cocokkan": (_cocokkan, "tiru siluet pohon referensi (optimasi parameter dengan IoU)"),
    "uji": (_uji, "QC-001/002/005/006 + regresi acuan + negatif QC-001"),
}
