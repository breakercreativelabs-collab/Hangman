"""Pembungkus job (stdlib saja, Python sistem `-I`), dua tahap supaya job lepas dari pohon proses server MCP:

  python -I bungkus.py --lepas <folder>   tahap 1 (pemula): luncurkan tahap 2 terlepas (grup proses baru, tanpa konsol,
                                          lepas dari job object bila diizinkan), catat pembungkus.json, lalu keluar
                                          (anak menjadi yatim: `taskkill /T` dari klien tidak menjangkaunya)
  python -I bungkus.py --jalan <folder>   tahap 2 (pembungkus): pegang kunci hidup.lock, jalankan argv.json, layani
                                          berkas minta_batal, tulis selesai.json (atomik) di akhir

Hidup = hidup.lock sedang dikunci (bukan PID: PID bisa dipakai ulang proses lain, temuan review). Batal = berkas
minta_batal; hanya pembungkus yang menghentikan anaknya sendiri dan menulis selesai.json (satu penulis).
Batas yang diketahui: klien yang memasukkan server ke job object KILL_ON_JOB_CLOSE tanpa izin breakaway (mis. klien SDK
Python) tetap mematikan job saat sesi ditutup; status lalu tercatat `terputus` (lihat pekerjaan.status).
"""
import json
import os
import subprocess
import sys
import time

WINDOWS = sys.platform == "win32"


def kunci_berkas(f):
    """Kunci eksklusif tanpa menunggu pada berkas terbuka; True bila berhasil."""
    try:
        if WINDOWS:
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def buka_kunci_berkas(f):
    if WINDOWS:
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def masih_hidup(folder):
    """True = pembungkus memegang kunci; False = tidak (mati/selesai); None = kunci belum pernah dibuat."""
    p = os.path.join(folder, "hidup.lock")
    if not os.path.isfile(p):
        return None
    with open(p, "a+") as f:
        if kunci_berkas(f):
            buka_kunci_berkas(f)
            return False
        return True


def tulis_atomik(path, data):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def lepas(folder):
    argv = [sys.executable, "-I", os.path.abspath(__file__), "--jalan", folder]
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
              cwd=folder)
    lepas_job = True
    if WINDOWS:
        dasar = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            p = subprocess.Popen(argv, creationflags=dasar | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
        except OSError:  # job object klien tidak mengizinkan breakaway
            p = subprocess.Popen(argv, creationflags=dasar, **kw)
            lepas_job = False
    else:
        p = subprocess.Popen(argv, start_new_session=True, **kw)
    tulis_atomik(os.path.join(folder, "pembungkus.json"), dict(pid=p.pid, lepas_dari_job_object=lepas_job))
    return 0


def hentikan(p):
    """Hentikan anak pembungkus (Blender) beserta turunannya, lewat handle sendiri (bukan PID dari berkas)."""
    if WINDOWS:
        tk = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")
        subprocess.run([tk, "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        p.terminate()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()


def jalan(folder):
    with open(os.path.join(folder, "argv.json"), encoding="utf-8") as f:
        req = json.load(f)
    kode, batal = None, False
    with open(os.path.join(folder, "hidup.lock"), "a+") as kf:
        for _ in range(20):  # K-12: pemeriksa status bisa memegang kunci sesaat; coba lagi sebelum menyerah
            if kunci_berkas(kf):
                break
            time.sleep(0.1)
        else:
            return 3  # job ini sudah dipegang pembungkus lain
        try:
            with open(os.path.join(folder, "log.txt"), "a", encoding="utf-8", errors="replace") as log:
                try:
                    p = subprocess.Popen(req["argv"], cwd=req["cwd"], stdout=log, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL)
                except OSError as e:
                    log.write(f"GAGAL MEMULAI: {e}\n")
                    kode = 127
                else:
                    while p.poll() is None:
                        if not batal and os.path.exists(os.path.join(folder, "minta_batal")):
                            batal = True
                            hentikan(p)
                        time.sleep(0.5)
                    kode = p.returncode
        finally:
            tulis_atomik(os.path.join(folder, "selesai.json"), dict(kode=kode, selesai=time.time(), dibatalkan=batal))
    return 0


if __name__ == "__main__":
    mode, folder = sys.argv[1], os.path.abspath(sys.argv[2])
    sys.exit(lepas(folder) if mode == "--lepas" else jalan(folder))
