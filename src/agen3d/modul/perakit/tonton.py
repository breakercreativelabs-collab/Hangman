"""Mode tonton (keputusan pengguna 2026-10-16/17): pembangunan perakit ditulis per LANGKAH ke folder, lalu add-on
`addon/agen3d` di Blender yang terbuka menampilkannya satu per satu dengan efek tumbuh.

Tanpa socket/jaringan: satu-satunya jalur = berkas di disk (aman, tidak ada port yang bisa disalahgunakan).
Folder: tonton.json (manifest) + langkah_NN.npz (titik mm, quad) + model.glb (langkah akhir = mesh serah, identik).
Setiap berkas ditulis ke .tmp lalu os.replace (atomik): add-on tidak pernah membaca berkas setengah jadi.
"""
import json
import os
import shutil
import time

import numpy as np

from . import sdf


def _tulis_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


class Perekam:
    """Dipanggil perakit.medan setiap bagian/detail selesai; selesai() menautkan model.glb sebagai langkah akhir."""

    def __init__(self, folder, nama):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        for f in os.listdir(folder):  # sisa run lama tidak boleh ikut ditonton
            if f.startswith("langkah_") or f in ("tonton.json", "model.glb"):
                os.remove(os.path.join(folder, f))
        self.t0 = time.time()
        self.data = dict(nama=nama, mulai=time.strftime("%Y-%m-%dT%H:%M:%S"), selesai=False, langkah=[])
        _tulis_json(os.path.join(folder, "tonton.json"), self.data)

    def langkah(self, nama, total, asal, vox):
        titik, quad = sdf.ke_mesh(total, asal, vox)
        berkas = f"langkah_{len(self.data['langkah']):02d}.npz"
        tmp = os.path.join(self.folder, berkas + ".tmp.npz")
        np.savez(tmp, titik=titik.astype(np.float32), quad=quad.astype(np.int32))
        os.replace(tmp, os.path.join(self.folder, berkas))
        self.data["langkah"].append(dict(nama=nama, berkas=berkas, detik=round(time.time() - self.t0, 1)))
        _tulis_json(os.path.join(self.folder, "tonton.json"), self.data)

    def selesai(self, glb):
        tmp = os.path.join(self.folder, "model.glb.tmp")
        shutil.copyfile(glb, tmp)
        os.replace(tmp, os.path.join(self.folder, "model.glb"))
        self.data["langkah"].append(dict(nama="akhir (mesh serah)", berkas="model.glb",
                                         detik=round(time.time() - self.t0, 1)))
        self.data["selesai"] = True
        _tulis_json(os.path.join(self.folder, "tonton.json"), self.data)
