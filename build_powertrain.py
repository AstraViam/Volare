"""
build_powertrain.py -- the powertrain scene, headless.

    blender --background --python blender/build_powertrain.py

Reads out/powertrain.json, which scripts/powertrain.py produced from the
shared parameter file. Blender is a CONSUMER here: it draws what the numpy
model decided and re-measures every part to prove it drew the right thing.

WHY IT RE-MEASURES
------------------
build_scene.py already does this for the hull, and the reason is the same: a
unit slip or a transform error produces a scene that looks plausible and is
wrong by a factor of ten or a hundred. Blender works in metres and this model
is in millimetres, so there is exactly one conversion and it is the obvious
place to make that mistake.

So every box is measured after creation and compared with the JSON. A
disagreement over 0.01% aborts the build rather than saving a .blend that
somebody will later take a screenshot of.

COLLECTIONS
    POWERTRAIN_HV        pack, container, terminal box, PDU, inverter, motor
    POWERTRAIN_LV        DC-DC, service battery, VCU, E-stop
    POWERTRAIN_COOLING   pump, heat exchanger
    POWERTRAIN_CABLE     HV and three-phase runs, as swept curves
    POWERTRAIN_STRUCTURE bulkhead
    POWERTRAIN_ORGANISER the ENERGY_REQ_185 reservation
"""

import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out")

MM = 0.001          # the one and only unit conversion
TOL = 1e-4          # 0.01 % on dimensions

# Blender stores mesh coordinates as float32, so a 1 m part carries about
# 1e-7 m of representation error -- 1e-4 mm. A position tolerance tighter
# than that reports a mismatch between two numbers that print identically,
# which is worse than no check: it trains you to ignore the output.
POS_TOL_MM = 0.005


# ---------------------------------------------------------------------------
#  Scene
# ---------------------------------------------------------------------------

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.length_unit = "MILLIMETERS"


def collection(name, colour=None):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    if colour:
        c.color_tag = colour
    return c


ZONE_COLLECTION = {
    "HV":        ("POWERTRAIN_HV", "COLOR_01"),
    "LV":        ("POWERTRAIN_LV", "COLOR_04"),
    "COOLING":   ("POWERTRAIN_COOLING", "COLOR_05"),
    "STRUCTURE": ("POWERTRAIN_STRUCTURE", "COLOR_03"),
    "ORGANISER": ("POWERTRAIN_ORGANISER", "COLOR_02"),
}

ZONE_RGBA = {
    "HV":        (0.85, 0.25, 0.15, 1.0),   # orange, ENERGY_REQ_61
    "LV":        (0.20, 0.45, 0.80, 1.0),
    "COOLING":   (0.15, 0.65, 0.70, 1.0),
    "STRUCTURE": (0.55, 0.55, 0.58, 1.0),
    "ORGANISER": (0.90, 0.75, 0.15, 1.0),
}


def material(name, rgba, alpha=1.0):
    """A material that reads correctly in BOTH renderers.

    Workbench -- which the view script uses, because it is fast and
    deterministic -- colours by `diffuse_color`, the viewport display
    colour. EEVEE and Cycles read the Principled BSDF node. Setting only
    the node produces a scene that looks right in one renderer and
    uniformly grey in the other, which is how the first set of powertrain
    views came out.
    """
    if name in bpy.data.materials:
        return bpy.data.materials[name]

    m = bpy.data.materials.new(name)
    m.use_nodes = True

    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = 0.45

    # Workbench reads these two.
    m.diffuse_color = rgba
    m.roughness = 0.45

    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
        m.diffuse_color = (rgba[0], rgba[1], rgba[2], alpha)

    return m


# ---------------------------------------------------------------------------
#  Parts
# ---------------------------------------------------------------------------

def add_box(part):
    """One component, as a box, in metres."""
    size = [v * MM for v in part["size"]]
    centre = [v * MM for v in part["centre"]]

    mesh = bpy.data.meshes.new(part["name"])
    obj = bpy.data.objects.new(part["name"], mesh)

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()

    obj.scale = Vector(size)
    obj.location = Vector(centre)

    zone = part["zone"]

    # An enclosure that is drawn solid hides everything inside it, and the
    # whole point of modelling the container and the PDU is to see what is
    # in them. Enclosures that have children are drawn transparent.
    is_host = part["name"] in HOSTS
    mat = material(
        f"PT_{zone}" + ("_shell" if is_host else ""),
        ZONE_RGBA[zone], 0.18 if is_host else 1.0)
    obj.data.materials.append(mat)

    if is_host:
        # Tagged rather than set to WIRE: Workbench renders a WIRE object
        # as solid anyway, so the pack stayed hidden inside its container.
        # render_powertrain.py hides these for the internals view instead.
        obj["is_enclosure"] = True
        obj.display_type = "WIRE"

    cname, ccol = ZONE_COLLECTION[zone]
    collection(cname, ccol).objects.link(obj)

    obj["mass_kg"] = part["mass_kg"]
    obj["zone"] = zone
    obj["note"] = part.get("note", "")
    if part.get("parent"):
        obj["enclosed_by"] = part["parent"]

    return obj


