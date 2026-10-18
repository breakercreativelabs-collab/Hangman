# Blender agent architecture (package `agent3d`)

A guide for agents (and people) who edit the code. Written in Tugas 9, when the experiment code (about 7,600 lines in
`eksperimen/`) was refactored into a modular package. **Behaviour is identical** to the old code: proven by comparing
scene fingerprints (geometry, materials, lights, cameras, keyframes, render settings) of old vs new and by the single
test runner (see the Tugas 9 PR). In 2026-10 all identifiers, files and folders were renamed from Indonesian to
English; this document describes the current names.

## 1. Product name = one file
- The product name, slug, description and version live **only** in `identity.toml` (repo root).
- Packages, modules, classes and functions use neutral names (`agent3d`, `product_shot`, `tvc`, ...).
- CLI/log/MCP text reads the identity through `agent3d.identity` (`title()`, `name()`, `slug()`, `description()`,
  `version()`, `public_repo()`).
- **Renaming the product = editing `identity.toml` only.** Structure test (a) fails if the name/slug appears in any
  other file. Documented exceptions: the idea-room notes (`00-inbox/`, `01-ide/`, `02-arsip/`, `sesi/`, `INDEX.md`)
  are the history of brainstorming decisions, not the product, so the working name may appear there; and the
  `README.md` of the release package, which `tools/release.py` generates from `identity.toml`.
- Never write the product name into committed output (qc.json, contact sheets, CONTROL in a .blend): console only.

