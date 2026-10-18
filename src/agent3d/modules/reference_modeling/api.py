"""reference_modeling contract for other modules (tvc). The only cross-module import point (structure test e).

- load_project(id): load project.toml + reference data (required before any other function)
- path_model(): path of the model .blend produced by QC/build (artifact, used by tvc)
- build_model(**param) / save_model(path): build the model scene (M1+M2+M3) and save the .blend
- studio_palette(): the project's eye-check palette studio (gradient + softbox + rim), used by tvc
- qc_slot_material(): AM-18 (non-default role materials), re-run in the tvc scene
"""
import os

import bpy

from .shoe import data
from .shoe.qc_material import qc_slot_material
from .shoe.sole import build_shoe as build_model
from .shoe.studio import studio_p3 as studio_palette


def load_project(project="am1"):
    return data.load_data(project)


def path_model():
    return data.output_path("blend")


def save_model(path=None):
    path = os.path.abspath(path or path_model())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)  # C-10: absolute path
    return path


__all__ = ["load_project", "path_model", "build_model", "save_model", "studio_palette", "qc_slot_material"]
