"""Resep sepatu M2: tali silang (criss-cross) + jahitan putus-putus dari tepi panel data."""
import math

import numpy as np
from mathutils import Vector

from ..geometri import bvh_dunia, catmull, mesh_obj, tabung
from .bentuk import CELAH_LIDAH, JAHIT, R_TALI, TERAKHIR

# ---------------- tali ----------------
def _atas_permukaan(bvh, x, y):
    hit = bvh.ray_cast(Vector((x, y, 400.0)), Vector((0, 0, -1)))
    return hit[0].z if hit[0] is not None else None


def _hull_atas(s, z):
    """Selubung cembung atas (tali tegang di atas rintangan): monotone chain, lalu interpolasi di s."""
    h = []
    for p in zip(s, z):
        while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) >= 0:
            h.pop()
        h.append(p)
    h = np.array(h)
    return np.interp(s, h[:, 0], h[:, 1])


def bangun_tali(B, lubang, obs, mat, pk, turun=0.0):
    """Tali silang (criss-cross) seperti sepatu asli: tiap lubang dilewati SATU kali. Palang depan L0 -> R0 (kedua
    ujung masuk lubang). Segmen silang muncul dari celah lidah (di bawah tepi eyestay, dekat lubang k sisi A), melintas
    tegang di atas lidah (selubung cembung atas permukaan + r + 0,5 mm), lalu masuk lubang k+1 sisi B sepanjang
    normalnya (2,2 mm). Segmen 'atas' melintas di atas segmen 'bawah' (rintangan lingkaran 2r + 0,4 mm)."""
    bvh = bvh_dunia(list(obs.values()))[0]
    Lp, Rp = lubang["lateral"], lubang["medial"]
    n = min(len(Lp), len(Rp))

    def celah(sisi, k):
        # tali yang masuk lubang k berjalan di bawah eyestay ke celah dan muncul ~4,5 mm ke arah lubang berikut
        # (tidak tepat di x lubang k: palang/segmen lain melintas di atas titik itu)
        p = (Lp if sisi == "lateral" else Rp)[k][0].copy()
        p.x += 0.35 * B.lubang[sisi]["jarak"]
        cy, _ = B.plan(p.x)
        sg = 1 if sisi == "lateral" else -1
        y = cy + sg * (B.w(p.x) - CELAH_LIDAH / 2)
        z_tepi = B.z_atas(p.x, cy + sg * B.w(p.x))
        return [Vector((p.x, y, z_tepi - 3.5)), Vector((p.x, y, z_tepi - 1.0)), Vector((p.x, y, z_tepi + R_TALI + 0.6))]

    seg = [(None, Lp[0], Rp[0], "palang")]
    for k in range(n - 1):
        seg.append((celah("lateral", k), None, Rp[k + 1], "bawah"))
    for k in range(n - 1):
        seg.append((celah("medial", k), None, Lp[k + 1], "atas"))
    jalur, bawah = [], []
    V, F = [], []
    for awal, la, (pb, nb), jenis in seg:
        if awal is None:
            pa, na = la
            awal = [pa - na * 2.2, pa - na * 0.8, pa + na * 0.6, pa + na * (R_TALI + 0.9)]
        a_top, b_top = awal[-1], pb + nb * (R_TALI + 2.2)  # masuk lubang lurus sepanjang sumbu (lewati eyelet)
        d = b_top - a_top
        dxy = Vector((d.x, d.y, 0)).length
        ss = np.linspace(0.0, 1.0, max(int(dxy / 0.5), 16))
        z = np.empty(len(ss))
        for i, s_ in enumerate(ss):
            p = a_top + d * s_
            zs = _atas_permukaan(bvh, p.x, p.y)
            z[i] = (zs if zs is not None else -1e3) + R_TALI + 0.8
            if jenis == "atas":
                for xyb, zb_ in bawah:
                    dist = np.hypot(xyb[:, 0] - p.x, xyb[:, 1] - p.y)
                    j = int(np.argmin(dist))
                    rr = 2 * R_TALI + 0.4
                    if dist[j] < rr:
                        z[i] = max(z[i], zb_[j] + math.sqrt(rr * rr - dist[j] ** 2))
        z[0], z[-1] = a_top.z, b_top.z
        z = _hull_atas(ss, z) - turun
        tengah = [Vector(((a_top + d * s_).x, (a_top + d * s_).y, zi)) for s_, zi in zip(ss, z)]
        if jenis in ("bawah", "palang"):
            bawah.append((np.array([(p.x, p.y) for p in tengah]), np.array([p.z for p in tengah])))
        kontrol = awal[:-1] + tengah + \
            [pb + nb * 2.0, pb + nb * 0.8, pb - nb * 0.6, pb - nb * 2.2]
        titik = catmull(kontrol, 2)
        jalur.append([tuple(p) for p in titik])
        Vt, Ft = tabung(titik, R_TALI)
        o = len(V)
        V += Vt
        F += [tuple(i + o for i in f) for f in Ft]
    ob = mesh_obj("tali", np.array(V) / 1000.0, F, pk, mat["tali"])
    TERAKHIR["jalur_tali"] = jalur  # garis tengah (mm) untuk QC AM-12
    return ob, dict(segmen=len(seg), pasang=n)


