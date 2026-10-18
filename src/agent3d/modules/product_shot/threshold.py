"""Product shot QC thresholds (QC-01..12). Change only with a measured reason in QC_RULES.md (never loosen)."""

THRESHOLD = {
    "floor_contact_mm": 0.5,      # QC-01 product |z_min|
    "fill_min": 0.55,              # QC-02 frame fraction filled by the product (longest side of projected bbox)
    "fill_max": 0.85,
    "margin_min": 0.02,           # QC-03 product distance to frame edge
    "front_angle_max": 15.0,     # QC-04 degrees between product front direction and direction to camera
    "luma_min": 0.08,             # QC-05 mean frame luminance (0..1, display space)
    "luma_max": 0.92,
    "black_fraction_max": 0.50,    # pixels with luminance < 0.02
    "white_fraction_max": 0.50,    # pixels with luminance > 0.98
    "product_contrast_min": 0.04,   # mean difference render vs clean plate in product box
    "tip_speed_max": 0.50, # QC-06 rotation speed in first/last 5% vs mean
    "dimension_mm": 1.0,            # QC-07 dimension tolerance vs spec
    "camera_distance_min_x_clip": 2.0,  # QC-08 camera not inside/touching product
    "saturation_ratio_min": 0.60,   # QC-10 label color saturation at pixel / target hex saturation
    "hue_delta_max": 20.0,     # QC-10 degrees
    "value_delta_max": 0.35,   # QC-10 for neutral colors (target saturation < 0.2)
    "wall_ratio_max": 0.35,   # QC-11 glass wall thickness / object width (solid = 1.0; bottle 2-4 mm ~ 0.05-0.13)
    "glass_ior_min": 1.40,          # QC-11 only clear materials with glass/plastic IOR (liquid ~1.33 excluded)
    "metal_black_max": 0.08,     # QC-12 fraction of metal pixels (not underside) with luma < 0.02 (C-15: slim 0.11-0.13)
}
