# Buku Aturan & QC: Generator Pohon

Setiap cacat yang ditemukan mata **wajib** dicatat di sini, lalu diubah menjadi aturan di generator dan/atau pengecekan angka otomatis. File ini adalah "ingatan keahlian" agen. Claude tidak mengingat antar sesi, tetapi file ini ya.

Format: ID · cacat · ditemukan oleh · perbaikan di generator · cek angka (QC) · ambang lulus · status

| ID | Cacat | Ditemukan | Perbaikan generator | Cek angka (QC) | Ambang lulus | Status |
|---|---|---|---|---|---|---|
| QC-001 | Gumpalan kotak hijau di ujung cabang (titik tumbuh dobel di posisi yang sama) | Mata, v1 (2026-10-13) | Tolak titik baru yang jaraknya < 0,4 × langkah dari titik lama | `QC_titik_menumpuk` (titik < 1 cm dari titik lain) | = 0 | ✅ v2 |
| QC-002 | Daun menggumpal tidak wajar di satu area | Mata, v1 | (efek QC-001) | `QC_gumpalan_daun_maks_x_median` (voxel 0,5 m) | ≤ 8 | ✅ v2 |
| QC-003 | Daun berupa persegi polos, terlihat seperti game | Mata, v2 | Bentuk daun dari UV + alfa, variasi warna per daun, tembus cahaya | (visual, belum ada angka) | n/a | ✅ v3 |
| QC-004 | Cabang tengah setebal "mi" | Mata, v2 | Peruncingan pangkat 1,5 (model pipa) | `radius_cabang_min_max_m` | ujung ≤ 0,015 m | ⚠️ v3 ujung masih 0,022 m |
| QC-005 | Tajuk hanya di ujung, tampak bolong | Mata, v2 | Daun juga di 3 ruas terakhir ranting | jumlah daun per pohon | ≥ 15 × jumlah ujung | ✅ v3 |
| QC-006 | Daun di bawah tanah | Pencegahan | n/a | `QC_daun_di_bawah_tanah` | = 0 | ✅ v3 |
| QC-007 | Tajuk terlalu bulat dan simetris, seperti topiari | Mata, v3 | Rencana: tonjolan (lobus) dan noise pada volume tajuk | Rencana: variasi radius tajuk per arah mata angin | koefisien variasi ≥ 0,15 | 🔜 |
| QC-008 | Batang lurus seperti tiang, tanpa peruncingan dan tanpa akar melebar | Mata, v3 | Rencana: batang meruncing + root flare + sedikit lengkung | Rencana: rasio radius pangkal/radius di dasar tajuk | ≥ 1,3 | 🔜 |

## Cara menjaga agar tidak mundur (regresi)
Setiap perubahan generator dijalankan ulang dengan preset dan seed yang sama, lalu semua QC di atas harus tetap lulus sebelum perubahan diterima.

Sejak Tugas 9 (refactor ke `src/agen3d/modul/prosedural/`): `prosedural uji` menjalankan QC-001/002/005/006 di 3 pohon contoh, regresi laporan terhadap `acuan_pohon.json` (diambil dari kode spike v3 sebelum refactor; generator deterministik, harus sama persis) dan uji negatif QC-001 (`tumbuh(cegah_duplikat=False)` = perilaku v1: 2.995 titik menumpuk, tertangkap). QC-004 tetap ⚠ (dilaporkan, tidak menggagalkan) sampai Tugas 1 dilanjutkan. Render contoh: `prosedural pohon` (perangkat GPU bila ada, selain itu CPU; spike lama memaksa OptiX). Gambar v1–v3: `proyek/pohon/hasil/` (JPG).
