"""Perintah CLI modul modeling_referensi (kontrak cli: PERINTAH = {nama: (fungsi(argv) -> kode keluar, ringkasan)})."""
import os

from ...inti import io


def _qc(argv):
    from .sepatu import laporan
    return laporan.main(argv)


def _bangun(argv):
    """Bangun model dari data proyek dan simpan .blend (sama dengan model_am1.py lama, tanpa QC)."""
    from . import api
    o = io.opsi(argv, dict(proyek="am1", out=""))
    api.muat_proyek(o["proyek"])
    obs = api.bangun_model()
    out = api.simpan_model(os.path.abspath(o["out"]) if o["out"] else None)
    print("MODEL tersimpan:", out, {k: len(v.data.vertices) for k, v in obs.items() if getattr(v, "type", "") == "MESH"})
    return 0 if os.path.isfile(out) else 1


def _ekstrak_kontur(argv):
    from .ekstraksi import kontur
    from .sepatu import data
    o = io.opsi(argv, dict(proyek="am1", ref="", out=""))
    k = data.muat_data(o["proyek"], tanpa_referensi=True)
    out = os.path.abspath(o["out"] or io.proyek(o["proyek"], k["data"]["referensi"]))
    kontur.ekstrak_kontur(os.path.abspath(o["ref"]), out, k["ekstraksi"])
    return 0


def _ekstrak_panel(argv):
    from .ekstraksi import panel
    from .sepatu import data
    o = io.opsi(argv, dict(proyek="am1", ref="", data="", out=""))
    k = data.muat_data(o["proyek"], tanpa_referensi=True)
    acuan = os.path.abspath(o["data"] or io.proyek(o["proyek"], k["data"]["referensi"]))
    out = os.path.abspath(o["out"] or io.proyek(o["proyek"], k["data"]["panel"]))
    panel.ekstrak_panel(os.path.abspath(o["ref"]), acuan, out, k["ekstraksi"])
    return 0


def _ekstrak_kelas(argv):
    from .ekstraksi import kelas
    from .sepatu import data
    o = io.opsi(argv, dict(proyek="am1", ref="", data="", out=""))
    k = data.muat_data(o["proyek"], tanpa_referensi=True)
    acuan = os.path.abspath(o["data"] or io.proyek(o["proyek"], k["data"]["referensi"]))
    out = os.path.abspath(o["out"] or io.proyek(o["proyek"], k["data"]["kelas"]))
    kelas.ekstrak_kelas(os.path.abspath(o["ref"]), acuan, out, k["ekstraksi"])
    return 0


def _tujuan(o, d, kunci):
    """Path berkas data `kunci` ([data] proyek.toml): di folder --out bila diberikan (uji / MCP: data proyek yang
    ter-track tidak tersentuh), selain itu di folder proyek (perilaku lama)."""
    if o.get("out"):
        os.makedirs(os.path.abspath(o["out"]), exist_ok=True)
        return os.path.join(os.path.abspath(o["out"]), os.path.basename(d[kunci]))
    return io.proyek(o["proyek"], d[kunci])


def _ekstrak_tapak(argv):
    from .ekstraksi import tapak
    from .sepatu import data
    o = io.opsi(argv, dict(proyek="am1", ref="", data="", out=""))
    k = data.muat_data(o["proyek"], tanpa_referensi=True)
    d = k["data"]
    acuan = os.path.abspath(o["data"]) if o["data"] else io.proyek(o["proyek"], d["referensi"])
    tapak.ekstrak_tapak(os.path.abspath(o["ref"]), acuan, _tujuan(o, d, "tapak"), _tujuan(o, d, "tapak_alur"),
                        k["ekstraksi"])
    return 0


def _data(argv):
    """Satu perintah foto -> data: analisis alfa + kontur (kalibrasi sol) + kelas warna (garis midsole, jendela, panel)
    atau panel luma (AM1). Cek silang skala dicetak; kode 1 bila selisih rasio lab > ambang [ekstraksi] cek_rasio_pct."""
    import json
    from .ekstraksi import alfa
    from .sepatu import data
    o = io.opsi(argv, dict(proyek="am1", ref="", out=""))
    k = data.muat_data(o["proyek"], tanpa_referensi=True)
    d, ref = k["data"], os.path.abspath(o["ref"])
    dasar = ["--proyek", o["proyek"], "--ref", ref]
    acuan = _tujuan(o, d, "referensi")
    ke = (lambda kunci: ["--data", acuan, "--out", _tujuan(o, d, kunci)]) if o["out"] else (lambda kunci: [])
    alfa.analisis_alfa(ref)
    _ekstrak_kontur(dasar + (["--out", acuan] if o["out"] else []))
    if k["ekstraksi"].get("garis_luma", True):
        _ekstrak_panel(dasar + ke("panel"))
    else:
        _ekstrak_kelas(dasar + ke("kelas"))
    if "tapak" in d:
        _ekstrak_tapak(dasar + (["--data", acuan, "--out", o["out"]] if o["out"] else []))
    kal = json.load(open(acuan, encoding="utf-8"))["kalibrasi"]
    print("KALIBRASI", json.dumps(kal))
    batas = k["ekstraksi"].get("cek_rasio_pct")
    if batas is not None and abs(kal.get("selisih_rasio_pct", 0.0)) > batas:
        print(f"GAGAL cek silang skala: selisih rasio tumit/forefoot {kal['selisih_rasio_pct']} % > {batas} %")
        return 1
    return 0


def _analisis_alfa(argv):
    from .ekstraksi import alfa
    alfa.analisis_alfa(os.path.abspath(io.opsi(argv, dict(ref=""))["ref"]))
    return 0


def _foto_uji(argv):
    """Foto referensi sintetis dari model proyek (uji asap ekstraksi, suite cli; C-B3)."""
    from . import api
    from .ekstraksi import foto_uji
    o = io.opsi(argv, dict(proyek="am1", out=""))
    api.muat_proyek(o["proyek"])
    api.bangun_model()
    hasil = foto_uji.foto_uji(os.path.abspath(o["out"] or io.artefak(o["proyek"], "foto_uji")))
    print("FOTO UJI:", hasil)
    return 0


PERINTAH = {
    "qc": (_qc, "bangun model proyek + QC AM-01..18 + 25 uji negatif + contact sheet (--proyek am1)"),
    "bangun": (_bangun, "bangun model dari data proyek -> .blend (artefak) tanpa QC"),
    "ekstrak_kontur": (_ekstrak_kontur, "foto referensi (klien/) -> JSON siluet/plan/garis (--ref <folder>)"),
    "ekstrak_panel": (_ekstrak_panel, "foto referensi (klien/) -> JSON panel upper (--ref <folder>)"),
    "analisis_alfa": (_analisis_alfa, "distribusi alfa foto referensi + masker uji (--ref <folder>)"),
    "foto_uji": (_foto_uji, "foto referensi SINTETIS dari model (render rata per peran) untuk uji asap ekstraksi (--out)"),
    "ekstrak_kelas": (_ekstrak_kelas, "foto referensi -> JSON panel per kelas warna + garis midsole/jendela (--ref <folder>)"),
    "ekstrak_tapak": (_ekstrak_tapak, "foto sol -> zona warna outsole (poligon plan) + peta alur tapak PNG (--ref <folder>; "
                                      "--out <folder> = jangan tulis ke data proyek)"),
    "data": (_data, "SATU perintah foto -> data: alfa + kontur + kelas/panel + tapak + cek silang skala (--proyek <id> "
                    "--ref <folder>; --out <folder> = tulis ke folder itu, bukan data proyek)"),
}
