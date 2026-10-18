"""Shoe recipe M2: upper parameters [D] + base shape S (class Shape) + collar line from the panel edge_line."""
import math

import numpy as np
from mathutils import Vector

from ..filters import gauss, smoothstep
from . import data
from .sole import BULGE, UPPER_INSET

px = data.map_x  # AM1 position -> project shoe (identity for AM1)

# ---------------- parameters [D] (modeling choices, not data) ----------------
N_RINGS = 64            # points per S section
STEP = 1.0            # mm between S stations
# Gauss (mm). Besides the 0.23 mm/px quantization steps, the data top silhouette has 8-16 mm ripples ~0.4 mm high
# (mesh texture/creases in the photo): sigma 2 mm still leaves 2.5-3 degrees of ripple (AM-09). Tongue/collar
# (x >= 188) stays at 2 mm so the tongue peak and collar curve do not go blunt.
SIGMA_TOP = 5.0
SIGMA_TOP_COLLAR = 2.0
SIGMA_MID = 5.0          # midsole line (only for the upper sections; the M1 midsole keeps raw data)
SIGMA_PLAN = 4.0         # plan (upper only)
LAYERS = {                # (inner, outer) offset from S, mm
    "upper": (None, -2.0),
    "panel_mesh": (-1.5, -1.0),
    "overlay": (-0.7, 0.0),
    "swoosh": (-0.7, 0.3),
}
COLLAR_DROP = 2.5        # panel layers stop 2.5 mm below the collar lip (collar band = upper body, lining)
COLLAR_WALL = 6.0      # collar wall thickness (from outer S to the inner opening wall)
OPENING_X = (200.0, 283.0)  # foot opening [D]: front (behind the tongue) to inside the heel counter
OPENING_FLOOR = 4.0      # opening floor (insole) = midsole line + 4 mm
GAP_DEPTH = 10.0       # tongue gap: base = top silhouette - 10 mm
COLLAR_OVERSHOOT = 12.0   # S is made taller in the collar area, then cut exactly to the top silhouette (vertical wall)
E_TOP, E_TOP_COLLAR, E_BOTTOM = 2.4, 4.0, 2.2  # E_BOTTOM M1 = 4 (sharp bottom corner, see BASE_DEPTH)
BASE_DEPTH = 8.0        # upper base below the midsole line (hidden inside the midsole)
N_PAIRS = 7             # [D] AM1: 6-7 pairs
HOLE_TO_EDGE = 7.0     # hole center to gap edge (eyestay) [D]
EYESTAY_WIDTH = 14.0     # eyestay band width from the gap edge (Y projection) [D]
GAP_SLOPE = 0.15  # gap half width grows 0.15 mm per mm toward the collar [D]
R_HOLE, HOLE_DEPTH = 2.0, 4.0
R_LACE = 1.25            # 2.5 mm lace
GAP_EDGE_DROP = 4.5   # eyestay edge below the top silhouette: the throat silhouette = laces crossing above it
                         # (lace bottom ~ edge + 3.2 mm, crossing ~ edge + 6.1 mm; mean ~ data silhouette)
TONGUE_DROP = 1.0        # tongue peak (middle) below the eyestay edge; 1.5 mm transverse curvature
TONGUE_GAP = 3.5        # tongue-eyestay gap: the lace crossings emerge here (2.5 mm lace + 2 x 0.5 mm)
LAST = {}            # last build data for QC (lace path, holes)
STITCH = dict(offset=1.5, dash=3.0, pause=1.6, width=0.6, thickness=0.35)
PANEL_GAP = 0.4        # distance between panels on the same layer (e.g. heel_overlay vs eyestay)


