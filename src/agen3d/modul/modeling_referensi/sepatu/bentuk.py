"""Resep sepatu M2: parameter upper [D] + bentuk acuan S (class Bentuk) + garis kerah dari garis_tepi panel."""
import math

import numpy as np
from mathutils import Vector

from ..penyaring import gauss, smoothstep
from . import data
from .sol import BENGKAK, UPPER_MASUK

px = data.peta_x  # posisi AM1 -> sepatu proyek (identitas untuk AM1)

# ---------------- parameter [D] (pilihan modeling, bukan data) ----------------
N_CINCIN = 64            # titik per penampang S
LANGKAH = 1.0            # mm antar stasiun S
# Gauss (mm). Siluet atas data berisi riak 8-16 mm setinggi ~0,4 mm (tekstur mesh/kerut di foto) selain tangga
# kuantisasi 0,23 mm/px: sigma 2 mm masih menyisakan riak 2,5-3 derajat (AM-09). Lidah/kerah (x >= 188) tetap 2 mm
# agar puncak lidah dan lekuk kerah tidak tumpul.
SIGMA_ATAS = 5.0
SIGMA_ATAS_KERAH = 2.0
SIGMA_MID = 5.0          # garis midsole (hanya untuk penampang upper; midsole M1 tetap data mentah)
SIGMA_PLAN = 4.0         # plan (hanya upper)
LAPIS = {                # (dalam, luar) offset dari S, mm
    "upper": (None, -2.0),
    "panel_mesh": (-1.5, -1.0),
    "overlay": (-0.7, 0.0),
    "swoosh": (-0.7, 0.3),
}
KERAH_TURUN = 2.5        # lapisan panel berhenti 2,5 mm di bawah bibir kerah (pita kerah = badan upper, lining)
DINDING_KERAH = 6.0      # tebal dinding kerah (dari luar S ke dinding dalam bukaan)
BUKAAN_X = (200.0, 283.0)  # bukaan kaki [D]: depan (belakang lidah) s.d. dalam counter tumit
LANTAI_BUKAAN = 4.0      # lantai bukaan (insole) = garis midsole + 4 mm
DALAM_CELAH = 10.0       # celah lidah: dasar = siluet atas - 10 mm
OVERSHOOT_KERAH = 12.0   # S di daerah kerah dibuat lebih tinggi lalu dipotong tepat ke siluet atas (dinding tegak)
E_ATAS, E_ATAS_KERAH, E_BAWAH = 2.4, 4.0, 2.2  # E_BAWAH M1 = 4 (sudut bawah tajam, lihat DASAR_DALAM)
DASAR_DALAM = 8.0        # dasar upper di bawah garis midsole (tersembunyi di dalam midsole)
N_PASANG = 7             # [D] AM1: 6-7 pasang
LUBANG_KE_TEPI = 7.0     # pusat lubang ke tepi celah (eyestay) [D]
LEBAR_EYESTAY = 14.0     # lebar pita eyestay dari tepi celah (proyeksi Y) [D]
KEMIRINGAN_CELAH = 0.15  # setengah lebar celah bertambah 0,15 mm per mm ke arah kerah [D]
R_LUBANG, DALAM_LUBANG = 2.0, 4.0
R_TALI = 1.25            # tali 2,5 mm
TEPI_CELAH_TURUN = 4.5   # tepi eyestay di bawah siluet atas: siluet throat = tali yang melintas di atasnya
                         # (tali bawah ~ tepi + 3,2 mm, persilangan ~ tepi + 6,1 mm; rata-rata ~ siluet data)
LIDAH_TURUN = 1.0        # puncak lidah (tengah) di bawah tepi eyestay; lengkung melintang 1,5 mm
CELAH_LIDAH = 3.5        # celah lidah-eyestay: tali silang muncul dari sini (tali 2,5 mm + 2 x 0,5 mm)
TERAKHIR = {}            # data bangun terakhir untuk QC (jalur tali, lubang)
JAHIT = dict(offset=1.5, dash=3.0, jeda=1.6, lebar=0.6, tebal=0.35)
CELAH_PANEL = 0.4        # jarak antar panel selapis (mis. overlay_tumit vs eyestay)


# ---------------- garis C (overlay tumit/kerah) dari garis_tepi ----------------
def garis_kerah(panel_sisi):
    """AM-D04: garis tepi bawah overlay kerah/tumit = komponen terbesar `garis_tepi` (8-tetangga, grid 1 mm;
    satu-satunya komponen >= 100 mm), median z per kolom, lalu median 5 + Gauss 3 mm. Derau tekstur mesh tumit
    (x > 270) ikut teredam oleh median."""
    pts = set(map(tuple, np.array(panel_sisi["garis_tepi"], int)))
    sisa, terbesar = set(pts), []
    while sisa:
        q = sisa.pop()
        st, komp = [q], [q]
        while st:
            x, z = st.pop()
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    n = (x + dx, z + dz)
                    if n in sisa:
                        sisa.remove(n)
                        st.append(n)
                        komp.append(n)
        if len(komp) > len(terbesar):
            terbesar = komp
    c = np.array(terbesar, float)
    xs = np.unique(c[:, 0])
    z = np.array([np.median(c[c[:, 0] == x, 1]) for x in xs])
    zm = np.array([np.median(z[max(0, i - 2):i + 3]) for i in range(len(z))])
    g, zh = gauss(xs, zm, 3.0, 1.0)
    return g, zh