# ---------------- jahitan ----------------
def _offset_xz(poli, d, tertutup):
    """Offset polyline (x, z) sejauh d (positif = kiri arah jalan). Titik yang jaraknya ke garis asli < 0,85 d
    (lipatan di takik/ujung lancip) dibuang (None = putus)."""
    P = np.array(poli, float)
    n = len(P)
    nrm = np.zeros_like(P)
    for i in range(n):
        a = P[i - 1] if (i or tertutup) else P[i]
        b = P[(i + 1) % n] if (i < n - 1 or tertutup) else P[i]
        t = b - a
        L = np.hypot(*t)
        nrm[i] = (-t[1] / L, t[0] / L) if L > 1e-9 else (0, 0)
    Q = P + nrm * d
    seg = np.stack([P, np.roll(P, -1, 0)], 1)
    if not tertutup:
        seg = seg[:-1]
    out = []
    for q in Q:
        ab = seg[:, 1] - seg[:, 0]
        t = np.clip(((q - seg[:, 0]) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
        dist = np.hypot(*(seg[:, 0] + ab * t[:, None] - q).T).min()
        out.append(tuple(q) if dist >= 0.85 * abs(d) else None)
    return out


def _resample_xz(poli, langkah=0.25):
    out = [poli[0]]
    for a, b in zip(poli, poli[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        for k in range(1, max(int(L / langkah), 1) + 1):
            f = k / max(int(L / langkah), 1)
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def bangun_jahitan(B, obs, mud, ctx, mat, pk):
    """Jahitan putus-putus 1,5 mm di dalam tepi mudguard (atas) dan swoosh (keliling). C-A6: garis tepi data
    di-offset 1,5 mm di bidang xz (dinding samping hampir tegak: offset xz ~ offset di permukaan), lipatan di takik /
    ujung lancip dibuang, lalu tiap titik dipetakan ke S analitik pada sisinya (y dari tinggi z) dengan normal S
    (beda hingga). Versi BVH (kueri tepat di tepi panel) memberi dash acak di sepanjang tepi mudguard."""
    J = JAHIT
    V, F = [], []

    def titik_S(x, z, sisi, angkat):
        y = B.y_sisi(x, z, sisi)
        if y is None:
            return None
        p = Vector((x, y, z))
        ya, yb = B.y_sisi(x + 0.3, z, sisi), B.y_sisi(x, z + 0.3, sisi)
        if ya is None or yb is None:
            return None
        n = (Vector((0.3, ya - y, 0.0))).cross(Vector((0.0, yb - y, 0.3))).normalized()
        if (n.y > 0) != (sisi == "lateral"):
            n = -n
        return p + n * angkat, n

    def dash(titik):
        seg, acc, on, start, prev = [], 0.0, True, None, None
        for g in titik:
            if g is None:
                prev = None
                continue
            if prev is None:
                start, on, acc = g, True, 0.0
            else:
                acc += (g[0] - prev[0]).length
                if on and acc >= J["dash"]:
                    seg.append((start, g))
                    on, acc = False, 0.0
                elif not on and acc >= J["jeda"]:
                    on, acc, start = True, 0.0, g
            prev = g
        for (p0, n0), (p1, n1) in seg:
            t = (p1 - p0).normalized()
            n = (n0 + n1).normalized()
            u = n.cross(t).normalized()
            h, w = J["tebal"] / 2, J["lebar"] / 2
            kot = [c + u * su * w + n * sn * h for c in (p0, p1) for su, sn in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            o = len(V)
            V.extend(tuple(k) for k in kot)
            F.extend([(o, o + 1, o + 2, o + 3), (o + 7, o + 6, o + 5, o + 4), (o, o + 4, o + 5, o + 1),
                      (o + 1, o + 5, o + 6, o + 2), (o + 2, o + 6, o + 7, o + 3), (o + 3, o + 7, o + 4, o)])
        return len(seg)

    # mudguard: garis atas (toe -> tumit), offset ke bawah (kanan arah jalan = -d)
    mg = np.array(M_DATA_MUD(ctx, mud))
    garis = _offset_xz(_resample_xz([tuple(p) for p in mg], 0.5), -J["offset"], False)
    n_mud = 0
    for sisi in ("lateral", "medial"):
        n_mud += dash([None if q is None else titik_S(q[0], q[1], sisi, 0.1) for q in garis])
    # swoosh: poligon tertutup (bawah toe->tumit, atas tumit->toe = berlawanan jarum jam) -> dalam = kiri
    n_sw = 0
    for sisi in ("lateral", "medial"):
        ob = obs[f"swoosh_{sisi}"]
        sw = np.array(ctx["panel"][sisi]["swoosh"], float)
        xsw = np.array(ob["poligon_data_x"])
        poli = [(x, z) for x, z in zip(xsw, sw[:, 1])] + [(x, z) for x, z in zip(xsw[::-1], sw[::-1, 2])]
        poli = _resample_xz(poli + [poli[0]], 0.25)[:-1]
        garis = _offset_xz(poli, J["offset"], True)
        n_sw += dash([None if q is None else titik_S(q[0], q[1], sisi, 0.3 + 0.1) for q in garis])
    ob = mesh_obj("jahitan", np.array(V) / 1000.0, F, pk, mat["tali"])
    ob["dash_mudguard"], ob["dash_swoosh"] = n_mud, n_sw
    return ob


def M_DATA_MUD(ctx, mud):
    """Garis atas mudguard (x, z) dari toe ke tumit pada x data."""
    return [(x, mud(x)) for x in np.arange(12.36, 292.0, 0.5)]
