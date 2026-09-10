"""Build the Volare baseline Blender scene from the supplied STLs.

Run headless:

    blender --background --python cad/blender/build_scene.py

or with options:

    blender -b -P cad/blender/build_scene.py -- --out cad/out/volare_baseline.blend

What it does
------------
* Reads both STLs with the project's own numpy reader rather than Blender's STL
  importer, so the mesh Blender sees is bit-identical to the one the analysis
  scripts measured. No import operator, no axis-convention surprises.
* Splits FULLCOCPITV1_3 into its 17 loose parts and names each one after the CFD
  wall zone it will become (note 01 section 5).
* Puts everything in the canonical boat frame: X forward, Y port, Z up, origin at
  centreline x hull mid-length x keel. Scene units are metres, displayed in mm.
* Locks the organiser-supplied parts (ENERGY_REQ_3) so they cannot be edited.
* Adds reference geometry the STL gets wrong or omits: the true round D104 poles,
  the ENERGY_REQ_38-compliant rail positions, and a seated-pilot envelope.
* Re-measures every part inside Blender and asserts it against the numpy values,
  so a silent unit or transform error cannot get past this script.
"""
import json
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "cad" / "scripts"))

import geom            # noqa: E402
import parts as P      # noqa: E402
import volare as V     # noqa: E402

MM = 0.001             # scene works in metres; all source data is mm

COLLECTIONS = {
    "SUPPLIED":  (0.55, 0.55, 0.58, 1.0),   # organiser hardware - do not modify
    "COCKPIT":   (0.85, 0.80, 0.62, 1.0),   # the pod shell
    "FRAME":     (0.35, 0.55, 0.80, 1.0),   # rails, pads, clamps - ours
    "PROPOSED":  (0.30, 0.75, 0.45, 1.0),   # rule-compliant replacements
    "REFERENCE": (0.80, 0.35, 0.35, 1.0),   # non-physical: envelopes, datums
}

# Placeholder anthropometry - 95th-percentile seated male plus a helmet.
# REPLACE with the actual pilot's measurements before any clearance call is
# treated as final. Drives the egress opening and the ENERGY_REQ_25 500 mm
# energy-container standoff.
PILOT = {
    "seated_height_mm": 970.0,
    "helmet_add_mm": 60.0,
    "bideltoid_mm": 510.0,
    "buttock_to_toe_mm": 1100.0,
    "hip_x_mm": 250.0,        # seat reference point, forward of the pod centroid
}


# --------------------------------------------------------------- scene helpers

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.unit_settings.system = "METRIC"
    s.unit_settings.scale_length = 1.0
    s.unit_settings.length_unit = "MILLIMETERS"
    return s


def get_collection(name):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def get_material(name, rgba, alpha=1.0):
    key = f"mat_{name}"
    if key in bpy.data.materials:
        return bpy.data.materials[key]
    m = bpy.data.materials.new(key)          # already node-backed in 4.x/5.x
    bsdf = m.node_tree.nodes.get("Principled BSDF") if m.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.45
        if alpha < 1.0 and "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
    m.diffuse_color = rgba
    if alpha < 1.0:
        m.blend_method = "BLEND"
    return m


def add_mesh(name, verts_mm, faces, collection, rgba, alpha=1.0, smooth=False):
    """verts_mm is (N,3) in mm, boat frame. Scaled to metres on the way in."""
    me = bpy.data.meshes.new(name)
    me.from_pydata((np.asarray(verts_mm, float) * MM).tolist(), [],
                   [list(map(int, f)) for f in faces])
    me.update()
    me.validate(verbose=False)
    ob = bpy.data.objects.new(name, me)
    # Key the material on the COLOUR, not the collection: keying on collection
    # silently gives every object in a multi-colour collection whichever material
    # was created first, which is how the parametric pod ended up fairing-blue.
    key = "_".join(f"{c:.3f}" for c in tuple(rgba) + (alpha,))
    ob.data.materials.append(get_material(key, rgba, alpha))
    collection.objects.link(ob)
    if smooth:
        try:
            me.shade_smooth()
        except AttributeError:
            for p in me.polygons:
                p.use_smooth = True
    return ob


def add_tri_soup(name, T_mm, collection, rgba, alpha=1.0):
    """Welded triangle soup -> Blender object."""
    Vt, F = geom.weld(T_mm)
    return add_mesh(name, Vt, F, collection, rgba, alpha)


