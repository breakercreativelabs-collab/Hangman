"""Spesifikasi produk uji dari ukuran asli (pengganti model klien).

Semua ukuran dalam mm, dikonversi ke meter saat membangun mesh.
Status angka: [F] fakta dari datasheet (riset web 2026-10-13), [D] dugaan (belum ada sumber tegas).
Konvensi: origin di tengah dasar, sisi depan (logo label) menghadap -Y.
"""
import math

SPEC = {
    # Kaleng 330 ml "standard" 66/52 x 115 (CanIt BB-CPS-330, biopineoe, aluminum-can.com)
    "kaleng": dict(
        nama="Kaleng 330 ml standard",
        tinggi_mm=115.2,          # [F] 115.2 ±0.3
        diameter_mm=66.2,         # [F] 66.0-66.3
        leher_mm=17.4,            # [F] panjang necking
        plug_mm=52.4,             # [F] diameter leher dalam
        cincin_dasar_mm=47.3,     # [F] 46.6-48.0
        kubah_mm=10.0,            # [D] kedalaman kubah dasar
        brimful_ml=359,           # [F] info
        logo_mm=(35.0, 80.0), garis_mm=(20.0, 26.0), warna_z_mm=88.0,  # [D] tata letak label uji
        sumber="canit.co.uk BB-CPS-330-A119; biopineoe.com; aluminum-can.com",
    ),
    # Botol longneck 330 ml, crown 26 mm (Vetropack 31748, sbi4beer Longneck 33cl 216g)
    "botol": dict(
        nama="Botol longneck 330 ml",
        tinggi_mm=226.5,          # [F] 225-227 (tinggi kaca sampai bibir)
        diameter_mm=60.4,         # [F] 60.2-60.4
        crown_mm=26.0,            # [F] finish ISO 26 H 180
        tutup_mm=32.1,            # [D] diameter crown cap terpasang
        tinggi_badan_mm=112.0,    # [D] akhir silinder badan / awal bahu
        tinggi_leher_mm=165.0,    # [D] awal leher lurus
        label_mm=(38.0, 102.0),   # [D] tinggi label badan
        dinding_mm=2.5,           # [D] tebal dinding kaca (botol kaca umum 2-4 mm); C-11: bukan kaca pejal
        isi_mm=186.5,             # [D] tinggi permukaan cairan (±40 mm di bawah bibir, di leher)
        tinggi_total_mm=226.5 + 0.6,  # crown cap menonjol 0,6 mm di atas bibir
        logo_mm=(55.0, 90.0), garis_mm=(43.0, 48.0), warna_z_mm=96.0,  # [D] tata letak label uji
        sumber="katalog.vetropack.com 31748; sbi4beer.com Longneck-33cl-216g; berlinpackaging.eu",
    ),
    # ---- Kurikulum Tugas 4 (riset web 2026-10-13). [F*] = angka eksplisit di ringkasan hasil pencarian;
    # halaman sumber tidak bisa dibuka dari cloud (DNS ditolak), jadi verifikasi ulang di laptop. ----
    # Kotak susu UHT 200 ml (format Tetra Brik Aseptic 200 Slim). Tetra Pak TIDAK menerbitkan dimensi kemasan:
    # semua angka [D], dicek hanya lewat volume (52 x 36 x 113,5 mm = 212 ml > 200 ml + ruang kepala).
    "kotak_susu": dict(
        nama="Kotak susu UHT 200 ml",
        bentuk="kotak",
        lebar_mm=52.0,            # [D] sisi depan (logo)
        tebal_mm=36.0,            # [D]
        tinggi_mm=115.0,          # [D] termasuk sirip seal atas
        sirip_mm=1.5,             # [D] sirip seal atas yang dilipat rata
        logo_mm=(55.0, 85.0), garis_mm=(40.0, 46.0), warna_z_mm=95.0,
        sumber="tetrapak.com TBA 200 Slim (tanpa dimensi publik); semua [D]",
    ),
    # Jar kaca selai 314 ml, tutup lug TO63 (Berlin Packaging / Raja 314 ml TO63 H10 flint)
    "jar_selai": dict(
        nama="Jar kaca selai 314 ml TO63",
        tinggi_mm=98.5,           # [F*] tinggi kaca
        diameter_mm=76.8,         # [F*] diameter maksimum
        finish_mm=63.0,           # [F*] TO63
        tutup_mm=66.0,            # [D] diameter rok tutup lug
        tutup_tinggi_mm=11.0,     # [D]
        tutup_naik_mm=1.0,        # [D] tutup menonjol di atas bibir kaca
        dinding_mm=3.0,           # [D] kaca jar 2,5-4 mm (berat kaca 200 g [F*])
        isi_mm=78.0,              # [D] permukaan selai, di bawah bahu
        label_mm=(25.0, 65.0),    # [D]
        tinggi_total_mm=98.5 + 1.0,
        logo_mm=(38.0, 56.0), garis_mm=(29.0, 32.0), warna_z_mm=60.0,
        sumber="berlinpackaging.eu raja-314ml-to-63-reg-flint (98,5 x 76,8 mm, 200 g)",
    ),
    # Tube kosmetik 100 ml D40, berdiri di flip-top cap; ujung atas dipipihkan (seal)
    "tube": dict(
        nama="Tube kosmetik 100 ml D40",
        bentuk="pipih",
        diameter_mm=40.0,         # [F*] tube ekstrusi D40 (emballator.com exttube-40)
        panjang_mm=125.0,         # [D] 90-180 mm untuk 60-150 ml; 100 ml ~120-130 mm
        lebar_mm=40.0 * math.pi / 2,  # [D] seal = setengah keliling (keliling tetap saat dipipihkan) = 62,8
        seal_tebal_mm=1.2,        # [D] dua lapis dinding
        seal_mm=8.0,              # [D] tinggi pita seal
        tutup_mm=40.0,            # [D] flip-top selebar tube
        tutup_tinggi_mm=22.0,     # [D]
        tinggi_mm=22.0 + 125.0,
        tebal_mm=40.0,
        logo_mm=(68.0, 92.0), garis_mm=(56.0, 59.0), warna_z_mm=51.0,
        sumber="emballator.com exttube-40; packagingsolutions.amcor.com 40mm flip-top (leher 22 mm)",
    ),
    # Botol PET bening 600 ml (acuan: PET 20 oz/591 ml, leher 28 mm PCO, US Plastic item 132340) + air
    "botol_pet": dict(
        nama="Botol PET air 600 ml",
        tinggi_mm=200.8,          # [F*] 7,906 in (tanpa tutup)
        diameter_mm=71.4,         # [F*] 2,812 in
        finish_mm=27.4,           # [D] ulir luar 28 mm PCO
        tutup_mm=30.5,            # [D]
        tutup_tinggi_mm=16.0,     # [D]
        tutup_naik_mm=1.5,        # [D]
        dinding_mm=0.35,          # [D] dinding badan PET 0,25-0,4 mm; leher preform ~2,9 mm
        isi_mm=172.0,             # [D] permukaan air di bahu
        label_mm=(60.0, 125.0),   # [D] label film
        tinggi_total_mm=200.8 + 1.5,
        logo_mm=(78.0, 105.0), garis_mm=(66.0, 69.0), warna_z_mm=115.0,
        sumber="usplastic.com item 132340 (20 oz PET 28mm PCO); petainer.com 28mm PCO 1881",
    ),
    # Kaleng slim 250 ml 202 (Ardagh 53/250 via Nomoq; Crown 250ml slim; Ajanta 134 x 53,4)
    "kaleng_slim": dict(
        nama="Kaleng slim 250 ml",
        tinggi_mm=134.0,          # [F*] 134,0 +-0,4 (seamed)
        diameter_mm=53.4,         # [F*] diameter luar badan maks
        plug_mm=50.0,             # [F*] diameter neck plug
        leher_mm=12.0,            # [D] panjang necking
        cincin_dasar_mm=40.0,     # [D]
        kubah_mm=8.0,             # [D]
        logo_mm=(40.0, 92.0), garis_mm=(24.0, 30.0), warna_z_mm=103.0,
        sumber="help.nomoq.com 04_5_1_53_250_1_01 (Ardagh); crowncork.com 83oz-250ml-slim; ajantabottle.com",
    ),
}


