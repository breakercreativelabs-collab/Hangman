# Hangman 0.2.0

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
   `hangman-0.2.0-windows-x64.zip` · `-macos-arm64.zip` · `-macos-x64.zip` · `-linux-x64.zip`.
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

## Agen makin pintar dari banyak pengguna
Setiap koreksi Anda bisa menjadi aturan QC permanen untuk semua pengguna:
1. Saat melihat cacat atau punya selera: minta Claude "catat cacat: ..." (`belajar catat`). Tersimpan **lokal**.
2. Bila bersedia berbagi: `belajar ekspor --setuju 1` membuat `kiriman.json` yang sudah dibersihkan (path, email,
   nama pengguna, berkas klien, token) dan diaudit. Tidak ada yang dikirim otomatis.
3. Buka Issue di https://github.com/breakercreativelabs-collab/hangman/issues/new?template=kiriman-belajar.yml dan lampirkan isinya.
4. Pengelola mengubahnya menjadi aturan + cek angka + uji negatif; rilis berikutnya membawa keahlian itu ke semua orang.
Detail: `docs/BELAJAR.md`.

## Batas yang jujur
- Bentuk organik (hewan, karakter) dari prompt belum setingkat ahli; jalurnya aset 3D terbuka berlisensi yang dinilai
  juri kualitas (KA-01..08) lalu disesuaikan. Aset diunduh sendiri ke `klien/` (tidak disertakan).
- Render final butuh GPU (OptiX/CUDA); CPU bisa, lambat.
- Kode bebas (`jalankan_kode`) selalu meminta izin Anda di setiap panggilan.

## Lisensi
GPL-3.0-or-later (lihat `LICENSE`). Kode yang berjalan di dalam Blender (bpy) wajib GPL saat didistribusikan.
Aset pihak ketiga yang dipakai contoh (mis. "A Beautiful Game", CC-BY 4.0) tidak disertakan; atribusinya ada di
rancangan masing-masing.
