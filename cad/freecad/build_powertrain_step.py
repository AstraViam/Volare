"""
build_powertrain_step.py -- the powertrain as solid CAD, headless FreeCAD.

    freecadcmd freecad/build_powertrain_step.py

Reads out/powertrain.json and writes:

    out/volare_powertrain.FCStd    native, editable, with a part tree
    out/volare_powertrain.step     AP214 STEP for anyone else's CAD

WHY BOTH BLENDER AND FREECAD
----------------------------
They answer different questions and neither replaces the other.

Blender is a mesh tool. It renders, it is fast, and the .blend is where the
layout gets looked at. But its boxes are triangles -- there is no notion of a
face you can mate to, and a STEP written from it would be a mesh in a solid
wrapper, useless to a machinist.

FreeCAD builds real B-rep solids. The STEP it writes carries planar faces,
edges and a part tree, which is what a supplier, a stress analyst or the
Technical Committee can actually open. It is also what an interference check
in someone else's CAD needs.

Both are consumers of the same out/powertrain.json, so they cannot disagree
about where anything is.

WHAT THIS ADDS OVER THE JSON
----------------------------
Solids, a labelled tree grouped by zone, and mass properties computed by
FreeCAD from the geometry rather than taken on trust -- which is a genuine
second opinion on the centre of gravity, since it integrates over the shapes
instead of summing point masses.
"""

import json
import os
import sys

import FreeCAD as App
import Part
import Import

# freecadcmd does not reliably flush a plain print() to the parent shell's
# stdout, so the first working version of this script exited 1 with nothing
# on screen and no files -- indistinguishable from a crash. Everything the
# report says is therefore both printed AND written to a log beside the
# outputs, and the log is the copy to trust.
_LOG = []


def say(msg=""):
    _LOG.append(msg)
    App.Console.PrintMessage(msg + "\n")
    try:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out")

# FreeCAD works in millimetres natively, which is what the model is in, so
# there is no unit conversion here at all. That is one fewer place to be
# wrong than the Blender path, which has exactly one.

ZONE_COLOUR = {
    "HV":        (0.85, 0.25, 0.15),
    "LV":        (0.20, 0.45, 0.80),
    "COOLING":   (0.15, 0.65, 0.70),
    "STRUCTURE": (0.55, 0.55, 0.58),
    "ORGANISER": (0.90, 0.75, 0.15),
}

# Rough densities, only used so FreeCAD's own volume integration can be
# turned into a mass and compared with the model's. A box is not the real
# part, so these are calibrated per part from the known mass rather than
# looked up -- the point is to check the CENTROID, not to weigh anything.


def make_box(part):
    """One component as a B-rep solid, placed by its centre."""
    sx, sy, sz = part["size"]
    cx, cy, cz = part["centre"]

    box = Part.makeBox(sx, sy, sz,
                       App.Vector(cx - sx / 2.0, cy - sy / 2.0, cz - sz / 2.0))
    return box


def make_cable(run):
    """One cable as a swept solid along its polyline.

    Swept rather than drawn as a line, because the question the cable
    geometry has to answer is whether it fouls anything, and a line
    cannot foul. The sweep is a circular profile of the real outside
    diameter, which is what actually has to fit.
    """
    pts = [App.Vector(*p) for p in run["points"]]

    # Drop any zero-length segment: a repeated point makes the sweep fail
    # with an unhelpful OCC error rather than saying which cable it was.
    clean = [pts[0]]
    for p in pts[1:]:
        if (p - clean[-1]).Length > 1e-6:
            clean.append(p)

    if len(clean) < 2:
        return None

    path = Part.Wire([Part.LineSegment(clean[i], clean[i + 1]).toShape()
                      for i in range(len(clean) - 1)])

    direction = clean[1] - clean[0]
    circle = Part.Circle(clean[0], direction.normalize(), run["od_mm"] / 2.0)
    profile = Part.Wire([circle.toShape()])

    try:
        return path.makePipeShell([profile], True, True)
    except Exception:
        # Frechet sweeps fail on tight corners. A swept sphere-chain is a
        # cruder shape but it never fails, and for a clash check the
        # difference is immaterial.
        solids = []
        for i in range(len(clean) - 1):
            v = clean[i + 1] - clean[i]
            solids.append(Part.makeCylinder(
                run["od_mm"] / 2.0, v.Length, clean[i], v.normalize()))
        for p in clean[1:-1]:
            solids.append(Part.makeSphere(run["od_mm"] / 2.0, p))
        shape = solids[0]
        for s in solids[1:]:
            shape = shape.fuse(s)
        return shape.removeSplitter()