PRODUK = tuple(SPEC)
BARU = ("kotak_susu", "jar_selai", "tube", "botol_pet", "kaleng_slim")  # kurikulum Tugas 4


def tinggi_total_mm(nama):
    """Tinggi produk jadi (termasuk tutup) yang diharapkan QC dimensi."""
    s = SPEC[nama]
    return s.get("tinggi_total_mm", s["tinggi_mm"])


def logo(nama):
    """Posisi logo: (u di UV, tinggi tengah logo m). Dipakai QC-04 (logo menghadap kamera)."""
    z0, z1 = SPEC[nama]["logo_mm"]
    return (0.5, (z0 + z1) / 2000)


def depan_mm(nama, z):
    """Jarak permukaan depan (label) ke sumbu, di tinggi z (mm)."""
    s = SPEC[nama]
    if s.get("bentuk") == "kotak":
        return s["tebal_mm"] / 2
    if nama == "tube":
        from .profil import tube_ab
        return tube_ab(s, z)[1]
    if "label_mm" in s:  # label tempel/film di luar badan
        return s["diameter_mm"] / 2 + 0.25
    return s["diameter_mm"] / 2


def titik_warna(nama):
    """Titik permukaan label (m, ruang lokal produk) di sisi depan, di luar logo dan garis: sampel QC warna."""
    z = SPEC[nama]["warna_z_mm"]
    return (0.0, -depan_mm(nama, z) / 1000, z / 1000)


def spec_qc(nama):
    """Spec untuk QC-07: produk bulat -> diameter; kotak/pipih -> lebar (X, sisi depan) dan tebal (Y)."""
    s = SPEC[nama]
    if s.get("bentuk") in ("kotak", "pipih"):
        return dict(spec_lebar_mm=s["lebar_mm"], spec_tebal_mm=s["tebal_mm"])
    return dict(spec_diameter_mm=s["diameter_mm"])
