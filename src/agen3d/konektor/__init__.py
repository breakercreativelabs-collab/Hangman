"""konektor: server MCP yang membuka agen3d ke aplikasi Claude (Desktop / Code).

Berjalan di Python SISTEM (butuh paket `mcp`, tidak ada di Python Blender) dan TIDAK mengimpor bpy maupun modul/.
Semua kerja Blender lewat proses Blender baru (CLI tunggal `blender_cli.py`), sama seperti runner uji:
  blender.py    cari Blender + katalog perintah (`bantuan --json`, satu alat MCP per perintah CLI)
  pekerjaan.py  job latar: mulai, status, batal, ringkasan keluaran (QC JSON, contact sheet)
  eksekusi.py   dijalankan DI DALAM Blender: kode Python bebas (alat `jalankan_kode`) + diagnosa
  server.py     daftar alat MCP + instruksi untuk Claude
Peluncur: `konektor_mcp.py` di akar repo. Nama produk dibaca dari identitas.toml (tidak ditulis di sini).
"""
