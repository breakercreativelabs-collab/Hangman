# Buku Aturan & QC: konektor MCP + CLI tunggal

Ingatan keahlian lapisan konektor. Setiap cacat dicatat di sini (cacat → perbaikan → cek angka/uji → status), lalu
diwujudkan di kode. Uji: suite `struktur` (f), `cli` (`uji/asap.py`) dan `konektor` (`uji/konektor.py`, klien MCP
sungguhan) di runner tunggal. Setiap aturan punya uji negatif.

## Aturan
| ID | Aturan | Cek (uji) | Negatif |
|---|---|---|---|
| K-01 | Nama server = slug `identitas.toml` (rename produk = edit satu file) | konektor K-01 | struktur (a) menolak nama di file lain |
| K-02 | Setiap perintah `bantuan` = satu alat MCP (katalog otomatis) + baris uji asap CLI; katalog membaca opsi semua perintah | konektor K-02 (jumlah alat CLI == katalog > 0; opsi terbaca) | cli: perintah tanpa uji asap = gagal; katalog menandai perintah tanpa io.opsi |
| K-03 | Hanya `jalankan_kode` yang wajib minta izin pengguna (`anthropic/requiresUserInteraction`) | konektor K-03 | alat lain tidak membawa penanda (cek tidak tautologis) |
| K-04 | Galat kode bebas = job gagal + traceback (bukan sukses palsu); `sys.exit(0)` = sukses | konektor K-04 | kode `1/0` |
| K-05 | Path hanya di zona `artefak/`, `proyek/`, `klien/` (realpath + normcase); drive-relatif, `..`, rahasia, kode, `.git` ditolak dengan pesan terbaca; `proyek` = folder yang ada; nama opsi_lain divalidasi | konektor K-05 (huruf drive kecil diterima) | `..`, `artefak/../../x`, `github-recovery-codes.txt`, `identitas.toml`, temp di luar repo, `C:..`, `D:x`, `proyek=../am1`, kunci `x --evil` |
| K-06 | Panggilan alat tidak menggantung: tunggu ≤ `AGEN3D_BATAS_TUNGGU` (bawaan 50 s < batas Claude Desktop ±60 s), lalu id job | konektor K-06 | minta 600 s → kembali ≤ batas + 5 s |
| K-07 | Job dijalankan pembungkus dua tahap (yatim, lepas dari job object bila boleh). Hidup = kunci `hidup.lock`, bukan PID. Status selalu berakhir jujur | konektor K-07a (lolos `taskkill /T` pemulainya) | K-07b: sesi klien SDK ditutup → `terputus` + alasan, bukan "berjalan" abadi |
| K-08 | Server stdio tidak menulis ke stdout; cwd = repo; `NoDefaultCurrentDirectoryInExePath=1` | semua uji konektor (protokol rusak bila dilanggar) | — |
| K-09 | Perintah CLI lulus = kode 0 **dan** berkas yang dijanjikan ada | cli | perintah tanpa berkas yang dijanjikan |
| K-10 | Respons dibatasi: HASIL ≤ 8000 karakter (lengkap di hasil.json), log ≤ 20 baris × 300, teks ≤ 60k, gambar ≤ 700 KB | konektor K-10 | HASIL 500 ribu karakter |
| K-12 | Status job tidak pernah "terputus" palsu: selesai.json dibaca ulang setelah kunci lepas; masa mulai berlaku juga saat lock ada tapi belum dikunci; pembungkus mencoba kunci 2 s | ekstensi KE-06 (uji ujung-ke-ujung menemukannya: pion selesai kode 0 tetapi status "terputus") | konektor K-12 (uji ras deterministik: kode lama -> 'terputus' palsu) |
| K-11 | Konektor (Python sistem) tidak mengimpor bpy/mathutils/inti/modul, kecuali `eksekusi.py` (di dalam Blender) | struktur (f) | pohon sintetis `konektor/server.py` mengimpor bpy + inti |