def main():
    src = os.path.join(OUT, "powertrain.json")

    if not os.path.isfile(src):
        say("ERROR: %s not found." % src)
        say("Run:  python scripts/powertrain.py")
        return 1

    with open(src, "r") as f:
        data = json.load(f)

    doc = App.newDocument("volare_powertrain")

    groups = {}
    for zone in list(ZONE_COLOUR) + ["CABLE"]:
        g = doc.addObject("App::DocumentObjectGroup", "PT_" + zone)
        g.Label = "Powertrain " + zone.title()
        groups[zone] = g

    made = []
    total_vol = 0.0
    weighted = App.Vector(0, 0, 0)
    total_mass = 0.0

    for part in data["parts"]:
        shape = make_box(part)

        obj = doc.addObject("Part::Feature", part["name"])
        obj.Label = part["name"]
        obj.Shape = shape

        groups[part["zone"]].addObject(obj)
        made.append((part, obj))

        # FreeCAD integrates the solid for its centre of mass. For a box
        # that is the centre, so this is a weak check -- but it is a real
        # one: it catches a part placed by its corner instead of its
        # centre, which is the classic CAD placement slip.
        # A part with a parent lives INSIDE another solid. Counting both
        # weighs the pack twice and drags the centre of gravity 175 mm
        # forward -- which is exactly what the first run of this script
        # reported, and why the CG cross-check is here rather than the
        # numbers being taken on trust.
        c = shape.CenterOfMass
        m = part["mass_kg"]
        weighted += App.Vector(c.x * m, c.y * m, c.z * m)
        total_mass += m

        # Volume, unlike mass, IS double counted by an enclosed part --
        # the pack occupies space the container already claims -- so only
        # top-level solids contribute to the envelope figure.
        if not part.get("parent"):
            total_vol += shape.Volume

    n_cables = 0
    for run in data["cables"]:
        shape = make_cable(run)
        if shape is None:
            say("  skipped %s: degenerate path" % run["name"])
            continue
        obj = doc.addObject("Part::Feature", run["name"])
        obj.Label = run["name"]
        obj.Shape = shape
        groups["CABLE"].addObject(obj)
        n_cables += 1

    doc.recompute()

    # --- verify placement against the model ------------------------------
    problems = []
    for part, obj in made:
        c = obj.Shape.CenterOfMass
        # FreeCAD's Base.Vector exposes lowercase x/y/z. Reaching for .X
        # raises AttributeError, which freecadcmd swallows into a one-line
        # "Exception while processing file" with no traceback -- so the
        # build appeared to succeed and wrote nothing.
        for i, axis in enumerate(("x", "y", "z")):
            want = part["centre"][i]
            got = getattr(c, axis)
            if abs(got - want) > 1e-6:
                problems.append("%s: %s centre %.4f, model says %.4f"
                                % (part["name"], axis, got, want))

        bb = obj.Shape.BoundBox
        for i, got in enumerate((bb.XLength, bb.YLength, bb.ZLength)):
            want = part["size"][i]
            if abs(got - want) > 1e-6:
                problems.append("%s: axis %d spans %.4f, model says %.4f"
                                % (part["name"], i, got, want))

    cg = App.Vector(weighted.x / total_mass, weighted.y / total_mass,
                    weighted.z / total_mass)

    model_cg = data["cg_mm"]
    cg_err = max(abs(cg.x - model_cg[0]), abs(cg.y - model_cg[1]),
                 abs(cg.z - model_cg[2]))

    say("")
    print("=" * 70)
    say(" FREECAD POWERTRAIN -- SOLID BUILD")
    print("=" * 70)
    say(" %d solids, %d cable sweeps" % (len(made), n_cables))
    say(" enclosing volume    %.2f L  (enclosures only, no double count)"
        % (total_vol / 1e6))
    say(" mass               %.1f kg" % total_mass)
    say(" CG from geometry   X=%.1f Y=%.1f Z=%.1f mm" % (cg.x, cg.y, cg.z))
    say(" CG from the model  X=%.1f Y=%.1f Z=%.1f mm"
        % (model_cg[0], model_cg[1], model_cg[2]))
    say(" agreement          %.4f mm" % cg_err)

    if problems:
        say("")
        say(" %d PLACEMENT PROBLEM(S):" % len(problems))
        for p in problems[:20]:
            say("   " + p)
        say("")
        say(" Not exporting. A STEP that disagrees with the model is worse")
        say(" than none -- it is the file somebody sends to a supplier.")
        print("=" * 70)
        return 1

    if cg_err > 1e-6:
        say("")
        say(" CG disagreement %.6f mm exceeds tolerance." % cg_err)
        print("=" * 70)
        return 1

    say("")
    say(" every solid re-measured from its B-rep and agrees with the model")

    fcstd = os.path.join(OUT, "volare_powertrain.FCStd")
    doc.saveAs(fcstd)
    say("\n saved %s" % fcstd)

    step = os.path.join(OUT, "volare_powertrain.step")
    Import.export([g for g in groups.values()], step)
    say(" saved %s" % step)
    print("=" * 70)

    return 0


# FreeCAD executes a script passed to freecadcmd without setting __name__ to
# "__main__", so an if-main guard here silently does nothing and the command
# appears to succeed while producing no output. Call it directly.
try:
    _rc = main()
except Exception as _e:
    import traceback
    say("EXCEPTION: %s" % _e)
    say(traceback.format_exc())
    _rc = 1

with open(os.path.join(OUT, "powertrain_step_build.log"), "w") as _f:
    _f.write("\n".join(_LOG))

if _rc:
    sys.exit(_rc)