## 2. Layout
```
identity.toml                  product name (the only place), version, public_repo, telemetry_url
release.toml                   public release manifest (include / exclude / forbidden / brand), read by tools/release.py
blender_cli.py                 CLI launcher (outside src/: adds src/ to sys.path, then agent3d.cli.main)
mcp_connector.py               MCP server launcher (.venv Python with the mcp package; --config prints the setup). docs/CONNECTOR.md
LICENSE                        GPL-3.0-or-later
src/agent3d/
  identity.py                  reads identity.toml
  cli.py                       THE single entry point: <module> <command> [--option value]; `help --json <file>` =
                               machine-readable catalog (each command's options are read by intercepting io.options);
                               __run_code__/__diagnose__ = connector meta commands
  telemetry.py                 automatic anonymous usage stats (whitelist, queue, off switch); docs/FEEDBACK.md
  connector/                   MCP server (system Python, NO bpy and NO imports from modules/): blender (find Blender,
                               catalog), job (background jobs), wrap (two-stage wrapper that records completion), server
                               (MCP tools), execution (runs inside Blender: free code + diagnose), QC_RULES.md (K-01..13).
                               Structure test (f): only execution.py may import bpy/core
  core/                        used by every module; must NOT import modules/
    scene.py                   standard .blend PS-1 (PRODUCT/LIGHTS/CAMERAS/BACKDROP + CONTROL), TURNTABLE -> PRODUCT_ROOT,
                               CONTROL drivers, fcurves (layered actions in 5.x), product points
    material.py                the ONE node helper: bsdf, make_material, new_node, math_node, ramp, transmission_shadow
                               (C-11), clear_material
    color.py                   hex <-> linear, HSV, hue difference, luma, WCAG relative luminance
    camera.py                  az/el direction, look_at, projection of points -> frame, fixed camera, ray per pixel, uv_to_local
    render.py                  select_device (OptiX -> CUDA -> HIP -> oneAPI -> CPU), QUALITY, setup_render, render_image/frame
    io.py                      absolute repo paths (C-10), artifact()/project(), CLI options, read/write PNG-JPG, resize, JSON
    sheets.py                  contact sheets (bitmap font, green/red QC bar; .jpg quality 85 or .png)
    qc.py                      check(), iou(), caught() (negative tests), NegativeTests, Logger (tests), summarize()
    log.py                     CLI banner from the identity
  modules/
    product_shot/              verbs (verbs, light, framing, make_material), QC-01..12 (threshold, qc_scene, qc_image),
                               sample products (specification, profile, sample_products), run, curriculum, test,
                               JUDGE_RUBRIC.md (judge), QC_RULES.md, api.py
    reference_modeling/        extraction/ (alpha, contour, panel, photo, classes, polygon, tread, file, test_photo =
                               synthetic photos for the smoke test), geometry (loft/boolean/offset/tube/BVH), filters
                               (Gauss, opening, hull), qc_silhouette (mask, overlay, ray, ripple, hue),
                               shoe/ (shoe recipe from data: data, sole, shape, upper, lace, p3_material, neutral_material,
                               colorway_material, panel_data, studio, threshold, qc_bottom AM-01..08, qc_upper AM-09..14,
                               qc_material AM-15..18, qc_panel, viewpoints, report, stage_report), api.py
    tvc/                       shot-list engine driven by tvc.toml: config, key (easing), camera (rig + bisection), props
                               (bubbles, podium), props_neon, text (kinetic), compositor, production (build/render/MP4),
                               TV QC (qc_scene, qc_image), negative (generic corruptor), report
    procedural/                tree (space colonization), match (inverse silhouette), test, reference_tree.json, QC_RULES.md
    builder/                   models from a text prompt: shape design (TOML written by Claude) -> sdf (recipes lathe,
                               cushion, asset; details) -> openvdb mesh -> QC KC + negatives (builder), asset (adapted
                               open-licence models, KA), set (chess set on a board, KS), live (step recorder for the live
                               preview) + test_live (KT), staging (render, contact sheets), QC_RULES.md
    feedback/                  written feedback recorded locally + anonymised export (KB-01..06), test_telemetry
                               (KM-01..08), QC_RULES.md
addon/agent3d/                 Blender add-on (live preview, GPL, no socket): __init__ (panel, preferences), connect
                               (Install & connect to Claude), live (watches output/live/)
projects/<id>/                 ONLY configuration + reference data + QC rules + small results
  am1/                         project.toml (labels, P3 palette, output, extraction), tvc.toml, reference_am1*.json,
                               RULES_QC.md (AM-xx, C-Axx, TV-xx), result/ (qc_am1.json, contact sheet JPG, tvc/, preview/)
  am90/                        generic shoe template (Tugas 11): project.toml, tvc.toml, reference_am90*.json,
                               tread_grooves.png, BRIEF.md, RULES_QC.md, result/ (M1-M3)
  sample_products/result/      product shot results for the sample products (qc.json, contact sheet JPG, curriculum, judge)
  trees/result/                tree spike renders v1-v3 (JPG)
  chess_*/                     design.toml (shape design from a prompt) + result/ (contact sheet JPG, report_qc.json);
                               chess_set/set.toml = the full set on a board
tests/
  run.py                       the SINGLE runner for all regression tests + negative tests + structure tests
  structure.py                 structure tests (a)-(f) + their negative tests
  smoke.py                     cli suite: smoke test for EVERY help command (code 0 + the promised files) + negatives
  connector.py                 connector suite: the MCP server through a real MCP client + negatives
tools/
  release.py                   public package (source zip + one Blender extension per OS), audit KR-01..09 + negatives
  test_extension.py            end-to-end test of one extension zip in a clean Blender (KE-01..07)
  mcp_test_client.py           MCP client used by test_extension.py (runs on Blender's bundled Python)
  benchmark.py                 fixed benchmark (6 chess pieces) for the automatic gate
  analyze_telemetry.py         daily telemetry analysis (signals per command/check, poisoning filter)
services/telemetry/            Cloudflare Worker + D1 that receives the usage stats (worker.js, schema.sql, test.mjs)
docs/                          ARCHITECTURE.md, CONNECTOR.md, LIVE_PREVIEW.md, FEEDBACK.md, README_PUBLIC.md (release README template)
output/                        IGNORED: .blend, raw renders, MP4, test logs. Everything can be rebuilt through the CLI.
eksperimen/                    briefs & working notes (TUGAS_CLOUD, KRITERIA_SIAP, METRIK_BELAJAR, GERBANG_OTOMATIS,
                               selera.md, cloud-setup.sh, parked tasks); old briefs in eksperimen/arsip/
```

