"""Test product specifications from real-world sizes (stand-ins for client models).

All sizes in mm, converted to meters when building meshes.
Number status: [F] fact from a datasheet (web research 2026-10-13), [D] estimate (no firm source yet).
Convention: origin at bottom center, front side (label logo) faces -Y.
"""
import math

SPEC = {
    # 330 ml "standard" can 66/52 x 115 (CanIt BB-CPS-330, biopineoe, aluminum-can.com)
    "can": dict(
        name="Standard 330 ml can",
        height_mm=115.2,          # [F] 115.2 ±0.3
        diameter_mm=66.2,         # [F] 66.0-66.3
        neck_mm=17.4,            # [F] necking length
        plug_mm=52.4,             # [F] inner neck diameter
        base_ring_mm=47.3,     # [F] 46.6-48.0
        dome_mm=10.0,            # [D] base dome depth
        brimful_ml=359,           # [F] info
        logo_mm=(35.0, 80.0), line_mm=(20.0, 26.0), color_z_mm=88.0,  # [D] test label layout
        source="canit.co.uk BB-CPS-330-A119; biopineoe.com; aluminum-can.com",
    ),
    # 330 ml longneck bottle, 26 mm crown (Vetropack 31748, sbi4beer Longneck 33cl 216g)
    "bottle": dict(
        name="Longneck bottle 330 ml",
        height_mm=226.5,          # [F] 225-227 (glass height to rim)
        diameter_mm=60.4,         # [F] 60.2-60.4
        crown_mm=26.0,            # [F] finish ISO 26 H 180
        cap_mm=32.1,            # [D] diameter of the fitted crown cap
        body_height_mm=112.0,    # [D] end of cylindrical body / start of shoulder
        neck_height_mm=165.0,    # [D] start of straight neck
        label_mm=(38.0, 102.0),   # [D] body label height
        wall_mm=2.5,           # [D] glass wall thickness (glass bottles typically 2-4 mm); C-11: not solid glass
        fill_mm=186.5,             # [D] liquid surface height (±40 mm below the rim, in the neck)
        total_height_mm=226.5 + 0.6,  # crown cap sits 0.6 mm above the rim
        logo_mm=(55.0, 90.0), line_mm=(43.0, 48.0), color_z_mm=96.0,  # [D] test label layout
        source="catalog.vetropack.com 31748; sbi4beer.com Longneck-33cl-216g; berlinpackaging.eu",
    ),
    # ---- Task 4 curriculum (web research 2026-10-13). [F*] = explicit number in a search result snippet;
    # the source page could not be opened from the cloud (DNS refused), so re-verify on the laptop. ----
    # UHT milk carton 200 ml (Tetra Brik Aseptic 200 Slim format). Tetra Pak does NOT publish package dimensions:
    # all numbers [D], checked only via volume (52 x 36 x 113.5 mm = 212 ml > 200 ml + headspace).
    "milk_carton": dict(
        name="UHT milk carton 200 ml",
        shape="box",
        width_mm=52.0,            # [D] front side (logo)
        thickness_mm=36.0,            # [D]
        height_mm=115.0,          # [D] including top seal fin
        fin_mm=1.5,             # [D] top seal fin, folded flat
        logo_mm=(55.0, 85.0), line_mm=(40.0, 46.0), color_z_mm=95.0,
        source="tetrapak.com TBA 200 Slim (no public dimensions); all [D]",
    ),
    # 314 ml glass jam jar, TO63 lug cap (Berlin Packaging / Raja 314 ml TO63 H10 flint)
    "jam_jar": dict(
        name="Glass jam jar 314 ml TO63",
        height_mm=98.5,           # [F*] glass height
        diameter_mm=76.8,         # [F*] maximum diameter
        finish_mm=63.0,           # [F*] TO63
        cap_mm=66.0,            # [D] lug cap skirt diameter
        cap_height_mm=11.0,     # [D]
        cap_rise_mm=1.0,        # [D] cap protrudes above the glass rim
        wall_mm=3.0,           # [D] jar glass 2.5-4 mm (glass weight 200 g [F*])
        fill_mm=78.0,              # [D] jam surface, below the shoulder
        label_mm=(25.0, 65.0),    # [D]
        total_height_mm=98.5 + 1.0,
        logo_mm=(38.0, 56.0), line_mm=(29.0, 32.0), color_z_mm=60.0,
        source="berlinpackaging.eu king-314ml-to-63-reg-flint (98,5 x 76,8 mm, 200 g)",
    ),
    # 100 ml D40 cosmetic tube, standing on a flip-top cap; top end flattened (seal)
    "tube": dict(
        name="Cosmetic tube 100 ml D40",
        shape="flat",
        diameter_mm=40.0,         # [F*] extruded tube D40 (emballator.com exttube-40)
        length_mm=125.0,         # [D] 90-180 mm for 60-150 ml; 100 ml ~120-130 mm
        width_mm=40.0 * math.pi / 2,  # [D] seal = half the perimeter (perimeter is preserved when flattened) = 62.8
        seal_thickness_mm=1.2,        # [D] two wall layers
        seal_mm=8.0,              # [D] seal band height
        cap_mm=40.0,            # [D] flip-top as wide as the tube
        cap_height_mm=22.0,     # [D]
        height_mm=22.0 + 125.0,
        thickness_mm=40.0,
        logo_mm=(68.0, 92.0), line_mm=(56.0, 59.0), color_z_mm=51.0,
        source="emballator.com exttube-40; packagingsolutions.amcor.com 40mm flip-top (neck 22 mm)",
    ),
    # Clear PET bottle 600 ml (baseline: PET 20 oz/591 ml, 28 mm PCO neck, US Plastic item 132340) + water
    "pet_bottle": dict(
        name="PET water bottle 600 ml",
        height_mm=200.8,          # [F*] 7.906 in (without cap)
        diameter_mm=71.4,         # [F*] 2.812 in
        finish_mm=27.4,           # [D] outer thread 28 mm PCO
        cap_mm=30.5,            # [D]
        cap_height_mm=16.0,     # [D]
        cap_rise_mm=1.5,        # [D]
        wall_mm=0.35,          # [D] PET body wall 0.25-0.4 mm; preform neck ~2.9 mm
        fill_mm=172.0,             # [D] water surface at the shoulder
        label_mm=(60.0, 125.0),   # [D] film label
        total_height_mm=200.8 + 1.5,
        logo_mm=(78.0, 105.0), line_mm=(66.0, 69.0), color_z_mm=115.0,
        source="usplastic.com item 132340 (20 oz PET 28mm PCO); petainer.com 28mm PCO 1881",
    ),
    # Slim 250 ml can 202 (Ardagh 53/250 via Nomoq; Crown 250ml slim; Ajanta 134 x 53.4)
    "slim_can": dict(
        name="Slim can 250 ml",
        height_mm=134.0,          # [F*] 134.0 +-0.4 (seamed)
        diameter_mm=53.4,         # [F*] max outer body diameter
        plug_mm=50.0,             # [F*] neck plug diameter
        neck_mm=12.0,            # [D] necking length
        base_ring_mm=40.0,     # [D]
        dome_mm=8.0,             # [D]
        logo_mm=(40.0, 92.0), line_mm=(24.0, 30.0), color_z_mm=103.0,
        source="help.nomoq.com 04_5_1_53_250_1_01 (Ardagh); crowncork.com 83oz-250ml-slim; ajantabottle.com",
    ),
}


