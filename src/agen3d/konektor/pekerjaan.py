"""Job latar konektor: setiap perintah CLI / kode bebas = satu proses dengan folder pekerjaan sendiri.

artefak/konektor/pekerjaan/<id>/  meta.json · argv.json · log.txt · hidup.lock (dipegang pembungkus selama hidup) ·
pembungkus.json · minta_batal · selesai.json (satu penulis: pembungkus) · keluaran.json (ringkasan, dihitung sekali) ·
untuk kode bebas: kode.py, permintaan.json, hasil.json, pratinjau.png.
Status: memulai | berjalan | selesai | gagal | dibatalkan | terputus (pembungkus mati tanpa kode keluar, mis. sesi Claude
ditutup oleh klien yang mematikan seluruh job object, atau komputer restart).
"""
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time

from . import blender as bl
from . import bungkus

FOLDER = os.path.join(bl.AKAR, "artefak", "konektor", "pekerjaan")
BUNGKUS = os.path.abspath(bungkus.__file__)
BATAS_TUNGGU = max(0, min(int(os.environ.get("AGEN3D_BATAS_TUNGGU", "50")), 3600))  # < batas Claude Desktop ±60 s
MASA_MULAI = 20                       # detik: tanpa hidup.lock setelah ini = pembungkus tidak pernah mulai
PINDAI = ("artefak", "proyek")        # cadangan bila job tidak menyatakan folder keluaran
MAKS_PINDAI = 20000                   # entri berkas maksimum per pemindaian
GAMBAR = (".jpg", ".jpeg", ".png")
MAKS_GAMBAR = 700_000                 # byte mentah (base64 ±930 KB, di bawah batas hasil alat klien)
PRIORITAS_GAMBAR = ("contact_sheet", "storyboard", "lembar", "pratinjau", "sebelum_sesudah")
MAKS_HASIL = 8000                     # karakter HASIL kode bebas di respons; versi penuh tetap di hasil.json
MAKS_TEKS = 4000                      # stdout/galat di respons


def muat_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def folder_baru():
    """(id, folder) unik lintas instance server (pid + acak), folder diklaim atomik."""
    os.makedirs(FOLDER, exist_ok=True)
    while True:
        ident = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid() % 100000:05d}-{secrets.token_hex(2)}"
        d = os.path.join(FOLDER, ident)
        try:
            os.makedirs(d)
            return ident, d
        except FileExistsError:
            continue


def mulai(argv, jenis, judul, ident=None, folder=None, keluaran=()):
    """Jalankan argv di latar lewat pembungkus dua tahap; kembalikan id job. keluaran = path yang dinyatakan job
    (dipindai untuk ringkasan hasil; kosong = pindai artefak/ + proyek/)."""
    if ident is None:
        ident, folder = folder_baru()
    meta = dict(id=ident, jenis=jenis, judul=judul, argv=argv, mulai=time.time(), keluaran=list(keluaran))
    bungkus.tulis_atomik(os.path.join(folder, "meta.json"), meta)
    bungkus.tulis_atomik(os.path.join(folder, "argv.json"), dict(argv=argv, cwd=bl.AKAR))
    try:
        r = subprocess.run([sys.executable, "-I", BUNGKUS, "--lepas", folder], cwd=bl.AKAR, capture_output=True,
                           text=True, errors="replace", timeout=30, stdin=subprocess.DEVNULL)
        galat = None if r.returncode == 0 else (r.stdout + r.stderr)[-800:]
    except (OSError, subprocess.SubprocessError) as e:
        galat = str(e)
    if galat:
        bungkus.tulis_atomik(os.path.join(folder, "selesai.json"), dict(kode=127, selesai=time.time(),
                                                                          galat=f"pembungkus gagal dimulai: {galat}"))
    return ident


def _folder(ident):
    d = os.path.join(FOLDER, os.path.basename(str(ident)))
    return d if os.path.isfile(os.path.join(d, "meta.json")) else None


