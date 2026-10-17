"""Geometri produk uji: lathe profil (putar_profil), profil per produk, pelat, penampang non-lingkaran.
Semua profil dalam mm (r, z) dari spesifikasi.SPEC."""
import math

import bpy

def putar_profil(nama, profil, seg=96, modulasi=None, penampang=None, uv_busur=True):
    """Lathe: profil (r_mm, z_mm) diputar di sumbu Z. Titik r=0 menjadi satu vertex di sumbu.
    penampang(t, r, z) -> (x_mm, y_mm): penampang non-lingkaran (kotak membulat, tube pipih); default lingkaran.
    C-13: pada penampang non-lingkaran, u label = panjang busur dari depan / keliling (bukan sudut), sehingga logo
    selebar tetap di permukaan (tube yang memipih tidak membuat logo trapesium)."""
    vs, cincin, busur = [], [], {}
    for r, z in profil:
        if r == 0:
            cincin.append([len(vs)])
            vs.append((0.0, 0.0, z / 1000))
            continue
        idx = []
        for k in range(seg):
            t = 2 * math.pi * k / seg
            if penampang:
                x, y = penampang(t, r, z)
            else:
                rr = r * (modulasi(t, z) if modulasi else 1.0)
                x, y = rr * math.cos(t), rr * math.sin(t)
            idx.append(len(vs))
            vs.append((x / 1000, y / 1000, z / 1000))
        cincin.append(idx)
        if penampang and uv_busur:  # sudut semu = 2 pi x (busur dari depan, t = 270 derajat) / keliling
            L = [0.0]
            for k in range(1, seg + 1):
                (x0, y0, _), (x1, y1, _) = vs[idx[k - 1]], vs[idx[k % seg]]
                L.append(L[-1] + math.hypot(x1 - x0, y1 - y0))
            P, kf = L[-1], 3 * seg // 4
            for k in range(seg):
                d = (L[k] - L[kf]) / P
                busur[idx[k]] = 2 * math.pi * (d - round(d))
    fs = []
    for a, b in zip(cincin, cincin[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            fs += [(a[0], b[(k + 1) % seg], b[k]) for k in range(seg)]  # urutan dibalik: normal keluar (bawah)
        elif len(b) == 1:
            fs += [(a[k], a[(k + 1) % seg], b[0]) for k in range(seg)]
        else:
            fs += [(a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]) for k in range(seg)]
    me = bpy.data.meshes.new(nama)
    me.from_pydata(vs, [], fs)
    me.validate()
    # UV label: u = 0,5 + sudut/(2 pi) dengan sudut 0 di depan (-Y), v = tinggi (m). Logo ikut mesh saat ekspor/impor.
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        pc = poly.center
        sc_ = math.atan2(pc.x, -pc.y)
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            vi = me.loops[li].vertex_index
            a = sc_ if math.hypot(co.x, co.y) < 1e-9 else busur.get(vi, math.atan2(co.x, -co.y))
            a += 2 * math.pi * round((sc_ - a) / (2 * math.pi))  # buka jahitan di belakang
            uv.data[li].uv = (0.5 + a / (2 * math.pi), co.z)
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(35))
    return me


def profil_kaleng(s):
    H, R = s["tinggi_mm"], s["diameter_mm"] / 2
    rc, rp, k = s["cincin_dasar_mm"] / 2, s["plug_mm"] / 2, s["kubah_mm"]
    zb = H - s["leher_mm"]  # akhir badan lurus
    # leher: kaleng standard menyempit 6,9 mm (2 titik); kaleng slim 202 hanya 1,7 mm (1 titik, tetap menurun)
    leher = [(R - 1.2, zb + 4), (rp + 3.5, zb + 9.5)] if R - rp > 5 else [(R - 0.6, zb + 4)]
    return [(0, k), (rc - 5, 3.0), (rc - 1.2, 0.5), (rc, 0), (rc + 1.4, 0.6), (R - 3.5, 4.5), (R - 0.8, 8.5),
            (R, 11.0), (R, zb)] + leher + [(rp + 0.9, H - 4.2),
            (rp + 0.8, H - 2.2), (rp + 1.6, H - 0.6), (rp + 1.4, H), (rp + 0.2, H),  # bibir sambungan tutup [D]
            (rp - 0.4, H - 5.8), (rp - 1.6, H - 6.3), (0, H - 6.0)]  # panel tutup cekung [D]


def profil_botol(s):
    H, R, rf = s["tinggi_mm"], s["diameter_mm"] / 2, s["crown_mm"] / 2
    zb, zl = s["tinggi_badan_mm"], s["tinggi_leher_mm"]
    rl = rf - 0.6  # leher sedikit lebih kecil dari finish crown
    return [(0, 3.0), (R - 7, 0.9), (R - 4, 0), (R - 1.2, 1.2), (R, 4.5), (R, zb),
            (R - 1.5, zb + 10), (R - 6.5, zb + 24), (rl + 6.5, zb + 38), (rl + 1.5, zl - 4), (rl, zl),
            (rl, H - 12), (rf + 0.3, H - 10.5), (rf + 0.3, H - 7.5), (rf - 0.2, H - 6.5),
            (rf, H - 3), (rf - 0.6, H), (0, H)]


