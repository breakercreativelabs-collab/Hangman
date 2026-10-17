"""Resep bentuk sebagai medan jarak bertanda (SDF, numpy, mm; negatif = di dalam) + SDF -> mesh quad (openvdb).

Resep: putar (revolusi profil r-z), bantal (siluet samping digembungkan dengan tebal h(x, z) dan penampang
membulat). Detail: bola, kapsul, kotak membulat, digabung/diukir dengan union/kurang halus (polinomial, k mm).
Semua deterministik: rancangan yang sama -> mesh yang sama.
"""
import numpy as np


def kisi(bawah, atas, vox):
    """Sumbu x, y, z (mm) kisi voxel dari pojok `bawah` ke `atas`."""
    return [np.arange(b, a + vox, vox, dtype=np.float32) for b, a in zip(bawah, atas)]


def poligon2d(u, v, poli):
    """Jarak bertanda titik (u, v) ke poligon tertutup [(u, v)...] (negatif di dalam, even-odd). Bentuk u = bentuk v."""
    P = np.asarray(poli, np.float32)
    d2 = np.full(u.shape, np.inf, np.float32)
    di_dalam = np.zeros(u.shape, bool)
    for (ua, va), (ub, vb) in zip(P, np.roll(P, -1, axis=0)):
        eu, ev = ub - ua, vb - va
        wu, wv = u - ua, v - va
        t = np.clip((wu * eu + wv * ev) / max(eu * eu + ev * ev, 1e-12), 0.0, 1.0)
        d2 = np.minimum(d2, (wu - eu * t) ** 2 + (wv - ev * t) ** 2)
        silang = (va > v) != (vb > v)
        with np.errstate(divide="ignore", invalid="ignore"):
            xs = ua + (v - va) * eu / np.where(ev == 0, 1e-12, ev)
        di_dalam ^= silang & (u < xs)
    return np.where(di_dalam, -1.0, 1.0).astype(np.float32) * np.sqrt(d2)


def haluskan_profil(profil, langkah=0.3, tajam=()):
    """Profil poligon -> kurva Catmull-Rom sentripetal (melewati semua titik) dengan sampel tiap ~`langkah` mm.
    Menghapus pita kerucut hasil revolusi ruas lurus. Kurva bisa melengkung keluar di sudut (pion rev 1: +0,3 mm),
    jadi titik sudut (indeks di `tajam`, plus kedua ujung) memotong kurva: tiap potongan dihaluskan terpisah."""
    potong = sorted({0, len(profil) - 1, *tajam})
    if len(potong) > 2:
        hasil = []
        for a, b in zip(potong[:-1], potong[1:]):
            bagian = haluskan_profil(profil[a:b + 1], langkah)
            hasil += bagian if not hasil else bagian[1:]
        return hasil
    P = np.asarray(profil, float)
    out = [P[0]]
    for i in range(len(P) - 1):
        p0, p1, p2 = P[max(i - 1, 0)], P[i], P[i + 1]
        p3 = P[min(i + 2, len(P) - 1)]
        t1 = t0 = 0.0
        t1 = t0 + max(np.linalg.norm(p1 - p0), 1e-6) ** 0.5
        t2 = t1 + max(np.linalg.norm(p2 - p1), 1e-6) ** 0.5
        t3 = t2 + max(np.linalg.norm(p3 - p2), 1e-6) ** 0.5
        n = max(int(np.ceil(np.linalg.norm(p2 - p1) / langkah)), 1)
        for t in np.linspace(t1, t2, n + 1)[1:]:
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out = np.array(out)
    out[:, 0] = np.maximum(out[:, 0], 0.0)
    return out.tolist()


