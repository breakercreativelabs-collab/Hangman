# Rubrik Juri: Product Shot (lapis 2 sistem belajar)

Juri melihat **satu contact sheet per produk** (`proyek/produk_uji/hasil/kurikulum/<produk>/contact_sheet.jpg`), sesudah QC angka lulus. Juri menilai hal yang **belum** punya angka. Hal yang sudah diukur QC (lantai, isi frame, terpotong, dimensi) tidak dinilai ulang, kecuali mata melihat QC itu salah.

Hasil ditulis ke `proyek/produk_uji/hasil/kurikulum/juri.json`: per produk, 7 kriteria × (skor 1–5 + alasan satu kalimat yang menyebut sel/baris contact sheet).

**Aturan:** skor **≤ 2 = cacat**. Wajib masuk `ATURAN_QC.md` sebagai C-xx (cacat → ditemukan oleh "Juri" → perbaikan → cek angka bila bisa), lalu diperbaiki dan dinilai ulang. Skor 3 = layak tetapi ada catatan (masuk "Pantauan"). Target lapis 2 (`KRITERIA_SIAP.md`): rata-rata ≥ 3,5 dan tidak ada skor ≤ 2 yang belum ditangani.

**Batas juri cloud:** contact sheet berisi render uji (CPU, 360 px, 24 sampel + denoise). Noise dan detail halus dinilai **relatif terhadap kualitas uji**. Penilaian akhir material/teknis tetap di render final laptop (OptiX). Juri belum terkalibrasi terhadap mata pengguna (`KRITERIA_SIAP.md`: ≥ 80% cocok dari ≥ 15 penilaian), jadi skornya penyaring awal, bukan vonis.

## Kriteria

| # | Kriteria | 5 (siap kirim) | 3 (layak, ada catatan) | 1 (cacat) |
|---|---|---|---|---|
| 1 | **Komposisi** | Produk terpusat, ruang napas seimbang di 16:9 / 9:16 / 1:1; elevasi kamera menampilkan bentuk (bukan siluet datar) | Terpusat tetapi terasa kaku/kosong di salah satu rasio | Produk miring/terpotong/tertutup, atau sudut kamera menyembunyikan ciri utama produk |
| 2 | **Cahaya** (key/rim/fill, sorot) | Key membentuk volume, rim memisahkan tepi dari latar, sorot (specular) jatuh di tempat yang menjelaskan bentuk; ketiga preset punya karakter berbeda dan terbaca | Bentuk terbaca, tetapi salah satu preset datar/terlalu keras, atau sorot kecil memotong label | Sisi produk hilang ke latar, sorot meledak menutupi label, atau bayangan hitam yang tidak fisik |
| 3 | **Material** (logam/kaca/kertas/plastik) | Logam punya refleksi berarah, kaca/PET bening dengan tepi gelap/terang yang benar dan isi terlihat, kertas/karton difus (tidak plastik), plastik ber-sorot lembut | Material bisa ditebak tetapi satu tampak "CG" (terlalu bersih/abu) | Material salah baca: kaca pejal/hitam, logam seperti plastik, kertas mengilap seperti kaca |
| 4 | **Kebersihan latar** | Cyclorama mulus tanpa horizon, gradasi lembut, tanpa noda/garis; bayangan kontak menapakkan produk | Gradasi agak belang atau bayangan kontak lemah | Garis horizon/tepi backdrop terlihat, noda, atau produk tampak melayang |
| 5 | **Gerak turntable** (baris TURNTABLE) | Sudut di F25/F50/F75 sesuai easing (lambat di ujung), produk tetap di tengah, tidak goyang | Bergerak benar tetapi satu frame menampilkan sisi yang kurang menarik tanpa cahaya pengisi | Produk keluar tengah, bergetar, atau kecepatan linear |
| 6 | **Akurasi brand** (warna/logo) | Warna varian sesuai hex di semua preset (sel hijau), logo/label menghadap kamera di frame hero, tidak ada warna bocor ke material lain | Warna benar tetapi bergeser di satu preset (mis. lebih gelap di dramatis) | Warna salah/pudar, logo di belakang, atau varian tidak berubah |
| 7 | **Teknis** (noise, artefak) | Tanpa artefak geometri (lubang, sambungan UV, shading bergerigi), noise wajar untuk kualitas uji | Artefak kecil yang hanya terlihat diperbesar | Artefak jelas: pita hitam, z-fighting, firefly besar, permukaan bergelombang |

## Cara menilai (urutan juri)
1. Baca `qc.json` dulu: kalau QC angka gagal, juri tidak menilai (kembalikan ke langkah perbaikan).
2. Lihat contact sheet **sekali** secara utuh. Catat kesan pertama (apakah produk langsung dikenali?).
3. Nilai 7 kriteria. Setiap skor wajib punya alasan yang bisa dicek ulang (sel mana, apa yang terlihat).
4. Skor ≤ 2 → C-xx di `ATURAN_QC.md` + perbaikan di verbs/produk + render ulang + nilai ulang. Catat skor sebelum/sesudah.
5. Hal yang bisa diukur (mis. pita gelap, warna) → jadikan QC angka dengan uji negatif, bukan hanya catatan juri.
