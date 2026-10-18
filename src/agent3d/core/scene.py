"""Standard .blend scene (PS-1), used by all modules.

Collections PRODUCT / LIGHTS / CAMERAS / BACKDROP + CONTROL object (custom properties).
Product hierarchy: TURNTABLE (empty, animated) -> PRODUCT_ROOT (empty, identity) -> product meshes.
Conventions: meters, floor at z = 0, product front faces -Y, camera on the -Y side.
"""
import bpy
import numpy as np
from bpy_extras import anim_utils

COLLECTION = ("PRODUCT", "LIGHTS", "CAMERAS", "BACKDROP")
STANDARD = "PS-1"
DEFAULT_RATIO = "16:9,9:16,1:1"  # CONTROL['ratio'] (product shot render aspect ratios)


def collection(name):
    k = bpy.data.collections.get(name)
    if k is None:
        k = bpy.data.collections.new(name)
    if k.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(k)
    return k


def control():
    return bpy.data.objects.get("CONTROL")


def prepare_scene():
    """Clear the scene, create the 4 standard collections + the CONTROL object."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for k in list(bpy.data.collections):
        bpy.data.collections.remove(k)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)  # old materials/meshes don't pile up
    for name in COLLECTION:
        collection(name)
    c = bpy.data.objects.new("CONTROL", None)
    c.empty_display_type, c.empty_display_size = "CUBE", 0.02
    bpy.context.scene.collection.objects.link(c)
    c["standard"] = STANDARD
    c["variant_color"] = [0.5, 0.5, 0.5]
    c.id_properties_ui("variant_color").update(subtype="COLOR", min=0.0, max=1.0)
    c["hex_color"] = "#808080"
    c["light_intensity"] = 1.0
    c.id_properties_ui("light_intensity").update(min=0.0, soft_max=3.0)
    for k, v in (("product", ""), ("light_preset", ""), ("easing", ""), ("duration_seconds", 0.0),
                 ("fps", 25), ("fill_target", 0.70), ("ratio", DEFAULT_RATIO)):
        c[k] = v
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.view_settings.view_transform = "Khronos PBR Neutral"  # accurate brand colors (AgX desaturates bright yellow, QC-10)
    sc.view_settings.look = "None"
    return c


def drive(idblock, path, prop, expression="var", index=-1):
    """Simple driver from CONTROL[prop] (simple arithmetic expression, no Python auto-run needed)."""
    fc = idblock.driver_add(path, index) if index >= 0 else idblock.driver_add(path)
    d = fc.driver
    d.type, d.expression = "SCRIPTED", expression
    v = d.variables.new()
    v.name, v.type = "var", "SINGLE_PROP"
    v.targets[0].id = control()
    v.targets[0].data_path = f'["{prop}"]' + (f"[{index}]" if index >= 0 else "")
    return fc


def fcurves(idblock):
    """F-curves of an ID (object, camera, node group; layered actions in Blender 4.4+/5.x)."""
    ad = idblock.animation_data
    if not ad or not ad.action:
        return []
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return list(cb.fcurves) if cb else []


def product_object():
    return [o for o in collection("PRODUCT").all_objects if o.type == "MESH" and not o.hide_render]


def product_points():
    """All product vertices (after modifiers) in world coordinates, N x 3 array (meters)."""
    dg = bpy.context.evaluated_depsgraph_get()
    result = []
    for ob in product_object():
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, "f")
        me.vertices.foreach_get("co", co)
        M = np.array(ev.matrix_world)
        result.append(co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3])
        ev.to_mesh_clear()
    return np.vstack(result) if result else np.zeros((0, 3))


def root():
    """PRODUCT_ROOT (created together with its TURNTABLE parent if missing)."""
    r = bpy.data.objects.get("PRODUCT_ROOT")
    if r:
        return r
    pk = collection("PRODUCT")
    tt = bpy.data.objects.new("TURNTABLE", None)
    tt.empty_display_type, tt.empty_display_size = "CIRCLE", 0.05
    r = bpy.data.objects.new("PRODUCT_ROOT", None)
    r.empty_display_size = 0.02
    pk.objects.link(tt)
    pk.objects.link(r)
    r.parent = tt
    r["front"] = "-Y"
    return r
