"""Warna: hex <-> linear, HSV, luminans (Rec.709) dan luminans relatif WCAG."""
import colorsys

import numpy as np

KOEF_LUMA = (0.2126, 0.7152, 0.0722)


def hex_ke_linear(h):
    """'#RRGGBB' (sRGB) -> [r, g, b] linear."""
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]


def lin(hexa):
    return tuple(hex_ke_linear(hexa))


def hex_rgb(hexa):
    """'#RRGGBB' -> [r, g, b] 0..1 (nilai tampilan sRGB, sama dengan yang dibaca dari PNG)."""
    return [int(hexa.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def hsv(rgb):
    return colorsys.rgb_to_hsv(*[float(c) for c in rgb])


def dhue(a, b):
    """Selisih hue sirkular (0..1) dalam derajat."""
    return abs((a - b + 0.5) % 1.0 - 0.5) * 360


def luma(rgb, presisi="f"):
    """Luminans tampilan per piksel. presisi 'f' = float32 (QC gambar), None = float64 (QC TV)."""
    return rgb @ np.array(KOEF_LUMA, presisi)


def lum_relatif(rgb):
    """WCAG: sRGB tampilan -> linear -> luminans relatif."""
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return c @ np.array(KOEF_LUMA)
