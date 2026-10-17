"""QC TV-01..08 bagian scene (tanpa render): durasi shot + ketukan, bingkai produk, subjek di frame, jerk kamera,
exploded rakit kembali, title-safe teks, tanpa keyframe linear (+ AM-18 di scene TVC lewat kontrak modeling_referensi).
Setiap cek = satu baris ATURAN_QC.md proyek (TV-xx)."""
import math

import bpy
import numpy as np
from mathutils import Vector

from ...inti.kamera import proyeksi
from ...inti.qc import cek
from ...inti.scene import fcurves, koleksi, objek_produk, titik_produk
from ..modeling_referensi import api as model_api
from ..product_shot.api import AMBANG as AMBANG_PS
from . import konfig
from .konfig import makro, shot_di

AMBANG = {
    "durasi_frame": 1,            # TV-01 |durasi shot - rencana| (frame)
    "ketukan_frame": 0.5,         # TV-01 potongan di grid 120 BPM (12,5 frame) +- 0,5 frame
    "margin_min": AMBANG_PS["margin_min"],  # TV-02 = QC-03 (0,02): produk tidak terpotong
    "isi_min": 0.40,              # TV-02 isi frame (sisi bbox proyeksi terpanjang); lihat ATURAN_QC
    "isi_maks": 0.95,
    "luma_min": AMBANG_PS["luma_min"],      # TV-03 = QC-05: frame hitam (0,08)
    "luma_maks": AMBANG_PS["luma_maks"],    # TV-03 = QC-05: frame putih/kosong (0,92) kecuali flash tercatat
    "std_min": 0.02,              # TV-03 frame rata (kosong): std luma; lihat ATURAN_QC
    "subjek_min": 0.02,           # TV-03 luas bbox subjek (produk/teks/gelembung) di frame, fraksi frame
    "flash_lonjak": 0.15,         # TV-03 kenaikan luma rata-rata vs median +-3 frame = flash
    "jerk_pos": 0.0025,           # TV-04 |selisih ke-3 posisi kamera| / jarak ke target, per frame^3; lihat ATURAN_QC
    "jerk_sudut_deg": 0.15,       # TV-04 |selisih ke-3 arah pandang| (deg per frame^3); lihat ATURAN_QC
    "rakit_mm": 0.1,              # TV-05 perpindahan maks bagian vs rakitan, frame >= akhir rakit
    "safe": 0.05,                 # TV-06 title-safe 90 %: semua vertex teks di [0,05; 0,95]
    "kontras_min": 4.5,           # TV-06 WCAG teks vs latar (render setelah compositor)
    "linear_maks": 0,             # TV-08 segmen keyframe LINEAR yang berubah nilai
}


def f_rakit():
    """Frame pertama semua bagian exploded sudah rakit (216 untuk AM1)."""
    X = konfig.K["exploded"]
    return max(X["rakit"] + b["tunda"] // 2 for b in X["bagian"]) + 1


# ---------------- pengumpulan per frame (satu lintasan) ----------------
def _sudut(cam):
    return np.array(cam.matrix_world.to_3x3() @ Vector((0, 0, -1)))


def _bbox_dunia(ob):
    M = np.array(ob.matrix_world)
    b = np.array([tuple(c) for c in ob.bound_box])
    return b @ M[:3, :3].T + M[:3, 3]


def _luas_subjek(cam, obs):
    """Luas bbox proyeksi (dipotong ke frame) gabungan subjek yang tampil, fraksi frame. Titik di belakang kamera
    dibuang."""
    pts = [_bbox_dunia(o) for o in obs if not o.hide_render and max(o.scale) > 1e-3]
    if not pts:
        return 0.0
    u, v, z = proyeksi(cam, np.concatenate(pts))
    ok = z > 0
    if not ok.any():
        return 0.0
    u, v = np.clip(u[ok], 0, 1), np.clip(v[ok], 0, 1)
    return float((u.max() - u.min()) * (v.max() - v.min()))


def _vertex_teks(ob, dg):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3, "f")
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    M = np.array(ev.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]


