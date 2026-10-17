# Konektor MCP (colokan agen ke aplikasi Claude)

Konektor membuat agen Blender bisa dipakai langsung dari **Claude Desktop** atau **Claude Code**: Anda mengetik atau
bicara di Claude, Claude memanggil alat konektor, dan konektor menjalankan Blender di laptop ini. Front end-nya adalah
aplikasi Claude; konektor hanya colokannya. Nama yang tampil di Claude dibaca dari `identitas.toml`.

```
Anda (chat/suara) -> aplikasi Claude -> konektor MCP (konektor_mcp.py) -> Blender headless (blender_cli.py)
```

## Alat yang tersedia
| Alat | Fungsi |
|---|---|
| `<modul>__<perintah>` | Satu alat per perintah CLI, **dibuat otomatis** dari katalog (`bantuan --json`). Perintah baru langsung jadi alat setelah Claude dimulai ulang. Opsi CLI menjadi parameter. |
| `jalankan_kode` | Python Blender **bebas** untuk hal yang belum ada perintahnya. Selalu minta izin Anda di setiap panggilan (Claude Code: `requiresUserInteraction`; Claude Desktop: dialog izin alat; jangan pilih "Always allow" untuk alat ini). Kode tersimpan di folder job sebagai jejak audit. |
| `status_pekerjaan`, `batalkan_pekerjaan`, `daftar_pekerjaan` | Render/QC panjang berjalan sebagai job latar. Alat menunggu maks. `tunggu_detik` (dibatasi 50 s lewat `AGEN3D_BATAS_TUNGGU`, di bawah batas waktu Claude Desktop ±60 s), lalu mengembalikan id job. Status: memulai, berjalan, selesai, gagal, dibatalkan, terputus. |
| `diagnosa` | Versi Blender, GPU (OptiX/CUDA), Python, paket mcp, sisa disk, branch git. |
| `lihat_gambar` | Tampilkan contact sheet / pratinjau (≤ 700 KB) di chat. |
| `uji_regresi` | Runner uji tunggal (`uji/jalankan.py`). |
| `panduan` | Cara kerja agen + daftar perintah. |

Job: `artefak/konektor/pekerjaan/<id>/` (log, meta, kode, hasil). Job dijalankan pembungkus dua tahap
(`src/agen3d/konektor/bungkus.py`): saat Claude Code menutup server (`taskkill /T`), job tetap selesai (teruji). Klien
yang mematikan seluruh job object Windows (mis. klien SDK Python; Claude Desktop belum diketahui) ikut menghentikan job:
statusnya tercatat `terputus` beserta alasannya, tidak pernah "berjalan" selamanya.

## Pasang termudah: satu berkas ekstensi Blender
Zip ekstensi per OS dari `alat/rilis.py` (atau halaman Releases) -> Blender: Install from Disk -> panel Agen3D ->
"Pasang & hubungkan ke Claude". Konektor memakai Python bawaan Blender + paket `mcp` yang dibawa ekstensi (`lib/` di
folder kerja); config Claude Desktop ditulis otomatis (digabung, cadangan .bak; config rusak tidak disentuh).
Diuji ujung-ke-ujung: `python3 alat/uji_ekstensi.py` (KE-01..07).

## Pasang manual (pengembang)
1. Python 3.11+ dan Blender 5.x terpasang. Bila Blender tidak di lokasi standar, set env `AGEN3D_BLENDER` ke `blender.exe`.
2. Di folder repo:
   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install "mcp>=2,<3"
   .venv\Scripts\python konektor_mcp.py --config
   ```
   (Linux/macOS: `.venv/bin/python`.)
3. Perintah ke-3 mencetak dua hal:
   - **Claude Desktop:** potongan JSON untuk `claude_desktop_config.json` (Settings → Developer → Edit Config), lalu tutup
     penuh Claude dari tray dan buka lagi. Catatan Windows: versi Claude dari Microsoft Store (MSIX) bisa membaca berkas di
     `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\`; pastikan berkas yang diedit adalah yang dibaca.
   - **Claude Code:** satu perintah `claude mcp add --scope user ...`.
4. Cek: minta Claude "jalankan diagnosa". Log server Claude Desktop: `%APPDATA%\Claude\logs\mcp-server-<nama>.log`.

## Uji
`python uji/jalankan.py --hanya struktur,cli,konektor` (suite `konektor` memakai klien MCP sungguhan; lihat `uji/konektor.py`).
Aturan QC dan riwayat cacat konektor: `src/agen3d/konektor/ATURAN_QC.md`.

## Batas v0 (diketahui)
- Setiap panggilan alat = proses Blender baru (tidak ada sesi Blender yang terus hidup). Kerja bertahap: simpan ke `.blend`
  lalu buka lagi. Mengoperasikan Blender yang sedang terbuka di layar = fase 2 (add-on Blender).
- Path berkas hanya di zona `artefak/` (biner, render), `proyek/` (data + hasil), `klien/` (referensi). Kode, `.git`,
  dan berkas rahasia di akar repo tidak bisa disentuh alat CLI. Kode bebas tetap punya hak penuh (selalu minta izin).
- Job bersamaan ke folder keluaran yang sama belum dicegah.
- Multi-pengguna, pemasangan sekali klik (paket MCPB), dan belajar dari banyak pengguna belum dibangun.