def _akhir(d):
    """selesai.json; bila pembungkus mati tanpa menulisnya, tulis status terminal `terputus` (sekali)."""
    akhir = muat_json(os.path.join(d, "selesai.json"))
    if akhir is not None:
        return akhir
    h = bungkus.masih_hidup(d)
    meta = muat_json(os.path.join(d, "meta.json")) or {}
    if h or time.time() - meta.get("mulai", 0) < MASA_MULAI:  # K-12: jendela buka->kunci saat pembungkus mulai
        return None
    akhir = muat_json(os.path.join(d, "selesai.json"))  # K-12: pembungkus menulisnya TEPAT sebelum melepas kunci
    if akhir is not None:
        return akhir
    akhir = dict(kode=None, selesai=time.time(), terputus=True,
                 alasan="proses job berhenti tanpa kode keluar (sesi Claude ditutup, komputer restart, atau "
                        "pembungkus tidak pernah mulai)")
    bungkus.tulis_atomik(os.path.join(d, "selesai.json"), akhir)
    return akhir


async def tunggu(ident, detik):
    """Tunggu job selesai, maksimal min(detik, BATAS_TUNGGU)."""
    d = _folder(ident)
    t_akhir = time.monotonic() + max(0, min(int(detik), BATAS_TUNGGU))
    while d and time.monotonic() < t_akhir:
        if await asyncio.to_thread(_akhir, d) is not None:
            return True
        await asyncio.sleep(0.5)
    return bool(d) and _akhir(d) is not None


def ekor_log(d, n=20, maks_baris=300):
    p = os.path.join(d, "log.txt")
    try:
        with open(p, "rb") as f:
            f.seek(max(0, os.path.getsize(p) - 65536))
            baris = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    penting = [b.rstrip()[:maks_baris] for b in baris if b.strip() and not b.lstrip().startswith(("Fra:", "|"))]
    return penting[-n:]


def ringkas_qc(path):
    j = muat_json(path)
    if not isinstance(j, dict) or "lulus" not in j:
        return None
    jumlah = len(j["cek"]) if isinstance(j.get("cek"), list) else j.get("jumlah_cek", j.get("jumlah"))
    gagal = j.get("gagal")
    r = dict(berkas=os.path.relpath(path, bl.AKAR), lulus=j["lulus"], jumlah_cek=jumlah,
             gagal=gagal[:15] if isinstance(gagal, list) else gagal)
    neg = j.get("uji_negatif")
    if isinstance(neg, list):
        r["uji_negatif"] = f"{sum(bool(n.get('tertangkap')) for n in neg)}/{len(neg)} tertangkap"
    return r


def keluaran_baru(akar_pindai, sejak, sampai):
    """Berkas yang ditulis dalam jendela [sejak-1, sampai+2] di bawah akar_pindai (folder job dilewati)."""
    baru, dilihat = [], 0
    tumpuk = [p for p in akar_pindai if os.path.isdir(p)]
    for p in akar_pindai:
        if os.path.isfile(p):
            st = os.stat(p)
            if sejak - 1 <= st.st_mtime <= sampai + 2:
                baru.append((st.st_mtime, st.st_size, p))
    while tumpuk and dilihat < MAKS_PINDAI:
        try:
            with os.scandir(tumpuk.pop()) as it:
                for e in it:
                    dilihat += 1
                    if e.is_dir(follow_symlinks=False):
                        if e.name != "__pycache__" and os.path.normcase(e.path) != os.path.normcase(FOLDER):
                            tumpuk.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        st = e.stat()
                        if sejak - 1 <= st.st_mtime <= sampai + 2:
                            baru.append((st.st_mtime, st.st_size, e.path))
        except OSError:
            continue
    baru.sort(reverse=True)
    per_folder = {}
    for _, _, p in baru:
        k = os.path.relpath(os.path.dirname(p), bl.AKAR)
        per_folder[k] = per_folder.get(k, 0) + 1
    qc = [r for r in (ringkas_qc(p) for _, _, p in baru if p.endswith(".json")) if r][:10]
    gambar = [(t, s, p) for t, s, p in baru if p.lower().endswith(GAMBAR) and s <= MAKS_GAMBAR]
    gambar.sort(key=lambda x: (not any(k in os.path.basename(x[2]).lower() for k in PRIORITAS_GAMBAR), -x[0]))
    contoh = [os.path.relpath(p, bl.AKAR) for _, _, p in baru if not p.lower().endswith(".png")][:15]
    return dict(jumlah_berkas=len(baru), per_folder=dict(list(per_folder.items())[:15]), contoh=contoh, qc=qc,
                gambar=gambar[0][2] if gambar else None, pindaian_terpotong=dilihat >= MAKS_PINDAI)