def add_cable(run):
    """One cable, as a swept circular profile along the polyline."""
    curve = bpy.data.curves.new(run["name"], "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = run["od_mm"] * MM / 2.0
    curve.bevel_resolution = 6
    curve.use_fill_caps = True

    spline = curve.splines.new("POLY")
    pts = run["points"]
    spline.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        spline.points[i].co = (p[0] * MM, p[1] * MM, p[2] * MM, 1.0)

    obj = bpy.data.objects.new(run["name"], curve)

    # ENERGY_REQ_61: every HV run outside the enclosure is orange.
    obj.data.materials.append(material("PT_CABLE_HV", (0.95, 0.35, 0.05, 1.0)))

    collection("POWERTRAIN_CABLE", "COLOR_01").objects.link(obj)

    obj["length_mm"] = run["length_mm"]
    obj["od_mm"] = run["od_mm"]
    obj["note"] = run.get("note", "")

    return obj


# ---------------------------------------------------------------------------
#  Verify
# ---------------------------------------------------------------------------

def verify(objects, data):
    """Re-measure everything Blender drew against the JSON it came from."""
    problems = []

    deps = bpy.context.evaluated_depsgraph_get()

    for part in data["parts"]:
        obj = objects.get(part["name"])
        if obj is None:
            problems.append(f"{part['name']}: not created")
            continue

        ev = obj.evaluated_get(deps)
        bb = [ev.matrix_world @ Vector(c) for c in ev.bound_box]

        for axis in range(3):
            vals = [v[axis] for v in bb]
            measured = (max(vals) - min(vals)) / MM
            expected = part["size"][axis]
            if abs(measured - expected) > max(TOL * expected, POS_TOL_MM):
                problems.append(
                    f"{part['name']}: axis {axis} measures {measured:.3f} mm, "
                    f"JSON says {expected:.3f} mm")

            centre = (max(vals) + min(vals)) / 2.0 / MM
            if abs(centre - part["centre"][axis]) > POS_TOL_MM:
                problems.append(
                    f"{part['name']}: axis {axis} centred at {centre:.3f} mm, "
                    f"JSON says {part['centre'][axis]:.3f} mm")

    return problems


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------

def main():
    src = os.path.join(OUT, "powertrain.json")

    if not os.path.isfile(src):
        print(f"ERROR: {src} not found.")
        print("Run:  python scripts/powertrain.py")
        sys.exit(1)

    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    global HOSTS
    HOSTS = {p["parent"] for p in data["parts"] if p.get("parent")}

    reset_scene()

    objects = {}
    for part in data["parts"]:
        objects[part["name"]] = add_box(part)

    for run in data["cables"]:
        add_cable(run)

    problems = verify(objects, data)

    print()
    print("=" * 70)
    print(" BLENDER POWERTRAIN BUILD")
    print("=" * 70)
    print(f" {len(data['parts'])} parts, {len(data['cables'])} cable runs")
    print(f" {data['mass_kg']:.1f} kg, CG "
          f"X={data['cg_mm'][0]:.0f} Y={data['cg_mm'][1]:.0f} "
          f"Z={data['cg_mm'][2]:.0f} mm")
    print(f" frame: {data['frame']}")

    if problems:
        print(f"\n {len(problems)} GEOMETRY MISMATCH(ES):")
        for p in problems:
            print(f"   {p}")
        print("\n Not saving. A scene that disagrees with the model it was")
        print(" built from is worse than no scene -- somebody will screenshot")
        print(" it.")
        print("=" * 70)
        sys.exit(1)

    print(f"\n every part re-measured and agrees with the model to "
          f"{TOL*100:.2f}%")

    blend = os.path.join(OUT, "volare_powertrain.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print(f"\n saved {blend}")
    print("=" * 70)


if __name__ == "__main__":
    main()
