"""Identitas produk dibaca dari identitas.toml di akar repo (satu-satunya tempat nama produk)."""
import os
import tomllib

AKAR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BERKAS = os.path.join(AKAR, "identitas.toml")
_DATA = {}


def baca():
    if not _DATA:
        with open(BERKAS, "rb") as f:
            _DATA.update(tomllib.load(f))
    return dict(_DATA)


def nama():
    return baca()["nama"]


def slug():
    return baca()["slug"]


def deskripsi():
    return baca()["deskripsi"]


def versi():
    return baca()["versi"]


def judul():
    """Teks pendek untuk banner CLI/log/MCP, mis. '<nama> 0.1.0'."""
    return f"{nama()} {versi()}"


def repo_publik():
    """'pemilik/repo' tujuan kiriman belajar (GitHub Issue); '' bila belum dipublikasikan."""
    return baca().get("repo_publik", "")
