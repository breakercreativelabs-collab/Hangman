"""Color: hex <-> linear, HSV, luminance (Rec.709) and WCAG relative luminance."""
import colorsys

import numpy as np

LUMA_COEF = (0.2126, 0.7152, 0.0722)


def hex_to_linear(h):
    """'#RRGGBB' (sRGB) -> [r, g, b] linear."""
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]


def lin(hexa):
    return tuple(hex_to_linear(hexa))


def hex_rgb(hexa):
    """'#RRGGBB' -> [r, g, b] 0..1 (sRGB display values, same as read from a PNG)."""
    return [int(hexa.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def hsv(rgb):
    return colorsys.rgb_to_hsv(*[float(c) for c in rgb])


def dhue(a, b):
    """Circular hue difference (inputs 0..1), in degrees."""
    return abs((a - b + 0.5) % 1.0 - 0.5) * 360


def luma(rgb, precision="f"):
    """Per-pixel display luminance. precision 'f' = float32 (image QC), None = float64 (TV QC)."""
    return rgb @ np.array(LUMA_COEF, precision)


def relative_lum(rgb):
    """WCAG: sRGB display -> linear -> relative luminance."""
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return c @ np.array(LUMA_COEF)