# ---------------- line C (heel/collar overlay) from edge_line ----------------
def collar_line(panel_side):
    """AM-D04: bottom edge line of the collar/heel overlay = largest `edge_line` component (8-neighbor, 1 mm grid;
    the only component >= 100 mm), median z per column, then median-5 + 3 mm Gauss. Heel mesh texture noise
    (x > 270) is damped by the median as well."""
    pts = set(map(tuple, np.array(panel_side["edge_line"], int)))
    rest, largest = set(pts), []
    while rest:
        q = rest.pop()
        st, comps = [q], [q]
        while st:
            x, z = st.pop()
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    n = (x + dx, z + dz)
                    if n in rest:
                        rest.remove(n)
                        st.append(n)
                        comps.append(n)
        if len(comps) > len(largest):
            largest = comps
    c = np.array(largest, float)
    xs = np.unique(c[:, 0])
    z = np.array([np.median(c[c[:, 0] == x, 1]) for x in xs])
    zm = np.array([np.median(z[max(0, i - 2):i + 3]) for i in range(len(z))])
    g, zh = gauss(xs, zm, 3.0, 1.0)
    return g, zh


# ---------------- base shape S ----------------
class Shape:
    """Upper section functions per x. smoothness=False = raw input (negative test C-A3, same as the M1 block)."""

    def __init__(self, ctx, smoothness=True):
        self.smoothness = smoothness
        self.ctx = ctx  # from sole.build: xs_s, zb_raw, zt_raw, x_last, xs0, xs1, mt (raw functions)
        xs, zb, zt = ctx["xs_s"], ctx["zb_raw"], ctx["zt_raw"]
        s_top, s_mid, s_plan = (SIGMA_TOP, SIGMA_MID, SIGMA_PLAN) if smoothness else (0, 0, 0)
        self.g_zt, self.v_zt = gauss(xs, zt, s_top)
        if smoothness:  # sigma 5 only on vamp/toe box; toe tip (fast-changing silhouette) and tongue/collar use sigma 2
            _, v2 = gauss(xs, zt, SIGMA_TOP_COLLAR)
            f = np.maximum(smoothstep(px(176.0), px(188.0), self.g_zt), 1 - smoothstep(px(16.0), px(28.0), self.g_zt))
            self.v_zt = self.v_zt * (1 - f) + v2 * f
        self.g_zb, self.v_zb = gauss(xs, zb, SIGMA_TOP_COLLAR if smoothness else 0)
        mid = ctx["mid"]
        self.g_mt, self.v_mt = gauss(mid[:, 0], mid[:, 1], s_mid)
        gp = np.arange(0.0, data.LENGTH + 1e-9, 0.5)
        cy, a = np.array([data.plan_y(x) for x in gp]).T
        self.g_p, self.v_cy = gauss(gp, cy, s_plan)
        _, self.v_a = gauss(gp, a, s_plan)
        self.add = ctx["midsole_extra"]
        self.w_ref = {"lateral": 17.0, "medial": 17.0}
        self.hole = {}
        self.x_t0 = px(88.0)
        self._tab = None
        for _ in range(3):  # the gap (w) depends on delta and delta on w: fixed iteration count
            if smoothness:
                self.prepare_table()
            self._prepare_hole()
        if smoothness:
            self.prepare_table()

    # --- base functions (raw or smoothed) ---
    def zt(self, x):
        return float(np.interp(x, self.g_zt, self.v_zt))

    def zb(self, x):
        return float(np.interp(x, self.g_zb, self.v_zb))

    def mt(self, x):
        return float(np.interp(x, self.g_mt, self.v_mt)) + self.add

    def plan(self, x):
        return float(np.interp(x, self.g_p, self.v_cy)), float(np.interp(x, self.g_p, self.v_a))

    def k_collar(self, x):
        return float(smoothstep(px(196.0), px(202.0), x))

    # --- tongue gap ---
    def w_lin(self, x):
        """w without rounding the front end of the gap (for the smooth dome height correction)."""
        wr = np.mean(list(self.w_ref.values()))
        return max(wr + GAP_SLOPE * (min(x, px(196.0)) - px(153.0)), 0.0)

    def w(self, x, side=None):
        """Half width of the tongue gap (eyestay edge) from the plan center line. Calibrated so the model lace holes land
        at the data hole z (2 large holes per side); slope [D]."""
        wr = np.mean(list(self.w_ref.values())) if side is None else self.w_ref[side]
        v = wr + GAP_SLOPE * (min(x, px(196.0)) - px(153.0))
        R0 = 6.0
        if x < self.x_t0 + R0:
            v *= math.sqrt(max(0.0, 1 - ((self.x_t0 + R0 - x) / R0) ** 2))
        return max(v, 0.0)

    def param(self, x, delta=True):
        """(cy, a, zlo, zw, zhi, e_bottom, e_top) of section S at x (mm). Smooth mode: each channel is smoothed again
        along x (2 mm Gauss), because the 'on sole' -> 'off sole' switch at the heel (x 284-290) gives zlo a sharp
        V shape: inward layer offsets >= 1 mm fold there (boolean fails, AM-13)."""
        if self.smoothness and delta and getattr(self, "_tab", None) is not None:
            g, T = self._tab
            return tuple(float(np.interp(x, g, T[:, i])) for i in range(8))
        return self._param(x, delta)

    def prepare_table(self):
        self._tab = None
        g = np.arange(0.0, data.LENGTH + 1e-9, 0.25)
        T = np.array([self._param(x) for x in g])
        r = int(math.ceil(3 * 2.0 / 0.25))
        k = np.exp(-0.5 * (np.arange(-r, r + 1) * 0.25 / 2.0) ** 2)
        k /= k.sum()
        for i in range(1, 8):
            T[:, i] = np.convolve(np.pad(T[:, i], r, mode="edge"), k, "valid")
        self._tab = (g, T)

    def _param(self, x, delta=True):
        c = self.ctx
        x_last, xs0, xs1, L = c["x_last"], c["xs0"], c["xs1"], data.LENGTH
        zb, zt = self.zb(x), self.zt(x)
        cy, a = self.plan(x)
        if x > x_last:  # 1 px tail (same as M1)
            f = 1 - 0.9 * (x - x_last) / (L - x_last)
            m = (zb + zt) / 2
            zb, zt = m - (m - zb) * f, m + (zt - m) * f
            a *= f
        on_sole = xs0 <= x <= xs1
        wb = float(np.clip(min(x - xs0, xs1 - x) / 6.0, 0, 1)) if on_sole else 0.0
        if on_sole:
            m = self.mt(x)
            # smooth mode: upper base 8 mm inside the midsole (M1: 4 mm). A 5.5 mm thick x 70 mm wide bottom half
            # has end curvature radii ~0.9 mm < the 1.8 mm layer offset -> folds (C-A3); 9.5 mm -> ~2.6 mm
            zlo_s = max(m - BASE_DEPTH, zb + 7.0) if self.smoothness else max(m - 4.0, zb + 1.0)
            zw_s, a_s = m + 1.5, a * (1 - BULGE) - UPPER_INSET
        else:
            zlo_s, zw_s, a_s = zb, zb, a
        zlo = zb + wb * (zlo_s - zb)
        zw = max(zb + 0.3 * (zt - zb) + wb * (zw_s - (zb + 0.3 * (zt - zb))), zlo + 0.2)
        aa = a + wb * (a_s - a)
        zw = min(zw, zt - 0.5)
        # collar: S is made taller & boxier, then cut to the top silhouette (vertical collar wall). Long transition
        # (x 186-208, 22 mm) so the side wall does not kink (AM-09: a 6 mm transition = 17-20 degree fold).
        # Starts behind the eyestay (last hole + 9 mm ~ 188), so it does not collide with the gap edge correction.
        k = float(smoothstep(px(186.0), px(208.0), x)) * (1 - float(smoothstep(px(284.0), px(290.0), x)))
        e_t = E_TOP + (E_TOP_COLLAR - E_TOP) * k
        zhi = zt + COLLAR_OVERSHOOT * k
        dl = 0.0
        if delta and self.x_t0 < x < px(192.0):
            # gap edge (y = w) GAP_EDGE_DROP below the top silhouette: the side_view throat silhouette = laces crossing
            # over the eyestay edge. Correction only at the dome peak (bump (1-u^2)^2); the side wall is unchanged.
            w = self.w_lin(x)
            if 0 < w < aa:
                u = w / aa
                zbase = zw + (zhi - zw) * self._g(u, e_t)
                dl = (zt - GAP_EDGE_DROP - zbase) / (1 - u * u) ** 2
                dl *= float(smoothstep(self.x_t0, self.x_t0 + 12.0, x)) * (1 - float(smoothstep(px(182.0), px(192.0), x)))
        return cy, aa, zlo, zw, zhi, (E_BOTTOM if self.smoothness else 4.0), e_t, dl

    @staticmethod
    def _g(u, e):
        c = u ** (e / 2)
        return math.sqrt(max(1 - c * c, 0.0)) ** (2 / e)

    @staticmethod
    def _zu(u, zw, zhi, et, dl):
        return zw + (zhi - zw) * Shape._g(u, et) + dl * (1 - u * u) ** 2

    def z_top(self, x, y):
        """Height of the S top half at (x, y)."""
        cy, a, zlo, zw, zhi, eb, et, dl = self.param(x)
        u = abs(y - cy) / a
        if u >= 1:
            return None
        return self._zu(u, zw, zhi, et, dl)

    def y_side(self, x, z, side):
        """Point on the S top half at height z on the lateral (+Y) / medial (-Y) side: outermost intersection (bisection)."""
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
        return cy + (1 if side == "lateral" else -1) * a * (lo + hi) / 2

    def top_normal(self, x, y, h=0.05):
        dzx = (self.z_top(x + h, y) - self.z_top(x - h, y)) / (2 * h)
        dzy = (self.z_top(x, y + h) - self.z_top(x, y - h)) / (2 * h)
        return Vector((-dzx, -dzy, 1.0)).normalized()

    def ring(self, x, n=N_RINGS):
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

    # --- lace holes ---
    def _prepare_hole(self):
        xs_param = data.model("hole", "x", None)
        if xs_param:  # hole row [D] from project.toml (lace holes hidden by laces in the photo, e.g. AM90)
            for side in ("lateral", "medial"):
                self.w_ref[side] = data.model("hole", "w_mm", self.w_ref[side])
                # AM-12(b) baseline = that [D] row itself (x only, z from S): catches build shifts (AM90-C14)
                self.hole[side] = dict(data=[[x, None, 0.0] for x in xs_param], distance=float(np.median(np.diff(xs_param))),
                                         x0=xs_param[0], xs=list(xs_param))
            self.x_t0 = xs_param[0] - 6.0
            return
        P = self.ctx["panel"]
        lmin, zmin = data.model("hole", "area_min", 10.0), data.model("hole", "z_min", 90.0)
        for side in ("lateral", "medial"):
            large = sorted([l for l in P[side]["lace_hole"] if l[2] >= lmin and l[1] > zmin])[:2]
            wr = []
            for x, z, _ in large:
                y = self.y_side(x, z, side)
                cy, _ = self.plan(x)
                if y is not None:
                    wr.append(abs(y - cy) - HOLE_TO_EDGE - GAP_SLOPE * (x - px(153.0)))
            if wr:
                self.w_ref[side] = float(np.mean(wr))
            distance = large[1][0] - large[0][0]
            x0 = large[0][0]
            self.hole[side] = dict(data=large, distance=distance, x0=x0)
        k0 = data.model("hole", "data_index", 4)  # index of the first data hole in the row (AM1: 5th hole)
        first = min(self.hole[s]["x0"] - k0 * self.hole[s]["distance"] for s in self.hole)
        self.x_t0 = first - 6.0

    def hole_position(self, side, n=None, shift=0.0):
        """n holes per side: evenly spaced row (data spacing), holes 5 and 6 = the 2 large data holes
        (the rest [D]); y = gap edge + 7 mm; z from S."""
        L = self.hole[side]
        n = n or data.model("hole", "n_pairs", N_PAIRS)
        k0 = data.model("hole", "data_index", 4)
        if "xs" in L:
            xs = [(L["xs"][k] if k < len(L["xs"]) else L["xs"][-1] + L["distance"] * (k - len(L["xs"]) + 1)) + shift
                  for k in range(n)]
        else:
            xs = [L["x0"] + L["distance"] * k + shift for k in range(-k0, -k0 + n)]
        out = []
        for x in xs:
            cy, _ = self.plan(x)
            y = cy + (1 if side == "lateral" else -1) * (self.w(x) + HOLE_TO_EDGE)
            z = self.z_top(x, y)
            out.append((Vector((x, y, z)), self.top_normal(x, y)))
        return out
