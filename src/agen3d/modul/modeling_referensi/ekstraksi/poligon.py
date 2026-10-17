"""Masker biner -> poligon kontur (mm): marching squares + rantai segmen + Douglas-Peucker. Numpy murni (tanpa scipy).

Dipakai ekstrak_kelas: panel yang tidak cembung per kolom (mis. overlay pucat yang mengelilingi jendela mesh) tidak bisa
disimpan sebagai selubung [x, z_bawah, z_atas] per kolom (selubung mengisi area di antaranya). Poligon luar + lubang
dipakai resep sepatu sebagai prisma wilayah (prisma luar dikurangi prisma lubang).
"""
import numpy as np


# tepi sel marching squares: 0 = atas (y, x+.5), 1 = kanan (y+.5, x+1), 2 = bawah (y+1, x+.5), 3 = kiri (y+.5, x)
_TEPI = {1: [(3, 2)], 2: [(2, 1)], 3: [(3, 1)], 4: [(1, 0)], 5: [(3, 0), (1, 2)], 6: [(2, 0)], 7: [(3, 0)],
         8: [(0, 3)], 9: [(0, 2)], 10: [(0, 1), (2, 3)], 11: [(0, 1)], 12: [(1, 3)], 13: [(1, 2)], 14: [(2, 3)]}


def _titik(y, x, e):
    return {0: (y, x + 0.5), 1: (y + 0.5, x + 1.0), 2: (y + 1.0, x + 0.5), 3: (y + 0.5, x)}[e]


def kontur(mk):
    """Loop kontur (list array (n, 2) [y, x] piksel, titik di tengah tepi sel) dari masker biner."""
    m = np.pad(mk.astype(np.uint8), 1)
    kasus = m[:-1, :-1] * 8 + m[:-1, 1:] * 4 + m[1:, 1:] * 2 + m[1:, :-1] * 1  # TL TR BR BL
    seg = {}
    for y, x in zip(*np.nonzero((kasus > 0) & (kasus < 15))):
        for a, b in _TEPI[int(kasus[y, x])]:
            p, q = _titik(y, x, a), _titik(y, x, b)
            seg[p] = q
    loops = []
    while seg:
        p0, q = seg.popitem()
        loop = [p0]
        while q != p0 and q in seg:
            loop.append(q)
            q = seg.pop(q)
        if len(loop) >= 4:
            loops.append(np.array(loop) - 1.0)  # buang padding
    return loops


def rdp(P, eps):
    """Douglas-Peucker (iteratif) untuk polyline terbuka."""
    if len(P) < 3:
        return P
    simpan = np.zeros(len(P), bool)
    simpan[0] = simpan[-1] = True
    tumpuk = [(0, len(P) - 1)]
    while tumpuk:
        i, j = tumpuk.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        d = b - a
        n = np.hypot(*d)
        seg = P[i + 1:j]
        jarak = np.abs(d[0] * (seg[:, 1] - a[1]) - d[1] * (seg[:, 0] - a[0])) / n if n > 0 else np.hypot(*(seg - a).T)
        k = int(np.argmax(jarak))
        if jarak[k] > eps:
            simpan[i + 1 + k] = True
            tumpuk += [(i, i + 1 + k), (i + 1 + k, j)]
    return P[simpan]


def chaikin(P, n):
    """Penghalusan Chaikin loop tertutup (n iterasi): sudut tangga piksel/RDP membulat, bentuk tetap (titik baru di
    1/4 dan 3/4 tiap ruas)."""
    for _ in range(n):
        Q = np.roll(P, -1, 0)
        P = np.stack([0.75 * P + 0.25 * Q, 0.25 * P + 0.75 * Q], 1).reshape(-1, 2)
    return P


def luas_bertanda(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def poligon_mm(mk, to_x, to_z, eps_mm, sk, luas_lubang_min_mm2=4.0, halus=0):
    """Masker komponen -> dict(luar=[[x, z], ...], lubang=[[[x, z], ...], ...]) mm, disederhanakan eps_mm.
    Loop terbesar = luar; loop lain yang luasnya >= luas_lubang_min = lubang (lubang tali, celah antar panel)."""
    loops = []
    for L in kontur(mk):
        L = np.vstack([L, L[:1]])
        xz = np.c_[to_x(L[:, 1]), to_z(L[:, 0])]
        # rdp pada loop tertutup: belah di titik terjauh dari titik awal agar kedua ujung tetap
        k = int(np.argmax(np.hypot(*(xz - xz[0]).T)))
        s = np.vstack([rdp(xz[:k + 1], eps_mm)[:-1], rdp(xz[k:], eps_mm)[:-1]])
        if len(s) >= 3:
            loops.append(chaikin(s, halus) if halus else s)
    if not loops:
        return None
    luas = [abs(luas_bertanda(L)) for L in loops]
    i = int(np.argmax(luas))
    bulat = lambda L: [[round(float(a), 2), round(float(b), 2)] for a, b in L]
    return dict(luar=bulat(loops[i]),
                lubang=[bulat(L) for j, L in enumerate(loops) if j != i and luas[j] >= luas_lubang_min_mm2])