def kumpulkan():
    """Satu lintasan semua frame: kamera aktif (marker), matriks kamera, jarak ke target rig, luas subjek, teks, skala
    TURNTABLE, perpindahan bagian vs rakitan."""
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    tt, root = bpy.data.objects["TURNTABLE"], bpy.data.objects["PRODUCT_ROOT"]
    produk = objek_produk()
    subjek = produk + list(koleksi("TEKS").objects) + list(koleksi("GELEMBUNG").objects)
    teks = list(koleksi("TEKS").objects)
    marker = sorted(sc.timeline_markers, key=lambda m: m.frame)
    d = dict(frame=[], cam=[], pos=[], arah=[], jarak=[], subjek=[], safe=[], skala=[], rakit=[])
    F_RAKIT, XP_KELUAR = f_rakit(), konfig.K["exploded"]["keluar"]
    for f in range(sc.frame_start, sc.frame_end + 1):
        sc.frame_set(f)
        m = [m for m in marker if m.frame <= f]
        cam = m[-1].camera if m else sc.camera
        d["frame"].append(f)
        d["cam"].append(cam.name if cam else "")
        d["pos"].append(np.array(cam.matrix_world.translation))
        d["arah"].append(_sudut(cam))
        d["jarak"].append((cam.matrix_world.translation - cam.parent.matrix_world.translation).length
                          if cam.parent else 1.0)
        d["subjek"].append(_luas_subjek(cam, subjek))
        d["skala"].append(tt.matrix_world.to_scale().x)
        tampil = [o for o in teks if not o.hide_render and max(o.scale) > 1e-4]
        if tampil:
            u, v, z = proyeksi(cam, np.concatenate([_vertex_teks(o, dg) for o in tampil]))
            d["safe"].append(float(min(u.min(), v.min(), 1 - u.max(), 1 - v.max())) if (z > 0).all() else -1.0)
        else:
            d["safe"].append(None)
        if f >= F_RAKIT or f <= XP_KELUAR:
            Ri = root.matrix_world.inverted()
            w = 0.0
            for ob in produk:
                rel = np.array(Ri @ ob.matrix_world) - np.eye(4)
                b = np.c_[np.array([tuple(c) for c in ob.bound_box]), np.ones(8)]
                w = max(w, float(np.linalg.norm(b @ rel.T, axis=1).max()))
            d["rakit"].append(w * 1000)
        else:
            d["rakit"].append(None)
        d["marker_cam_aktif"] = d.get("marker_cam_aktif", True) and (sc.camera == cam)
    sc.frame_set(sc.frame_start)
    return d


# ---------------- cek ----------------
def qc_durasi(rasio):
    """TV-01: durasi tiap shot dari marker = rencana +- 1 frame; potongan di grid ketukan; kamera marker benar."""
    sc = bpy.context.scene
    mk = sorted(sc.timeline_markers, key=lambda m: m.frame)
    batas = [m.frame for m in mk] + [sc.frame_end + 1]
    salah, worst, ket = [], 0, 0.0
    for s in konfig.shot():
        nama, a, b = s["id"], s["mulai"], s["selesai"]
        rencana = round((b - a) * konfig.FPS)
        i = next((i for i, m in enumerate(mk) if m.name == nama), None)
        if i is None:
            salah.append(f"{nama}: marker hilang")
            continue
        dur = batas[i + 1] - batas[i]
        worst = max(worst, abs(dur - rencana))
        g = (mk[i].frame - 1) / konfig.KETUKAN
        ket = max(ket, abs(mk[i].frame - 1 - round(g) * konfig.KETUKAN))
        if mk[i].camera is None or mk[i].camera.get("shot") != nama:
            salah.append(f"{nama}: kamera marker salah")
    total = sc.frame_end - sc.frame_start + 1
    ok_total = total == round(konfig.DURASI * konfig.FPS) and sc.render.fps == konfig.FPS
    lulus = not salah and worst <= AMBANG["durasi_frame"] and ket <= AMBANG["ketukan_frame"] and ok_total
    return [cek("TV-01", f"durasi_shot_selisih_frame_{rasio}", worst, lulus,
                f"<= {AMBANG['durasi_frame']} frame; potongan di ketukan +- {AMBANG['ketukan_frame']}; "
                f"total {round(konfig.DURASI * konfig.FPS)} @ {konfig.FPS} fps",
                f"{len(mk)} marker, potongan {[m.frame for m in mk]}, galat ketukan maks {ket:.2f} frame, total {total} "
                f"@ {sc.render.fps} fps" + ("; " + "; ".join(salah) if salah else ""))]


