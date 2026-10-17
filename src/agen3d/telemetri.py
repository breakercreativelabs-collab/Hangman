"""Telemetri otomatis (keputusan pengguna 2026-10-17: menyala bawaan, tanpa ditanya; agen makin pintar dari pemakaian).

Batas yang tidak boleh dilanggar (ATURAN_QC belajar, KM-01..07):
- HANYA angka + ID pendek dari daftar putih skema: versi, OS, modul/perintah, kode keluar, durasi, hasil cek QC
  (ID, lulus, nilai angka), jumlah uji negatif, resep yang dipakai, jenis galat, vonis 👍/👎. Tanpa teks bebas, nama
  berkas/proyek, path, gambar, model, prompt.
- Diberitahukan (README + panel Blender) dan bisa dimatikan satu klik: berkas `artefak/telemetri/MATI`, env
  AGEN3D_TELEMETRI=0 (runner uji kita memakainya), atau tombol di panel.
- Tidak pernah memperlambat/menggagalkan job: antre ke berkas, kirim dengan batas waktu 3 s, galat ditelan.
"""
import json
import os
import platform
import re
import time
import urllib.request
import uuid

from . import identitas

FOLDER = os.path.join(identitas.AKAR, "artefak", "telemetri")
MAKS_ANTRE = 500
JEDA_ULANG = 600  # detik setelah kiriman gagal sebelum mencoba lagi
ID_POLA = re.compile(r"^[A-Za-z]{1,4}-\d{1,3}$")          # KC-01, KA-08, QC-11, TV-03, ...
NAMA_POLA = re.compile(r"^[a-z][a-z0-9_]{0,31}$")         # nama modul/perintah/resep/galat (kode, bukan data pengguna)
KUNCI = {"job": {"v", "jenis", "id_pasang", "versi", "os", "blender", "modul", "perintah", "kode", "detik", "cek",
                 "negatif", "resep", "galat"},
         "vonis": {"v", "jenis", "id_pasang", "versi", "os", "modul", "perintah", "nilai"}}


def aktif():
    return os.environ.get("AGEN3D_TELEMETRI", "1") != "0" and not os.path.exists(os.path.join(FOLDER, "MATI"))


def atur(nyala):
    """Saklar satu klik (dipakai panel Blender)."""
    os.makedirs(FOLDER, exist_ok=True)
    p = os.path.join(FOLDER, "MATI")
    if nyala and os.path.exists(p):
        os.remove(p)
    elif not nyala:
        open(p, "w").close()


def id_pasang():
    """UUID acak per pemasangan (bukan identitas orang): mendeteksi satu pemasangan yang membanjiri data (racun)."""
    p = os.path.join(FOLDER, "id_pasang")
    if not os.path.isfile(p):
        os.makedirs(FOLDER, exist_ok=True)
        with open(p, "w") as f:
            f.write(uuid.uuid4().hex)
    with open(p) as f:
        return f.read().strip()[:32]


def _nama(x):
    return x if isinstance(x, str) and NAMA_POLA.match(x) else None


