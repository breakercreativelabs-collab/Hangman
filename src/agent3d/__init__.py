"""agent3d: Blender operator agent package (neutral name; the product name lives only in identity.toml).

core/    = standard scene, material (single node helper), color, camera, render, io, sheets, qc, log (used by all modules)
modules/ = product_shot, reference_modeling, tvc, procedural (depend only on core/ and themselves; cross-module via api.py)
Contracts and how to add a module/verb/QC check: docs/ARCHITECTURE.md.
"""