## Riwayat cacat
| ID | Cacat | Perbaikan | Cek | Status |
|---|---|---|---|---|
| C-B1 | `modeling_referensi bangun` crash setelah menyimpan (`v.data.vertices` pada objek tanpa mesh) | cetak hanya MESH; kode 0 bila .blend tertulis (`bd1b4c7`) | cli: bangun | ✅ 2026-10-15 |
| C-B2 | `tvc render --blend 1` gagal: folder render belum ada | `os.makedirs` sebelum simpan | cli: tvc render | ✅ 2026-10-15 |
| C-B3 | Perintah ekstraksi tidak bisa diuji tanpa foto klien | `modeling_referensi foto_uji` (foto sintetis, non-generatif) | cli: ekstrak_kontur pulang-pergi ±3 mm | ✅ 2026-10-15 |
| C-K1 | Path ditolak tetapi pesan tertelan ("Error executing tool") | semua galat → `ToolError` | K-05 | ✅ |
| C-K2 | Job dibatalkan berstatus "tidak diketahui" | pembungkus satu-satunya penulis selesai.json; batal lewat berkas minta_batal | uji batal | ✅ |
| C-K3 | Nama helper bentrok lintas file (`_tulis`, `katalog`, `daftar`, `kunci`) | nama unik; `inti.io.tulis_json` di Blender | struktur (c) | ✅ |
| C-K4 | Pagar path ditembus nilai tanpa pemisah (`..`, `C:..`, `D:x`) dan zona = seluruh repo (bisa menimpa rahasia/kode) | pagar per nama opsi + zona artefak/proyek/klien + realpath/normcase | K-05 | ✅ (review adversarial) |
| C-K5 | Klaim "job tetap jalan walau sesi ditutup" tidak diuji dan salah untuk klien job object | peluncuran dua tahap + status `terputus` yang jujur; klaim di dokumen dikoreksi | K-07a/b | ✅ (review) |
| C-K6 | Batal/hidup memakai PID mentah (PID dipakai ulang → bisa membunuh proses lain; tasklist crash di Windows non-Inggris) | kunci berkas `hidup.lock` | K-07, uji batal | ✅ (review) |
| C-K7 | Suite konektor di runner mengabaikan kode keluar dan bisa membaca konektor.json basi | json dihapus dulu + butir wajib "kode keluar 0"; uji yang crash tetap menulis butir GAGAL | runner | ✅ (review) |
| C-K8 | tunggu_detik tak dibatasi; diagnosa menunggu 90 s (diputus Desktop, id job hilang) | `BATAS_TUNGGU` di satu tempat; diagnosa ≤ 40 s + id | K-06 | ✅ (review) |
| C-K9 | Start server menunggu Blender (katalog) hingga 120 s | katalog bercache (kunci: path Blender + mtime kode), dingin ≤ 25 s | start uji | ✅ (review) |
| C-K10 | Ringkasan keluaran job menyerap berkas job lain (jendela waktu terbuka, pindai seluruh repo) | jendela [mulai, selesai], pindai folder yang dinyatakan job, folder job lain dilewati, ringkasan disimpan sekali | — | ✅ (review) |
| C-K11 | Respons tak terbatas (HASIL, log) melewati batas keluaran klien | K-10 | K-10 | ✅ (review) |
| C-K12 | Membatalkan panggilan jalankan_kode tidak menghentikan kodenya | CancelledError → batalkan job | — (perlu klien yang membatalkan; diuji manual nanti) | 🟡 |

## Batas yang diketahui (bukan cacat, dicatat jujur)
- Klien yang memasukkan server ke job object KILL_ON_JOB_CLOSE tanpa izin breakaway (klien SDK Python; Claude Desktop belum
  diketahui) mematikan job saat sesi ditutup → status `terputus`. Claude Code menutup server dengan `taskkill /T`: job lolos (K-07a).
- Job bersamaan ke folder keluaran yang sama tidak dicegah (v0); instruksi Claude melarang mengulang perintah yang masih berjalan.
