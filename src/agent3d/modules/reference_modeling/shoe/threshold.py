"""QC thresholds of the shoe recipe (AM-01..18). Change only with a measured reason in the project QC_RULES.md (never loosen)."""
from ...product_shot.api import THRESHOLD as PS_THRESHOLD



# AM-09: M2 model ~1.5 deg; M1 block 5.7 deg (see QC_RULES). AM-10: IoU of the data polygon vs itself shifted (0.5; 0.5) mm
# = 0.928 lateral / 0.930 medial (error <= half the data column spacing of 0.9 mm)
RIPPLE, IOU_SW = 2.5, 0.93
THRESHOLD = {
    "iou_min": 0.95,          # AM-01 side_view silhouette, AM-02 bottom-view plan
    "midsole_mm": 1.5,        # AM-03 mean |top midsole line, model - data|
    "window_mm": 2.0,        # AM-04 error of Air window center (x, z) and size (width, height)
    "length_mm": 1.0,        # AM-05 length 293.7 +- 1
    "width_mm": 1.0,          # AM-05 forefoot width 107.9 +- 1
    "iou_medial_min": 0.95,   # AM-06 MEDIAL silhouette (independent data, not used for building); see QC_RULES
    "banding_max": 0.010,    # AM-07 COHERENT column lines (same in the top & bottom half of the sole), luma, 15 mm high-pass
    "tread_min": 0.020,       # AM-07 high-frequency luma std (residual of a 2.5 mm blur) on the outsole, bottom view
    "notch_mm": 1.0,          # AM-08 notch depth in the midsole side wall (C-A2)
    "ripple_deg": RIPPLE,         # AM-09 upper normal ripple (RMS vs 15 mm moving average), see QC_RULES
    "iou_swoosh_min": IOU_SW, # AM-10 swoosh IoU per side
    "mudguard_mm": 2.0,       # AM-11 mean |top mudguard line, model - data|
    "lace_distance_mm": 0.0,     # AM-12 lace surface distance to the upper (no penetration)
    "hole_mm": 3.0,         # AM-12 data holes vs model holes (x, z)
    "layer_mm": 0.2,          # AM-13 minimum distance between panel layers
    # M3 (AM-15 uses the product-shot QC-10 rule with the same thresholds: PS_THRESHOLD)
    "saturation_ratio_min": PS_THRESHOLD["saturation_ratio_min"],  # 0.60
    "hue_delta_max": PS_THRESHOLD["hue_delta_max"],      # 20 deg
    "value_delta_max": PS_THRESHOLD["value_delta_max"],  # 0.35 (neutral/pastel target, saturation < 0.2)
    "pastel_sat_max": 0.30,  # AM-15 pixel saturation of pastel/neutral roles (see QC_RULES)
    "pastel_hue_sat_min": 0.05,  # AM-15 pastel hue tested only when pixel & target saturation >= 0.05
    "holo_hue_min": 20.0,     # AM-16 swoosh hue difference between 2 camera angles (deg)
    "capsule_transmission_min": 0.01,  # AM-17 capsule pixel luma rise when the probe in the cavity is lit
}
PIX = 0.5                     # mm per pixel, orthographic render (AM-01/02)
SW = 0.25                     # mm, swoosh ray grid (AM-10)
RAY = 0.25                    # mm, side_view ray grid (AM-04, heel map)
WINDOW_SEARCH = (170.0, 265.0, 6.0, 40.0)  # x0, x1, z0, z1 mm: heel midsole band (outside it "transmission" = background, not window)
COLUMN_MIN = 3.0               # a window column counts when the gap height >= 3 mm (same rule as extract_contour.py)
VIEW = {  # x0, x1 (mm), v0, v1 (mm, image vertical axis), camera location, rotation
    "side_view": dict(h=(-4.0, 298.0), v=(-4.0, 146.0)),
    "bottom": dict(h=(-4.0, 298.0), v=(-62.0, 62.0)),
}