def profil_botol_dalam(s):
    """Dinding dalam kaca (turun dari mulut ke dasar). C-11: botol berongga, bukan kaca pejal."""
    H, R, rl = s["tinggi_mm"], s["diameter_mm"] / 2, s["crown_mm"] / 2 - 0.6
    zb, zl, t = s["tinggi_badan_mm"], s["tinggi_leher_mm"], s["dinding_mm"]
    bore = s["crown_mm"] / 2 - 4.2  # lubang mulut [D]
    return [(bore, H), (bore, H - 9.0), (rl - t, H - 12), (rl - t, zl), (rl + 1.5 - t, zl - 4),
            (rl + 6.5 - t, zb + 38), (R - 6.5 - t, zb + 24), (R - 1.5 - t, zb + 10), (R - t, zb),
            (R - t, 9.0), (R - 5.0, 6.6), (R - 10.0, 6.0), (0, 6.2)]


def cairan_dari(dalam, zi, celah=0.15, z_dasar=10.0):
    """Isi (cairan/selai) mengikuti dinding dalam `dalam` (turun, berakhir di (0, z) dasar) dengan celah tipis
    sampai tinggi `zi`. Radius permukaan diinterpolasi pada segmen dinding yang memotong `zi`."""
    naik = [(r, z) for r, z in reversed(dalam) if 0 < r]
    z0 = dalam[-1][1]
    p = [(0, z0 + celah)] + [(r - celah, z + (celah if z < z_dasar else 0)) for r, z in naik if z < zi]
    (ra, za), (rb, zb) = next((a, b) for a, b in zip(naik, naik[1:]) if a[1] < zi <= b[1])
    r_isi = ra + (rb - ra) * (zi - za) / (zb - za)
    return p + [(r_isi - celah, zi), (0, zi)]


def profil_cairan(s, celah=0.15):
    """Cairan botol mengikuti dinding dalam (celah tipis) sampai `isi_mm`."""
    return cairan_dari(profil_botol_dalam(s), s["isi_mm"], celah)


def pelat(nama, luar, dalam, z0, tebal):
    """Pelat datar (mm) dari loop luar & loop lubang (jumlah titik sama), tebal ke atas dari z0."""
    n = len(luar)
    vs = [(x / 1000, y / 1000, (z0 + dz) / 1000) for dz in (tebal, 0.0) for x, y in luar + dalam]
    lt, li, bt, bi = 0, n, 2 * n, 3 * n  # luar-atas, dalam-atas, luar-bawah, dalam-bawah
    fs = []
    for k in range(n):
        j = (k + 1) % n
        fs += [(lt + k, lt + j, li + j, li + k), (bt + k, bi + k, bi + j, bt + j),
               (bt + k, bt + j, lt + j, lt + k), (bi + k, li + k, li + j, bi + j)]
    me = bpy.data.meshes.new(nama)
    me.from_pydata(vs, [], fs)
    me.validate()
    return me


def tab_kaleng(s, n=48):
    """Pull-tab + rivet di panel tutup (C-12: kaleng tanpa tab terbaca seperti cangkir terbuka). Ukuran [D]."""
    H = s["tinggi_mm"]
    sg = lambda v, e: math.copysign(abs(v) ** e, v)
    luar = [(6.0 * sg(math.cos(t), 0.5), 1.0 + 9.5 * sg(math.sin(t), 0.5))
            for t in (2 * math.pi * k / n for k in range(n))]
    dalam = [(3.6 * math.cos(t), 5.6 + 3.2 * math.sin(t)) for t in (2 * math.pi * k / n for k in range(n))]
    z0 = H - 5.95  # tepat di atas panel cekung (panel H-6.0 di tengah s.d. H-6.3 di tepi)
    tab = pelat("kaleng_tab", luar, dalam, z0, 0.6)
    rivet = putar_profil("kaleng_rivet", [(1.9, z0 + 0.6), (1.8, z0 + 0.9), (1.0, z0 + 1.25), (0, z0 + 1.3)], seg=32)
    return tab, rivet


def profil_tutup(s):
    H, rt = s["tinggi_mm"], s["tutup_mm"] / 2
    return [(0, H + 0.6), (rt - 1.2, H + 0.6), (rt - 0.2, H - 0.3), (rt, H - 6.0), (rt - 2.3, H - 6.0), (0, H - 6.0)]


def _sg(v, e):
    return math.copysign(abs(v) ** e, v)


def superelips(a, b, n=10.0):
    """Penampang kotak membulat |x/a|^n + |y/b|^n = 1 (mm), diskalakan r (0..1). Sisi rata, sudut membulat."""
    return lambda t, r, z: (r * a * _sg(math.cos(t), 2 / n), r * b * _sg(math.sin(t), 2 / n))


def profil_kotak(s):
    """Kotak karton: skala penampang (0..1) per tinggi; tepi bawah/atas dibevel 1 mm. Sirip seal di atasnya."""
    H = s["tinggi_mm"] - s["sirip_mm"]
    return [(0, 0), (0.96, 0), (1.0, 1.0), (1.0, H - 1.0), (0.96, H), (0, H)]


