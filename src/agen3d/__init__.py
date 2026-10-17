"""agen3d: paket agen operator Blender (nama netral; nama produk hanya di identitas.toml).

inti/  = scene standar, material (node helper tunggal), warna, kamera, render, io, lembar, qc, log (dipakai semua modul)
modul/ = product_shot, modeling_referensi, tvc, prosedural (bergantung hanya ke inti/ + dirinya; antar-modul lewat api.py)
Kontrak dan cara menambah modul/verb/QC: docs/ARSITEKTUR.md.
"""
