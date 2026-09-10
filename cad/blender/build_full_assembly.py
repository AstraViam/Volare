"""
build_full_assembly.py -- the whole boat: supplied hardware, cockpit, powertrain.

    blender --background --python blender/build_full_assembly.py

This is the scene to look at. build_scene.py builds the supplied hull and
cockpit; build_powertrain.py builds the powertrain in isolation. Neither on
its own answers the question that actually matters, which is whether the
powertrain fits in the boat.

It reuses both existing pipelines rather than reimplementing either:

    scripts/parts.py       splits FULLCOCPITV1_3.stl into 17 named parts and
                           puts them in the canonical frame
    out/powertrain.json    scripts/powertrain.py's placed components

Both are already in X-forward, Y-port, Z-up with the origin on the keel at
hull mid-length, so no registration happens here. If that were done again in
this file it would be a third copy of a transform that is already verified
against three independently derived numbers in the notes.

WHAT IT ADDS OVER THE TWO SEPARATE SCENES
-----------------------------------------
The interference check between the powertrain and the real hull geometry.
scripts/powertrain.py checks components against each other and against
planes -- the bulkhead station, the seat station -- because it is working
with boxes. It cannot tell whether the outboard bracket clears the actual
transom, because it has no transom. This can.
"""

import json
import os
import sys

import numpy as np

import bpy
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out")

sys.path.insert(0, os.path.join(ROOT, "scripts"))

import volare as V          # noqa: E402
import parts as P           # noqa: E402

MM = 0.001
POS_TOL_MM = 0.005

HULL_RGBA = (0.72, 0.74, 0.78, 1.0)
POD_RGBA = (0.36, 0.40, 0.46, 1.0)

ZONE_RGBA = {
    "HV":        (0.85, 0.25, 0.15, 1.0),
    "LV":        (0.20, 0.45, 0.80, 1.0),
    "COOLING":   (0.15, 0.65, 0.70, 1.0),
    "STRUCTURE": (0.55, 0.55, 0.58, 1.0),
    "ORGANISER": (0.90, 0.75, 0.15, 1.0),
}


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


def material(name, rgba, alpha=1.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = 0.5
    # Workbench reads diffuse_color, EEVEE reads the node. Set both or the
    # scene is grey in one renderer and coloured in the other.
    m.diffuse_color = rgba
    m.roughness = 0.5
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
        m.diffuse_color = (rgba[0], rgba[1], rgba[2], alpha)
    return m


def add_tri_soup(name, T_mm, coll, rgba, alpha=1.0):
    """A triangle array straight from the STL splitter."""
    verts = (np.asarray(T_mm, float).reshape(-1, 3) * MM).tolist()
    faces = [(i, i + 1, i + 2) for i in range(0, len(verts), 3)]

    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()

    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(material(f"M_{name}", rgba, alpha))
    coll.objects.link(ob)
    return ob


def add_box(part):
    size = [v * MM for v in part["size"]]
    centre = [v * MM for v in part["centre"]]

    me = bpy.data.meshes.new(part["name"])
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()

    ob = bpy.data.objects.new(part["name"], me)
    ob.scale = Vector(size)
    ob.location = Vector(centre)

    zone = part["zone"]
    is_host = part["name"] in HOSTS

    ob.data.materials.append(material(
        f"PT_{zone}" + ("_shell" if is_host else ""),
        ZONE_RGBA[zone], 0.20 if is_host else 1.0))

    if is_host:
        ob["is_enclosure"] = True

    collection("POWERTRAIN", "COLOR_01").objects.link(ob)

    ob["mass_kg"] = part["mass_kg"]
    ob["zone"] = zone
    ob["note"] = part.get("note", "")
    return ob


def add_cable(run):
    cu = bpy.data.curves.new(run["name"], "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = run["od_mm"] * MM / 2.0
    cu.bevel_resolution = 5
    cu.use_fill_caps = True

    sp = cu.splines.new("POLY")
    pts = run["points"]
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0] * MM, p[1] * MM, p[2] * MM, 1.0)

    ob = bpy.data.objects.new(run["name"], cu)
    ob.data.materials.append(material("PT_CABLE", (0.95, 0.35, 0.05, 1.0)))
    collection("POWERTRAIN_CABLE", "COLOR_01").objects.link(ob)
    return ob


