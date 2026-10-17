"""Belajar dari banyak pengguna (keputusan pengguna 2026-10-17: open source publik, kiriman lewat GitHub Issue).

Alur: pengguna (atau Claude atas nama pengguna) `catat` cacat/selera -> tersimpan LOKAL (catatan.jsonl) ->
`ekspor --setuju 1` membuat kiriman anonim (path, email, nama pengguna, berkas klien, token dibuang) yang diaudit
KB-01..06 -> pengguna melampirkannya ke Issue -> pengelola mengubahnya jadi aturan + uji negatif -> rilis.
Tidak ada yang terkirim otomatis; tanpa persetujuan eksplisit, hanya pratinjau yang ditulis.
"""
import getpass
import json
import os
import platform
import re
import time

from ... import identitas
from ...inti import qc

JENIS = ("cacat", "selera")
POLA = {  # (ID, nama, regex yang TIDAK boleh ada di kiriman, pengganti)
    "KB-01": ("path absolut", re.compile(r"[A-Za-z]:[\\/][^\s\"',;]+|/(?:home|Users|root|mnt|tmp|var|opt|media)/[^\s\"',;]+"),
              "<path>"),
    "KB-02": ("alamat email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    "KB-03": ("berkas klien", re.compile(r"klien[\\/][^\s\"',;]*"), "<klien>"),
    "KB-04": ("token/kunci rahasia", re.compile(r"(?:ghp_|github_pat_|sk-ant-|sk-|AKIA|xox[bp]-)[A-Za-z0-9_\-]{8,}|-----BEGIN [A-Z ]+-----"),
              "<rahasia>"),
}
MAKS_BYTE = 200_000


def _nama_pengguna():
    nama = {os.environ.get(k, "") for k in ("USER", "USERNAME", "LOGNAME")}
    try:
        nama.add(getpass.getuser())
    except Exception:  # noqa: BLE001 - lingkungan tanpa nama pengguna
        pass
    return sorted((n for n in nama if len(n) >= 3), key=len, reverse=True)


def bersihkan(nilai, pengguna=None):
    """Bersihkan rekursif semua teks: rahasia, klien, path, email, nama pengguna OS."""
    pengguna = _nama_pengguna() if pengguna is None else pengguna
    if isinstance(nilai, dict):
        return {k: bersihkan(v, pengguna) for k, v in nilai.items()}
    if isinstance(nilai, list):
        return [bersihkan(v, pengguna) for v in nilai]
    if not isinstance(nilai, str):
        return nilai
    for kunci in ("KB-04", "KB-03", "KB-01", "KB-02"):  # rahasia & klien dulu (bisa berada di dalam path)
        nilai = POLA[kunci][1].sub(POLA[kunci][2], nilai)
    for n in pengguna:
        nilai = re.sub(re.escape(n), "<pengguna>", nilai, flags=re.IGNORECASE)
    return nilai


def ringkas_laporan(path):
    """Angka QC dari laporan JSON (id, nama, nilai, lulus) tanpa isi lain; None bila tidak ada."""
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    cek = d.get("cek", [])
    return dict(lulus=d.get("lulus"), cek=[{k: c.get(k) for k in ("id", "nama", "nilai", "lulus")} for c in cek][:80])