def putar(X, Y, Z, profil, vox=None):
    """Revolusi profil [(r, z)...] (tertutup lewat sumbu) mengelilingi sumbu Z. Dengan `vox`: jarak 2D dihitung sekali
    di kisi (r, z) halus (vox/2) lalu diambil bilinear -> ~100x lebih cepat dari menghitung di tiap voxel 3D."""
    R = np.sqrt(X * X + Y * Y)
    if vox is None:
        return poligon2d(R, Z, profil)
    h = vox / 2
    z0 = float(Z[0, 0, 0])
    rr = np.arange(0.0, float(R.max()) + 2 * h, h, dtype=np.float32)
    zz = z0 + np.arange(Z.shape[2], dtype=np.float32) * vox
    d2 = poligon2d(*np.meshgrid(rr, zz, indexing="ij"), profil)
    fi = R / h
    i0 = np.minimum(fi.astype(np.int32), len(rr) - 2)
    t = fi - i0
    k = np.broadcast_to(np.arange(Z.shape[2]), R.shape)
    return d2[i0, k] * (1 - t) + d2[i0 + 1, k] * t


def tebal_bantal(x, z, b):
    """Setengah tebal h(x, z) (mm): interpolasi tebal_z, menyempit linear mulai runcing_x0 ke arah +X."""
    tz = np.asarray(b["tebal_z"], np.float32)
    h = np.interp(z, tz[:, 0], tz[:, 1]).astype(np.float32)
    h = h - np.maximum(x - b["runcing_x0"], 0.0) * b["runcing_laju"]
    if "tebal_x" in b:  # pengali tebal sepanjang X (mis. punggung leher menyempit jadi punggungan surai)
        tx = np.asarray(b["tebal_x"], np.float32)
        h = h * np.interp(x, tx[:, 0], tx[:, 1]).astype(np.float32)
    return np.maximum(h, 0.5)


def bantal(x, y, z, b):
    """Siluet (x, z) diekstrusi simetris di Y dengan setengah tebal h(x, z) dan penampang membulat (jari-jari r)."""
    xx, zz = np.meshgrid(x, z, indexing="ij")
    d2 = poligon2d(xx, zz, b["siluet"])[:, None, :]
    h = tebal_bantal(xx, zz, b)[:, None, :]
    r = np.minimum(np.float32(b["bulat_mm"]), h - 0.05)
    qx, qy = d2 + r, np.abs(y)[None, :, None] - h + r
    luar = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
    return np.minimum(np.maximum(qx, qy), 0) + luar - r


def sdf_bola(X, Y, Z, pusat, r):
    return np.sqrt((X - pusat[0]) ** 2 + (Y - pusat[1]) ** 2 + (Z - pusat[2]) ** 2) - r


def sdf_kapsul(X, Y, Z, a, b, r):
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    ab = b - a
    t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1] + (Z - a[2]) * ab[2]) / float(ab @ ab), 0, 1)
    return np.sqrt((X - a[0] - ab[0] * t) ** 2 + (Y - a[1] - ab[1] * t) ** 2 + (Z - a[2] - ab[2] * t) ** 2) - r


def elipsoid(X, Y, Z, pusat, jari, sudut=0.0):
    """Elipsoid (pendekatan iq) jari-jari (ru, ry, rw) pada sumbu lokal: u = (cos a, 0, -sin a), y, w = (sin a, 0, cos a);
    a = `sudut` derajat (putar di sumbu Y, positif = ujung +u menunduk)."""
    a = np.radians(sudut)
    dx, dy, dz = X - pusat[0], Y - pusat[1], Z - pusat[2]
    u, w = dx * np.cos(a) - dz * np.sin(a), dx * np.sin(a) + dz * np.cos(a)
    k0 = np.sqrt((u / jari[0]) ** 2 + (dy / jari[1]) ** 2 + (w / jari[2]) ** 2)
    k1 = np.sqrt((u / jari[0] ** 2) ** 2 + (dy / jari[1] ** 2) ** 2 + (w / jari[2] ** 2) ** 2)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def kotak(X, Y, Z, pusat, setengah, r):
    q = [np.abs(P - c) - (s - r) for P, c, s in zip((X, Y, Z), pusat, setengah)]
    luar = np.sqrt(sum(np.maximum(k, 0) ** 2 for k in q))
    return luar + np.minimum(np.maximum(np.maximum(q[0], q[1]), q[2]), 0) - r


