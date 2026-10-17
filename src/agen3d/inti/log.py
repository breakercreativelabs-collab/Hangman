"""Log CLI. Nama produk dibaca dari identitas (jangan ditulis langsung di kode)."""
from .. import identitas


def banner(modul, perintah):
    print(f"== {identitas.judul()} :: {modul} {perintah}")


def info(pesan):
    print(pesan)
