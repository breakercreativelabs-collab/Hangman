# Rules & QC: Tree Generator

Every defect found by eye **must** be recorded here, then turned into a generator rule and/or an automatic numeric check. This file is the agent's "skill memory". Claude does not remember between sessions, but this file does.

Format: ID · defect · found by · generator fix · numeric check (QC) · pass threshold · status

| ID | Defect | Found by | Generator fix | Numeric check (QC) | Pass threshold | Status |
|---|---|---|---|---|---|---|
| QC-001 | Green box clumps at branch tips (duplicate growth points at the same position) | Eye, v1 (2026-10-13) | Reject a new point closer than 0.4 × step to an existing point | `QC_points_stacked` (points < 1 cm from another point) | = 0 | ✅ v2 |
| QC-002 | Leaves clump unnaturally in one area | Eye, v1 | (side effect of QC-001) | `QC_clump_leaf_max_x_median` (0.5 m voxels) | ≤ 8 | ✅ v2 |
| QC-003 | Leaves are plain squares, look game-like | Eye, v2 | Leaf shape from UV + alpha, per-leaf color variation, light transmission | (visual, no number yet) | n/a | ✅ v3 |
| QC-004 | Middle branches as thick as "noodles" | Eye, v2 | Taper with exponent 1.5 (pipe model) | `branch_radius_min_max_m` | tip ≤ 0.015 m | ⚠️ v3 tip still 0.022 m |
| QC-005 | Crown only at the tips, looks hollow | Eye, v2 | Leaves also on the last 3 twig segments | leaves per tree | ≥ 15 × tip count | ✅ v3 |
| QC-006 | Leaves below the ground | Prevention | n/a | `QC_leaf_in_bottom_ground` | = 0 | ✅ v3 |
| QC-007 | Crown too round and symmetric, like topiary | Eye, v3 | Plan: lobes and noise on the crown volume | Plan: crown radius variation per compass direction | coefficient of variation ≥ 0.15 | 🔜 |
| QC-008 | Trunk straight like a pole, no taper and no root flare | Eye, v3 | Plan: tapered trunk + root flare + a slight bend | Plan: ratio of base radius to radius at the crown base | ≥ 1.3 | 🔜 |

## Preventing regressions
Every generator change is rerun with the same presets and seeds, and every QC above must still pass before the change is accepted.

Since Task 9 (refactor into `src/agent3d/modules/procedural/`): `procedural test` runs QC-001/002/005/006 on 3 example trees, a report regression against `reference_tree.json` (taken from the v3 spike code before the refactor; the generator is deterministic, so it must match exactly) and the QC-001 negative test (`grow(prevent_duplicate=False)` = v1 behavior: 2,995 stacked points, caught). QC-004 stays ⚠ (reported, does not fail) until Task 1 resumes. Example render: `procedural tree` (GPU device if available, otherwise CPU; the old spike forced OptiX). Images v1–v3: `projects/trees/result/` (JPG).
