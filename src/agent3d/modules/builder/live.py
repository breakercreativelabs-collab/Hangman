"""Live mode (user decision 2026-10-16/17): the builder writes each build STEP to a folder, and the `addon/agent3d`
add-on in an open Blender shows them one by one with a grow effect.

No sockets or network: the only channel is files on disk (safe, no port that could be abused).
Folder: live.json (manifest) + step_NN.npz (points in mm, quads) + model.glb (final step = the handover mesh, identical).
Every file is written to .tmp and then os.replace'd (atomic): the add-on never reads a half-written file.
"""
import json
import os
import shutil
import time

import numpy as np

from . import sdf


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


class Recorder:
    """Called by builder.field after each part/detail; done() links model.glb as the final step."""

    def __init__(self, folder, name):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        for f in os.listdir(folder):  # leftovers from an old run must not be shown
            if f.startswith("step_") or f in ("live.json", "model.glb"):
                os.remove(os.path.join(folder, f))
        self.t0 = time.time()
        self.data = dict(name=name, start=time.strftime("%Y-%m-%dT%H:%M:%S"), done=False, step=[])
        _write_json(os.path.join(folder, "live.json"), self.data)

    def step(self, name, total, origin, vox):
        points, quad = sdf.sdf_to_mesh(total, origin, vox)
        file = f"step_{len(self.data['step']):02d}.npz"
        tmp = os.path.join(self.folder, file + ".tmp.npz")
        np.savez(tmp, points=points.astype(np.float32), quad=quad.astype(np.int32))
        os.replace(tmp, os.path.join(self.folder, file))
        self.data["step"].append(dict(name=name, file=file, seconds=round(time.time() - self.t0, 1)))
        _write_json(os.path.join(self.folder, "live.json"), self.data)

    def done(self, glb):
        tmp = os.path.join(self.folder, "model.glb.tmp")
        shutil.copyfile(glb, tmp)
        os.replace(tmp, os.path.join(self.folder, "model.glb"))
        self.data["step"].append(dict(name="final (handover mesh)", file="model.glb",
                                         seconds=round(time.time() - self.t0, 1)))
        self.data["done"] = True
        _write_json(os.path.join(self.folder, "live.json"), self.data)
