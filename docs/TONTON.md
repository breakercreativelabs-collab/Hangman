# Mode tonton (preview realtime di Blender yang terbuka)

Keputusan pengguna 2026-10-16/17: model dibangun **langkah demi langkah + efek tumbuh** di Blender GUI yang terbuka,
supaya prosesnya bisa ditonton. Kerja berat (SDF, QC, render) tetap di proses headless; GUI hanya menampilkan.

```
Claude -> konektor MCP -> perakit bangun --tonton 1 (headless)
                              | tiap bagian/detail selesai: langkah_NN.npz + tonton.json (ditulis atomik)
                              v
                      artefak/tonton/<proyek>/   <- dipantau add-on (bpy.app.timers, tiap 0,35 s)
                              v
             Blender terbuka: objek TONTON diganti per langkah, tumbuh dari alas (0,6 s), langkah akhir = model.glb
```

- **Tanpa socket/jaringan**: tidak ada port terbuka (MCP Blender lain dikritik karena socket tanpa autentikasi).
- **Mesh akhir identik**: langkah terakhir adalah `model.glb` yang sama dengan hasil serah (KT-02).
- **Satu langkah per tik**: walau headless sudah selesai, GUI tetap memutar langkah satu per satu.
- Job baru (folder dengan manifest paling baru) otomatis diikuti.

## Pasang
Bagian dari ekstensi satu berkas (`<slug>-<versi>-<os>.zip`, lihat README): setelah "Pasang & hubungkan ke Claude",
tonton menyala otomatis setiap Blender dibuka (hanya job baru; tombol "Mulai tonton" memutar ulang job terakhir).
Konektor mengirim `AGEN3D_TONTON=1`, jadi setiap `perakit bangun` dari Claude menulis langkah tanpa diminta.
Mode pengembang: pasang `addon/agen3d/` langsung (tanpa payload) -> folder kerja = repo.

## Uji
- Otomatis (cloud/tanpa GUI): `perakit uji_tonton` = perekam + pemuat add-on dipanggil seperti tik pemantau.
  KT-01 langkah lengkap & akhir = model.glb, KT-02 mesh akhir identik, KT-03 tiap langkah termuat, KT-04 efek tumbuh
  selesai di skala 1, KT-05 pemuat tahan berkas setengah tertulis; 4 uji negatif.
  KT-05 menemukan cacat nyata saat dibuat: npz setengah tertulis membuat pemuat galat (BadZipFile) -> diperbaiki.
- Ujung-ke-ujung `alat/uji_ekstensi.py` (KE-01..07): zip -> Blender bersih -> Pasang -> server MCP dari config -> Claude membangun pion -> add-on memutar semua langkah, akhir = mesh serah.
- **Wajib di laptop (GUI, belum teruji di cloud):** timer berdetak, viewport ter-refresh tiap langkah, efek tumbuh
  terlihat halus, panel menampilkan "n/N". Hasil uji GUI dicatat di sini.

## Batas
- Ukuran: langkah berupa mesh penuh (±6 MB per langkah kuda v2, 11 langkah = 65 MB). Folder ditimpa per proyek.
- Baru modul perakit. product_shot/modeling_referensi menyusul (perekam yang sama: tulis langkah + manifest).
