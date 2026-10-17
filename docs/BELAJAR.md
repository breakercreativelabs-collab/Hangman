# Belajar dari banyak pengguna

Tujuan (keputusan pengguna 2026-10-17): setiap pengguna yang memakai agen ikut membuatnya makin ahli, tanpa data
pribadi atau berkas klien keluar dari mesin mereka.

## Sisi pengguna
1. `belajar catat --jenis cacat|selera --modul <m> --proyek <p> --teks "..." [--laporan <laporan_qc.json>]`
   (lewat Claude: "catat cacat: mata kuda terlalu kecil"). Disimpan lokal di `artefak/belajar/catatan.jsonl`.
2. `belajar ekspor` = pratinjau saja (`pratinjau_kiriman.json`). `belajar ekspor --setuju 1` = `kiriman.json`
   (dibersihkan + audit KB-01..06; gagal audit = tidak dibuat).
3. Lampirkan ke Issue dengan template "Kiriman belajar" (`.github/ISSUE_TEMPLATE/kiriman-belajar.yml`).

## Sisi pengelola (alur yang sama dengan pengembangan sejak awal)
1. Triage Issue berlabel `kiriman-belajar`: cacat nyata? bisa diulang? modul mana?
2. Tulis baris di `ATURAN_QC.md` modul itu: cacat -> dugaan akar -> perbaikan -> **cek angka** -> ambang -> status.
3. Wujudkan cek di kode + **uji negatif** yang membuktikan cek itu menangkap cacatnya.
4. Runner hijau (`python3 uji/jalankan.py`), lalu rilis (`python3 alat/rilis.py`). Selera berulang dari banyak
   pengguna menjadi preset bawaan.
5. Balas Issue: aturan ID berapa, versi rilis berapa.

## Kenapa lewat Issue, bukan server
Tanpa server = tanpa biaya, tanpa data tersimpan diam-diam, mudah diaudit publik; pengguna melihat persis apa yang
dikirim. Bila volume kiriman besar, endpoint otomatis bisa ditambah kemudian (perlu kebijakan privasi).