def box_mesh(cen_mm, size_mm):
    cx, cy, cz = cen_mm
    hx, hy, hz = (s / 2.0 for s in size_mm)
    v = [(cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),
         (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz),
         (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
         (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, f


def cylinder_mesh(cen_mm, dia_mm, length_mm, axis=1, n=48):
    """Capped cylinder with its axis along `axis` (0=X, 1=Y, 2=Z)."""
    r = dia_mm / 2.0
    h = length_mm / 2.0
    a, b = [i for i in range(3) if i != axis]
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    v = []
    for s in (-h, +h):
        for t in th:
            p = [0.0, 0.0, 0.0]
            p[axis] = cen_mm[axis] + s
            p[a] = cen_mm[a] + r * np.cos(t)
            p[b] = cen_mm[b] + r * np.sin(t)
            v.append(tuple(p))
    f = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    f.append(tuple(range(n - 1, -1, -1)))
    f.append(tuple(range(n, 2 * n)))
    return v, f


def tag(ob, **props):
    for k, val in props.items():
        ob[k] = val


def lock(ob):
    ob.lock_location = ob.lock_rotation = ob.lock_scale = (True, True, True)
    ob.hide_select = True


# ------------------------------------------------------------------ scene body

def build_supplied_and_frame(report):
    """The 17 STL parts, named and filed."""
    plist = P.split_assembly()
    for p in plist:
        coll = get_collection(p["collection"])
        ob = add_tri_soup(p["name"], p["tris"], coll, COLLECTIONS[p["collection"]])
        tag(ob, cfd_zone=p["cfd_zone"], supplied=p["supplied"],
            source="FULLCOCPITV1_3.stl",
            area_m2_numpy=p["area_m2"], volume_L_numpy=p["volume_L"])
        if p["supplied"]:
            lock(ob)
        report["parts"].append({
            "name": p["name"], "collection": p["collection"],
            "cfd_zone": p["cfd_zone"], "supplied": p["supplied"],
            "triangles": p["triangles"], "area_m2_numpy": p["area_m2"],
        })
    return plist


def build_reference(report):
    """Geometry the STL gets wrong or leaves out."""
    ref = get_collection("REFERENCE")
    prop = get_collection("PROPOSED")
    rgba_ref, rgba_prop = COLLECTIONS["REFERENCE"], COLLECTIONS["PROPOSED"]

    # 1. The crossbeams are ROUND D104 poles (ENERGY_REQ_3). The STL models them
    #    as 104 x 104 square boxes, which is why note 00 charges them C_D 2.05
    #    instead of the ~1.2 a subcritical circular cylinder actually sees.
    for which in ("fwd", "aft"):
        b = V.BASELINE[f"beam_{which}"]
        cen = (b["x"], 0.0, (b["z_bottom"] + b["z_top"]) / 2.0)
        v, f = cylinder_mesh(cen, V.BEAM_DIAMETER, b["length"], axis=1)
        ob = add_mesh(f"beam_{which}_round_REF", v, f, ref, rgba_ref, alpha=0.5, smooth=True)
        ob.display_type = "WIRE"
        tag(ob, note="true round D104 pole per ENERGY_REQ_3; the STL models a square box",
            cfd_zone=f"beam-{which}")
        lock(ob)

    # 2. Rails moved outboard to satisfy the >=750 mm clamp spacing (ENERGY_REQ_38).
    r = V.BASELINE["rail"]
    dy = (V.CLAMP_MIN_SPACING - r["spacing_cc"]) / 2.0
    for side, sgn in (("port", +1), ("stbd", -1)):
        cen = (-485.3, sgn * V.CLAMP_MIN_SPACING / 2.0,
               (r["z_bottom"] + r["z_top"]) / 2.0)
        v, f = box_mesh(cen, (r["length"], r["width"], r["height"]))
        ob = add_mesh(f"rail_{side}_750_PROPOSED", v, f, prop, rgba_prop, alpha=0.6)
        ob.display_type = "WIRE"
        tag(ob, note=f"rail moved {dy:.0f} mm outboard to reach the 750 mm clamp "
                     f"spacing required by ENERGY_REQ_38", cfd_zone=f"rail-{side}")

    # 3. Seated-pilot envelope - placeholder anthropometry, see PILOT.
    hz = PILOT["seated_height_mm"] + PILOT["helmet_add_mm"]
    cen = (V.BASELINE["pod"]["x_nose"] - 1250.0 + PILOT["hip_x_mm"], 0.0,
           V.BASELINE["pod"]["z_floor"] + hz / 2.0)
    v, f = box_mesh(cen, (PILOT["buttock_to_toe_mm"], PILOT["bideltoid_mm"], hz))
    ob = add_mesh("pilot_envelope_REF", v, f, ref, rgba_ref, alpha=0.35)
    ob.display_type = "WIRE"
    tag(ob, note="PLACEHOLDER 95th-percentile seated male + helmet. Replace with the "
                 "real pilot before treating any clearance as final.",
        drives="egress opening, ENERGY_REQ_25 500 mm energy standoff")
    lock(ob)

    # 4. The 500 mm keep-out sphere around the pilot (ENERGY_REQ_25).
    v, f = box_mesh(cen, (PILOT["buttock_to_toe_mm"] + 1000.0,
                          PILOT["bideltoid_mm"] + 1000.0, hz + 1000.0))
    ob = add_mesh("energy_keepout_500_REF", v, f, ref, rgba_ref, alpha=0.12)
    ob.display_type = "WIRE"
    tag(ob, note="ENERGY_REQ_25: no energy container inside this volume")
    lock(ob)

    report["reference"] = {
        "round_poles_added": True,
        "rail_outboard_move_mm": dy,
        "pilot_envelope_mm": [PILOT["buttock_to_toe_mm"], PILOT["bideltoid_mm"], hz],
        "pilot_anthropometry": "PLACEHOLDER - replace with the real pilot",
    }


# ----------------------------------------------------------------- verification

def blender_area_m2(ob):
    """Surface area straight out of Blender, in m^2, with the object transform."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    a = sum(f.calc_area() for f in bm.faces)
    bm.free()
    return a


def verify(plist, report):
    """Blender's own measurement must agree with numpy, or the transform is wrong."""
    worst = 0.0
    rows = []
    for p in plist:
        ob = bpy.data.objects.get(p["name"])
        if ob is None:
            rows.append((p["name"], None, None, "MISSING"))
            worst = 1.0
            continue
        a_bl = blender_area_m2(ob)
        a_np = p["area_m2"]
        err = abs(a_bl - a_np) / max(a_np, 1e-9)
        worst = max(worst, err)
        rows.append((p["name"], a_np, a_bl, f"{err * 100:.4f}%"))
    report["verification"] = {
        "worst_area_error_pct": worst * 100,
        "passed": bool(worst < 1e-4),
        "rows": [{"name": n, "numpy_m2": a, "blender_m2": b, "err": e} for n, a, b, e in rows],
    }
    return rows, worst


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_blend = ROOT / "cad" / "out" / "volare_baseline.blend"
    if "--out" in argv:
        out_blend = Path(argv[argv.index("--out") + 1]).resolve()
    out_blend.parent.mkdir(parents=True, exist_ok=True)

    reset_scene()
    for name in COLLECTIONS:
        get_collection(name)

    report = {"frame": "X forward, Y port, Z up; origin = centreline x hull mid-length x keel",
              "units": "scene in metres, displayed in mm", "parts": []}

    print("\n[build_scene] splitting the assembly ...")
    plist = build_supplied_and_frame(report)
    print(f"[build_scene] {len(plist)} parts built")

    print("[build_scene] adding reference and proposed geometry ...")
    build_reference(report)

    print("[build_scene] verifying Blender vs numpy ...")
    rows, worst = verify(plist, report)
    print(f"\n  {'part':<20}{'numpy m2':>12}{'blender m2':>13}{'error':>11}")
    print("  " + "-" * 55)
    for n, a, b, e in rows:
        if a is None:
            print(f"  {n:<20}{'-':>12}{'-':>13}{e:>11}")
        else:
            print(f"  {n:<20}{a:>12.4f}{b:>13.4f}{e:>11}")
    ok = worst < 1e-4
    print(f"  {'-' * 55}\n  {'PASS' if ok else 'FAIL'}  worst error {worst * 100:.5f}%")

    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    (out_blend.with_suffix(".json")).write_text(json.dumps(report, indent=2))
    print(f"\n[build_scene] saved {out_blend}")
    print(f"[build_scene] saved {out_blend.with_suffix('.json')}")

    n_obj = len(bpy.context.scene.objects)
    print(f"[build_scene] {n_obj} objects across {len(COLLECTIONS)} collections")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
