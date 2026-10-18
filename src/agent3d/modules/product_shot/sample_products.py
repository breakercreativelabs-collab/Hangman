"""Procedural test products: build objects (with materials from make_material.py) from specification + profile.

Convention: origin at bottom center, front side (label logo) faces -Y. Products: specification.PRODUCT.
"""
import math

import bpy
from mathutils import Matrix

from .profile import (liquid_from, tube_section, bottle_profile, inner_bottle_profile, liquid_profile, flip_top_profile,
                     jar_profile, can_profile, box_profile, pet_profile, tube_profile, cap_profile, lug_cap_profile,
                     pet_cap_profile, lathe_profile, superellipse, can_tab_mesh)
from .specification import SPEC


def _object(name, me, collection):
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    return ob


def _shift(me, dx, dy):
    me.transform(Matrix.Translation((dx / 1000, dy / 1000, 0)))
    return me


def _band_label(name, s, collection, make_material):
    z0, z1 = s["label_mm"]
    r = s["diameter_mm"] / 2 + 0.25
    ob = _object(name, lathe_profile(name, [(r, z0), (r, z1)]), collection)
    ob.data.materials.append(make_material["LABEL"])
    return ob


def build_new(name, collection, make_material):
    """Task 4 curriculum products. Returns a list of objects."""
    s = SPEC[name]
    if name == "slim_can":
        return build_can(name, s, collection, make_material)
    if name == "milk_carton":
        a, b = s["width_mm"] / 2, s["thickness_mm"] / 2
        H, hs = s["height_mm"], s["fin_mm"]
        body = _object("body_box", lathe_profile("body_box", box_profile(s), section=superellipse(a, b)), collection)
        fin = _object("fin_box", lathe_profile("fin_box", [(0, H - hs), (1, H - hs), (1, H), (0, H)],
                                                   section=superellipse(a - 1.0, 3.5, 6)), collection)
        for ob in (body, fin):
            ob.data.materials.append(make_material["LABEL"])
        foil = _object("foil_box", _shift(lathe_profile("foil_box", [(0, H - hs), (3.5, H - hs), (3.5, H - hs + 0.15),
                                                                        (0, H - hs + 0.15)], seg=32), a / 2, b / 2 + 2.0),
                      collection)  # straw hole (foil) [D]
        foil.data.materials.append(make_material["foil"])
        return [body, fin, foil]
    if name == "tube":
        body = _object("tube_body", lathe_profile("tube_body", tube_profile(s), section=tube_section(s)), collection)
        body.data.materials.append(make_material["LABEL"])
        cap = _object("tube_cap", lathe_profile("tube_cap", flip_top_profile(s)), collection)
        cap.data.materials.append(make_material["cap"])
        return [body, cap]
    if name == "jam_jar":
        outer, inner = jar_profile(s)
        glass = _object("jar_glass", lathe_profile("jar_glass", outer + inner), collection)
        glass.data.materials.append(make_material["glass"])
        contents = _object("jar_fill", lathe_profile("jar_fill", liquid_from(inner, s["fill_mm"], 0.15, 6.0)), collection)
        contents.data.materials.append(make_material["contents"])
        cap = _object("jar_lid", lathe_profile("jar_lid", lug_cap_profile(s)), collection)
        cap.data.materials.append(make_material["cap"])
        return [glass, contents, _band_label("jar_label", s, collection, make_material), cap]
    if name == "pet_bottle":
        outer, inner = pet_profile(s)
        pet = _object("pet_body", lathe_profile("pet_body", outer + inner), collection)
        pet.data.materials.append(make_material["pet"])
        water = _object("pet_water", lathe_profile("pet_water", liquid_from(inner, s["fill_mm"], 0.1, 6.0)), collection)
        water.data.materials.append(make_material["water"])
        flute = lambda t, z: 1.0 + (0.02 * math.cos(60 * t) if z < s["height_mm"] + s["cap_rise_mm"] - 2.5 else 0.0)
        cap = _object("pet_cap", lathe_profile("pet_cap", pet_cap_profile(s), seg=120, modulation=flute), collection)
        cap.data.materials.append(make_material["cap"])
        return [pet, water, _band_label("pet_label", s, collection, make_material), cap]
    raise KeyError(name)


def build_can(name, s, collection, make_material):
    body = _object(f"{name}_body", lathe_profile(f"{name}_body", can_profile(s)), collection)
    body.data.materials.append(make_material["LABEL"])   # index 0: paint + logo (body)
    body.data.materials.append(make_material["metal"])   # index 1: bare aluminium (neck, lid, base)
    zb = (s["height_mm"] - s["neck_mm"]) / 1000
    for p in body.data.polygons:
        z = p.center.z
        p.material_index = 0 if 0.0105 < z < zb + 0.0005 else 1
    me_tab, me_rivet = can_tab_mesh(s)
    tab, rivet = _object(f"{name}_tab", me_tab, collection), _object(f"{name}_rivet", me_rivet, collection)
    for ob in (tab, rivet):
        ob.data.materials.append(make_material["metal"])
    return [body, tab, rivet]


def build_product(name, collection, make_material):
    """Build a test product. `make_material` = dict name->material (created by the verbs). Returns a list of objects."""
    s = SPEC[name]
    if name == "can":
        return build_can(name, s, collection, make_material)
    if name != "bottle":
        return build_new(name, collection, make_material)
    # C-11: hollow glass (outer wall up + inner wall down) + liquid, not a solid glass cylinder
    glass = _object("glass_bottle", lathe_profile("glass_bottle", bottle_profile(s)[:-1] + inner_bottle_profile(s)), collection)
    glass.data.materials.append(make_material["glass"])
    liquid = _object("bottle_liquid", lathe_profile("bottle_liquid", liquid_profile(s)), collection)
    liquid.data.materials.append(make_material["liquid"])
    z0, z1 = s["label_mm"]
    r = s["diameter_mm"] / 2 + 0.25
    label = _object("bottle_label", lathe_profile("bottle_label", [(r, z0), (r, z1)]), collection)
    label.data.materials.append(make_material["LABEL"])
    flute = lambda t, z: 1.0 + (0.025 * math.cos(21 * t) if z < s["height_mm"] - 0.5 else 0.0)  # 21 crown flutes
    cap = _object("bottle_cap", lathe_profile("bottle_cap", cap_profile(s), modulation=flute), collection)
    cap.data.materials.append(make_material["cap"])
    return [glass, liquid, label, cap]
