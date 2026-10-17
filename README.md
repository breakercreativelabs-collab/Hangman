# Hangman 0.2.1

Agen operator **Blender** yang dipakai dari aplikasi Claude (Claude Desktop / Claude Code) lewat konektor MCP.
Anda mengetik atau bicara di Claude; agen menjalankan perintah Blender yang sudah teruji, mengukur hasilnya dengan
**QC angka**, dan membuktikan QC itu benar lewat **uji negatif**. Semua hasil adalah kerja 3D asli di Blender
(geometri, material, cahaya, render) yang bisa diedit manusia: **non-generatif**, tanpa AI pembuat gambar/3D.

Komputasi (Blender, GPU) dan otak (langganan/API Claude) milik Anda sendiri. Paket ini berisi alat, QC, aturan, dan
preset.

## Yang bisa dilakukan
| Modul | Isi |
|---|---|
| `product_shot` | packshot studio, turntable, varian warna & rasio (16:9, 9:16, 1:1) + 10 QC |
| `perakit` | model 3D dari **prompt teks**: Claude menulis rancangan bentuk (TOML), perakit membangun SDF -> mesh -> QC. Contoh: set catur lengkap (`proyek/*_catur`, `perakit set`) |
| `modeling_referensi` | model produk dari foto referensi lewat data angka (kontur -> mm -> mesh -> QC siluet) |
| `tvc` | animatic/TVC produk berbasis konfigurasi |
| `prosedural` | pohon prosedural + pencocokan siluet |
| `belajar` | kiriman koreksi Anda (cacat/selera) yang membuat agen makin pintar (lihat di bawah) |

## Pasang (satu berkas, ±1 menit)
Butuh: **Blender 5.2 LTS** dan **Claude Desktop** (atau Claude Code). Tidak perlu Python, uv, atau mengedit JSON.
1. Unduh satu berkas dari halaman [Releases](https://github.com/breakercreativelabs-collab/hangman/releases/latest) sesuai OS:
   `hangman-0.2.1-windows-x64.zip` · `-macos-arm64.zip` · `-macos-x64.zip` · `-linux-x64.zip`.
2. Blender: **Edit > Preferences > Get Extensions > Install from Disk**, pilih zip itu (atau seret zip ke jendela Blender).
3. 3D View > sidebar (**N**) > tab **Agen3D** > **Pasang & hubungkan ke Claude**.
   Isi paket disalin ke folder kerja (bawaan `Documents/Hangman`), dan konektor didaftarkan ke Claude Desktop
   (server MCP lain tidak disentuh, cadangan `.bak` dibuat). Perintah untuk Claude Code ikut tersalin ke clipboard.
4. Tutup penuh Claude Desktop lalu buka lagi. Ketik: "jalankan diagnosa".
5. Biarkan Blender terbuka: setiap model yang dibangun Claude **tampil langkah demi langkah** di viewport (mode tonton,
   otomatis menyala).

Konektor berjalan dengan Python bawaan Blender. Tanpa socket/port jaringan: Claude menjalankan Blender di latar,
Blender yang terbuka hanya membaca hasilnya dari folder kerja.

## Mode tonton (preview realtime di Blender yang terbuka)
Coba: "bangun pion catur" atau "bangun set catur lengkap". Panel tab Agen3D menampilkan langkah ke berapa.
Langkah terakhir = mesh serah yang identik dengan hasil di folder kerja. Detail: `docs/TONTON.md`.

## Rilis
Setiap kenaikan `versi` di `identitas.toml` yang masuk ke `main` membuat GitHub Release otomatis berisi zip ekstensi
per OS (`.github/workflows/rilis.yml` -> `alat/rilis.py`: audit privasi + paket). Pasang konektor manual: `docs/KONEKTOR.md`.

## Agen makin pintar dari pemakaian (telemetri otomatis, MENYALA bawaan)
Setiap job mengirim **angka anonim** ke server proyek: versi, OS, nama perintah, durasi, hasil cek QC (ID + angka),
jenis galat, dan tombol Suka/Kurang di panel. **Tidak pernah**: nama berkas/proyek, path, gambar, model, prompt, teks
bebas, alamat IP (server tidak menyimpannya). Matikan kapan saja: panel Agen3D > **Matikan**, atau env
`AGEN3D_TELEMETRI=0`. Setiap hari agen menganalisis data, mengusulkan perbaikan, dan hanya merilisnya bila semua uji
dan tolok ukur membuktikan kemajuan; data dari satu pemasangan yang membanjiri ditolak.

Koreksi tertulis tetap bisa dikirim manual: `belajar catat` -> `belajar ekspor --setuju 1` -> Issue
https://github.com/breakercreativelabs-collab/hangman/issues/new?template=kiriman-belajar.yml. Detail: `docs/BELAJAR.md`.