def catat(simpan, jenis, modul, proyek, teks, laporan=""):
    if jenis not in JENIS:
        raise ValueError(f"jenis harus salah satu {JENIS}")
    if not teks.strip():
        raise ValueError("teks kosong: tulis cacat/selera dalam 1-3 kalimat")
    os.makedirs(simpan, exist_ok=True)
    e = dict(waktu=time.strftime("%Y-%m-%dT%H:%M:%S"), jenis=jenis, modul=modul, proyek=proyek, teks=teks.strip(),
             qc=ringkas_laporan(laporan))
    with open(os.path.join(simpan, "catatan.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def baca_catatan(simpan):
    path = os.path.join(simpan, "catatan.jsonl")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(b) for b in f if b.strip()]


def kiriman(catatan, setuju):
    """Bundel kiriman (sudah dibersihkan)."""
    lingkungan = dict(versi=identitas.versi(), os=platform.system(), python=platform.python_version())
    try:
        import bpy
        lingkungan["blender"] = bpy.app.version_string
    except ImportError:
        pass
    return dict(format="kiriman-belajar/1", setuju=bool(setuju), lingkungan=lingkungan, catatan=bersihkan(catatan))


def audit(bundel):
    """KB-01..06: kiriman tidak boleh memuat data pribadi/klien/rahasia; wajib disetujui; ukuran wajar."""
    teks = json.dumps(bundel, ensure_ascii=False)
    cek = [qc.cek(k, f"tidak ada {nama}", len(pola.findall(teks)), not pola.search(teks), "0 temuan")
           for k, (nama, pola, _) in POLA.items()]
    cek.append(qc.cek("KB-05", "persetujuan eksplisit pengguna", bundel.get("setuju"), bundel.get("setuju") is True,
                      "--setuju 1"))
    n = len(teks.encode("utf-8"))
    cek.append(qc.cek("KB-06", "ukuran kiriman (byte)", n, n <= MAKS_BYTE, f"<= {MAKS_BYTE}"))
    return cek


def url_issue():
    repo = identitas.repo_publik()
    return f"https://github.com/{repo}/issues/new?template=kiriman-belajar.yml" if repo else ""


def uji_negatif_kiriman():
    """Kiriman kotor tanpa pembersihan WAJIB ditolak audit; dengan pembersihan wajib lolos."""
    win, lin, mail, tok = "C:" + "\\Users\\budi\\Desktop\\job.blend", "/ho" + "me/sari/proyek/a.glb", \
        "budi" + "@" + "contoh.com", "gh" + "p_ABCDEFGHIJKLMNOP1234"  # dirangkai: sumber ini sendiri lolos audit rilis
    kotor = [dict(jenis="cacat", modul="perakit", proyek="x", qc=None,
                  teks=f"render di {win} dan {lin} salah; hubungi {mail}; foto klien/merek-x/produk.jpg; token {tok} bocor")]
    rusak = [
        ("path absolut tanpa dibersihkan", dict(kiriman([], True), catatan=[dict(teks=win)]),
         "KB-01"),
        ("email tanpa dibersihkan", dict(kiriman([], True), catatan=[dict(teks=mail)]), "KB-02"),
        ("berkas klien tanpa dibersihkan", dict(kiriman([], True), catatan=[dict(teks="klien/merek-x/a.jpg")]), "KB-03"),
        ("token tanpa dibersihkan", dict(kiriman([], True), catatan=[dict(teks=tok)]), "KB-04"),
        ("tanpa persetujuan", kiriman(kotor, False), "KB-05"),
        ("kiriman raksasa", kiriman([dict(teks="x" * (MAKS_BYTE + 10))], True), "KB-06"),
    ]
    hasil = []
    for nama, b, wajib in rusak:
        ok, gagal = qc.tertangkap(audit(b), [wajib])
        hasil.append(dict(nama=nama, wajib=[wajib], gagal=gagal, tertangkap=ok))
        print(f"  negatif belajar {'OK ' if ok else 'BOCOR'} {nama}: gagal {gagal}")
    bersih = kiriman(kotor, True)
    sisa = [c["id"] for c in audit(bersih) if not c["lulus"]]
    teks = bersih["catatan"][0]["teks"]
    nama_hilang = "budi" not in teks and "sari" not in teks
    hasil.append(dict(nama="kiriman kotor setelah dibersihkan lolos audit + nama pengguna di path hilang", wajib=[],
                      gagal=sisa, tertangkap=not sisa and nama_hilang))
    print(f"  pembersihan {'OK ' if not sisa and nama_hilang else 'BOCOR'}: {teks}")
    return hasil
