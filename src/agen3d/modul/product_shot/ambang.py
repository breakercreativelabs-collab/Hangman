"""Ambang QC product shot (QC-01..12). Ubah hanya dengan alasan terukur di ATURAN_QC.md (dilarang melonggarkan)."""

AMBANG = {
    "kontak_lantai_mm": 0.5,      # QC-01 |z_min| produk
    "isi_min": 0.55,              # QC-02 bagian frame yang diisi produk (sisi terpanjang bbox proyeksi)
    "isi_maks": 0.85,
    "margin_min": 0.02,           # QC-03 jarak produk ke tepi frame
    "sudut_depan_maks": 15.0,     # QC-04 derajat antara arah depan produk dan arah ke kamera
    "luma_min": 0.08,             # QC-05 rata-rata luminans frame (0..1, ruang tampilan)
    "luma_maks": 0.92,
    "fraksi_hitam_maks": 0.50,    # piksel luminans < 0,02
    "fraksi_putih_maks": 0.50,    # piksel luminans > 0,98
    "kontras_produk_min": 0.04,   # selisih rata-rata render vs clean plate di kotak produk
    "kecepatan_ujung_maks": 0.50, # QC-06 kecepatan rotasi di 5% awal/akhir dibanding rata-rata
    "dimensi_mm": 1.0,            # QC-07 toleransi dimensi terhadap spec
    "jarak_kamera_min_x_clip": 2.0,  # QC-08 kamera tidak di dalam/menempel produk
    "saturasi_rasio_min": 0.60,   # QC-10 saturasi warna label di piksel / saturasi hex target
    "hue_selisih_maks": 20.0,     # QC-10 derajat
    "nilai_selisih_maks": 0.35,   # QC-10 untuk warna netral (saturasi target < 0,2)
    "dinding_rasio_maks": 0.35,   # QC-11 tebal dinding kaca / lebar objek (pejal = 1,0; botol 2-4 mm ~ 0,05-0,13)
    "kaca_ior_min": 1.40,          # QC-11 hanya bahan bening ber-IOR kaca/plastik (cairan ~1,33 dikecualikan)
    "logam_hitam_maks": 0.08,     # QC-12 fraksi piksel logam (bukan sisi bawah) dengan luma < 0,02 (C-15: slim 0,11-0,13)
}