def kerucut(X, Y, Z, a, b, r1, r2, skala=(1.0, 1.0, 1.0)):
    """Kerucut membulat dari a (jari-jari r1) ke b (r2), opsional dipipihkan per sumbu (skala < 1 = pipih).
    SDF iq "round cone"; skala membuatnya pendekatan (cukup untuk permukaan nol)."""
    a = np.asarray(a, np.float32)
    s = np.asarray(skala, np.float32)
    P = [(Q - c) / k for Q, c, k in zip((X, Y, Z), a, s)]
    ba = (np.asarray(b, np.float32) - a) / s
    l2 = float(ba @ ba)
    rr = r1 - r2
    a2, il2 = l2 - rr * rr, 1.0 / l2
    y = P[0] * ba[0] + P[1] * ba[1] + P[2] * ba[2]
    z = y - l2
    x2 = sum((Pi * l2 - bi * y) ** 2 for Pi, bi in zip(P, ba))
    y2, z2 = y * y * l2, z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d = np.where(np.sign(z) * a2 * z2 > k, np.sqrt(x2 + z2) * il2 - r2,
                 np.where(np.sign(y) * a2 * y2 < k, np.sqrt(x2 + y2) * il2 - r1,
                          (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1))
    return d * float(s.min())


def pahat(d, X, Y, Z, titik, normal, pusat, setengah, transisi, skala=1.0):
    """Pahat bidang datar: buang materi di sisi +normal bidang lewat `titik`, hanya di dalam kotak wilayah
    (pusat, setengah) dengan transisi halus `transisi` di batas wilayah. Menghasilkan tepi keras (gaya ukir).
    X, Y, Z boleh koordinat lokal kerangka; `skala` = mm per satuan lokal (jarak dikembalikan ke mm)."""
    n = np.asarray(normal, np.float32)
    n = n / np.linalg.norm(n)
    bidang = ((X - titik[0]) * n[0] + (Y - titik[1]) * n[1] + (Z - titik[2]) * n[2]) * skala
    w = np.clip(-kotak(X, Y, Z, pusat, setengah, 0.0) / max(transisi, 1e-3), 0.0, 1.0)
    return d + w * (np.maximum(d, bidang) - d)


def gabung(a, b, k):
    """Union halus (fillet ~k mm)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def kurang(a, b, k):
    """a dikurangi b (ukiran) dengan tepi halus ~k mm."""
    return -gabung(-a, b, k)


def ke_mesh(medan, asal, vox):
    """SDF (array [x, y, z]) -> (titik mm Nx3, quad Mx4) pada permukaan nol, orientasi normal keluar."""
    import openvdb
    g = openvdb.FloatGrid(float(medan.max()))
    g.copyFromArray(np.ascontiguousarray(medan, np.float32))
    titik, quad = g.convertToQuads(0.0)
    titik = np.asarray(titik, np.float64) * vox + np.asarray(asal, np.float64)
    quad = np.asarray(quad, np.int64)
    if volume(titik, quad) < 0:
        quad = quad[:, ::-1]
    return titik, quad


def segitiga(quad):
    q = np.asarray(quad)
    return np.vstack([q[:, [0, 1, 2]], q[:, [0, 2, 3]]]) if q.shape[1] == 4 else q


def volume(titik, muka):
    """Volume bertanda mesh tertutup (mm3) dan titik beratnya dari tetrahedron ke titik asal."""
    t = segitiga(muka)
    a, b, c = titik[t[:, 0]], titik[t[:, 1]], titik[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def titik_berat(titik, muka):
    t = segitiga(muka)
    a, b, c = titik[t[:, 0]], titik[t[:, 1]], titik[t[:, 2]]
    v = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    return ((a + b + c) / 4.0 * v[:, None]).sum(0) / v.sum()
