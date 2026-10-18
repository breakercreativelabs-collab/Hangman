# Rules & QC: Builder (models from a text prompt)

The builder builds a model from a **shape design** (`projects/<id>/design.toml`) that Claude writes from a text prompt: Claude = the brain (reasoning, sizes, design, judgement), builder = the hands (deterministic SDF -> mesh, numeric QC). Non-generative. **Before writing a design, Claude must research the best examples on the web** (reference images, real dimensions, quality traits) and cite the sources in `[entity] source` (user decision 2026-10-16). Every defect found by eye **must** be recorded here and then implemented in code/design.

Format: ID · defect/risk · found by · fix · numeric check (QC) · pass threshold · status

| ID | Defect / risk | Found by | Fix | Numeric check (QC) | Pass threshold | Status |
|---|---|---|---|---|---|---|
| KC-01 | Height does not match the design | Prevention | n/a | Z bbox height (mm) | design ± `height_tolerance_mm` | ✅ v1 61.88 / 62 ± 0.5 |
| KC-02 | Base diameter does not match the design | Prevention | n/a | 2 × max radius of points with z < 3 mm | design ± `diameter_tolerance_mm` | ✅ v1 35.00 / 35 ± 0.4 |
| KC-03 | Leaky mesh (cannot be 3D printed / used in booleans) | Prevention | SDF -> openvdb quads (closed) | edges not shared by exactly 2 faces | = 0 | ✅ v1 |
| KC-04 | Not left-right symmetric | Measured, v1 (asymmetric decimate: point-to-point distance 0.91 mm; Blender's symmetric decimate breaks manifold) | Plain decimate + measure mirrored points to the **surface** (BVH), not to points | max distance from Y-mirrored points to the surface | ≤ `symmetry_tolerance_mm` (0.3) | ✅ v1 0.05 mm |
| KC-05 | Piece tips over (head too far forward) | Prevention | n/a | horizontal distance from the volume's center of mass to the axis | ≤ 0.5 × footprint radius | ✅ v1 0.29 / 8.4 mm |
| KC-06 | Too many polygons | Prevention | Decimate to `target_triangles` | triangle count | ≤ `max_polygons` | ✅ v1 120,000 |
| KC-07 | Head looks like a flat board from the front | Eye, v1 (2026-10-16) | Design rev 1: `round_mm` 3.0 -> 4.2, jaw thickness 7.4 -> 7.8, cheek detail | (visual, no number yet) | n/a | ✅ rev 1 |
| KC-07 | Every part is "soft" (1-2 mm fillets everywhere), no mix of hard/soft edges like a real carving | User's eye, rev 3 (2026-10-16) | Rev 4: `carve_plane` in the local skeleton (6 planes: nose ridge, muzzle side, nose front, forehead, jaw cheek, under the jaw); muscles/neck stay soft | per plane: flat area (faces <= 0.1 mm from the plane, normal <= 8 deg) AND edge fold angle = P75 of face-normal angles in a 0.7 mm ring outside the plane | area >= `min_area_mm2` (2) AND angle >= `min_edge_angle` (20 deg; calibration: rev 4 23-26 deg vs Laplacian smoothed 20x = 10-13 deg) | ✅ rev 4 min 23.3 deg |
| KC-08 | Mane reads as horizontal ribs ("radiator"), not strands | Eye, rev 1 | rev 2: mane band split by grooves (`subtract_line`) + dense lines; no strands yet | (visual) | n/a | ⚠️ |
| KC-09 | Head soft like a pillow; a real wooden knight has carved planes (crisp edges on cheek, forehead, nose bridge) | User's eye, comparison photo (2026-10-16) | `carve_plane` recipe (regional flat SDF plane, smooth transition) + 3 planes (cheek, neck, muzzle side) | (visual) | n/a | ✅ rev 2 |
| KC-10 | Low stepped base; the real one is a tall bulging base (large ball + collar + slim neck), ±35% of the height | User's eye, comparison photo | `lathe` profile rev 2 (parameters only): base 23.5 mm, ball Ø36 | base height / total height | 0.30-0.38 (not automated yet) | ✅ rev 2 = 0.38 |
| KC-11 | Muzzle short and blunt; the real one is a long boxy muzzle, open mouth, prominent chin, slim concave front of the neck | User's eye, comparison photo | Silhouette rev 2 (parameters): long muzzle, open mouth notch, chin, leaning neck | (visual) | n/a | ✅ rev 2 |
| KC-12 | Ears are one split block; real ones are two separate pointed, hollowed ears | User's eye, comparison photo | `add_/subtract_cone` recipe (flattened rounded cone) = ear + its hollow | (visual) | n/a | ✅ rev 2 |
| KC-13 | Plain material; the real one is grained wood | User's eye, comparison photo | `wood_material` (Z rings centered outside the piece + stretched distortion) via `[make_material]` | (visual) | n/a | ⏸ deferred: user decided to focus on modeling first (grey clay render) |
| KC-14 | The neck carve plane also cuts the base collar (notched from the front) | Eye, rev 2 | Carve region raised to z ≥ 25.5 | (visual) | n/a | ✅ rev 2b |
| KC-15 | Brown wood looks peach (lights too bright) | Eye, rev 2 | Exposure -1 in the contact sheet studio | (visual) | n/a | ✅ rev 2b |
| KC-16 | Mane still flat ribs (KC-08) despite the band boundary grooves | Eye, rev 2 | Plan: a strand recipe | (visual) | n/a | 🔜 |
| KC-17 | Face does not read as a horse (rev 2: head = thickened silhouette + carve planes = "board") | User's eye (2026-10-16) | Rev 3: head & neck assembled from anatomical primitives (skull/jaw/muzzle ellipsoids, nose bridge/lower jaw cones, tapered neck tube, mane crest) in a local head `[[skeleton]]` (+ `scale`) | (visual: the "face" close-up on the contact sheet) | n/a | ✅ rev 3 |
| KC-18 | Brow sticks out sideways like an ear (front view) | Eye, rev 3 | brow r 1.9 -> 1.4, set in 0.6 mm | (visual) | n/a | ✅ rev 3b |
| KC-19 | Mouth gap barely visible | Eye, rev 3b | Plan: deeper groove / silhouette notch | (visual) | n/a | 🔜 |
| KC-20 | A carve plane cuts other parts in its region (cheek tilted too far down = a "wound" notch; the under-jaw plane also cuts the neck) | Eye, rev 4 | Cheek normal -0.35 -> -0.15; under-jaw region u 11-22; wider neck (y scale 0.84) + soft throat | (visual) | n/a | ✅ rev 4b |
| KC-21 | Where the jowl meets the lower jaw there is a dark concave groove; in the photo it is a raised ridge/edge | Eye, rev 4b | Plan: two carve planes meeting (forming a ridge) instead of a hanging ellipsoid | (visual) | n/a | 🔜 |
| KC-22 | Eye-to-cheek area is messy; cheek deeply hollow like a hole | User's eye, rev 4 (2026-10-16) | Suspected root cause: the head = many separate blobs (skull, jaw, nose bridge) merged -> concave valleys at the seams + eye socket + cheek groove + cheek plane stacked in one area. Plan: base head mass as ONE unified shape first, then carve | Plan: detect unintended concavity (negative curvature where the design is convex) | planned | ✅ rev 5 (eye; number 🔜): head = 1 wedge mass + 2 soft bulges, brow & cheek groove removed -> hole gone |
| KC-23 | Chin / under the mouth is messy | User's eye, rev 4 | Suspected: mouth groove + chin ellipsoid + under-jaw plane stacked. Rev 5: lower jaw = part of the head mass, chin 1 bulge, under-jaw plane moved behind the chin (max 2 operations per area) | (visual) | n/a | ✅ rev 5 (eye) |
| KC-24 | Jaw cheek plane edge is soft (21 deg, just above the 20 threshold) because the plane barely grazes the gently sloping cheek surface | Measured, rev 5 | Carve 0.3 mm deeper (20 -> 21 deg); suspected: needs a more tilted normal if the cheek must be crisp | KC-07 | >= 20 deg | ⚠️ rev 5b barely passes |
| KC-25 | Pose/proportions differ from the reference: head tilted too far down & too long (muzzle z 34 vs reference ~41), neck looks short | Comparison judge (same-angle render vs reference), rev 6 | Head skeleton angle 32 -> 22, scale 1.12 -> 0.95, origin z 57 -> 55.5 (from the reference eye/muzzle heights; the Z axis is not distorted by the 3/4 angle) | (visual comparison; plan: key point heights vs reference) | n/a | ✅ rev 6b |
| KC-26 | Ears are thin spikes (reference: wide thick leaves); mouth a short line (reference: long open gap); mane like gear teeth (reference: fine dense lines); eyeballs bulge | Comparison judge, rev 6 | Ear r1 3.3 r2 1.0 thickness 0.8; mouth groove 7 points r 0.7 opening at the front; crest r 1.9 + notches r 0.5 spacing 1.6; eyeball r 0.85 | (visual) | n/a | ✅ rev 6 |
| KC-27 | The cavity between jaw and neck + bulging chest reads as a "hook"; front of the neck upright like a pole | Comparison judge + side view; diagnosed with 2 parallel variants (neck plane extended / disabled -> not the cause) | "Neck front" tube whose edge follows the reference line (x5,z42)->(x11,z24) + a "front neck" plane | KC-07 (front neck 32 deg) | >= 20 deg | ✅ rev 6e |
| KC-28 | Every hard edge is razor sharp (nose ridge 69 deg); real carved edges are slightly rounded | Comparison judge, rev 6e | Plan: bevel the carve plane edges (carve with an edge radius) | plan: max angle | planned | 🔜 |
| KC-29 | The user judged knight rev 6 "a step back, ruined" although numeric QC passed and every comparison round felt like an improvement | User (2026-10-16) | Knight PARKED (rev 5 = the best version according to the user; rev 6 stays in the repo as a record). Moved to a difficulty ladder: lathe pieces first (pawn) | (user judgement) | n/a | ⏸ parked |
| KC-30 | Revolving straight profile segments -> visible ring bands on the ball/body (pawn rev 0) | Eye, pawn rev 0 | `smoothed_profile` (centripetal Catmull-Rom) + `sharp_profile` (corner indices that split the curve; without it the curve bulges out 0.3 mm: height 53.29, base 32.28) | KC-01/02 catch the shift | design tolerance | ✅ pawn rev 1b |
| KC-31 | Too slow: pawn 98 s (SDF field 55 s) while a professional takes < 1 minute | User (2026-10-16) | `lathe` computes the 2D distance once on an (r, z) grid, then bilinear (not per 3D voxel x 600 segments) | build time without render | pawn: field 3.0 s, total 12 s (cloud CPU); with 6 renders 67 s; `--mode preview` (1 render, no negatives) 12.7 s wall; rook prompt -> preview 37 s | ✅ |
| KC-32 | Queen crown like "a cracked eggshell": round scallops tear the thin cup wall (1.8 mm) | Eye, queen rev 0-1 | Wall 3.6 mm + V notches (`subtract_cone` x8 via `spin_n`), notch 2.4 mm below the rim | (visual) | n/a | ✅ queen rev 2b |
| KC-33 | Repeated details (`spin_n`) are computed over the whole grid -> queen field 35.7 s (pawn 3 s) | Measured, queen | Plan: compute each detail only inside its bounding box | field time | plan < 10 s | 🔜 |
| KC-34 | Knight v2 rev 0 from reasoning alone: muzzle z 37 (reference ~45), base stacked like a spring, head-neck wide & flat from the front, puffy cheeks, pointed ears, "pig face" | 3D comparison judge (researched 3D reference, same 6 angles) | rev 1: proportions measured from the 3D reference (muzzle height, back curve, throat, low base with 1 ring, half thickness 6-8 mm); rev 2: oval cross section (round 7), `thickness_x` narrowing at the back, nostrils to the side | (3D visual comparison) | n/a | ✅ rev 2 (awaiting user) |
| KC-35 | Face details invisible (eyes/nose/mouth): Y positions were guessed; after the cross section became oval the surface moved -> carving spheres float outside the head | User + calculation, knight v2 rev 2 | `depth`/`bump`: the builder finds the Y surface itself and then attaches/carves; hard error when a detail does not touch the object (caught a mouth point inside the gap) | hard error on an empty column | - | ✅ rev 3 |

## ASSET quality judge (asset path, user decision 2026-10-17; `asset.py`)
Openly licensed assets are graded BEFORE use. Weighted score 0-100; A >= 85, B >= 65 (both require KA-01 to pass), otherwise C. Claude's eye still judges the render afterwards (numbers do not capture beauty).

| ID | Check | Threshold | Weight | Why |
|---|---|---|---|---|
| KA-01 | Open license + written attribution | CC0 / CC-BY / MIT + attribution | 30 | without it the asset must not be used at all |
| KA-02 | Leaky edges (non-manifold), after vertex welding | <= 0.1% | 15 | SDF conversion needs a closed mesh (a 1% threshold leaked in the 10% hole negative test) |
| KA-03 | Normal orientation (signed volume > 0) | > 0 | 10 | flipped normals = inside/outside swapped |
| KA-04 | Sliver triangles (ratio > 10) | <= 5% | 10 | dirty mesh/raw scan; note: 2 subdivision levels push it to ~5.1% (just fails; recorded, not loosened) |
| KA-05 | Triangle count | 2,000-500,000 | 10 | too coarse / too heavy |
| KA-06 | Loose parts | <= 3 (set per design) | 10 | junk, duplicate objects |
| KA-07 | Y mirror symmetry (median) | <= 0.5 mm | 15 | pieces are symmetric; skewed/broken asset |
| KA-08 | Required features per `object_kind` (`REQUIRED_FEATURES`, e.g. knight: eye, ear, nostril, mouth, mane): present in `asset_features` (checked by Claude in a close-up) or as a `[[detail]]` named after the feature | nothing missing | counts toward the model PASS | defect from the user's eye: a knight asset graded A 90 but **without eyes**; KA-01..07 only measure mesh cleanliness, not anatomy. Negative test: eye details removed -> fail |

Asset path lessons: (1) glTF splits vertices at UV seams -> 7.6% apparent leaks & 1,096 loose parts; vertices MUST be welded before grading/conversion. (2) A low-poly asset (11k triangles) looks faceted after SDF -> `subdiv = 2` (Catmull-Clark after welding). (3) Cut sign: dropping z < cut_z = subtracting the SDF (Z - cut_z); the wrong sign drops the whole head (caught by KC-01). (4) A grade-A asset is not necessarily complete: check the required features in a close-up, patch what is missing with surface-relative `[[detail]]` (KA-08). (5) Joining the asset to built parts: the rounded bottom of the asset looked like "a marble on a plate" (user's eye: "separate, not merged") -> `extend_from_z` (cross section extended straight down) + `smooth_union_mm` 2.5.

## SET QC (`builder set` command, `set.py`; 2026-10-17)
Pieces are judged as ONE set on a board in the starting position, not one by one. Sizes are measured from the finished models (glb), not from the design numbers.

| ID | Check | Threshold | Why / source |
|---|---|---|---|
| KS-01 | Height order king > queen > bishop > knight > rook > pawn | strictly decreasing | Staunton hierarchy; a 2x tall pawn is caught |
| KS-02 | King base / tile side | 0.68-0.80 | guideline 75-78% (USCF/chess.com; sources range 68-85%) |
| KS-03 | Tile side | 50-60 mm | FIDE (tournament) |
| KS-04 | Largest base / tile side | <= 0.80 | leaves a gap between neighboring pieces |
| KS-05 | Valid starting position | 32 pieces, unique tiles, count per kind, king e / queen d | swapped king-queen & two pieces on one tile are caught |
| KS-06 | Every piece passes its own QC (KC/KA report) | all | the set must not hide a failing piece |

Set negative tests (7): pawn 2x, tile 40 mm, tile 70 mm, knight base 50 mm, king-queen swapped, two pieces on one tile, knight failing its own QC.

## Live mode (`builder build --live 1` command, `test_live`; live.py + addon/agent3d; 2026-10-17)
| ID | Check | Threshold | Why |
|---|---|---|---|
| KT-01 | All steps present, last = model.glb, manifest done | >= 2 steps | the viewer must see it through to the handover mesh |
| KT-02 | Final mesh in the open Blender identical to the headless handover mesh | difference < 1e-6 m | user decision: live view must not differ from the result |
| KT-03 | Every step loads (mesh not empty) | all | a missing step = the process appears to jump |
| KT-04 | Grow effect ends at scale 1 | 1.0 | an object must not be left squashed |
| KT-05 | Loader survives a half-written manifest/npz | None, no error | **a real defect found by this test**: a truncated npz -> BadZipFile stopped the watcher; now caught and retried on the next tick |
Negative tests (4): final step missing, final = first step, one step fails to load, grow stops halfway. The GUI timer/viewport must be checked on the laptop (docs/LIVE_PREVIEW.md).

## Negative tests (required, run on every `builder build`)
The resulting mesh is corrupted 6 ways; each KC-01..06 must fail on its own corruptor (height × 1.05; base × 1.04; 1 face removed; shift Y 1 mm above z 30; head forward 25 mm; polygon limit 1000). v1: 6/6 caught, each only by its own check. Asset path: + 7 KA negative tests (empty license, 10% of triangles removed, flipped normals, slivers added, cut down to 1,000, 5 copies, half shifted) -> asset knight 13/13. Since rev 4 (when the design has planes with `min_area_mm2`): + KC-07 must fail on a mesh Laplacian smoothed 20x ("everything soft"); 7/7. Note: 3-6x Laplacian is not enough (flat planes stay flat; the area metric alone leaked -> edge fold angle added).

## Catalog gaps (recorded so the catalog grows from real needs)
- Strands/fibers (mane, hair): no recipe yet; approximated with capsule notches.
- Carve planes, ears, wood grain: added in rev 2 (from the user's comparison photo, used as shape knowledge).
- Web image research from the cloud: blocked by the environment's network policy (403 on wikimedia, houseofstaunton, jaqueslondon, chessbazaar, etc.); only search text snippets. Needs allowed domains or research done on the laptop.

## General lessons (apply to any model; from chess knight rev 0-4, 2026-10-16)
1. **Research first, then design.** Reasoning alone misses (rev 0: base, muzzle, ears wrong). Reference images + real dimensions + quality traits, cited in `[entity] source`.
2. **Pick the recipe that fits the shape type.** Turned objects -> `lathe`; flat/silhouette objects -> `cushion`; organic (animals, faces) -> assemble anatomical primitives. A wrong recipe cannot be patched with parameters (rev 2: "board" face).
3. **Big first, details later** (main mass -> secondary forms -> details). Details on a wrong mass only add chaos.
4. **Unify the base mass, then carve.** Many separate blobs merged smoothly create unintended concave valleys at the seams (KC-22). Proven in rev 5: 6 blobs -> 1 wedge + 2 soft bulges, the cheek hole is gone.
5. **Decide edge character per area:** hard (planes, bone, man-made edges) vs soft (muscle, cloth). All soft = a doll; all hard = a block (KC-07).
6. **Regional operations can leak** into other parts (the jaw plane cutting the neck, KC-20): keep regions as tight as possible, check the view from every side.
7. **Think in the part's local skeleton** (+ scale): a revision like "bigger head / less tilted" = 1-2 numbers.
8. **Judging needs an honest view:** grey clay (not white/textured), close-ups of important areas (face), texture only after the shape is right.
9. **Every numeric QC needs a negative test; the first metric can leak** (KC-07: area alone passed when smoothed -> fold angle added).
10. **The user's eye catches what QC does not measure yet** (beauty of the face, neatness). Every eye finding -> a row here -> a number where possible.
11. **Comparison judge:** a researched reference + a model render from the same camera angle, side by side (`[[comparison]]`). Measure key point heights (eye, muzzle, ears) on the vertical axis (not distorted by the 3/4 angle), then correct the skeleton. Comparison images contain the reference photo -> sent to the user only, never committed.
12. **Diagnose with parallel variants:** when the cause of a defect is unclear, build 2 variants (disable/change one operation) at once and compare; do not guess repeatedly (KC-27: the first guess was wrong).
13. **Measure from the user's side, change little per round.** Knight rev 6: 6 comparison rounds + a dozen changes at once from ONE photo angle -> each step felt better to Claude, but the user judged the result a step back. Max 2-3 changes per round, show the user more often, keep the version the user likes as the baseline.
14. **Difficulty ladder:** lathe (pawn, rook) -> lathe + a little carving (bishop, queen, king) -> organic (knight, figurines). Move up only after the user rates the previous rung as good.
15. **3D reference > photo:** look for an openly licensed 3D model (e.g. Khronos glTF Sample Assets via raw GitHub, which is reachable from the cloud) -> `[reference_3d]` -> 6-angle 3D comparison with the same material & lighting. Measure proportions (key point heights, width per height) as data; the design is still written by hand. Knight v2: close after 2 rounds; knight v1 with 1 photo: still failing after 6 rounds.
16. **Details relative to the surface, not guessed coordinates:** use `depth` (carve) / `bump` (raise); when the shape changes, the detail stays attached. A detail that misses the object is a hard error, not a silent disappearance.