PRODUCT = tuple(SPEC)
NEW = ("milk_carton", "jam_jar", "tube", "pet_bottle", "slim_can")  # Task 4 curriculum


def total_height_mm(name):
    """Finished product height (including cap) expected by the dimension QC."""
    s = SPEC[name]
    return s.get("total_height_mm", s["height_mm"])


def logo(name):
    """Logo position: (u in UV, logo center height in m). Used by QC-04 (logo facing camera)."""
    z0, z1 = SPEC[name]["logo_mm"]
    return (0.5, (z0 + z1) / 2000)


def front_mm(name, z):
    """Distance from the front surface (label) to the axis at height z (mm)."""
    s = SPEC[name]
    if s.get("shape") == "box":
        return s["thickness_mm"] / 2
    if name == "tube":
        from .profile import tube_ab
        return tube_ab(s, z)[1]
    if "label_mm" in s:  # glued/film label on the outer body
        return s["diameter_mm"] / 2 + 0.25
    return s["diameter_mm"] / 2


def color_points(name):
    """Label surface point (m, product local space) on the front side, away from logo and line: QC color sample."""
    z = SPEC[name]["color_z_mm"]
    return (0.0, -front_mm(name, z) / 1000, z / 1000)


def spec_qc(name):
    """Spec for QC-07: round products -> diameter; box/flat -> width (X, front side) and thickness (Y)."""
    s = SPEC[name]
    if s.get("shape") in ("box", "flat"):
        return dict(spec_width_mm=s["width_mm"], spec_thickness_mm=s["thickness_mm"])
    return dict(spec_diameter_mm=s["diameter_mm"])