def qc_bingkai(rasio):
    """TV-02: shot non-makro, setiap 2 frame selama produk tampil (skala TURNTABLE >= 0,9): tidak terpotong (margin
    >= QC-03) dan isi frame wajar."""
    sc = bpy.context.scene
    tt = bpy.data.objects["TURNTABLE"]
    margin, isi_lo, isi_hi, f_m, f_lo, f_hi, n = 1.0, 9.0, 0.0, None, None, None, 0
    for nama, f0, f1 in konfig.rentang_shot():
        if makro(nama):
            continue
        for f in range(f0, f1 + 1, 2):
            sc.frame_set(f)
            if tt.matrix_world.to_scale().x < 0.9:
                continue
            cam = next(m.camera for m in sorted(sc.timeline_markers, key=lambda m: -m.frame) if m.frame <= f)
            u, v, z = proyeksi(cam, titik_produk()[::5])
            m = float(min(u.min(), v.min(), 1 - u.max(), 1 - v.max())) if (z > 0).all() else -1.0
            isi = float(max(u.max() - u.min(), v.max() - v.min()))
            n += 1
            if m < margin:
                margin, f_m = m, f
            if isi < isi_lo:
                isi_lo, f_lo = isi, f
            if isi > isi_hi:
                isi_hi, f_hi = isi, f
    sc.frame_set(sc.frame_start)
    A = AMBANG
    return [cek("TV-02", f"margin_tepi_min_{rasio}", margin, margin >= A["margin_min"], f">= {A['margin_min']} (QC-03)",
                f"{n} frame non-makro, terburuk frame {f_m} ({shot_di(f_m)})" + (" TERPOTONG" if margin < 0 else "")),
            cek("TV-02", f"isi_frame_{rasio}", [round(isi_lo, 3), round(isi_hi, 3)],
                A["isi_min"] <= isi_lo and isi_hi <= A["isi_maks"], f"{A['isi_min']}..{A['isi_maks']}",
                f"min frame {f_lo} ({shot_di(f_lo)}), maks frame {f_hi} ({shot_di(f_hi)})")]


def qc_subjek(d, rasio):
    """TV-03 (geometri): setiap frame ada subjek (produk / teks / gelembung) di frame, luas bbox >= 2 %."""
    s = np.array(d["subjek"])
    i = int(s.argmin())
    return cek("TV-03", f"subjek_min_{rasio}", float(s.min()), float(s.min()) >= AMBANG["subjek_min"],
               f">= {AMBANG['subjek_min']} fraksi frame", f"terkecil frame {d['frame'][i]} ({shot_di(d['frame'][i])})")


def _jerk(d):
    """Jerk kamera per jendela 4 frame di dalam satu shot (jendela yang melintasi potongan dilewati)."""
    P, A, D, cam = np.array(d["pos"]), np.array(d["arah"]), np.array(d["jarak"]), d["cam"]
    jp, ja, f_p, f_a = 0.0, 0.0, None, None
    potongan = 0
    for i in range(1, len(P) - 2):
        if len({cam[i - 1], cam[i], cam[i + 1], cam[i + 2]}) > 1:
            potongan += 1
            continue
        p = np.linalg.norm(P[i + 2] - 3 * P[i + 1] + 3 * P[i] - P[i - 1]) / max(D[i], 1e-6)
        a = math.degrees(np.linalg.norm(A[i + 2] - 3 * A[i + 1] + 3 * A[i] - A[i - 1]))
        if p > jp:
            jp, f_p = p, d["frame"][i]
        if a > ja:
            ja, f_a = a, d["frame"][i]
    return jp, ja, f_p, f_a, potongan