def tube_ab(s, z):
    """Semi-sumbu penampang tube (a di X, b di Y; mm) di tinggi z: bulat dekat tutup, pipih ke seal di atas.
    Keliling dijaga (a -> setengah lebar seal = pi R / 2, b -> setengah tebal seal)."""
    R, Hc, H = s["diameter_mm"] / 2, s["tutup_tinggi_mm"], s["tinggi_mm"]
    z1, z2 = Hc + 25.0, H - s["seal_mm"]
    t = min(1.0, max(0.0, (z - z1) / (z2 - z1)))
    f = t * t * (3 - 2 * t)
    return R + (s["lebar_mm"] / 2 - R) * f, R + (s["seal_tebal_mm"] / 2 - R) * f


def profil_tube(s):
    """Badan tube (r mm = radius penampang bulat; dipipihkan oleh tube_ab) dari bahu di atas tutup sampai seal."""
    R, Hc, H = s["diameter_mm"] / 2, s["tutup_tinggi_mm"], s["tinggi_mm"]
    badan = [(R, Hc + 4.0 + k * (H - Hc - 4.0) / 40) for k in range(41)]
    return [(0, Hc), (R - 6.0, Hc), (R - 1.5, Hc + 1.2)] + badan + [(0, H)]


def penampang_tube(s):
    R = s["diameter_mm"] / 2

    def f(t, r, z):
        a, b = tube_ab(s, z)
        return r / R * a * math.cos(t), r / R * b * math.sin(t)
    return f


def profil_flip_top(s):
    R, Hc = s["tutup_mm"] / 2, s["tutup_tinggi_mm"]
    return [(0, 0), (R - 1.5, 0), (R - 0.3, 0.6), (R, 2.0), (R, Hc - 1.0), (R - 0.6, Hc), (0, Hc)]


def profil_jar(s):
    """Jar kaca: dinding luar naik (dasar -> bibir) lalu dinding dalam turun. Berongga (C-11/QC-11)."""
    H, R, rf, t = s["tinggi_mm"], s["diameter_mm"] / 2, s["finish_mm"] / 2, s["dinding_mm"]
    zb = H - 22.0  # akhir badan lurus [D]
    luar = [(0, 2.5), (R - 7.0, 0.8), (R - 3.5, 0), (R - 0.8, 1.5), (R, 5.0), (R, zb), (R - 2.5, zb + 6.0),
            (rf + 2.0, zb + 11.0), (rf, zb + 12.5), (rf, H - 1.0), (rf - 0.6, H)]
    dalam = [(rf - t, H), (rf - t, zb + 12.5), (R - 2.5 - t, zb + 6.0), (R - t, zb), (R - t, 5.0 + t),
             (R - 4.0, t + 1.5), (R - 9.0, t + 1.0), (0, t + 2.0)]
    return luar, dalam


def profil_tutup_lug(s):
    H, rt, ht, naik = s["tinggi_mm"], s["tutup_mm"] / 2, s["tutup_tinggi_mm"], s["tutup_naik_mm"]
    za, zb = H + naik, H + naik - ht
    return [(0, za), (rt - 1.5, za), (rt - 0.3, za - 0.5), (rt, za - 1.5), (rt, zb), (rt - 1.5, zb), (0, zb)]


def profil_pet(s):
    """Botol PET: dinding badan tipis (0,35 mm), leher preform tebal; alur dekoratif + support ring. Berongga."""
    H, R, rf, t = s["tinggi_mm"], s["diameter_mm"] / 2, s["finish_mm"] / 2, s["dinding_mm"]
    rn = rf - 0.2  # leher di bawah ulir [D]
    badan = [(R, 6.0), (R, 130.0), (R - 1.8, 133.0), (R, 136.0), (R - 1.8, 139.0), (R, 142.0), (R - 3.0, 150.0),
             (R - 12.0, 163.0), (rn + 3.0, 174.0), (rn, 177.0)]
    leher = [(rn, 178.5), (rf + 3.1, 179.0), (rf + 3.1, 180.5), (rf, 181.0), (rf, H - 0.6), (rf - 0.6, H)]
    bore = rf - 2.9  # [D] leher preform tidak ditiup
    luar = [(0, 3.5), (R - 8.0, 1.2), (R - 5.0, 0), (R - 1.5, 1.5)] + badan + leher
    dalam = [(bore, H), (bore, 177.0)] + [(r - t, z) for r, z in reversed(badan[1:-1])] + [
        (R - t, 6.0), (R - 1.8, 1.5 + t), (R - 5.0, t), (R - 8.0, 1.2 + t), (0, 3.5 + t)]
    return luar, dalam


def profil_tutup_pet(s):
    H, rt, ht, naik = s["tinggi_mm"], s["tutup_mm"] / 2, s["tutup_tinggi_mm"], s["tutup_naik_mm"]
    za, zb = H + naik, H + naik - ht
    return [(0, za), (rt - 1.0, za), (rt - 0.2, za - 0.6), (rt, za - 2.0), (rt, zb), (rt - 1.2, zb), (0, zb)]
