# ATURAN_QC modul belajar (kiriman pengguna)

Kiriman = bahan agen makin pintar dari banyak pengguna. Prinsip: **tidak ada yang terkirim otomatis**; tanpa
`--setuju 1` hanya pratinjau. Kiriman dibersihkan (`bersihkan`) lalu diaudit; gagal audit = kiriman tidak dibuat.

| ID | Cek | Ambang | Kenapa |
|---|---|---|---|
| KB-01 | Tidak ada path absolut (Windows `C:\...`, `/home`, `/Users`, ...) | 0 temuan | path memuat nama pengguna & nama job klien |
| KB-02 | Tidak ada alamat email | 0 | data pribadi |
| KB-03 | Tidak ada `klien/...` | 0 | nama berkas klien bisa membocorkan merek/proyek rahasia |
| KB-04 | Tidak ada token/kunci (`ghp_`, `sk-ant-`, `AKIA`, kunci PEM, ...) | 0 | rahasia |
| KB-05 | Persetujuan eksplisit (`--setuju 1`) | true | data hanya keluar atas izin pengguna |
| KB-06 | Ukuran kiriman | <= 200 KB | Issue tetap terbaca; bukan tempat berkas besar |

Pembersihan juga mengganti nama pengguna OS (USER/USERNAME) dengan `<pengguna>`.
Uji negatif (`belajar uji`): 6 kiriman kotor tanpa pembersihan WAJIB gagal di cek masing-masing; kiriman kotor setelah
dibersihkan WAJIB lolos dan nama pengguna di path hilang.

Celah yang diketahui (jangan dijanjikan): teks bebas bisa saja memuat nama merek/klien yang diketik manusia; regex tidak
mengenali itu. Karena itu pengguna wajib membaca pratinjau sebelum mengirim (template Issue mengingatkan).

## Telemetri otomatis (keputusan pengguna 2026-10-17: menyala bawaan tanpa ditanya; diberitahukan + saklar mati)
`src/agen3d/telemetri.py` (klien) + `layanan/telemetri/worker.js` (server, repo pengembang saja). Uji: `belajar uji_telemetri`
(KM) dan `node layanan/telemetri/uji.mjs` (KS-T).

| ID | Cek | Ambang | Kenapa |
|---|---|---|---|
| KM-01 | Peristiwa hanya daftar putih skema (ID cek, angka, nama kode) | 0 teks bebas/path/nama proyek | privasi tanpa bertanya hanya sah bila datanya memang anonim |
| KM-02 | Saklar mati dihormati (env AGEN3D_TELEMETRI=0, berkas MATI, tombol panel) | 0 peristiwa | pengguna wajib bisa berhenti satu klik |
| KM-03 | Terkirim ke endpoint sungguhan, antrean dikosongkan | true | |
| KM-04 | Antrean dibatasi | <= 500 | disk pengguna offline tidak membengkak |
| KM-05 | Server mati tidak menahan job | <= 3,5 s, lalu jeda 10 menit | telemetri tidak boleh memperlambat kerja |
| KM-06 | Server mati: antrean disimpan | > 0 | |
| KM-07 | Galat hanya jenisnya | nama kode | pesan galat bisa memuat path |
| KS-T01..06 | Server: terima sah; teks/path tidak tersimpan; tanpa kolom IP; banjir 2000/pemasangan/hari; ringkasan hanya dengan token; JSON rusak aman | lulus | racun & privasi di sisi server |
Racun di analisis: pemasangan > 30% peristiwa atau >= 50 vonis seragam dikucilkan; sinyal wajib dari >= 3 pemasangan.