# ---------------------------------------------------------------------------
#  Clearance between the powertrain and the real hull
# ---------------------------------------------------------------------------

def hull_clearance(plist, pt_parts):
    """Closest approach of each powertrain box to each supplied part.

    Vertex-to-box, not surface-to-surface. That understates a clash where a
    large triangle spans a box without any of its corners entering -- so a
    clean result here is necessary and not sufficient, and the number is
    reported as an indication rather than a proof.
    """
    rows = []

    for part in pt_parts:
        lo = np.array(part["centre"]) - np.array(part["size"]) / 2.0
        hi = np.array(part["centre"]) + np.array(part["size"]) / 2.0

        worst = np.inf
        worst_name = ""

        for sp in plist:
            Vtx = sp["tris"].reshape(-1, 3)

            # distance from each vertex to the box, zero if inside
            d = np.maximum(np.maximum(lo - Vtx, Vtx - hi), 0.0)
            dist = np.linalg.norm(d, axis=1)

            m = float(dist.min())
            if m < worst:
                worst, worst_name = m, sp["name"]

        rows.append((part["name"], worst, worst_name))

    return rows


def main():
    src = os.path.join(OUT, "powertrain.json")

    if not os.path.isfile(src):
        print(f"ERROR: {src} not found. Run: python scripts/powertrain.py")
        sys.exit(1)

    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    global HOSTS
    HOSTS = {p["parent"] for p in data["parts"] if p.get("parent")}

    reset_scene()

    # --- supplied hardware and cockpit, from the STL ---------------------
    plist = P.split_assembly()

    supplied = collection("SUPPLIED", "COLOR_04")
    cockpit = collection("COCKPIT", "COLOR_03")

    for sp in plist:
        is_supplied = sp["collection"].upper().startswith("SUPPLIED")
        add_tri_soup(sp["name"], sp["tris"],
                     supplied if is_supplied else cockpit,
                     HULL_RGBA if is_supplied else POD_RGBA,
                     alpha=1.0 if is_supplied else 0.30)

    # --- powertrain ------------------------------------------------------
    for part in data["parts"]:
        add_box(part)
    for run in data["cables"]:
        add_cable(run)

    # --- does it fit? -----------------------------------------------------
    rows = hull_clearance(plist, data["parts"])
    rows.sort(key=lambda r: r[1])

    print()
    print("=" * 74)
    print(" VOLARE FULL ASSEMBLY")
    print("=" * 74)
    print(f" {len(plist)} supplied and cockpit parts from FULLCOCPITV1_3.stl")
    print(f" {len(data['parts'])} powertrain components, "
          f"{len(data['cables'])} cable runs")
    print(f" powertrain {data['mass_kg']:.1f} kg, CG "
          f"X={data['cg_mm'][0]:.0f} Y={data['cg_mm'][1]:.0f} "
          f"Z={data['cg_mm'][2]:.0f} mm")

    print("\n CLOSEST APPROACH TO THE SUPPLIED GEOMETRY\n")
    print(f"   {'component':<22}{'mm':>9}   nearest part")

    clashes = 0
    for name, d, near in rows[:12]:
        flag = "  CLASH" if d <= 0.0 else ""
        if d <= 0.0:
            clashes += 1
        print(f"   {name:<22}{d:>9.1f}   {near}{flag}")

    if clashes:
        print(f"\n {clashes} component(s) intersect the supplied geometry.")
        print(" The powertrain does not fit the boat as placed.")
    else:
        print(f"\n nothing intersects the hull or the cockpit shell")
        print(" (vertex-to-box test -- necessary, not sufficient)")

    blend = os.path.join(OUT, "volare_full_assembly.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print(f"\n saved {blend}")
    print("=" * 74)


if __name__ == "__main__":
    main()
