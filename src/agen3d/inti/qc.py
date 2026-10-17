"""Kerangka QC bersama: cek angka, uji negatif, pencatat uji, laporan ringkas.

Setiap cek = satu baris ATURAN_QC.md modul/proyeknya (ID sama). Semua cek berbentuk dict:
id, nama, nilai, ambang, lulus, konteks. Uji negatif = scene/berkas sengaja dirusak; cek yang `wajib` gagal harus gagal.
"""
import json
import os
import time
from dataclasses import dataclass, field


def cek(id_, nama, nilai, lulus, ambang, konteks=""):
    if isinstance(nilai, float):
        nilai = round(nilai, 4)
    return dict(id=id_, nama=nama, nilai=nilai, ambang=ambang, lulus=bool(lulus), konteks=konteks)


def iou(a, b):
    """Intersection over union dua masker boolean."""
    return float((a & b).sum() / max((a | b).sum(), 1))


def tertangkap(hasil, wajib):
    """Uji negatif tertangkap jika semua `wajib` gagal. Butir wajib: 'ID' (ada cek ID itu yang gagal) atau
    'ID:nama' (cek itu persis yang gagal). Mengembalikan (tertangkap, daftar ID yang gagal)."""
    gagal = {c["id"] for c in hasil if not c["lulus"]}
    gagal_nama = {f"{c['id']}:{c['nama']}" for c in hasil if not c["lulus"]}
    return all(w in gagal_nama if ":" in w else w in gagal for w in wajib), sorted(gagal)


@dataclass
class UjiNegatif:
    """Satu uji negatif: nama, cara merusak (parameter atau fungsi), cek yang WAJIB gagal."""
    nama: str
    rusak: object
    wajib: list = field(default_factory=list)


class Pencatat:
    """Pencatat hasil uji (uji verb, uji negatif, uji struktur): cetak per baris, ringkas, tulis JSON."""

    def __init__(self):
        self.hasil, self.t0 = [], time.time()

    def uji(self, nama, kondisi, detail=""):
        self.hasil.append(dict(uji=nama, lulus=bool(kondisi), detail=str(detail)))
        print(("  OK  " if kondisi else "  GAGAL ") + nama + (f"  [{detail}]" if detail else ""))
        return bool(kondisi)

    @property
    def lulus(self):
        return sum(h["lulus"] for h in self.hasil)

    @property
    def durasi(self):
        return time.time() - self.t0

    @property
    def semua_lulus(self):
        return self.lulus == len(self.hasil)

    def tulis(self, path, **tambahan):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        data = dict(lulus=self.semua_lulus, jumlah=len(self.hasil), **tambahan,
                    detik=round(time.time() - self.t0, 1), hasil=self.hasil)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        return path


def ringkas(cek_semua, negatif=()):
    """Ringkasan laporan: lulus, daftar gagal, jumlah negatif tertangkap."""
    return dict(lulus=all(c["lulus"] for c in cek_semua),
                gagal=[c["id"] + " " + c["nama"] for c in cek_semua if not c["lulus"]],
                negatif_tertangkap=sum(n["tertangkap"] for n in negatif), negatif_jumlah=len(negatif))
