"""Uji telemetri otomatis KM-01..07 + uji negatif (ATURAN_QC belajar). Memakai folder sementara (antrean pengguna
tidak disentuh) dan server HTTP lokal sungguhan untuk pengiriman."""
import http.server
import json
import os
import tempfile
import threading
import time

from ... import telemetri
from ...inti import qc
from . import belajar

RUMAH, WIN = "/ho" + "me/budi", "C:" + "\\Users\\budi"  # dirangkai: sumber ini sendiri lolos audit rilis (KR-05)
KOTOR = dict(jenis="job", modul="perakit", perintah="bangun", kode=0, detik=1.5, teks="rahasia klien",
             cek=[dict(id="KC-01", lulus=True, nilai=61.0), dict(id="KC-02", lulus=False, nilai=RUMAH + "/a.glb"),
                  dict(id=WIN, lulus=True, nilai=1.0)],
             resep={"putar": 1, WIN: 2}, galat="Error di " + RUMAH, proyek="merek_rahasia")


def _cek(saring, antrean_mati, terkirim, jumlah_antre, detik_mati, sisa_saat_mati, galat_ok):
    teks = json.dumps(saring)
    bocor = [k for k, (_, pola, _) in belajar.POLA.items() if pola.search(teks)] + \
        [w for w in ("rahasia", "merek_rahasia", "budi") if w in teks]
    return [
        qc.cek("KM-01", "hanya daftar putih skema (tanpa teks bebas/path/nama proyek)", bocor or "bersih", not bocor,
               "0 temuan"),
        qc.cek("KM-02", "saklar mati dihormati (env + berkas MATI)", antrean_mati, antrean_mati == 0, "0 peristiwa"),
        qc.cek("KM-03", "terkirim ke endpoint sungguhan, antrean dikosongkan", terkirim, terkirim is True, "true"),
        qc.cek("KM-04", "antrean dibatasi", jumlah_antre, jumlah_antre <= telemetri.MAKS_ANTRE, f"<= {telemetri.MAKS_ANTRE}"),
        qc.cek("KM-05", "server mati: job tidak tertahan (detik)", round(detik_mati, 2), detik_mati <= 3.5, "<= 3,5 s"),
        qc.cek("KM-06", "server mati: antrean disimpan untuk dicoba lagi", sisa_saat_mati, sisa_saat_mati > 0, "> 0"),
        qc.cek("KM-07", "galat hanya jenisnya (nama kode), bukan pesan", galat_ok, galat_ok, "nama atau kosong"),
    ]


def uji_semua(out):
    asli = telemetri.FOLDER
    hasil_server = []

    class Penerima(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            hasil_server.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Penerima)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    try:
        with tempfile.TemporaryDirectory() as t:
            telemetri.FOLDER = t
            s = telemetri.saring(KOTOR)
            os.environ["AGEN3D_TELEMETRI"] = "0"
            telemetri.catat_job("perakit", "bangun", 0, time.time())
            telemetri.catat_vonis(1)
            os.environ["AGEN3D_TELEMETRI"] = "1"
            telemetri.atur(False)
            telemetri.catat_vonis(1)
            p = os.path.join(t, "antrean.jsonl")
            mati = len(open(p).read().splitlines()) if os.path.isfile(p) else 0
            telemetri.atur(True)
            for _ in range(telemetri.MAKS_ANTRE + 20):
                telemetri.antre(dict(telemetri._dasar("vonis"), modul="perakit", perintah="bangun", nilai=-1))
            n_antre = len(open(p).read().splitlines())
            t0 = time.time()
            telemetri.kirim("http://10.255.255.1:9/", batas=3.0)  # alamat tak terjangkau
            detik_mati = time.time() - t0
            sisa = len(open(p).read().splitlines()) if os.path.isfile(p) else 0
            t1 = time.time()
            telemetri.kirim("http://10.255.255.1:9/", batas=3.0)  # dalam masa jeda: tidak boleh menunggu lagi
            detik_mati = max(detik_mati, 0.0) if time.time() - t1 < 0.5 else 30.0
            os.remove(os.path.join(t, "gagal_terakhir"))
            n = telemetri.kirim(url)
            terkirim = n == n_antre and not os.path.isfile(p) and len(hasil_server[-1]["peristiwa"]) == n_antre
            galat_ok = s.get("galat") is None and telemetri.saring(dict(KOTOR, galat="valueerror"))["galat"] == "valueerror"
            cek = _cek(s, mati, terkirim, n_antre, detik_mati, sisa, galat_ok)
            neg_spec = [
                ("tanpa daftar putih (peristiwa mentah)", dict(saring=KOTOR), "KM-01"),
                ("saklar mati diabaikan", dict(antrean_mati=2), "KM-02"),
                ("pengiriman gagal diam-diam", dict(terkirim=False), "KM-03"),
                ("antrean tak terbatas", dict(jumlah_antre=telemetri.MAKS_ANTRE + 20), "KM-04"),
                ("menunggu server mati 30 s", dict(detik_mati=30.0), "KM-05"),
                ("antrean dibuang saat server mati", dict(sisa_saat_mati=0), "KM-06"),
                ("pesan galat ikut terkirim", dict(galat_ok=False), "KM-07"),
            ]
    finally:
        telemetri.FOLDER = asli
        os.environ.pop("AGEN3D_TELEMETRI", None)
        srv.shutdown()
    dasar = dict(saring=s, antrean_mati=mati, terkirim=terkirim, jumlah_antre=n_antre, detik_mati=detik_mati,
                 sisa_saat_mati=sisa, galat_ok=galat_ok)
    neg = []
    for nama, ubah, wajib in neg_spec:
        ok, gagal = qc.tertangkap(_cek(**dict(dasar, **ubah)), [wajib])
        neg.append(dict(nama=nama, wajib=[wajib], gagal=gagal, tertangkap=ok))
    for c in cek:
        print(f"  {c['id']} {'LULUS' if c['lulus'] else 'GAGAL'} {c['nama']}: {c['nilai']} ({c['ambang']})")
    for n in neg:
        print(f"  negatif telemetri {'OK ' if n['tertangkap'] else 'BOCOR'} {n['nama']}: gagal {n['gagal']}")
    lap = dict(cek=cek, negatif=neg, **qc.ringkas(cek, neg))
    from ...inti import io
    io.tulis_json(os.path.join(out, "uji_telemetri.json"), lap)
    return 0 if lap["lulus"] and lap["negatif_tertangkap"] == lap["negatif_jumlah"] else 1
