"""Perintah CLI modul product_shot (kontrak cli: PERINTAH = {nama: (fungsi(argv) -> kode keluar, ringkasan)})."""


def _jalankan(argv):
    from . import jalankan
    return jalankan.main(argv)


def _kurikulum(argv):
    from . import kurikulum
    return kurikulum.main(argv)


def _uji(argv):
    from . import uji
    return uji.main(argv)


PERINTAH = {
    "jalankan": (_jalankan, "produk uji/klien -> render varian + QC-01..12 + contact sheet (--produk botol,kaleng)"),
    "kurikulum": (_kurikulum, "semua produk uji x 3 preset x palet -> LAPORAN.md + laporan.json"),
    "uji": (_uji, "uji verbs + uji negatif QC (88 uji) -> uji_verbs.json"),
}
