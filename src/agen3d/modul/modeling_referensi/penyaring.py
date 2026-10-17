"""Penyaring sinyal 1D/2D untuk data siluet foto (numpy): Gauss, smoothstep, opening morfologis, selubung bawah."""
import math

import numpy as np

LEBAR_LUG = 21.0  # mm: jendela selubung bawah > plateau celah lug terlebar di data AM1 (x 96,8-107,1 = 10 mm; 65,9-84,5 = 18 mm)
HALUS = 9.0       # mm: rata-rata geser setelah opening


def gauss(x, v, sigma, langkah=0.5):
    """Halus Gauss pada grid seragam `langkah` mm, tepi dipadding nilai ujung. Kembalikan (grid, nilai)."""
    g = np.arange(x[0], x[-1] + 1e-9, langkah)
    vg = np.interp(g, x, v)
    if sigma <= 0:
        return g, vg
    r = int(math.ceil(3 * sigma / langkah))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) * langkah / sigma) ** 2)
    k /= k.sum()
    return g, np.convolve(np.pad(vg, r, mode="edge"), k, "valid")


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def median5(z):
    """Median 5 sampel (meredam takik foto di garis bawah); 2 sampel ujung tetap mentah (ujung toe/tumit melengkung)."""
    out = z.copy()
    for i in range(2, len(z) - 2):
        out[i] = np.median(z[i - 2:i + 3])
    return out


def opening(x, z, lebar=LEBAR_LUG):
    """Opening morfologis (min bergulir lalu maks bergulir): membuang puncak lebih sempit dari `lebar` mm.
    Tepi dipadding nilai ujung, sehingga lereng monoton di ujung tidak terpotong. Dipakai juga oleh QC AM-08."""
    k = max(1, int(round(lebar / 2 / np.median(np.diff(x)))))
    zp = np.r_[np.full(k, z[0]), z, np.full(k, z[-1])]
    ero = np.array([zp[max(i - k, 0):i + k + 1].min() for i in range(len(zp))])
    return np.array([ero[max(i - k, 0):i + k + 1].max() for i in range(len(zp))])[k:-k]


def selubung_bawah(x, z, lebar=LEBAR_LUG, halus=HALUS):
    """C-A2: garis dasar sol = selubung bawah z_bawah siluet. Siluet samping = titik terendah per kolom, jadi celah
    antar lug yang melintang membuat plateau naik 3-4,6 mm selebar 2-6 sampel (mis. x 224,6-228,7). Opening membuang
    plateau itu, toe spring & bevel tumit tetap. Lalu rata-rata geser 9 mm: tangga kuantisasi foto (0,23 mm/px)
    menekuk normal per stasiun = garis di tampak bawah (C-A1). Lug hanya di outsole (tapak material)."""
    h = max(1, int(round(halus / 2 / np.median(np.diff(x)))))
    return np.convolve(np.pad(opening(x, z, lebar), h, mode="edge"), np.ones(2 * h + 1) / (2 * h + 1), "valid")


def rata_geser(a, n, sumbu):
    """Rata-rata geser n sampel sepanjang `sumbu` (tepi dipadding nilai ujung)."""
    k = np.ones(n) / n
    return np.apply_along_axis(lambda r: np.convolve(np.pad(r, n // 2, mode="edge"), k, "valid"), sumbu, a)