## 3. Contracts
1. **core/** depends on no module.
2. A **module** imports only `core/` + itself. Need a function from another module? Go through that module's
   **`api.py`** (the only door between modules, structure test e). Current contracts:
   - `product_shot.api`: `THRESHOLD` (QC-01..12; used by AM-15 and TV-02/03), `qc_glass` (QC-11 hollow clear glass).
   - `reference_modeling.api`: `load_project`, `path_model`, `build_model`, `save_model`, `studio_palette`,
     `qc_slot_material` (used by tvc).
3. **commands.py** per module: `COMMANDS = {name: (function(argv) -> exit code, summary)}`; cli.py finds it.
   Every command automatically becomes an MCP tool `<module>__<command>` (connector) and must have a smoke-test row in
   `tests/smoke.py`. Options are read with `io.options(argv, defaults)` so the catalog can read their names and
   defaults. Private `_x` functions in commands.py are CLI adapters (the same name may appear in several modules).
4. A **project** is data, not code: modules read `projects/<id>/project.toml` / `tvc.toml`. New project = new folder.
   The [D] numbers of the shoe recipe (shape, QC camera) still live in the `shoe/` code because they were calibrated
   on a single shoe (AM1); move them to `project.toml [model]` when a second shoe arrives (reason: moving them now
   would be a guess without data). AM90 (section 9) already overrides most of them per project.
5. One helper, one place (structure test c): material nodes only in `core/material.py`, image I/O in `core/io.py`, etc.
6. `.py` files ≤ 400 lines (structure test d). Any exception must be listed with a reason in the table below.
7. Paths written by bpy are always absolute (C-10): use `core.io` (`path_repo`, `artifact`, `project`) or `os.path.abspath`.
8. Large binaries (.blend, .mp4, raw renders) go to `output/` (ignored). Only small results go into the repo: JSON,
   Markdown, contact sheet/storyboard JPG.

### File size exceptions
| File | Reason |
|---|---|
| (none) | Every file is ≤ 400 lines (largest: `builder/builder.py` 387, `product_shot/test.py` 363). |

## 4. CLI (one entry point for every module)
Everything goes through one entry point, the same on the Windows laptop (OptiX) and in the Linux cloud (CPU):
```
blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- <module> <command> [--option value ...]
blender -b --factory-startup -P blender_cli.py -- help          # list of modules + commands
```
| Module | Main command | Others |
|---|---|---|
| product_shot | `run [--product bottle,can] [--source references/x.glb --unit mm --front +X --logo_u .. --logo_z ..] [--quality test\|final] [--color red,blue,green] [--out ..] [--artifact ..]` | `curriculum [--product ..] [--palette ..]`, `test` |
| reference_modeling | `qc [--project am1] [--stage m1\|m2\|m3\|all_items] [--out ..] [--artifact ..] [--without_negatives 1] [--negative "a\|b"]` | `data --project <id> --ref ..` (one command photo → data), `build`, `extract_contour`, `extract_panel`, `extract_class`, `extract_tread`, `alpha_analysis` (`--ref ..`), `test_photo` |
| tvc | `render [--project am1] [--ratio 9x16\|16x9] [--quality test\|final] [--frame 1-375] [--blend 1] [--model x.blend]` | `qc` (TV-01..08 + negatives + animatic + storyboard) |
| procedural | `test` | `tree [--render 0] [--sample 128]`, `match` |
| builder | `build [--design projects/<id>/design.toml] [--mode preview\|full] [--render 0] [--sample 32] [--live 1] [--out ..]` | `set [--set projects/chess_set/set.toml]` (QC KS), `test_live` (KT, docs/LIVE_PREVIEW.md) |
| feedback | `record --kind defect\|taste --module .. --project .. --text ".." [--report ..] [--save ..]` | `export [--approve 1] [--out ..]` (anonymous submission, KB-01..06, docs/FEEDBACK.md), `test`, `test_telemetry` (KM-01..08) |

Outside `src/`: `addon/agent3d/` (Blender add-on for the live preview, GPL, no socket), `tools/release.py` (open
source package from `release.toml`, audit KR-01..09 + 10 negative tests; README from `docs/README_PUBLIC.md`),
`LICENSE` (GPL-3.0-or-later).

Default output: small results to `projects/<id>/result/`, binaries to `output/`. `HEGEMONI_DEVICE=CPU` forces the CPU.

## 5. Tests
```
python3 tests/run.py                                                 # full runner (~1.5-2 h on cloud CPU; much faster on an RTX)
python3 tests/run.py --only structure,product_shot,run,procedural    # quick (~6 min)
blender -b --factory-startup -P tests/run.py -- --only structure     # without a system Python (Windows)
```
Suites: `structure` (a–f + 6 negatives) · `product_shot` (≥ 88 verb tests + negative QC) · `run` (bottle + can QC
PASS) · `model` (AM-01..18 + QC-11, 25 negatives) · `am90` (generic shoe template M1–M3, 22 negatives) · `tvc`
(TV-01..08 + AM-18, 16 negatives; uses the .blend from `model`) · `procedural` (tree QC + baseline regression +
negatives) · `builder` (KC-01..06 + negatives) · `cli` (smoke test of every command) · `connector` (MCP server through
a real client). Results: `output/tests/<suite>/` + `output/tests/summary.json`. Exit code 1 if anything failed. A
change is accepted only when the runner is green (regression).

## 6. How to add
- **Verb** (product_shot): a function in the matching verb file (≤ 400 lines; start a new file when full), explicit
  parameters, writes its state to `CONTROL`. Positive + negative tests in `product_shot/test.py`. Document it in the
  `blender-operator` skill.
- **QC**: the threshold goes in the module's `threshold.py` (loosening is not allowed; any change needs a measured
  reason in QC_RULES.md); the check uses `core.qc.check(id, name, value, passed, threshold, context)`; **a negative test
  is mandatory** (corrupt the scene -> the check must fail); add a row to the module's/project's QC_RULES.md (defect →
  found by → fix → numeric check → threshold → status).
- **Module**: `src/agent3d/modules/<name>/` with `__init__.py`, `commands.py` (COMMANDS), `QC_RULES.md`, tests in
  `test.py`; add the name to `MODULE` in `cli.py`, a suite to `tests/run.py` and smoke-test rows to `tests/smoke.py`.
  If another module needs its functions: `api.py`.
- **Project**: `projects/<id>/project.toml` (+ `tvc.toml` when there is a TVC) + data + a QC rules file; run it with
  `--project <id>`.
- **New TVC**: copy `projects/am1/tvc.toml` and change the shot list/camera/animation/text/negatives. No code changes.

## 7. Old → new file map (Tugas 9)
The left column keeps the original (Indonesian) paths from before Tugas 9; the right column shows today's paths
(relative to `src/agent3d/`) after the 2026-10 English rename.

| Old | New |
|---|---|
| `eksperimen/product-shot/verbs.py` | `modules/product_shot/verbs.py` (import/normalize/turntable/material_variant) + `light.py` (studio_lighting) + `framing.py` (camera, render_variants) + `make_material.py` (labels, product materials); scene basics → `core/scene.py`, node helpers → `core/material.py`, device/render → `core/render.py`, projection → `core/camera.py` |
| `eksperimen/product-shot/qc.py` | `modules/product_shot/threshold.py` + `qc_scene.py` + `qc_image.py`; PNG reading/resizing → `core/io.py`; checks → `core/qc.py` |
| `eksperimen/product-shot/produk_uji.py` | `modules/product_shot/specification.py` + `profile.py` + `sample_products.py` |
| `eksperimen/product-shot/lembar.py` | `core/sheets.py` |
| `eksperimen/product-shot/jalankan.py`, `kurikulum.py`, `uji_verbs.py` | `modules/product_shot/run.py`, `curriculum.py`, `test.py` |
| `eksperimen/product-shot/ATURAN_QC.md`, `RUBRIK_JURI.md` | `modules/product_shot/QC_RULES.md`, `JUDGE_RUBRIC.md` |
| `eksperimen/product-shot/hasil/` | `projects/sample_products/result/` (PNG → JPG, .blend removed) |
| `eksperimen/am1/model_am1.py` | `modules/reference_modeling/shoe/sole.py` + `data.py` (derived data) + `neutral_material.py`; loft/boolean/mesh → `geometry.py`, opening/hull/median → `filters.py` |
| `eksperimen/am1/upper_am1.py` | `shoe/shape.py` (parameters + shape) + `upper.py` + `lace.py` (laces + stitching); mesh utilities → `geometry.py` |
| `eksperimen/am1/material_am1.py` | `shoe/p3_material.py` (palette from `projects/am1/project.toml`) |
| `eksperimen/am1/qc_am1.py` | `shoe/threshold.py`, `qc_bottom.py`, `qc_upper.py`, `qc_material.py`, `studio.py`, `viewpoints.py`, `report.py`; IoU/overlay/ray → `qc_silhouette.py` + `core/qc.py` |
| `eksperimen/am1/ekstrak_kontur.py`, `ekstrak_panel.py`, `analisis_alfa.py` | `reference_modeling/extraction/contour.py`, `panel.py`, `alpha.py` (+ `photo.py`); URL, lab size, notes → `project.toml [extraction]` |
| `eksperimen/am1/tvc/tvc_am1.py` | `modules/tvc/` (config, key, camera, props, text, compositor, production) + `projects/am1/tvc.toml` |
| `eksperimen/am1/tvc/qc_tvc.py` | `modules/tvc/qc_scene.py`, `qc_image.py`, `negative.py`, `report.py` (+ `[[negative]]` in tvc.toml) |
| `eksperimen/am1/referensi_am1*.json`, `ATURAN_QC.md` | `projects/am1/` (`reference_am1*.json`, `RULES_QC.md`) |
| `eksperimen/am1/hasil/`, `pratinjau/`, `tvc/hasil/` | `projects/am1/result/` (+ `preview/`, `tvc/`); PNG → JPG; `am1_m3.blend`, MP4 → `output/` (rebuilt) |
| `eksperimen/pohon-prosedural/pohon.py`, `cocokkan.py`, `ATURAN_QC.md` | `modules/procedural/` (`tree.py`, `match.py`, `QC_RULES.md`; source `exec` replaced by module imports) |
| `eksperimen/pohon-prosedural/*.png`, `pohon.blend` | `projects/trees/result/*.jpg`; .blend removed (`procedural tree` rebuilds it) |

## 8. Intended behaviour changes (not logic)
- Output location: small results in `projects/<id>/result/`, binaries in `output/` (previously everything was in
  `eksperimen/.../hasil/`).
- Contact sheets, palettes, storyboards: `.jpg` quality 85 (previously `.png`, 1–3 MB per sheet). Pixel content is the
  same before compression.
- `procedural tree` / `match`: the device comes from `core.render.select_device` (GPU when available, otherwise CPU);
  the old spike forced OptiX (Tugas 1 item 1). On the OptiX laptop the result is the same.
- `tvc qc`: the model is read from the `.blend` written by `reference_modeling qc` (artifact) or from `--model`, not
  from a committed file.
- Function names that clashed across files were renamed (structure test c), e.g. `build` → `build_product` /
  `build_shoe` / `build_tvc` / `build_tree`; the product shot palette's `hex_to_linear` → `color_to_linear`.

## 9. Generic shoe template (Tugas 11, through project am90, 2026-10-14)
A new shoe = **a project folder + data**, not new code. AM90 was built with 0 lines of project-specific Python; every
difference is in `projects/am90/project.toml`. AM1 keeps the old path (every new parameter defaults to the AM1 value;
the regression runner stays green).

| Layer | Files | Contents |
|---|---|---|
| Photo → data | `extraction/classes.py`, `polygon.py`, `tread.py`; command `data` | CIELAB color classes from `[[extraction.classes]]` rules (shadow tolerant), midsole line + window from a layer scan, panel = union of components per `[[extraction.panel]]` zone → polygons (outer + holes, Chaikin), panel colors [F-photo]; tread: sole color zones (plan polygons) + a small groove-map PNG |
| Recipe parameters | `shoe/data.py` `model()`, `map_x()` | `[model.<part>]` per project (`viewpoints`, `upper`, `hole`, `common` roles) and an x-map from AM1 landmarks → project (piecewise linear) for the AM1 recipe's position constants |
| Panels | `shoe/panel_data.py` | `[[model.panel]]`: S-layer shell ∩ polygon prism (L + M merged), `midsole`/`outsole` bases = paint/zone regions (cut after all sole booleans), stitching from the polygons |
| Materials | `shoe/colorway_material.py` | `[palette.role] = [hex, source, kind]`, kinds: `leather`, `striped_leather`, `tpu`, `foam`, `striped_foam`, `mesh`, `rubber`, `photo_rubber` (tread from the groove map), `capsule` (film tint ≠ visible color), `lace`, `soft`, `suede` |
| Staged QC | `shoe/stage_report.py`, `qc_panel.py` | `--stage m1/m2/m3`; AM-10 per panel (threshold = the panel data floor); AM-15 roles from the object/slot structure; generic M1–M3 negatives |
| TVC | `tvc/props_neon.py` + hook in `production.py` | `props = [...]` in tvc.toml: `wet_floor`, `neon_rings`, `shock_wave`, `splash` (bullet time), `plasma_capsule`, `energy_line`; `[contact]` puts the lowest point exactly on the floor; `[[lamp]]` AREA lights without a parent |

Not generic yet (watch list): `tvc qc` (report/negatives) still locks 9:16 as the main ratio; for a 16:9-only project
the TV QC runs per function (qc_scene_tv, qc_frame, qc_video, qc_contrast) until the next generalisation (Tugas 10,
parked 2026-10-14, not merged).