def _ringkas_hasil_kode(d, hasil):
    r = dict(hasil)
    for k in ("stdout", "galat", "galat_pratinjau"):
        if isinstance(r.get(k), str) and len(r[k]) > MAKS_TEKS:
            r[k] = "...(terpotong)...\n" + r[k][-MAKS_TEKS:]
    if "HASIL" in r:
        teks = json.dumps(r["HASIL"], ensure_ascii=False, default=str)
        if len(teks) > MAKS_HASIL:
            r["HASIL"] = dict(terpotong=True, panjang=len(teks), awal=teks[:2000],
                              berkas_lengkap=os.path.relpath(os.path.join(d, "hasil.json"), bl.AKAR))
    return r


def status(ident):
    d = _folder(ident)
    if not d:
        return dict(id=ident, status="tidak dikenal")
    meta = muat_json(os.path.join(d, "meta.json")) or {}
    r = dict(id=meta.get("id", ident), judul=meta.get("judul"), jenis=meta.get("jenis"))
    akhir = _akhir(d)
    if akhir is None:
        st = "berjalan" if bungkus.masih_hidup(d) else "memulai"
        r.update(status=st, detik=round(time.time() - meta.get("mulai", time.time())), log=ekor_log(d, 12))
        return r
    st = ("dibatalkan" if akhir.get("dibatalkan") else "terputus" if akhir.get("terputus") else
          "selesai" if akhir.get("kode") == 0 else "gagal")
    r.update(status=st, kode=akhir.get("kode"), detik=round(akhir["selesai"] - meta.get("mulai", akhir["selesai"])),
             log=ekor_log(d))
    for k in ("alasan", "galat"):
        if akhir.get(k):
            r[k] = akhir[k]
    hasil = muat_json(os.path.join(d, "hasil.json"))
    if isinstance(hasil, dict):
        r["hasil_kode"] = _ringkas_hasil_kode(d, hasil)
    kel = muat_json(os.path.join(d, "keluaran.json"))
    if kel is None:
        akar = [p for p in meta.get("keluaran", []) if p] or [os.path.join(bl.AKAR, a) for a in PINDAI]
        kel = keluaran_baru(akar, meta.get("mulai", akhir["selesai"]), akhir["selesai"])
        if meta.get("jenis") == "kode":
            kel["gambar"] = (hasil or {}).get("pratinjau")  # kode bebas: hanya pratinjau yang diminta
        bungkus.tulis_atomik(os.path.join(d, "keluaran.json"), kel)
    r["keluaran"] = kel
    if meta.get("jenis") == "uji":
        u = muat_json(os.path.join(d, "uji", "ringkasan.json")) or {}
        h = u.get("hasil", [])
        r["ringkasan_uji"] = dict(lulus=u.get("lulus"), butir=len(h), lewat=u.get("lewat"),
                                  gagal=[x["nama"] for x in h if x.get("lulus") is False][:15])
    return r


def batalkan(ident):
    d = _folder(ident)
    if not d or _akhir(d) is not None or not bungkus.masih_hidup(d):
        return dict(id=ident, dibatalkan=False, alasan="job tidak dikenal atau sudah tidak berjalan")
    with open(os.path.join(d, "minta_batal"), "w", encoding="utf-8") as f:
        f.write(str(time.time()))
    for _ in range(60):  # pembungkus menghentikan anaknya sendiri lalu menulis selesai.json
        akhir = muat_json(os.path.join(d, "selesai.json"))
        if akhir is not None:
            return dict(id=ident, dibatalkan=bool(akhir.get("dibatalkan")), kode=akhir.get("kode"))
        time.sleep(0.25)
    return dict(id=ident, dibatalkan=False, alasan="permintaan batal terkirim; job belum berhenti dalam 15 s")


def daftar_terbaru(n=15):
    if not os.path.isdir(FOLDER):
        return []
    hasil = []
    for ident in sorted(os.listdir(FOLDER), reverse=True)[:max(1, min(int(n), 100))]:
        d = os.path.join(FOLDER, ident)
        meta = muat_json(os.path.join(d, "meta.json")) or {}
        akhir = muat_json(os.path.join(d, "selesai.json"))
        st = ("berjalan/memulai" if akhir is None else "dibatalkan" if akhir.get("dibatalkan") else
              "terputus" if akhir.get("terputus") else "selesai" if akhir.get("kode") == 0 else "gagal")
        hasil.append(dict(id=ident, judul=str(meta.get("judul"))[:120], status=st))
    return hasil