# ---------------- bentuk acuan S ----------------
class Bentuk:
    """Fungsi penampang upper per x. halus=False = input mentah (uji negatif C-A3, sama dengan blok M1)."""

    def __init__(self, ctx, halus=True):
        self.halus = halus
        self.ctx = ctx  # dari sol.bangun: xs_s, zb_raw, zt_raw, x_last, xs0, xs1, mt (fungsi mentah)
        xs, zb, zt = ctx["xs_s"], ctx["zb_raw"], ctx["zt_raw"]
        s_atas, s_mid, s_plan = (SIGMA_ATAS, SIGMA_MID, SIGMA_PLAN) if halus else (0, 0, 0)
        self.g_zt, self.v_zt = gauss(xs, zt, s_atas)
        if halus:  # sigma 5 hanya di vamp/toe box; ujung toe (siluet berubah cepat) dan lidah/kerah sigma 2
            _, v2 = gauss(xs, zt, SIGMA_ATAS_KERAH)
            f = np.maximum(smoothstep(px(176.0), px(188.0), self.g_zt), 1 - smoothstep(px(16.0), px(28.0), self.g_zt))
            self.v_zt = self.v_zt * (1 - f) + v2 * f
        self.g_zb, self.v_zb = gauss(xs, zb, SIGMA_ATAS_KERAH if halus else 0)
        mid = ctx["mid"]
        self.g_mt, self.v_mt = gauss(mid[:, 0], mid[:, 1], s_mid)
        gp = np.arange(0.0, data.PANJANG + 1e-9, 0.5)
        cy, a = np.array([data.plan_y(x) for x in gp]).T
        self.g_p, self.v_cy = gauss(gp, cy, s_plan)
        _, self.v_a = gauss(gp, a, s_plan)
        self.tambah = ctx["midsole_tambah"]
        self.w_ref = {"lateral": 17.0, "medial": 17.0}
        self.lubang = {}
        self.x_t0 = px(88.0)
        self._tab = None
        for _ in range(3):  # celah (w) bergantung pada delta, delta pada w: iterasi tetap
            if halus:
                self.siapkan_tabel()
            self._siapkan_lubang()
        if halus:
            self.siapkan_tabel()

    # --- fungsi dasar (mentah atau halus) ---
    def zt(self, x):
        return float(np.interp(x, self.g_zt, self.v_zt))

    def zb(self, x):
        return float(np.interp(x, self.g_zb, self.v_zb))

    def mt(self, x):
        return float(np.interp(x, self.g_mt, self.v_mt)) + self.tambah

    def plan(self, x):
        return float(np.interp(x, self.g_p, self.v_cy)), float(np.interp(x, self.g_p, self.v_a))

    def k_kerah(self, x):
        return float(smoothstep(px(196.0), px(202.0), x))

    # --- celah lidah ---
    def w_lin(self, x):
        """w tanpa pembulatan ujung depan celah (untuk koreksi tinggi kubah yang halus)."""
        wr = np.mean(list(self.w_ref.values()))
        return max(wr + KEMIRINGAN_CELAH * (min(x, px(196.0)) - px(153.0)), 0.0)

    def w(self, x, sisi=None):
        """Setengah lebar celah lidah (tepi eyestay) dari garis tengah plan. Dikalibrasi agar lubang tali model jatuh
        di z lubang data (2 lubang besar per sisi), kemiringan [D]."""
        wr = np.mean(list(self.w_ref.values())) if sisi is None else self.w_ref[sisi]
        v = wr + KEMIRINGAN_CELAH * (min(x, px(196.0)) - px(153.0))
        R0 = 6.0
        if x < self.x_t0 + R0:
            v *= math.sqrt(max(0.0, 1 - ((self.x_t0 + R0 - x) / R0) ** 2))
        return max(v, 0.0)

    def param(self, x, delta=True):
        """(cy, a, zlo, zw, zhi, e_bawah, e_atas) penampang S di x (mm). Mode halus: tiap kanal dihaluskan lagi
        sepanjang x (Gauss 2 mm), karena pergantian 'di sol' -> 'di luar sol' di tumit (x 284-290) membuat zlo
        berbentuk V tajam: offset lapisan ke dalam >= 1 mm terlipat di sana (boolean gagal, AM-13)."""
        if self.halus and delta and getattr(self, "_tab", None) is not None:
            g, T = self._tab
            return tuple(float(np.interp(x, g, T[:, i])) for i in range(8))
        return self._param(x, delta)

    def siapkan_tabel(self):
        self._tab = None
        g = np.arange(0.0, data.PANJANG + 1e-9, 0.25)
        T = np.array([self._param(x) for x in g])
        r = int(math.ceil(3 * 2.0 / 0.25))
        k = np.exp(-0.5 * (np.arange(-r, r + 1) * 0.25 / 2.0) ** 2)
        k /= k.sum()
        for i in range(1, 8):
            T[:, i] = np.convolve(np.pad(T[:, i], r, mode="edge"), k, "valid")
        self._tab = (g, T)

    def _param(self, x, delta=True):
        c = self.ctx
        x_last, xs0, xs1, L = c["x_last"], c["xs0"], c["xs1"], data.PANJANG
        zb, zt = self.zb(x), self.zt(x)
        cy, a = self.plan(x)
        if x > x_last:  # ekor 1 px (sama dengan M1)
            f = 1 - 0.9 * (x - x_last) / (L - x_last)
            m = (zb + zt) / 2
            zb, zt = m - (m - zb) * f, m + (zt - m) * f
            a *= f
        di_sol = xs0 <= x <= xs1
        wb = float(np.clip(min(x - xs0, xs1 - x) / 6.0, 0, 1)) if di_sol else 0.0
        if di_sol:
            m = self.mt(x)
            # mode halus: dasar upper 8 mm di dalam midsole (M1: 4 mm). Separuh bawah setebal 5,5 mm x lebar 70 mm
            # punya jari-jari lengkung ujung ~0,9 mm < offset lapisan 1,8 mm -> terlipat (C-A3); 9,5 mm -> ~2,6 mm
            zlo_s = max(m - DASAR_DALAM, zb + 7.0) if self.halus else max(m - 4.0, zb + 1.0)
            zw_s, a_s = m + 1.5, a * (1 - BENGKAK) - UPPER_MASUK
        else:
            zlo_s, zw_s, a_s = zb, zb, a
        zlo = zb + wb * (zlo_s - zb)
        zw = max(zb + 0.3 * (zt - zb) + wb * (zw_s - (zb + 0.3 * (zt - zb))), zlo + 0.2)
        aa = a + wb * (a_s - a)
        zw = min(zw, zt - 0.5)
        # kerah: S dibuat lebih tinggi & lebih kotak lalu dipotong ke siluet atas (dinding kerah tegak). Transisi
        # panjang (x 186-208, 22 mm) agar dinding samping tidak menekuk (AM-09: transisi 6 mm = lipatan 17-20 derajat).
        # Mulai di belakang eyestay (lubang terakhir + 9 mm ~ 188), jadi tidak bertabrakan dengan koreksi tepi celah.
        k = float(smoothstep(px(186.0), px(208.0), x)) * (1 - float(smoothstep(px(284.0), px(290.0), x)))
        e_t = E_ATAS + (E_ATAS_KERAH - E_ATAS) * k
        zhi = zt + OVERSHOOT_KERAH * k
        dl = 0.0
        if delta and self.x_t0 < x < px(192.0):
            # tepi celah (y = w) TEPI_CELAH_TURUN di bawah siluet atas: siluet samping throat = tali yang melintas
            # di atas tepi eyestay. Koreksi hanya di puncak kubah (benjolan (1-u^2)^2), dinding samping tidak berubah.
            w = self.w_lin(x)
            if 0 < w < aa:
                u = w / aa
                zbase = zw + (zhi - zw) * self._g(u, e_t)
                dl = (zt - TEPI_CELAH_TURUN - zbase) / (1 - u * u) ** 2
                dl *= float(smoothstep(self.x_t0, self.x_t0 + 12.0, x)) * (1 - float(smoothstep(px(182.0), px(192.0), x)))
        return cy, aa, zlo, zw, zhi, (E_BAWAH if self.halus else 4.0), e_t, dl

    @staticmethod
    def _g(u, e):
        c = u ** (e / 2)
        return math.sqrt(max(1 - c * c, 0.0)) ** (2 / e)

    @staticmethod
    def _zu(u, zw, zhi, et, dl):
        return zw + (zhi - zw) * Bentuk._g(u, et) + dl * (1 - u * u) ** 2

    def z_atas(self, x, y):
        """Tinggi S separuh atas di (x, y)."""
        cy, a, zlo, zw, zhi, eb, et, dl = self.param(x)
        u = abs(y - cy) / a
        if u >= 1:
            return None
        return self._zu(u, zw, zhi, et, dl)

    def y_sisi(self, x, z, sisi):
        """Titik S separuh atas pada tinggi z di sisi lateral (+Y) / medial (-Y): perpotongan terluar (bisection)."""
        cy, a, zlo, zw, zhi, eb, et, dl = self.param(x)
        uu = np.linspace(0.0, 1.0, 401)
        zz = np.array([self._zu(u, zw, zhi, et, dl) for u in uu])
        i = np.nonzero(zz >= z)[0]
        if not len(i) or i[-1] == len(uu) - 1 or z < zw:
            return None
        lo, hi = uu[i[-1]], uu[i[-1] + 1]
        for _ in range(30):
            m = (lo + hi) / 2
            lo, hi = (m, hi) if self._zu(m, zw, zhi, et, dl) >= z else (lo, m)
        return cy + (1 if sisi == "lateral" else -1) * a * (lo + hi) / 2

    def normal_atas(self, x, y, h=0.05):
        dzx = (self.z_atas(x + h, y) - self.z_atas(x - h, y)) / (2 * h)
        dzy = (self.z_atas(x, y + h) - self.z_atas(x, y - h)) / (2 * h)
        return Vector((-dzx, -dzy, 1.0)).normalized()

    def cincin(self, x, n=N_CINCIN):
        cy, a, zlo, zw, zhi, eb, et, dl = self.param(x)
        pts = []
        for t in np.linspace(-math.pi / 2, 3 * math.pi / 2, n, endpoint=False):
            c, s = math.cos(t), math.sin(t)
            e = et if s > 0 else eb
            y = a * math.copysign(abs(c) ** (2 / e), c)
            z = zw + (zhi - zw if s > 0 else zw - zlo) * math.copysign(abs(s) ** (2 / e), s)
            if s > 0:
                z += dl * (1 - (y / a) ** 2) ** 2
            pts.append((cy + y, z))
        return pts

    # --- lubang tali ---
    def _siapkan_lubang(self):
        xs_param = data.model("lubang", "x", None)
        if xs_param:  # deret lubang [D] dari proyek.toml (lubang tali tertutup tali di foto, mis. AM90)
            for sisi in ("lateral", "medial"):
                self.w_ref[sisi] = data.model("lubang", "w_mm", self.w_ref[sisi])
                # acuan AM-12(b) = deret [D] itu sendiri (x saja, z dari S): menangkap pergeseran build (AM90-C14)
                self.lubang[sisi] = dict(data=[[x, None, 0.0] for x in xs_param], jarak=float(np.median(np.diff(xs_param))),
                                         x0=xs_param[0], xs=list(xs_param))
            self.x_t0 = xs_param[0] - 6.0
            return
        P = self.ctx["panel"]
        lmin, zmin = data.model("lubang", "luas_min", 10.0), data.model("lubang", "z_min", 90.0)
        for sisi in ("lateral", "medial"):
            besar = sorted([l for l in P[sisi]["lubang_tali"] if l[2] >= lmin and l[1] > zmin])[:2]
            wr = []
            for x, z, _ in besar:
                y = self.y_sisi(x, z, sisi)
                cy, _ = self.plan(x)
                if y is not None:
                    wr.append(abs(y - cy) - LUBANG_KE_TEPI - KEMIRINGAN_CELAH * (x - px(153.0)))
            if wr:
                self.w_ref[sisi] = float(np.mean(wr))
            jarak = besar[1][0] - besar[0][0]
            x0 = besar[0][0]
            self.lubang[sisi] = dict(data=besar, jarak=jarak, x0=x0)
        k0 = data.model("lubang", "indeks_data", 4)  # urutan lubang data pertama dalam deret (AM1: lubang ke-5)
        first = min(self.lubang[s]["x0"] - k0 * self.lubang[s]["jarak"] for s in self.lubang)
        self.x_t0 = first - 6.0

    def posisi_lubang(self, sisi, n=None, geser=0.0):
        """n lubang per sisi: deret berjarak sama (jarak data), lubang ke-5 dan ke-6 = 2 lubang besar data
        (sisanya [D]); y = tepi celah + 7 mm; z dari S."""
        L = self.lubang[sisi]
        n = n or data.model("lubang", "n_pasang", N_PASANG)
        k0 = data.model("lubang", "indeks_data", 4)
        if "xs" in L:
            xs = [(L["xs"][k] if k < len(L["xs"]) else L["xs"][-1] + L["jarak"] * (k - len(L["xs"]) + 1)) + geser
                  for k in range(n)]
        else:
            xs = [L["x0"] + L["jarak"] * k + geser for k in range(-k0, -k0 + n)]
        out = []
        for x in xs:
            cy, _ = self.plan(x)
            y = cy + (1 if sisi == "lateral" else -1) * (self.w(x) + LUBANG_KE_TEPI)
            z = self.z_atas(x, y)
            out.append((Vector((x, y, z)), self.normal_atas(x, y)))
        return out
