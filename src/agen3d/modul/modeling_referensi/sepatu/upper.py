"""Resep sepatu M2: UPPER dari data (referensi + panel proyek), non-generatif.

Dipanggil oleh sol.bangun_sepatu() (upper="m2"). Semua angka mm; konvensi data.py (X panjang dari ujung toe, +Y lateral,
Z dari tanah). Bentuk acuan S: bentuk.py; tali + jahitan: tali.py.

Struktur (C-A3: upper M1 bergelombang -> permukaan acuan S halus):
- S = permukaan luar acuan: loft penampang superelips per stasiun 1 mm dari siluet atas, plan, dan garis midsole yang
  DIHALUSKAN (Gauss). Data mentah bertangga (kuantisasi foto 0,23 mm/px) -> normal menekuk per stasiun = gelombang.
- Lapisan = offset S sepanjang normal (tidak ada dua permukaan berimpit, AM-13):
    upper (badan + lining)  : pejal, luar S-2,0
    panel_mesh (toe box/quarter/tumit): cangkang S-1,5..S-1,0
    overlay (mudguard, eyestay, overlay_tumit): cangkang S-0,7..S
    swoosh                   : cangkang S-0,7..S+0,3 (di atas mesh; tidak tumpang tindih dengan overlay)
  Panel = cangkang  ∩  prisma wilayah (poligon xz dari data, diekstrusi sepanjang Y per sisi).
- Bukaan kerah (lining gelap) + celah lidah dipotong dari atas; tepi kerah dipotong ke siluet atas data (AM-01).
- Lidah, 7 pasang lubang tali + eyelet, tali (tabung 2,5 mm, silang di atas lidah), jahitan putus-putus.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

from ..geometri import bevel_panel, boolean, cincin_loft, grid_loft, kotak_loft, mesh_obj, normal_vertex, salin, torus
from ..penyaring import smoothstep
from . import data
from .bentuk import (BUKAAN_X, CELAH_LIDAH, CELAH_PANEL, DALAM_CELAH, DALAM_LUBANG, DINDING_KERAH, KERAH_TURUN, LANGKAH,
                     LANTAI_BUKAAN, LAPIS, LEBAR_EYESTAY, LIDAH_TURUN, N_PASANG, R_LUBANG, TEPI_CELAH_TURUN, TERAKHIR,
                     Bentuk, garis_kerah)
from .tali import bangun_jahitan, bangun_tali


# ---------------- bangun upper M2 ----------------
def bangun_upper(ctx, mat, pk, halus=True, geser_swoosh_mm=0.0, swoosh_medial_dari_lateral=False,
                 geser_mudguard_mm=0.0, tali_turun_mm=0.0, n_pasang=None, geser_lubang_mm=0.0,
                 gap_lapis=True, panel_param=None):
    """Bangun semua bagian upper M2. Parameter selain default hanya untuk uji negatif QC."""
    B = Bentuk(ctx, halus)
    L = data.PANJANG
    xs = list(np.arange(0.0, ctx["x_last"], LANGKAH)) + [ctx["x_last"]] + list(np.linspace(ctx["x_last"], L, 4)[1:])
    if not halus:  # C-A3 negatif: stasiun 1 mm mentah (sama dengan blok M1)
        xs = list(np.unique(np.r_[np.arange(0.0, ctx["x_last"], 1.0), ctx["x_last"], np.linspace(ctx["x_last"], L, 4)]))
    cin = [[(x, y, z) for y, z in B.cincin(x)] for x in xs]
    V0, F0 = grid_loft(cin)
    N0, F0 = normal_vertex(V0, F0)
    tmp = bpy.data.collections.new("_tmp_m2")
    bpy.context.scene.collection.children.link(tmp)

    def permukaan(d):
        return V0 + N0 * d

    def cangkang(nama, d_in, d_out, koleksi):
        n = len(V0)
        V = np.vstack([permukaan(d_out), permukaan(d_in)])
        F = list(F0) + [tuple(i + n for i in f[::-1]) for f in F0]
        return mesh_obj(nama, V / 1000.0, F, koleksi, recalc=False)

    def pejal(nama, d, koleksi):
        return mesh_obj(nama, permukaan(d) / 1000.0, F0, koleksi)

    # ---- pemotong umum ----
    x_t0 = B.x_t0
    x_b0, x_b1 = (data.peta_x(v) for v in BUKAAN_X)
    w200 = B.w(x_b0)

    def h_bukaan(x):
        cy = B.plan(x)[0]
        y = B.y_sisi(x, B.zt(x), "lateral")
        if y is None:
            return 0.5
        hw = abs(y - cy) - DINDING_KERAH
        f = float(smoothstep(x_b0, x_b0 + 14.0, x))
        h = w200 + (hw - w200) * f
        R = 22.0
        if x > x_b1 - R:
            h *= math.sqrt(max(0.0, 1 - ((x - (x_b1 - R)) / R) ** 2))
        return max(h, 0.3)

    def lantai(x):
        if x < x_b0:
            return B.zt(x) - DALAM_CELAH
        return B.mt(x) + LANTAI_BUKAAN

    xs_cut = list(np.arange(x_t0, x_b0, 0.5)) + [x_b0 - 0.01] + list(np.arange(x_b0, x_b1 - 0.2, 0.5)) + [x_b1 - 0.2]

    def fy_cut(x):
        cy, _ = B.plan(x)
        h = B.w(x) if x < x_b0 else h_bukaan(x)
        h = max(h, 0.3)
        return cy - h, cy + h

    potong_atas = kotak_loft("_potong_atas", xs_cut, fy_cut, lambda x: (lantai(x), 400.0), tmp, mat["lining"])
    xs_full = list(np.arange(-5.0, L + 5.0, 0.5))

    xs0, xs1 = ctx["xs0"], ctx["xs1"]

    def klip(turun):
        def fz(x):
            k = B.k_kerah(x)
            # bawah: lapisan dipotong 3 mm di bawah garis midsole (tersembunyi) di dalam rentang sol; membuang dasar
            # kubah tempat offset ke dalam terlipat (AM-13). Di luar sol (toe, tumit belakang) tidak dipotong.
            akhir = xs1 + data.model("upper", "klip_akhir_mm", -1.5)  # AM90: sol sampai ujung tumit -> potong s.d. ujung
            bawah = B.mt(min(max(x, xs0), xs1)) - 3.0 if xs0 + 3 <= x <= akhir else -50.0
            return bawah, B.zt(min(max(x, 0.0), L)) + 0.3 * (1 - k) - turun * k
        return kotak_loft("_klip", xs_full, lambda x: (-200.0, 200.0), fz, tmp, mat["lining"])

    obs = {}
    # ---- badan upper (lining) ----
    up = pejal("upper", LAPIS["upper"][1], pk)
    up["lipat"] = True  # offset 1,8 mm masih terlipat sedikit di dasar toe/tumit (tersembunyi di midsole): self-intersection
    up.data.materials.append(mat["lining"])
    boolean(up, potong_atas, "DIFFERENCE", transfer=True)
    boolean(up, klip(0.0), "INTERSECT", hapus=True)
    obs["upper"] = up

    # ---- panel mesh (A) ----
    d_in, d_out = LAPIS["panel_mesh"]
    if not gap_lapis:  # negatif AM-13: lapisan mesh berimpit dengan overlay
        d_in, d_out = -0.7, 0.0
    pm = cangkang("panel_mesh", d_in, d_out, pk)
    pm["lipat"] = True
    pm.data.materials.append(mat["upper_mesh"])
    boolean(pm, potong_atas, "DIFFERENCE", transfer=True)
    klip_l = klip(KERAH_TURUN)
    boolean(pm, klip_l, "INTERSECT")
    obs["panel_mesh"] = pm

    lubang = {s: B.posisi_lubang(s, n_pasang, geser_lubang_mm) for s in ("lateral", "medial")}
    TERAKHIR["lubang"] = {s: [tuple(p) for p, _ in lubang[s]] for s in lubang}
    TERAKHIR["lubang_data"] = {s: B.lubang[s]["data"] for s in lubang}

    def e_bawah(x, sisi):
        cy = B.plan(x)[0]
        y = cy + (1 if sisi == "lateral" else -1) * (B.w(x) + LEBAR_EYESTAY)
        z = B.z_atas(x, y)
        return z if z is not None else B.param(x)[3]

    def wil_eyestay(sisi, dil=0.0):
        xl = [p.x for p, _ in lubang[sisi]]
        x0, x1 = max(min(xl) - 9.0, x_t0 + 1.0) - dil, max(xl) + 9.0 + dil
        R = 5.0
        xe = list(np.arange(x0, x1, 0.5)) + [x1]

        def fz(x):
            z = e_bawah(x, sisi) - dil
            for xc, d in ((x0 + R, x0 + R - x), (x1 - R, x - (x1 - R))):
                if d > 0:
                    z += R * (1 - math.sqrt(max(0.0, 1 - (d / R) ** 2)))
            return z, 400.0
        sgn = 1 if sisi == "lateral" else -1
        return kotak_loft(f"_wil_eyestay_{sisi}", xe,
                          lambda x: tuple(sorted((B.plan(x)[0], B.plan(x)[0] + sgn * 200.0))), fz, tmp)

    # lubang tali: silinder sepanjang normal
    def silinder(p, n, r, z0, z1, seg=20):
        a = Vector((1, 0, 0)) if abs(n.x) < 0.9 else Vector((0, 1, 0))
        u = n.cross(a).normalized()
        v = n.cross(u)
        V, F = [], []
        for z in (z0, z1):
            for j in range(seg):
                ang = 2 * math.pi * j / seg
                V.append(tuple(p + n * z + (u * math.cos(ang) + v * math.sin(ang)) * r))
        F = [(j, (j + 1) % seg, seg + (j + 1) % seg, seg + j) for j in range(seg)]
        F += [tuple(range(seg))[::-1], tuple(range(seg, 2 * seg))]
        return V, F

    Vh, Fh = [], []
    for sisi in lubang:
        for p, n in lubang[sisi]:
            V, F = silinder(p, n, R_LUBANG, -DALAM_LUBANG, 2.0)
            o = len(Vh)
            Vh += V
            Fh += [tuple(i + o for i in f) for f in F]
    lub = mesh_obj("_lubang", np.array(Vh) / 1000.0, Fh, tmp, mat["lining"])

    if data.KELAS is not None:  # Tugas 11: panel dari poligon data kelas warna (proyek.toml [[model.panel]])
        from .panel_data import bangun_panel_data
        obs.update(bangun_panel_data(B, cangkang, potong_atas, klip_l, lub, pk, tmp, mat, **(panel_param or {})))
        boolean(pm, lub, "DIFFERENCE", transfer=True)
        boolean(up, lub, "DIFFERENCE", transfer=True)
    else:  # resep AM1: panel dari garis data luma (mudguard, eyestay, overlay tumit, swoosh)
        # ---- cangkang overlay (B) bersama ----
        ov = cangkang("_overlay", *LAPIS["overlay"], tmp)
        ov.data.materials.append(mat["overlay_suede"])
        boolean(ov, potong_atas, "DIFFERENCE", transfer=True)
        boolean(ov, klip_l, "INTERSECT")

        xs_mid = ctx["mid"][:, 0]

        def bawah_panel(x):
            """Batas bawah panel: 2 mm di dalam midsole (tertanam, tidak terlihat); di depan sol = seluruh toe."""
            if x < xs_mid[0] + 2:
                return -20.0 + (B.mt(xs_mid[0]) - 2 + 20.0) * float(smoothstep(xs_mid[0] - 2, xs_mid[0] + 2, x))
            return B.mt(min(x, xs_mid[-1])) - 2.0

        # mudguard: z <= garis atas mudguard lateral (medial diasumsikan sama [D], seperti ekstrak_panel)
        mg = np.array(data.DATA["garis_mudguard_atas_lateral"], float)
        mud = lambda x: float(np.interp(x, mg[:, 0], mg[:, 1])) + geser_mudguard_mm
        potong_mud = kotak_loft("_wil_mudguard", xs_full, lambda x: (-200.0, 200.0),
                                lambda x: (bawah_panel(x), mud(x)), tmp)
        mud_ob = salin(ov, "mudguard", pk)
        mud_ob.data.materials.clear()
        mud_ob.data.materials.append(mat["mudguard"])
        mud_ob.data.materials.append(mat["lining"])
        boolean(mud_ob, potong_mud, "INTERSECT", hapus=True)
        obs["mudguard"] = mud_ob

        # eyestay per sisi
        for sisi in ("lateral", "medial"):
            es = salin(ov, f"eyestay_{sisi}", pk)
            boolean(es, wil_eyestay(sisi), "INTERSECT", hapus=True)
            boolean(es, lub, "DIFFERENCE", transfer=True)
            obs[f"eyestay_{sisi}"] = es
        boolean(pm, lub, "DIFFERENCE", transfer=True)
        boolean(up, lub, "DIFFERENCE", transfer=True)

        # overlay tumit/kerah: z >= garis C per sisi (garis_tepi), dikurangi wilayah eyestay (+ celah 0,4 mm)
        C = {s: garis_kerah(ctx["panel"][s]) for s in ("lateral", "medial")}
        c0 = max(C["lateral"][0][0], C["medial"][0][0])
        cyh = B.plan(285.0)[0]

        def fcin_kerah(x):
            zl = float(np.interp(x, *C["lateral"]))
            zm = float(np.interp(x, *C["medial"]))
            return [(-200.0, zm), (cyh - 2.0, zm), (cyh + 2.0, zl), (200.0, zl), (200.0, 400.0), (-200.0, 400.0)]

        wk = cincin_loft("_wil_kerah", list(np.arange(c0, L + 5.0, 0.5)), fcin_kerah, tmp)
        ot = salin(ov, "overlay_tumit", pk)
        boolean(ot, wk, "INTERSECT", hapus=True)
        for sisi in ("lateral", "medial"):
            boolean(ot, wil_eyestay(sisi, CELAH_PANEL), "DIFFERENCE", hapus=True)
        obs["overlay_tumit"] = ot

        # ---- swoosh per sisi ----
        swc = cangkang("_swoosh", *LAPIS["swoosh"], tmp)
        swc.data.materials.append(mat["swoosh"])
        for sisi in ("lateral", "medial"):
            sw = np.array(ctx["panel"]["medial" if sisi == "medial" and not swoosh_medial_dari_lateral else "lateral"]
                          ["swoosh"], float)
            xsw = sw[:, 0] + geser_swoosh_mm
            g = list(np.arange(xsw[0], xsw[-1], 0.25)) + [xsw[-1]]
            sgn = 1 if sisi == "lateral" else -1

            def fz(x, xsw=xsw, sw=sw):
                z0, z1 = float(np.interp(x, xsw, sw[:, 1])), float(np.interp(x, xsw, sw[:, 2]))
                if z1 - z0 < 0.1:
                    m = (z0 + z1) / 2
                    z0, z1 = m - 0.05, m + 0.05
                return z0, z1
            wsw = kotak_loft(f"_wil_swoosh_{sisi}", g, lambda x, sgn=sgn: tuple(sorted((B.plan(x)[0], B.plan(x)[0] + sgn * 200.0))),
                             fz, tmp)
            s_ob = salin(swc, f"swoosh_{sisi}", pk)
            boolean(s_ob, wsw, "INTERSECT", hapus=True)
            obs[f"swoosh_{sisi}"] = s_ob
            s_ob["poligon_data_x"] = [float(v) for v in xsw]

    # ---- lidah ----
    def lidah_top(x):
        f = float(smoothstep(data.peta_x(178.0), data.peta_x(192.0), x))
        return (B.zt(x) - TEPI_CELAH_TURUN - LIDAH_TURUN) * (1 - f) + B.zt(x) * f

    xl0 = x_t0 + 0.8
    xs_l = list(np.arange(xl0, x_b0 + 3.0, 0.5)) + [x_b0 + 3.0]
    z_lantai_celah = lambda x: B.zt(min(x, x_b0 - 0.01)) - DALAM_CELAH

    def fcin_lidah(x):
        cy, _ = B.plan(min(x, x_b0))
        hw = max(B.w(min(x, x_b0 - 0.01)) - CELAH_LIDAH, 0.3)
        zb, zt = z_lantai_celah(x) + 0.5, lidah_top(x)
        R_ujung = 0.45 * (zt - zb)  # punggung lidah membulat (bukan balok)
        x_end = xs_l[-1]
        if x > x_end - R_ujung:
            t = min((x - (x_end - R_ujung)) / R_ujung, 0.999)
            m_ = (zt + zb) / 2
            f = math.sqrt(1 - t * t)
            zt, zb = m_ + (zt - m_) * f, m_ - (m_ - zb) * f
        pts = []
        k = 1.5 / max(hw, 1.0) ** 2
        R = min(2.0, hw * 0.4, (zt - zb) * 0.3)
        for t in np.linspace(-1, 1, 15):  # atas melengkung
            y = t * (hw - R)
            pts.append((cy - y, zt - k * y * y))
        for t in np.linspace(0, math.pi / 2, 5)[1:]:
            pts.append((cy - (hw - R) - R * math.sin(t), zt - k * (hw - R) ** 2 - R + R * math.cos(t)))
        pts.append((cy - hw, zb))
        pts.append((cy + hw, zb))
        for t in np.linspace(math.pi / 2, 0, 5)[:-1]:
            pts.append((cy + (hw - R) + R * math.sin(t), zt - k * (hw - R) ** 2 - R + R * math.cos(t)))
        return pts[::-1]

    li = cincin_loft("lidah", xs_l, fcin_lidah, pk, mat["upper_mesh"])
    obs["lidah"] = li

    # ---- eyelet (aksen chrome; [model.lubang] eyelet = false: lubang tali tanpa ring logam, mis. AM90) ----
    Ve, Fe = [], []
    for sisi in lubang:
        for p, n in lubang[sisi]:
            V, F = torus(p + n * 0.55, n, R_LUBANG + 0.45, 0.45)
            o = len(Ve)
            Ve += V
            Fe += [tuple(i + o for i in f) for f in F]
    if data.model("lubang", "eyelet", True):
        obs["eyelet"] = mesh_obj("eyelet", np.array(Ve) / 1000.0, Fe, pk, mat["aksen_chrome"])

    # bersihkan pemotong
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp)
    bpy.context.view_layer.update()

    # ---- tali ----
    obs["tali"], info_tali = bangun_tali(B, lubang, obs, mat, pk, tali_turun_mm)
    # ---- jahitan ----
    if data.KELAS is not None:
        from .panel_data import bangun_jahitan_data
        jh = bangun_jahitan_data(B, obs, mat, pk)
        panel = [o for o in obs.values() if o.get("panel")]
        if jh is not None:
            obs["jahitan"] = jh
    else:
        obs["jahitan"] = bangun_jahitan(B, obs, mud, ctx, mat, pk)
        panel = [obs[k] for k in ("mudguard", "eyestay_lateral", "eyestay_medial", "overlay_tumit", "swoosh_lateral",
                                  "swoosh_medial")]
    bevel_panel(panel)
    for nama, ob in obs.items():
        for p in ob.data.polygons:
            p.use_smooth = nama not in ("jahitan",)
        # tepi potong boolean (90 derajat) tajam: normal halus tidak merembes ke permukaan panel (garis/belang)
        ob.data.set_sharp_from_angle(angle=math.radians(35))
    info = dict(lubang={s: [[round(v, 2) for v in p] for p, _ in lubang[s]] for s in lubang},
                lubang_data={s: B.lubang[s]["data"] for s in lubang}, x_celah=round(x_t0, 1),
                w_ref={k: round(v, 2) for k, v in B.w_ref.items()}, tali=info_tali,
                garis_kerah={s: [[float(a), round(float(b), 1)] for a, b in zip(*C[s])][::4] for s in C}
                if data.KELAS is None else {})
    return obs, B, info
