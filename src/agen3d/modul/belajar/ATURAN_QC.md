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
