"""Build the ENERGY_REQ_38-compliant frame and check it clears everything.

    blender -b -P cad/blender/frame_redesign.py
    blender -b -P cad/blender/frame_redesign.py -- --out cad/out/volare_frame_v2.blend

Two problems are fixed together, because the fixes interact:

  * ENERGY_REQ_38 - clamps must be >= 750 mm apart. Rails move from +/-200 to
    +/-375 mm.
  * The 85.7 mm rail/pod interference. Note 00 prefers raising the pod onto
    discrete pads over moulding recess channels, so that is what is built here.

Raising the pod is what makes the rail move affordable: once the pod sits on top
of the rails instead of through them, the rails can be anywhere without cutting
the floor. The two fixes are cheaper together than either is alone.

Everything is reported as a clearance, not a boolean clash - a clash test tells
you something is wrong, a clearance tells you how much room you have to move.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "cad" / "scripts"))
sys.path.insert(0, str(HERE))

import build_scene as BS      # noqa: E402  - reuse its mesh/collection helpers
import geom                   # noqa: E402
import parts as P             # noqa: E402
import volare as V            # noqa: E402

# --- the redesign -------------------------------------------------------------
RAIL_Y = V.CLAMP_MIN_SPACING / 2.0        # 375 mm
RAIL_W = 100.0                            # 100 x 50 x 3 RHS, note 02 s4
RAIL_H = 50.0
PAD_MM = 10.0                             # standoff pad, pod floor onto rail top
CLAMP_W = 60.0                            # >= 50 mm, ENERGY_REQ_38
GASKET_MM = 2.0                           # >= 1 mm
CLAMP_WALL = 8.0
KEEL_W, KEEL_H = 60.0, 40.0               # centreline keel beam, option B

COLL = "FRAME_V2"
RGBA = (0.95, 0.55, 0.15, 1.0)


def stack_heights():
    """Work UP from the beams. The rail height is not a free choice.

    The clamps wrap the poles, the rails sit on the clamps, and the pod sits on
    pads on the rails. The two poles are at different heights (the forward one is
    91.4 mm lower), so a level rail has to be shimmed at the forward station -
    the beam step is not cosmetic, it sets the whole stack.
    """
    od = V.BEAM_DIAMETER + 2 * (GASKET_MM + CLAMP_WALL)
    tops = {}
    for which in ("fwd", "aft"):
        b = V.BASELINE[f"beam_{which}"]
        tops[which] = (b["z_bottom"] + b["z_top"]) / 2.0 + od / 2.0
    rail_bottom = max(tops.values())
    return {"clamp_od": od, "clamp_top": tops,
            "shim_fwd_mm": rail_bottom - tops["fwd"],
            "rail_bottom": rail_bottom,
            "rail_top": rail_bottom + RAIL_H,
            "pod_floor": rail_bottom + RAIL_H + PAD_MM}


def build():
    coll = BS.get_collection(COLL)
    rail = V.BASELINE["rail"]
    made = {}
    st = stack_heights()

    # 1. rails at +/-375, sitting on top of the clamps
    rail_top = st["rail_top"]
    rail_cz = rail_top - RAIL_H / 2.0
    for side, sgn in (("port", +1), ("stbd", -1)):
        v, f = BS.box_mesh((-485.3, sgn * RAIL_Y, rail_cz),
                           (rail["length"], RAIL_W, RAIL_H))
        ob = BS.add_mesh(f"rail_{side}_v2", v, f, coll, RGBA)
        BS.tag(ob, note=f"100x50x3 RHS at Y={sgn * RAIL_Y:+.0f}, ENERGY_REQ_38",
               cfd_zone=f"rail-{side}")
        made[ob.name] = ob

    # 2. two clamps per beam, symmetric, enveloping the full circumference
    od = st["clamp_od"]
    for which in ("fwd", "aft"):
        b = V.BASELINE[f"beam_{which}"]
        cz = (b["z_bottom"] + b["z_top"]) / 2.0
        for side, sgn in (("port", +1), ("stbd", -1)):
            v, f = BS.cylinder_mesh((b["x"], sgn * RAIL_Y, cz), od, CLAMP_W, axis=1)
            ob = BS.add_mesh(f"clamp_{which}_{side}", v, f, coll, RGBA, smooth=True)
            BS.tag(ob, note=f"{CLAMP_W:.0f} mm wide, envelops D{V.BEAM_DIAMETER:.0f} "
                            f"+ {GASKET_MM:.0f} mm gasket, at Y={sgn * RAIL_Y:+.0f}",
                   rule="ENERGY_REQ_38")
            made[ob.name] = ob

            # the forward pole sits lower, so a level rail needs a shim there
            if which == "fwd" and st["shim_fwd_mm"] > 1.0:
                sv, sf = BS.box_mesh(
                    (b["x"], sgn * RAIL_Y,
                     st["clamp_top"]["fwd"] + st["shim_fwd_mm"] / 2.0),
                    (CLAMP_W, RAIL_W, st["shim_fwd_mm"]))
                sob = BS.add_mesh(f"shim_fwd_{side}", sv, sf, coll, RGBA)
                BS.tag(sob, note=f"{st['shim_fwd_mm']:.1f} mm packer - the forward "
                                 f"pole sits that much lower than the aft one")
                made[sob.name] = sob

    # 3. centreline keel beam (frame.py option B) - also the seat mount
    v, f = BS.box_mesh((V.BASELINE["pod"]["x_nose"] - 1250.0, 0.0,
                        st["pod_floor"] + KEEL_H / 2.0),
                       (1200.0, KEEL_W, KEEL_H))
    ob = BS.add_mesh("keel_beam", v, f, coll, RGBA)
    BS.tag(ob, note="halves the floor span 750 -> 375 mm; doubles as the seat mount")
    made[ob.name] = ob
    return made, st


def clearances(st):
    """The numbers that decide whether this is buildable."""
    pod = V.BASELINE["pod"]
    hull = V.BASELINE["hull"]
    out = []

    def add(name, value, limit, sense, note=""):
        ok = value >= limit if sense == ">=" else value <= limit
        out.append({"check": name, "value_mm": value, "limit_mm": limit,
                    "sense": sense, "pass": bool(ok), "note": note})

    add("clamp spacing (c-c)", 2 * RAIL_Y, V.CLAMP_MIN_SPACING, ">=",
        "ENERGY_REQ_38; note 09 Q-TC-5 asks if this is c-c or inner-face")
    add("clamp width", CLAMP_W, V.CLAMP_MIN_WIDTH, ">=", "ENERGY_REQ_38")
    add("clamp gasket", GASKET_MM, 1.0, ">=", "ENERGY_REQ_38")
    add("pod floor above rail top", PAD_MM, 5.0, ">=",
        "was -85.7 mm, i.e. the rail passed through the floor")
    add("rail bottom above fwd clamp top",
        st["rail_bottom"] - st["clamp_top"]["fwd"], 0.0, ">=",
        "negative means the forward clamp fouls the rail")
    add("rail bottom above aft clamp top",
        st["rail_bottom"] - st["clamp_top"]["aft"], 0.0, ">=",
        "negative means the aft clamp fouls the rail")
    add("forward shim height", st["shim_fwd_mm"], 120.0, "<=",
        "forced by the 91.4 mm pole height step; a packer this tall is a "
        "structural part, not a washer - it carries 79% of the load "
        "(note 08 s1) and needs its own check")

    # rail must stay inboard of the hull inner face
    hull_inner = abs(hull["y_centres"][0]) - hull["beam"] / 2.0
    add("rail outer face to hull inner face",
        hull_inner - (RAIL_Y + RAIL_W / 2.0), 50.0, ">=",
        "room for the clamp bolts and a fairing")

    # how far the rail sticks out past the pod
    add("rail protrusion beyond pod edge",
        (RAIL_Y + RAIL_W / 2.0) - pod["beam_max"] / 2.0, 0.0, ">=",
        "positive means the rail is exposed and needs fairing (drag item)")

    # raising the pod raises everything above it
    add("pod crown after raising",
        pod["z_crown"] + (st["pod_floor"] - pod["z_floor"]),
        99999.0, "<=", "check against any air-draft or CG limit")

    # clamp must clear the pod shell in Y at the beam stations
    add("clamp inner face to pod edge",
        pod["beam_max"] / 2.0 - (RAIL_Y - CLAMP_W / 2.0), 0.0, ">=",
        "positive means the clamp tucks under the pod; negative means it needs "
        "an outboard bracket")
    return out


def supersede_baseline():
    """Retire the geometry FRAME_V2 replaces.

    Without this the scene carries three sets of rails at two different
    heights and nobody can read it. The originals stay as wireframe for
    reference; PROPOSED was only ever a marker for "rails belong further
    out", and FRAME_V2 now does that properly.
    """
    for n in ("rail_port", "rail_stbd"):
        ob = bpy.data.objects.get(n)
        if ob:
            ob.display_type = "WIRE"
            ob.hide_render = True
            ob["superseded_by"] = "rail_*_v2 (ENERGY_REQ_38)"
    prop = bpy.data.collections.get("PROPOSED")
    if prop:
        for ob in list(prop.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
    # the old rail pads sat on the old rail tops and are now floating
    for ob in list(bpy.data.objects):
        if ob.name.startswith("rail_pad_"):
            bpy.data.objects.remove(ob, do_unlink=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_blend = ROOT / "cad" / "out" / "volare_frame_v2.blend"
    if "--out" in argv:
        out_blend = Path(argv[argv.index("--out") + 1]).resolve()

    BS.reset_scene()
    for name in BS.COLLECTIONS:
        BS.get_collection(name)
    report = {"parts": []}
    plist = BS.build_supplied_and_frame(report)
    BS.build_reference(report)

    supersede_baseline()

    made, st = build()
    rail_top = st["rail_top"]

    # raise the pod onto the pads
    pod = bpy.data.objects.get("pod_shell")
    lift = st["pod_floor"] - V.BASELINE["pod"]["z_floor"]
    if pod:
        pod.location.z += lift * BS.MM
        pod["raised_mm"] = lift
        pod["note"] = ("raised onto discrete pads to clear the rails; "
                       "note 00 s1 option (b)")

    checks = clearances(st)

    # matrix_world is cached until the depsgraph re-evaluates, so without this the
    # measurements below read the pod's PRE-move position and silently agree with
    # the parametric checks. This line is the whole reason the measured check works.
    bpy.context.view_layer.update()

    # Measure the built result instead of trusting the parameters that built it.
    # The parametric checks above cannot catch a placement bug; these can.
    def world_z(name):
        o = bpy.data.objects.get(name)
        if o is None:
            return None
        zs = [(o.matrix_world @ Vector(c)).z / BS.MM for c in o.bound_box]
        return min(zs), max(zs)

    measured = {n: world_z(n) for n in
                ("pod_shell", "rail_port_v2", "clamp_fwd_port", "clamp_aft_port",
                 "shim_fwd_port", "beam_fwd", "beam_aft")}
    gap = None
    if measured["pod_shell"] and measured["rail_port_v2"]:
        gap = measured["pod_shell"][0] - measured["rail_port_v2"][1]
        checks.append({"check": "MEASURED pod floor over rail top",
                       "value_mm": gap, "limit_mm": 5.0, "sense": ">=",
                       "pass": bool(gap >= 5.0),
                       "note": "read off the built meshes, not the parameters"})
    print("\nFRAME V2 - CLEARANCES AND RULE CHECKS")
    print(f"  {'check':<38}{'value':>9}{'limit':>9}{'':>3}  result")
    print("  " + "-" * 72)
    for c in checks:
        print(f"  {c['check']:<38}{c['value_mm']:>9.1f}{c['limit_mm']:>9.1f}"
              f"{c['sense']:>3}  {'PASS' if c['pass'] else 'REVIEW'}")
    print("  " + "-" * 72)
    for c in checks:
        if c["note"]:
            print(f"    {c['check']}: {c['note']}")

    fails = [c for c in checks if not c["pass"]]
    print(f"\n  pod raised {lift:.1f} mm; rail top now at Z {rail_top:.1f}, "
          f"pod floor at Z {rail_top + PAD_MM:.1f}")
    print(f"  {len(checks) - len(fails)}/{len(checks)} checks pass")
    for c in fails:
        print(f"  REVIEW: {c['check']} = {c['value_mm']:.1f} mm "
              f"(wanted {c['sense']} {c['limit_mm']:.1f})")

    report["frame_v2"] = {"rail_y_mm": RAIL_Y, "pod_lift_mm": lift,
                          "stack": st, "checks": checks}
    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    out_blend.with_suffix(".json").write_text(json.dumps(report, indent=2, default=float))
    print(f"\n  saved {out_blend}")
    print(f"  saved {out_blend.with_suffix('.json')}")


if __name__ == "__main__":
    main()
