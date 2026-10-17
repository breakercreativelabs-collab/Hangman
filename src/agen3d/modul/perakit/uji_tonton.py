"""Uji mode tonton tanpa GUI: bangun bidak dengan perekam, lalu jalankan PEMUAT add-on (addon/agen3d) langkah
demi langkah seperti tik pemantau di Blender terbuka. QC KT-01..04 + uji negatif. Bagian yang hanya bisa dicek di GUI
(timer berdetak, viewport ter-refresh, efek tumbuh terlihat) tetap wajib dilihat di laptop (docs/TONTON.md)."""
import importlib.util
import json
import os
import shutil

from ...inti import io, log, qc


def muat_addon():
    path = io.path_repo("addon", "agen3d", "tonton.py")
    spec = importlib.util.spec_from_file_location("agen3d_tonton", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def qc_tonton(manifest, titik_langkah, titik_akhir, titik_serah, skala_akhir):
    """manifest dict; titik_langkah = [jumlah titik per langkah (None = gagal dimuat)]; titik_akhir/serah = array
    titik mesh akhir di add-on vs model.glb headless (m); skala_akhir = skala objek setelah efek tumbuh selesai."""
    import numpy as np
    n = len(manifest.get("langkah", []))
    akhir_glb = n > 0 and manifest["langkah"][-1]["berkas"] == "model.glb"
    sama = titik_akhir is not None and titik_serah is not None and titik_akhir.shape == titik_serah.shape and \
        float(np.abs(np.sort(titik_akhir, 0) - np.sort(titik_serah, 0)).max()) < 1e-6
    gagal_muat = [i for i, t in enumerate(titik_langkah) if not t]
    return [
        qc.cek("KT-01", "langkah lengkap + akhir = model.glb + selesai", n, n >= 2 and akhir_glb and
               bool(manifest.get("selesai")) and len(titik_langkah) == n, ">= 2 langkah, terakhir model.glb, selesai"),
        qc.cek("KT-02", "mesh akhir di Blender terbuka identik dengan mesh serah headless", "identik" if sama else
               "beda", sama, "titik sama (selisih < 1e-6 m)"),
        qc.cek("KT-03", "setiap langkah termuat (mesh tidak kosong)", gagal_muat or "semua", not gagal_muat,
               "semua langkah"),
        qc.cek("KT-04", "efek tumbuh berakhir di skala 1", round(skala_akhir, 4), abs(skala_akhir - 1.0) < 1e-6, "1,0"),
    ]


def jalankan(out):
    from . import perakit
    if os.path.isdir(out):
        shutil.rmtree(out)
    folder = os.path.join(out, "tonton", "pion_catur")
    kode = perakit.rakit(io.proyek("pion_catur", "rancangan.toml"), os.path.join(out, "model"), render=False,
                         mode="pratinjau", tonton=folder)
    import bpy
    import numpy as np
    a = muat_addon()
    m = a.baca_manifest(folder)
    jumlah, ob = [], None
    for item in m["langkah"]:
        me = a.muat_langkah(folder, item)
        jumlah.append(len(me.vertices) if me else None)
        if me:
            ob = a.tampilkan(me)
            a.tumbuh(ob, a._keadaan["mulai_tumbuh"] + 10.0)

    def titik(me):
        t = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", t)
        return t.reshape(-1, 3)
    akhir = titik(ob.data) if ob else None
    serah = a.mesh_glb(os.path.join(out, "model", "model.glb"), "serah")
    serah_t = titik(serah) if serah else None
    pertama = a.muat_langkah(folder, m["langkah"][0])
    cek = qc_tonton(m, jumlah, akhir, serah_t, ob.scale.z if ob else 0.0)
    # ketahanan pemuat terhadap berkas setengah jadi (tik berikutnya mencoba lagi, tidak boleh galat)
    rusak = os.path.join(out, "rusak")
    os.makedirs(rusak)
    with open(os.path.join(rusak, "tonton.json"), "w") as f:
        f.write('{"langkah": [')
    with open(os.path.join(rusak, "langkah_00.npz"), "wb") as f:
        f.write(b"PK\x03\x04setengah")
    tahan = a.baca_manifest(rusak) is None and a.mesh_npz(os.path.join(rusak, "langkah_00.npz"), "x") is None
    cek.append(qc.cek("KT-05", "pemuat tahan manifest/npz setengah tertulis", tahan, tahan, "None, tanpa galat"))
    for c in cek:
        print(f"  {c['id']} {'LULUS' if c['lulus'] else 'GAGAL'} {c['nama']}: {c['nilai']} ({c['ambang']})")
    m_pendek = dict(m, langkah=m["langkah"][:-1])
    rusak_uji = [
        ("langkah akhir hilang", (m_pendek, jumlah[:-1], akhir, serah_t, 1.0), "KT-01"),
        ("akhir = langkah pertama (bukan mesh serah)", (m, jumlah, titik(pertama), serah_t, 1.0), "KT-02"),
        ("satu langkah gagal dimuat", (m, [None] + jumlah[1:], akhir, serah_t, 1.0), "KT-03"),
        ("tumbuh berhenti di tengah", (m, jumlah, akhir, serah_t, 0.6), "KT-04"),
    ]
    neg = []
    for nama, argumen, wajib in rusak_uji:
        ok, gagal = qc.tertangkap(qc_tonton(*argumen), [wajib])
        neg.append(dict(nama=nama, wajib=[wajib], gagal=gagal, tertangkap=ok))
        print(f"  negatif tonton {'OK ' if ok else 'BOCOR'} {nama}: gagal {gagal}")
    bpy.data.meshes.remove(pertama)
    lap = dict(langkah=[i["nama"] for i in m["langkah"]], titik=jumlah, cek=cek, negatif=neg, kode_bangun=kode,
               **qc.ringkas(cek, neg))
    io.tulis_json(os.path.join(out, "uji_tonton.json"), lap)
    log.info(f"tonton: {len(m['langkah'])} langkah; lulus {lap['lulus']}; negatif "
             f"{lap['negatif_tertangkap']}/{lap['negatif_jumlah']}")
    return 0 if kode == 0 and lap["lulus"] and lap["negatif_tertangkap"] == lap["negatif_jumlah"] else 1