def qc_gerak(d, rasio):
    """TV-04: gerak kamera halus. Selisih ke-3 posisi (relatif jarak ke target) dan arah pandang per frame, di dalam
    shot. Lonjakan hanya boleh di potongan (jendela melintasi potongan tidak dihitung)."""
    jp, ja, f_p, f_a, n = _jerk(d)
    A = AMBANG
    return [cek("TV-04", f"jerk_posisi_relatif_{rasio}", jp, jp <= A["jerk_pos"], f"<= {A['jerk_pos']} /frame^3",
                f"maks frame {f_p} ({shot_di(f_p)}); {n} jendela melintasi potongan dilewati"),
            cek("TV-04", f"jerk_arah_deg_{rasio}", ja, ja <= A["jerk_sudut_deg"], f"<= {A['jerk_sudut_deg']} deg/frame^3",
                f"maks frame {f_a} ({shot_di(f_a)})")]


def qc_rakit(d, rasio):
    """TV-05: setelah exploded (frame >= akhir rakit) dan sebelum terurai, setiap bagian di posisi rakitan: perpindahan
    maks sudut bbox objek (ruang PRODUCT_ROOT) vs rakitan model."""
    r = [(f, w) for f, w in zip(d["frame"], d["rakit"]) if w is not None]
    f_b, w_b = max(r, key=lambda x: x[1])
    shot_x = konfig.K["exploded"]["shot"]
    f_akhir = konfig.f_shot(shot_x)[1]
    akhir = next(w for f, w in r if f == f_akhir)
    return cek("TV-05", f"rakit_kembali_mm_{rasio}", w_b, w_b <= AMBANG["rakit_mm"], f"<= {AMBANG['rakit_mm']} mm",
               f"frame 1-{konfig.K['exploded']['keluar']} dan {f_rakit()}-{konfig.FRAME_AKHIR} ({len(r)} frame); "
               f"akhir {shot_x.split('_')[0]} ({f_akhir}) {akhir:.4f} mm; "
               f"terburuk frame {f_b}")


def qc_safe(d, rasio):
    """TV-06 (a): semua vertex teks yang tampil di title-safe 90 % di setiap frame (termasuk overshoot kinetik)."""
    s = [(f, v) for f, v in zip(d["frame"], d["safe"]) if v is not None]
    if not s:
        return cek("TV-06", f"title_safe_margin_{rasio}", -1.0, False, f">= {AMBANG['safe']}", "teks tidak ditemukan")
    f_b, v_b = min(s, key=lambda x: x[1])
    return cek("TV-06", f"title_safe_margin_{rasio}", v_b, v_b >= AMBANG["safe"],
               f">= {AMBANG['safe']} (90 % title-safe)", f"{len(s)} frame bertek; terburuk frame {f_b}")


def qc_easing():
    """TV-08: tidak ada segmen keyframe LINEAR yang mengubah nilai (objek + data kamera + compositor)."""
    linear, n = [], 0
    ids = list(bpy.data.objects) + list(bpy.data.cameras) + list(bpy.data.node_groups)
    for idb in ids:
        for fc in fcurves(idb):
            if fc.data_path.startswith("hide_"):
                continue
            kp = fc.keyframe_points
            for a, b in zip(kp[:-1], kp[1:]):
                n += 1
                if a.interpolation == "LINEAR" and abs(a.co.y - b.co.y) > 1e-9:
                    linear.append(f"{idb.name}.{fc.data_path}[{fc.array_index}]@{int(a.co.x)}")
    return cek("TV-08", "segmen_linear", len(linear), len(linear) <= AMBANG["linear_maks"], "= 0",
               f"{n} segmen; " + (", ".join(linear[:4]) if linear else "BACK/BOUNCE/SINE/BEZIER/CONSTANT"))


def qc_scene_tv(rasio):
    d = kumpulkan()
    hasil = qc_durasi(rasio) + qc_bingkai(rasio) + [qc_subjek(d, rasio)] + qc_gerak(d, rasio)
    hasil += [qc_rakit(d, rasio), qc_safe(d, rasio), qc_easing()]
    if not d["marker_cam_aktif"]:
        hasil.append(cek("TV-01", f"kamera_ikut_marker_{rasio}", 0, False, "scene.camera = kamera marker", "switch gagal"))
    am18 = model_api.qc_slot_material()
    am18["nama"] += f"_scene_tvc_{rasio}"
    return hasil + [am18], d