def _angka(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 1e9 else None


def saring(e):
    """Daftar putih: buang semua kunci/nilai di luar skema. Hasil tidak pernah memuat teks bebas."""
    jenis = e.get("jenis")
    if jenis not in KUNCI:
        return None
    k = {x: e[x] for x in KUNCI[jenis] if x in e}
    k["modul"], k["perintah"] = _nama(k.get("modul")), _nama(k.get("perintah"))
    if jenis == "vonis":
        k["nilai"] = k.get("nilai") if k.get("nilai") in (1, -1) else None
        return k if k["nilai"] else None
    k["kode"], k["detik"] = _angka(k.get("kode")), _angka(k.get("detik"))
    k["cek"] = [dict(id=c["id"], lulus=bool(c.get("lulus")), **({"nilai": _angka(c.get("nilai"))}
                                                                  if _angka(c.get("nilai")) is not None else {}))
                for c in (k.get("cek") or [])[:200] if isinstance(c, dict) and ID_POLA.match(str(c.get("id", "")))]
    neg = k.get("negatif") or [0, 0]
    k["negatif"] = [int(_angka(neg[0]) or 0), int(_angka(neg[1]) or 0)] if isinstance(neg, list) and len(neg) == 2 else [0, 0]
    k["resep"] = {n: int(v) for n, v in (k.get("resep") or {}).items() if _nama(n) and _angka(v) is not None}
    k["galat"] = _nama(k.get("galat"))
    for x in ("versi", "os", "blender"):
        k[x] = str(k.get(x, ""))[:20] if re.match(r"^[\w .\-]*$", str(k.get(x, ""))) else ""
    k["id_pasang"] = str(k.get("id_pasang", ""))[:32] if re.match(r"^[0-9a-f]*$", str(k.get("id_pasang", ""))) else ""
    return k


def _dasar(jenis):
    d = dict(v=1, jenis=jenis, id_pasang=id_pasang(), versi=identitas.versi(), os=platform.system())
    try:
        import bpy
        d["blender"] = bpy.app.version_string.split()[0]
    except ImportError:
        pass
    return d


def ringkas_keluaran(t0, akar=None):
    """Cek QC, uji negatif, dan resep dari laporan JSON yang ditulis job ini (mtime >= t0) di artefak/ dan proyek/."""
    cek, neg, resep = [], [0, 0], {}
    for a in akar or (os.path.join(identitas.AKAR, "artefak"), os.path.join(identitas.AKAR, "proyek")):
        for d, sub, fs in os.walk(a):
            sub[:] = [s for s in sub if s not in ("telemetri", "konektor", "tonton")]
            for f in fs:
                p = os.path.join(d, f)
                if not f.endswith(".json") or os.path.getmtime(p) < t0 or os.path.getsize(p) > 5_000_000:
                    continue
                try:
                    with open(p, encoding="utf-8") as fh:
                        j = json.load(fh)
                except (OSError, ValueError):
                    continue
                if isinstance(j, dict):
                    cek += [c for c in j.get("cek", []) if isinstance(c, dict)]
                    neg[0] += sum(1 for n in j.get("negatif", []) if isinstance(n, dict) and n.get("tertangkap"))
                    neg[1] += sum(1 for n in j.get("negatif", []) if isinstance(n, dict))
                    for b in j.get("resep_dipakai", []):
                        resep[b] = resep.get(b, 0) + 1
    return cek, neg, resep


def catat_job(modul, perintah, kode, t0, galat=None):
    if not aktif():
        return
    try:
        cek, neg, resep = ringkas_keluaran(t0)
        antre(dict(_dasar("job"), modul=modul, perintah=perintah, kode=kode, detik=round(time.time() - t0, 1), cek=cek,
                   negatif=neg, resep=resep, galat=galat))
        kirim()
    except Exception:  # noqa: BLE001 - telemetri tidak boleh menggagalkan job
        pass


def catat_vonis(nilai, modul="perakit", perintah="bangun"):
    if not aktif():
        return
    try:
        antre(dict(_dasar("vonis"), modul=modul, perintah=perintah, nilai=nilai))
        kirim()
    except Exception:  # noqa: BLE001
        pass


def antre(e):
    e = saring(e)
    if not e:
        return
    os.makedirs(FOLDER, exist_ok=True)
    p = os.path.join(FOLDER, "antrean.jsonl")
    baris = open(p, encoding="utf-8").read().splitlines()[-(MAKS_ANTRE - 1):] if os.path.isfile(p) else []
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(baris + [json.dumps(e, ensure_ascii=True)]) + "\n")


def kirim(url=None, batas=3.0):
    """POST antrean ke endpoint (identitas.toml telemetri_url); berhasil -> antrean dikosongkan. Kembalikan jumlah."""
    url = url if url is not None else identitas.baca().get("telemetri_url", "")
    p = os.path.join(FOLDER, "antrean.jsonl")
    if not url or not os.path.isfile(p):
        return 0
    with open(p, encoding="utf-8") as f:
        isi = [json.loads(b) for b in f if b.strip()]
    if not isi:
        return 0
    jeda = os.path.join(FOLDER, "gagal_terakhir")
    if os.path.isfile(jeda) and time.time() - os.path.getmtime(jeda) < JEDA_ULANG:
        return 0  # baru saja gagal: jangan tahan job berikutnya 3 s lagi (KM-05)
    data = json.dumps(dict(peristiwa=isi)).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=batas) as r:
            if r.status // 100 != 2:
                return 0
    except Exception:  # noqa: BLE001 - jaringan mati / server down: coba lagi setelah JEDA_ULANG
        open(jeda, "w").close()
        return 0
    os.remove(p)
    if os.path.isfile(jeda):
        os.remove(jeda)
    return len(isi)
