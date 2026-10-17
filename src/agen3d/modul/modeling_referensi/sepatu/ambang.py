"""Ambang QC resep sepatu (AM-01..18). Ubah hanya dengan alasan terukur di ATURAN_QC.md proyek (dilarang melonggarkan)."""
from ...product_shot.api import AMBANG as AMBANG_PS



# AM-09: model M2 ~1,5 deg; blok M1 5,7 deg (lihat ATURAN_QC). AM-10: IoU poligon data vs dirinya digeser (0,5; 0,5) mm
# = 0,928 lateral / 0,930 medial (galat <= setengah jarak kolom data 0,9 mm)
RIAK, IOU_SW = 2.5, 0.93
AMBANG = {
    "iou_min": 0.95,          # AM-01 siluet samping, AM-02 plan tampak bawah
    "midsole_mm": 1.5,        # AM-03 rata-rata |garis atas midsole model - data|
    "jendela_mm": 2.0,        # AM-04 galat pusat (x, z) dan ukuran (lebar, tinggi) jendela Air
    "panjang_mm": 1.0,        # AM-05 panjang 293,7 +- 1
    "lebar_mm": 1.0,          # AM-05 lebar forefoot 107,9 +- 1
    "iou_medial_min": 0.95,   # AM-06 siluet MEDIAL (data independen, tidak dipakai membangun); lihat ATURAN_QC
    "banding_maks": 0.010,    # AM-07 garis kolom KOHEREN (sama di separuh atas & bawah sol), luma, high-pass 15 mm
    "tapak_min": 0.020,       # AM-07 std luma frekuensi tinggi (sisa blur 2,5 mm) di outsole tampak bawah
    "takik_mm": 1.0,          # AM-08 kedalaman takik dinding samping midsole (C-A2)
    "riak_deg": RIAK,         # AM-09 riak normal upper (RMS vs rata-rata geser 15 mm), lihat ATURAN_QC
    "iou_swoosh_min": IOU_SW, # AM-10 IoU swoosh per sisi
    "mudguard_mm": 2.0,       # AM-11 rata-rata |garis atas mudguard model - data|
    "tali_jarak_mm": 0.0,     # AM-12 jarak permukaan tali ke upper (tidak menembus)
    "lubang_mm": 3.0,         # AM-12 lubang data vs lubang model (x, z)
    "lapis_mm": 0.2,          # AM-13 jarak min antar lapisan panel
    # M3 (AM-15 memakai aturan QC-10 product-shot, ambang sama: AMBANG_PS)
    "saturasi_rasio_min": AMBANG_PS["saturasi_rasio_min"],  # 0,60
    "hue_selisih_maks": AMBANG_PS["hue_selisih_maks"],      # 20 deg
    "nilai_selisih_maks": AMBANG_PS["nilai_selisih_maks"],  # 0,35 (target netral/pastel, saturasi < 0,2)
    "pastel_sat_maks": 0.30,  # AM-15 saturasi piksel peran pastel/netral (lihat ATURAN_QC)
    "pastel_hue_sat_min": 0.05,  # AM-15 hue pastel hanya diuji jika saturasi piksel & target >= 0,05
    "holo_hue_min": 20.0,     # AM-16 selisih hue swoosh antar 2 sudut kamera (deg)
    "kapsul_tembus_min": 0.01,  # AM-17 kenaikan luma piksel kapsul saat probe di rongga menyala
}
PIX = 0.5                     # mm per piksel render ortografis (AM-01/02)
SW = 0.25                     # mm grid ray swoosh (AM-10)
RAY = 0.25                    # mm grid ray samping (AM-04, peta tumit)
CARI_JENDELA = (170.0, 265.0, 6.0, 40.0)  # x0, x1, z0, z1 mm: pita midsole tumit (di luar ini "tembus" = latar, bukan jendela)
KOLOM_MIN = 3.0               # kolom jendela dihitung jika tinggi celah >= 3 mm (aturan sama dengan ekstrak_kontur.py)
VIEW = {  # x0, x1 (mm), v0, v1 (mm, sumbu tegak gambar), lokasi kamera, rotasi
    "samping": dict(h=(-4.0, 298.0), v=(-4.0, 146.0)),
    "bawah": dict(h=(-4.0, 298.0), v=(-62.0, 62.0)),
}
