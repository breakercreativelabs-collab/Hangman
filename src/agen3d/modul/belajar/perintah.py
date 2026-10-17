"""Perintah CLI modul belajar (kontrak cli: def _uji_telemetri(argv):
    from . import uji_telemetri
    o = io.opsi(argv, dict(out=io.artefak("uji", "telemetri")))
    return uji_telemetri.uji_semua(os.path.abspath(o["out"]))


PERINTAH = {nama: (fungsi(argv) -> kode keluar, ringkasan)})."""
import os

from ...inti import io, log, qc


def _catat(argv):
    from . import belajar
    o = io.opsi(argv, dict(jenis="cacat", modul="", proyek="", teks="", laporan="", simpan=io.artefak("belajar")))
    e = belajar.catat(os.path.abspath(o["simpan"]), o["jenis"], o["modul"], o["proyek"], o["teks"],
                      os.path.abspath(o["laporan"]) if o["laporan"] else "")
    log.info(f"tercatat LOKAL ({e['jenis']}, {e['modul']}/{e['proyek']}); belum terkirim ke mana pun. Kirim: belajar ekspor --setuju 1")
    return 0


def _ekspor(argv):
    from . import belajar
    o = io.opsi(argv, dict(simpan=io.artefak("belajar"), setuju="0", out=""))
    simpan = os.path.abspath(o["simpan"])
    b = belajar.kiriman(belajar.baca_catatan(simpan), o["setuju"] == "1")
    cek = belajar.audit(b)
    for c in cek:
        print(f"  {c['id']} {'LULUS' if c['lulus'] else 'GAGAL'} {c['nama']}: {c['nilai']} ({c['ambang']})")
    io.tulis_json(os.path.join(simpan, "pratinjau_kiriman.json"), b)
    if not all(c["lulus"] for c in cek):
        log.info(f"kiriman TIDAK dibuat (gagal {[c['id'] for c in cek if not c['lulus']]}); pratinjau: "
                 f"{os.path.join(simpan, 'pratinjau_kiriman.json')}")
        return 0 if o["setuju"] != "1" else 1
    out = os.path.abspath(o["out"] or os.path.join(simpan, "kiriman.json"))
    io.tulis_json(out, b)
    url = belajar.url_issue()
    log.info(f"kiriman {len(b['catatan'])} catatan -> {out}. Lampirkan ke Issue: {url or '(repo publik belum diisi di identitas.toml)'}")
    return 0


def _uji(argv):
    from . import belajar
    o = io.opsi(argv, dict(out=io.artefak("uji", "belajar")))
    neg = belajar.uji_negatif_kiriman()
    lap = dict(negatif=neg, **qc.ringkas([], neg))
    io.tulis_json(os.path.join(os.path.abspath(o["out"]), "uji_belajar.json"), lap)
    return 0 if lap["negatif_tertangkap"] == lap["negatif_jumlah"] else 1


def _uji_telemetri(argv):
    from . import uji_telemetri
    o = io.opsi(argv, dict(out=io.artefak("uji", "telemetri")))
    return uji_telemetri.uji_semua(os.path.abspath(o["out"]))


PERINTAH = {
    "catat": (_catat, "catat cacat/selera pengguna LOKAL (teks + angka QC dari --laporan), bahan agen makin pintar"),
    "ekspor": (_ekspor, "kiriman anonim (path/email/klien/token dibuang, audit KB-01..06) untuk GitHub Issue; wajib --setuju 1"),
    "uji_telemetri": (_uji_telemetri, "uji telemetri otomatis KM-01..07 (daftar putih, saklar mati, kirim, server mati) + negatif"),
    "uji": (_uji, "uji negatif audit privasi kiriman belajar (KB-01..06) + pembersihan"),
}
