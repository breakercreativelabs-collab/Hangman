"""1D/2D signal filters for photo silhouette data (numpy): Gaussian, smoothstep, morphological opening, bottom hull."""
import math

import numpy as np

LUG_WIDTH = 21.0  # mm: bottom-hull window > widest lug-gap plateau in the AM1 data (x 96.8-107.1 = 10 mm; 65.9-84.5 = 18 mm)
SMOOTH = 9.0       # mm: moving average after opening


def gauss(x, v, sigma, step=0.5):
    """Gaussian smoothing on a uniform `step` mm grid, edges padded with the end values. Returns (grid, value)."""
    g = np.arange(x[0], x[-1] + 1e-9, step)
    vg = np.interp(g, x, v)
    if sigma <= 0:
        return g, vg
    r = int(math.ceil(3 * sigma / step))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) * step / sigma) ** 2)
    k /= k.sum()
    return g, np.convolve(np.pad(vg, r, mode="edge"), k, "valid")


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def median5(z):
    """5-sample median (damps photo notches in the bottom line); the 2 end samples stay raw (curved toe/heel ends)."""
    out = z.copy()
    for i in range(2, len(z) - 2):
        out[i] = np.median(z[i - 2:i + 3])
    return out


def opening(x, z, width=LUG_WIDTH):
    """Morphological opening (rolling min, then rolling max): removes peaks narrower than `width` mm.
    Edges are padded with the end values, so monotonic slopes at the ends are not clipped. Also used by QC AM-08."""
    k = max(1, int(round(width / 2 / np.median(np.diff(x)))))
    zp = np.r_[np.full(k, z[0]), z, np.full(k, z[-1])]
    ero = np.array([zp[max(i - k, 0):i + k + 1].min() for i in range(len(zp))])
    return np.array([ero[max(i - k, 0):i + k + 1].max() for i in range(len(zp))])[k:-k]


def bottom_hull(x, z, width=LUG_WIDTH, smoothness=SMOOTH):
    """C-A2: base sole line = bottom hull of the silhouette z_bottom. The side_view silhouette is the lowest point per
    column, so transverse gaps between lugs create plateaus 3-4.6 mm high and 2-6 samples wide (e.g. x 224.6-228.7).
    Opening removes those plateaus while keeping toe spring and the heel bevel. Then a 9 mm moving average: the photo's
    quantization steps (0.23 mm/px) bend the normal per station = lines in the bottom views (C-A1). Lugs live only in
    the outsole (tread material)."""
    h = max(1, int(round(smoothness / 2 / np.median(np.diff(x)))))
    return np.convolve(np.pad(opening(x, z, width), h, mode="edge"), np.ones(2 * h + 1) / (2 * h + 1), "valid")


def moving_average(a, n, axis):
    """Moving average of n samples along `axis` (edges padded with the end values)."""
    k = np.ones(n) / n
    return np.apply_along_axis(lambda r: np.convolve(np.pad(r, n // 2, mode="edge"), k, "valid"), axis, a)
