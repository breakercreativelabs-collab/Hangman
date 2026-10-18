# Judge Rubric: Product Shot (learning system, layer 2)

The judge looks at **one contact sheet per product** (`projects/sample_products/result/curriculum/<product>/contact_sheet.jpg`), after the numeric QC has passed. The judge scores what does **not** have a number yet. Things QC already measures (floor, frame fill, cut-off, dimensions) are not scored again, unless the eye sees that the QC is wrong.

Results go to `projects/sample_products/result/curriculum/juri.json`: per product, 7 criteria × (score 1–5 + a one-sentence reason naming the contact sheet cell/row).

**Rule:** score **≤ 2 = defect**. It must go into `QC_RULES.md` as C-xx (defect → found by "Judge" → fix → numeric check if possible), then be fixed and rescored. Score 3 = acceptable with a note (goes into "Watch list"). Layer 2 target (`KRITERIA_SIAP.md`): mean ≥ 3.5 and no unhandled score ≤ 2.

**Cloud judge limits:** the contact sheet holds test renders (CPU, 360 px, 24 samples + denoise). Noise and fine detail are judged **relative to test quality**. Final material/technical judgment stays with the final laptop render (OptiX). The judge is not yet calibrated against the user's eye (`KRITERIA_SIAP.md`: ≥ 80% agreement over ≥ 15 ratings), so its scores are a first filter, not a verdict.

## Criteria

| # | Criterion | 5 (ready to ship) | 3 (acceptable, with notes) | 1 (defect) |
|---|---|---|---|---|
| 1 | **Composition** | Product centered, balanced breathing room in 16:9 / 9:16 / 1:1; camera elevation shows the form (not a flat silhouette) | Centered but feels stiff/empty in one of the ratios | Product tilted/cut off/occluded, or the camera angle hides the product's main feature |
| 2 | **Lighting** (key/rim/fill, highlights) | Key shapes the volume, rim separates edges from the background, specular highlights fall where they explain the form; the three presets have distinct, readable character | Form reads, but one preset is flat/too harsh, or a small highlight cuts across the label | Product side lost in the background, blown highlight covering the label, or non-physical black shadow |
| 3 | **Material** (metal/glass/paper/plastic) | Metal has directional reflections, glass/PET is clear with correct dark/light edges and visible contents, paper/carton is diffuse (not plastic), plastic has soft highlights | Material is guessable but one looks "CG" (too clean/grey) | Material misread: solid/black glass, metal looks like plastic, paper glossy like glass |
| 4 | **Background cleanliness** | Seamless cyclorama with no horizon, soft gradient, no smudges/lines; contact shadow grounds the product | Gradient slightly blotchy or weak contact shadow | Horizon line/backdrop edge visible, smudges, or product looks like it floats |
| 5 | **Turntable motion** (TURNTABLE row) | Angles at F25/F50/F75 match the easing (slow at the ends), product stays centered, no wobble | Moves correctly but one frame shows a less attractive side without fill light | Product drifts off center, jitters, or moves at linear speed |
| 6 | **Brand accuracy** (color/logo) | Variant color matches the hex in every preset (green cells), logo/label faces the camera in the hero frame, no color bleeding into other materials | Color correct but shifted in one preset (e.g. darker in dramatic) | Color wrong/washed out, logo at the back, or variant does not change |
| 7 | **Technical** (noise, artifacts) | No geometry artifacts (holes, UV seams, jagged shading), noise reasonable for test quality | Small artifacts only visible when zoomed in | Obvious artifacts: black bands, z-fighting, large fireflies, wavy surfaces |

## How to judge (judge's order)
1. Read `qc.json` first: if numeric QC failed, do not score (send it back to the fix step).
2. Look at the contact sheet **once** as a whole. Note the first impression (is the product recognized immediately?).
3. Score the 7 criteria. Every score needs a reason that can be rechecked (which cell, what is visible).
4. Score ≤ 2 → C-xx in `QC_RULES.md` + fix in verbs/product + re-render + rescore. Record the score before/after.
5. Anything measurable (e.g. dark bands, color) → make it a numeric QC with a negative test, not just a judge note.
