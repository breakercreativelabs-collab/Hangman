"""Perintah CLI modul tvc (kontrak cli: PERINTAH = {nama: (fungsi(argv) -> kode keluar, ringkasan)})."""


def _render(argv):
    from . import produksi
    return produksi.main(argv)


def _qc(argv):
    from . import laporan
    return laporan.main(argv)


PERINTAH = {
    "render": (_render, "bangun scene TVC dari tvc.toml + render frame + MP4 (--rasio 9x16|16x9 --kualitas uji|final)"),
    "qc": (_qc, "QC TV-01..08 + 16 uji negatif + animatic uji + storyboard (--proyek am1)"),
}
