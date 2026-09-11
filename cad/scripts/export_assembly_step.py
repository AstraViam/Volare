"""The whole boat as one STEP file: supplied structure, frame, powertrain, motor.

    python cad/scripts/export_assembly_step.py
        -> cad/out/step/volare_assembly.step

ONE FILE, TRUE SOLIDS, ONE FRAME

Everything here is a B-rep solid. That became possible when the team's Onshape
model of the boat arrived as `cad/blender/Main_Assembly_v_scaled.step`: before
it, the hulls and pod existed only as Organiser-supplied meshes and had to ship
as STL alongside the STEP. They no longer do.

Three sources feed this file and they are kept visibly separate:

  BOAT        cad/blender/Main_Assembly_v_scaled.step -- the team's CAD of the
              hulls, poles, pod, rails, clamps and the cooling pack.
  POWERTRAIN  cad/out/powertrain.json -- boxes and cable runs solved by
              cad/scripts/powertrain.py from the parameter file.
  MOTOR       cad/scripts/export_motor_step.py -- the Competr outboard built
              from its dimensioned drawing, with the team's rotors on it.

THE FRAME IS DERIVED, NOT ASSUMED

The Onshape file has its own origin and its X points aft. Rather than hard-code
a transform that silently rots when someone re-exports from Onshape with a
different origin, this script MEASURES the hulls and derives the transform from
them: the canonical origin is the hull pair's mid-length, their centreline, and
their keel. The derived numbers are printed and checked against
`volare.BASELINE`, which was measured independently off the supplied STL.

CLASHES ARE COMPUTED, NOT REMEMBERED

Every designed part is intersected against the structure it must not hit. The
old export carried a hardcoded list of five clashing components copied out of a
Blender run. A list like that is right until the day it is not, and nothing
tells you which day that was.

Team Volare / ICT Mumbai.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np  # noqa: E402


# cadquery pulls in OCP, a ~400 MB binary wheel. Nothing else in cad/scripts
# needs it, so this module degrades to a clear skip rather than failing
# tools/run_python_selftests.py on a machine that only has the analysis
# environment.
try:
    import cadquery as cq
    HAVE_CADQUERY = True
except ImportError:                                  # pragma: no cover
    cq = None
    HAVE_CADQUERY = False

import export_motor_step as MOTOR  # noqa: E402
import frame_geometry as FG  # noqa: E402
import params  # noqa: E402
import solids as S  # noqa: E402
import volare as V  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cad" / "out" / "step"
BOAT_STEP = ROOT / "cad" / "blender" / "Main_Assembly_v_scaled.step"
POWERTRAIN_JSON = ROOT / "cad" / "out" / "powertrain.json"

# Connected solids of the Onshape file, recognised by volume. Onshape's own
# part names are ambiguous -- three different bodies are called "Part 1" -- so
# volume is the reliable key, and the expected count is asserted for each.
#         volume m3     label          group             count
BOAT_PARTS = [
    (0.684066, "hull",           "SUPPLIED",  2),
    (0.661418, "pod",            "COCKPIT",   1),
    (0.001423, "beam_aft",       "SUPPLIED",  1),
    (0.001352, "beam_fwd",       "SUPPLIED",  1),
    (0.013900, "rail",           "FRAME",     2),
    (0.000432, "clamp",          "FRAME",     4),
    (0.015823, "heat_exchanger", "COOLING",   1),
    (0.004606, "hx_tray",        "COOLING",   1),
]
VOL_TOL = 1e-5

# Transom-mounted, so being outside the pod envelope is where they belong.
TRANSOM_MOUNTED = {"outboard", "drive_leg"}

ZONE_GROUP = {"HV": "POWERTRAIN_HV", "LV": "POWERTRAIN_LV",
              "COOLING": "POWERTRAIN_COOLING", "STRUCTURE": "STRUCTURE",
              "ORGANISER": "ORGANISER"}

COLOUR = {
    "SUPPLIED": (0.62, 0.65, 0.68, 1.0),
    "COCKPIT": (0.86, 0.87, 0.88, 1.0),
    "FRAME": (0.95, 0.55, 0.15, 1.0),
    "COOLING": (0.30, 0.62, 0.55, 1.0),
    "POWERTRAIN_HV": (0.55, 0.60, 0.65, 1.0),
    "POWERTRAIN_LV": (0.55, 0.60, 0.65, 1.0),
    "POWERTRAIN_COOLING": (0.30, 0.62, 0.55, 1.0),
    "STRUCTURE": (0.55, 0.60, 0.65, 1.0),
    "ORGANISER": (0.55, 0.60, 0.65, 1.0),
    "CABLES": (0.95, 0.70, 0.10, 1.0),
    "CLASH": (0.90, 0.10, 0.10, 1.0),
}


def classify(solids):
    """Label every solid of the Onshape file and assert the expected counts."""
    out, tally = [], {}
    for s in solids:
        v = s.Volume() / 1e9
        hit = next((p for p in BOAT_PARTS if abs(v - p[0]) < VOL_TOL), None)
        if hit is None:
            out.append({"label": f"unknown_{v:.6f}", "group": "UNKNOWN",
                        "solid": s})
            tally["unknown"] = tally.get("unknown", 0) + 1
            continue
        _v, label, group, _n = hit
        tally[label] = tally.get(label, 0) + 1
        out.append({"label": f"{label}_{tally[label]}", "group": group,
                    "solid": s, "kind": label})
    return out, tally


def derive_frame(parts):
    """Measure the hulls and derive the Onshape-to-canonical transform.

    The canonical frame is defined by the hulls: origin at their mid-length,
    their centreline and their keel; +X forward. The Onshape file has +X aft,
    so X and Y both flip and the result stays right-handed.
    """
    hulls = [p for p in parts if p.get("kind") == "hull"]
    if len(hulls) != 2:
        raise ValueError(f"expected 2 hulls, labelled {len(hulls)}")
    boxes = [h["solid"].BoundingBox() for h in hulls]
    xmin = min(b.xmin for b in boxes)
    xmax = max(b.xmax for b in boxes)
    zmin = min(b.zmin for b in boxes)
    cys = [h["solid"].Center().y for h in hulls]

    mid_x = 0.5 * (xmin + xmax)
    mid_y = float(np.mean(cys))
    return dict(mid_x=mid_x, mid_y=mid_y, keel_z=zmin,
                hull_len=xmax - xmin, hull_spacing=abs(cys[0] - cys[1]),
                hull_y=sorted(cys, reverse=True))


def to_canonical(solid, F):
    """Onshape frame -> canonical boat frame. X and Y flip, Z shifts."""
    return (solid.translate(cq.Vector(-F["mid_x"], -F["mid_y"], -F["keel_z"]))
            .rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 180.0))





def compare_frame(parts, F):
    """Diff the repo's frame v2 intent against what the CAD actually has.

    `frame_geometry.py` holds the frame the repository proposed; the Onshape
    file holds the frame the team drew. They are not the same frame, and until
    somebody decides which is real, every mass and stiffness number that leans
    on the rails is provisional. Printing the differences is cheaper than
    discovering them in a fabrication drawing.
    """
    rails = [to_canonical(p["solid"], F) for p in parts
             if p.get("kind") == "rail"]
    clamps = [to_canonical(p["solid"], F) for p in parts
              if p.get("kind") == "clamp"]
    if not rails or not clamps:
        return

    def sides(boxes):
        """Port and starboard centre Y, in canonical coordinates.

        Taking max(|Y|) over both sides looks harmless and is not: once the
        hull pair defines the origin, the cockpit sub-assembly is 5.42 mm off
        it, the two sides are no longer mirror images, and max(|Y|) reports
        the further one as if it were both. That inflates the spacing by twice
        the offset and turns a clamp gap that misses the rule into one that
        passes it.
        """
        ys = sorted(0.5 * (b.ymin + b.ymax) for b in boxes)
        return ys[-1], ys[0]                        # port (+Y), starboard (-Y)

    rb = [r.BoundingBox() for r in rails]
    cb = [c.BoundingBox() for c in clamps]
    r_port, r_stbd = sides(rb)
    c_port, c_stbd = sides(cb)
    c_width = float(np.mean([b.ylen for b in cb]))

    cad = {
        "rail spacing c-c": r_port - r_stbd,
        "rail width (Y)": float(np.mean([b.ylen for b in rb])),
        "rail height (Z)": float(np.mean([b.zlen for b in rb])),
        "rail length (X)": float(np.mean([b.xlen for b in rb])),
        "clamp spacing c-c": c_port - c_stbd,
        "clamp width (Y)": c_width,
    }
    intent = {
        "rail spacing c-c": 2 * FG.rail_y(),
        "rail width (Y)": FG.RAIL_W,
        "rail height (Z)": FG.RAIL_H,
        "rail length (X)": V.BASELINE["rail"]["length"],
        "clamp spacing c-c": 2 * FG.rail_y(),
        "clamp width (Y)": FG.CLAMP_W,
    }
    st = FG.stack_heights()
    print("\n frame: what frame_geometry.py proposes against what the CAD has")
    for what in intent:
        d = cad[what] - intent[what]
        print(f"   {'same ' if abs(d) < 1.0 else 'DIFF '} {what:<18} "
              f"CAD {cad[what]:8.1f}   frame v2 {intent[what]:8.1f}   "
              f"{d:+8.1f} mm")

    need = params.get("rules.clamp_min_spacing_mm")
    clear = (c_port - c_width / 2.0) - (c_stbd + c_width / 2.0)
    print(f"\n   ENERGY_REQ_38 needs {need:.0f} mm between clamps installed "
          f"symmetrically")
    print( "   either side of the ship's centreline, which the hulls define.")
    print(f"     CAD clamps    {cad['clamp spacing c-c']:7.1f} mm c-c "
          f"({cad['clamp spacing c-c'] - need:+.1f}),  "
          f"{clear:7.1f} mm clear ({clear - need:+.1f})")
    print(f"     frame v2      {intent['clamp spacing c-c']:7.1f} mm c-c "
          f"({intent['clamp spacing c-c'] - need:+.1f}),  "
          f"{intent['clamp spacing c-c'] - FG.CLAMP_W:7.1f} mm clear "
          f"({intent['clamp spacing c-c'] - FG.CLAMP_W - need:+.1f})")
    print( "   Read centre-to-centre both pass. Read as a clear gap the CAD is "
           "5 mm short")
    print( "   and frame v2 is 60 mm short. Moving the CAD clamps out 2.5 mm a "
           "side settles")
    print( "   the CAD under either reading.")
    print(f"\n   The CAD clamps sit at Y {c_port:+.1f} and {c_stbd:+.1f} about "
          f"the hull centreline,")
    print(f"   so they are {abs(c_port + c_stbd):.1f} mm from symmetric. That "
           "is the 5.42 mm mis-mate")
    print( "   above, and symmetry is what the rule asks for by name.")
    print(f"\n   Frame v2 shims the forward station level "
          f"({st['shim_fwd_mm']:.1f} mm); the CAD slopes the")
    print( "   rails to follow the pole step instead. One of the two has to go.")


def main() -> int:
    if not HAVE_CADQUERY:
        print(f"{Path(__file__).name}: skipped, cadquery is not "
              "installed. pip install cadquery to build the STEP.")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    ok = True

    print("=" * 74)
    print(" VOLARE -- WHOLE BOAT, ONE STEP, TRUE B-REP SOLIDS")
    print("=" * 74)

    # --- 1. the team's boat CAD ----------------------------------------
    if not BOAT_STEP.is_file():
        print(f" FAIL  {BOAT_STEP} is missing")
        return 1
    boat = cq.importers.importStep(str(BOAT_STEP))
    parts, tally = classify(boat.solids().vals())
    print(f"\n source  {BOAT_STEP.name}  {len(parts)} solids")
    for _v, label, group, want in BOAT_PARTS:
        got = tally.get(label, 0)
        good = got == want
        ok &= good
        print(f"   {'ok  ' if good else 'FAIL'}  {label:<15} {got} "
              f"(expected {want})  -> {group}")
    if tally.get("unknown"):
        ok = False
        print(f"   FAIL  {tally['unknown']} solid(s) matched nothing in "
              f"BOAT_PARTS; add them or the file is incomplete")

    F = derive_frame(parts)
    print("\n frame derived by measuring the hulls, not assumed")
    print(f"   hull mid-length  X = {F['mid_x']:9.2f} -> canonical 0")
    print(f"   hull centreline  Y = {F['mid_y']:9.2f} -> canonical 0")
    print(f"   keel bottom      Z = {F['keel_z']:9.2f} -> canonical 0")
    for what, got, want, tol in (
            ("hull length", F["hull_len"], V.BASELINE["hull"]["length"], 10.0),
            ("hull spacing c-c", F["hull_spacing"],
             V.BASELINE["hull"]["spacing_cc"], 40.0)):
        good = abs(got - want) <= tol
        ok &= good
        print(f"   {'ok  ' if good else 'FAIL'}  {what:<18} {got:8.1f} mm "
              f"(supplied STL {want:.1f}, tol {tol:.0f})")

    print(f"   note  hull centroids at Y {F['hull_y'][0]:+.2f} and "
          f"{F['hull_y'][1]:+.2f} about the file origin:")
    print(f"         the hull pair sits {F['mid_y']:+.2f} mm off the cockpit "
          f"centreline the rails,")
    print( "         clamps, pod and aft pole are all built symmetric about. "
           "One of the two")
    print( "         sub-assemblies is mis-mated by that much. It is small, "
           "and it is real.")

    compare_frame(parts, F)

    asm = cq.Assembly(name="volare_assembly")
    counts = {}

    def add(group, name, solid, colour=None):
        asm.add(solid, name=f"{group}/{name}",
                color=cq.Color(*(colour or COLOUR.get(group, (0.6, 0.6, 0.6, 1.0)))))
        counts[group] = counts.get(group, 0) + 1

    structure = []
    for p in parts:
        s = to_canonical(p["solid"], F)
        add(p["group"], p["label"], s)
        if p["group"] in ("SUPPLIED", "COCKPIT", "FRAME"):
            structure.append((p["label"], s))

    # --- 2. the designed powertrain ------------------------------------
    designed = []
    if POWERTRAIN_JSON.is_file():
        pt = json.loads(POWERTRAIN_JSON.read_text())
        for part in pt.get("parts", []):
            size = part.get("size_mm", part.get("size"))
            centre = part.get("centre_mm", part.get("centre"))
            designed.append((part["name"],
                             ZONE_GROUP.get(part.get("zone", ""), "STRUCTURE"),
                             S.box_solid(centre, size)))
        cables = []
        for c in pt.get("cables", []):
            run = S.capsule_chain(c.get("points_mm", c.get("points")),
                                  c["od_mm"])
            if run is not None:
                cables.append((c["name"], run))
    else:
        cables = []

    # --- 3. the motor, built by export_motor_step, not copied ----------
    motor_asm, motor_info = MOTOR.build_assembly()
    for child in motor_asm.children:
        solid = S.as_shape(child.obj)
        if child.loc is not None:
            solid = solid.moved(child.loc)
        group = child.name.split("/")[0]
        add(group, child.name.split("/", 1)[1], solid,
            (0.22, 0.24, 0.27, 1.0) if group == "OUTBOARD"
            else (0.13, 0.40, 0.72, 1.0))
        designed.append((child.name.split("/", 1)[1], group, solid))

    # --- 4. clashes, computed ------------------------------------------
    print("\n clash check: every designed part against the structure it must "
          "not hit")
    clashes = []
    for name, group, solid in designed:
        worst = (0.0, None)
        for sname, ssolid in structure:
            if sname.startswith("pod"):
                continue          # the pod is a solid body, not a shell; see below
            v = S.intersects(solid, ssolid)
            if v > worst[0]:
                worst = (v, sname)
        if worst[0] > 1.0:
            clashes.append((name, group, worst[1], worst[0]))

    for name, group, against, vol in sorted(clashes, key=lambda t: -t[3]):
        print(f"   CLASH  {name:<22} into {against:<12} {vol / 1000.0:9.1f} cm3")
    if not clashes:
        print("   none")

    clashing = {c[0] for c in clashes}
    for name, group, solid in designed:
        if name in clashing:
            continue
        if group in ("OUTBOARD", "PROPULSOR"):
            continue              # already added above
        add(group, name, solid)
    for name, group, solid in designed:
        if name in clashing and group not in ("OUTBOARD", "PROPULSOR"):
            add("CLASH", name, solid)
    for name, solid in cables:
        if solid is not None:
            add("CABLES", name, solid)

    print("\n   note  the pod is excluded from the clash test on purpose. In "
          "this CAD it is")
    print( "         a solid body of 0.66 m3, not a shell, so every piece of "
           "equipment")
    print( "         inside the cockpit 'intersects' it. Containment, not "
           "interference, is")
    print( "         the question there, and it needs the pod as a shell to "
           "answer.")

    # Containment is the weaker question the solid pod can still answer: does
    # each cockpit part lie inside the pod's envelope at all? A box test, not
    # a surface test, so it can pass on a part the real shell would clip.
    pod = next(s for label, s in structure if label.startswith("pod"))
    pb = pod.BoundingBox()
    outside = []
    for name, group, solid in designed:
        if group in ("OUTBOARD", "PROPULSOR") or name in TRANSOM_MOUNTED:
            continue
        b = solid.BoundingBox()
        if (b.xmin < pb.xmin or b.xmax > pb.xmax or b.ymin < pb.ymin
                or b.ymax > pb.ymax or b.zmin < pb.zmin or b.zmax > pb.zmax):
            outside.append(name)
    print(f"\n containment: cockpit equipment inside the pod envelope "
          f"X {pb.xmin:.0f}..{pb.xmax:.0f}, Z {pb.zmin:.0f}..{pb.zmax:.0f}")
    if outside:
        print(f"   {len(outside)} part(s) reach outside it: "
              f"{', '.join(sorted(outside))}")
        print( "   A bounding-box test, so this is the floor, not the ceiling: "
               "the real")
        print( "   shell curves inward and will clip more than these.")
    else:
        print("   all inside the envelope")

    # --- 5. out ---------------------------------------------------------
    print("\n assembly")
    for group in sorted(counts):
        print(f"   {group:<22} {counts[group]:3d} solid(s)")
    print(f"   {'TOTAL':<22} {sum(counts.values()):3d}")

    compound = asm.toCompound()
    bb = compound.BoundingBox()
    print(f"\n bounding box  X {bb.xmin:9.1f} .. {bb.xmax:9.1f} ({bb.xlen:7.1f} mm)")
    print(f"               Y {bb.ymin:9.1f} .. {bb.ymax:9.1f} ({bb.ylen:7.1f} mm)")
    print(f"               Z {bb.zmin:9.1f} .. {bb.zmax:9.1f} ({bb.zlen:7.1f} mm)")

    good = abs(bb.xlen - V.BASELINE["hull"]["length"]) < 1500.0
    ok &= good
    print(f"   {'ok  ' if good else 'FAIL'}  overall length {bb.xlen:.0f} mm is "
          f"within 1.5 m of the {V.BASELINE['hull']['length']:.0f} mm hull")

    path = OUT / "volare_assembly.step"
    asm.export(str(path))
    print(f"\n wrote {path}  ({path.stat().st_size / 1e6:.2f} MB)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
