"""Export the boat as STEP and STL for design review and clash checking.

    python cad/scripts/export_step.py

Writes into cad/out/step/:

    volare_designed.step          everything the team designs, as true B-rep solids
    volare_designed.stl           the same, tessellated
    volare_supplied.stl           hulls, beams and pod shell, as supplied
    volare_supplied_frame.stl     the original rails and pads, which v2 replaces

TWO KINDS OF FILE, ONE COORDINATE FRAME
---------------------------------------
The boat is a hybrid and pretending otherwise produces a bad file.

The frame, the powertrain boxes and the cable runs are parametric. They become
real B-rep solids with planar faces and edges a reviewer can measure and a
fabricator can mate to.

The hulls and the pod exist only as STL meshes, supplied by the Organiser and
tessellated at the source. There is no way to recover a parametric surface from
them, so a STEP containing them would be a mesh in a solid wrapper: large,
slow, and impossible to mate to. They ship as STL instead, which is what a mesh
is, honestly labelled.

Every file uses the canonical boat frame, X forward, Y port, Z up, origin at
centreline x hull mid-length x keel bottom, in millimetres. Load them together
and they overlay exactly. That is checked here, not assumed: the hull bounding
box is re-measured after transforming and has to land on the origin the frame
claims.

WHY THE ORIGINAL FRAME IS A SEPARATE FILE
-----------------------------------------
The supplied assembly carries a set of rails and pads that the v2 frame
replaces. Dropping them would hide what changed; merging them into the supplied
file would put two rails in the same place and read as a modelling error. They
get their own file, so an overlay of designed + supplied is unambiguous and a
reviewer who wants the before-and-after loads the third file as well.

CLASHES ARE GROUPED, NOT HIDDEN
-------------------------------
Five components currently intersect the pod shell. They are in a group named
CLASH so nobody opening the file mistakes the interference for an accepted
design, and nobody has to rediscover which five.

WHY CABLES ARE CAPSULES
-----------------------
Each run is built as cylinders with spheres at the joints rather than a swept
profile. A sweep along a polyline with sharp corners fails or self-intersects,
and the failure is silent in some kernels. Capsules cannot fail, and for
clearance checking the difference is immaterial: the envelope is identical
everywhere except inside the corner radius, where a real cable is fatter than
a sweep, not thinner.

Team Volare / ICT Mumbai.
"""

from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np  # noqa: E402

import frame_geometry as FG  # noqa: E402
import stl_audit as SA  # noqa: E402
import volare as V  # noqa: E402

# cadquery pulls in OCP, a ~400 MB binary wheel. The supplied half of this
# script is pure numpy and is worth running without it -- on CI, and on a
# teammate's machine that only has the analysis environment -- so the import is
# optional and the B-rep half is skipped rather than crashing the suite.
try:
    import cadquery as cq
    HAVE_CADQUERY = True
except ImportError:                                  # pragma: no cover
    cq = None
    HAVE_CADQUERY = False

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cad" / "out" / "step"
POWERTRAIN_JSON = ROOT / "cad" / "out" / "powertrain.json"
ASSEMBLY_STL = ROOT / "source_documents" / "FULLCOCPITV1_3.stl"

# Reported by cad/blender/build_full_assembly.py. Kept explicit so the group is
# reproducible without running Blender; re-run that script if the layout moves.
CLASHING = {"energy_container", "terminal_box", "dcdc", "heat_exchanger",
            "monitor_bay"}

ZONE_GROUP = {
    "HV": "POWERTRAIN_HV", "LV": "POWERTRAIN_LV", "COOLING": "POWERTRAIN_COOLING",
    "STRUCTURE": "STRUCTURE", "ORGANISER": "ORGANISER",
}

# Connected components of FULLCOCPITV1_3.stl, matched on their measured
# bounding box in the canonical frame. The target sizes come from
# volare.BASELINE, so this table cannot drift away from the measured baseline
# without the match failing loudly. Expected counts are asserted.
#
#   (label, file, expected count, size target or None, tolerance mm)
SUPPLIED_MATCH = [
    ("hull",  "supplied", 2, ("hull", ("length", "beam", "depth")), 1.0),
    ("pod",   "supplied", 1, ("pod", ("length", "beam_max", "height")), 1.0),
    ("rail",  "frame",    2, ("rail", ("length", "width", "height")), 1.0),
    ("pad",   "frame",    6, None, 1.0),
]
PAD_SIZE_MM = (16.5, 139.0, 50.4)      # volare.BASELINE["pads"]["size_mm"]
SHARD_AREA_M2 = 1e-3                    # below this a component is a stray shard


def box_solid(centre, size):
    """An axis-aligned box, centred."""
    return cq.Workplane("XY").box(*size).translate(tuple(centre))


def cylinder_solid(centre, od, length, axis, bore=0.0):
    """A cylinder, or a tube when bore is non-zero, along X, Y or Z.

    extrude(both=True) grows in both directions, so half the length is
    extruded and the result is centred on `centre`.
    """
    plane = {0: "YZ", 1: "XZ", 2: "XY"}[axis]
    wp = cq.Workplane(plane).circle(od / 2.0)
    if bore and bore > 0:
        wp = wp.circle(bore / 2.0)
    return wp.extrude(length / 2.0, both=True).translate(tuple(centre))


def capsule_chain(points, od):
    """A cable run as cylinders with spheres at the joints. See the docstring."""
    r = od / 2.0
    solid = None
    for a, b in zip(points[:-1], points[1:]):
        ax, ay, az = a
        bx, by, bz = b
        dx, dy, dz = bx - ax, by - ay, bz - az
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-6:
            continue
        seg = cq.Workplane("XY").circle(r).extrude(length)
        # Orient +Z onto the segment direction.
        zaxis = (0.0, 0.0, 1.0)
        d = (dx / length, dy / length, dz / length)
        cross = (zaxis[1] * d[2] - zaxis[2] * d[1],
                 zaxis[2] * d[0] - zaxis[0] * d[2],
                 zaxis[0] * d[1] - zaxis[1] * d[0])
        dot = max(-1.0, min(1.0, zaxis[0] * d[0] + zaxis[1] * d[1] + zaxis[2] * d[2]))
        angle = math.degrees(math.acos(dot))
        if abs(angle) > 1e-9:
            if math.sqrt(sum(c * c for c in cross)) < 1e-12:
                cross = (1.0, 0.0, 0.0)      # antiparallel; any perpendicular
            seg = seg.rotate((0, 0, 0), cross, angle)
        seg = seg.translate((ax, ay, az))
        solid = seg if solid is None else solid.union(seg)

    for p in points[1:-1]:
        ball = cq.Workplane("XY").sphere(r).translate(tuple(p))
        solid = ball if solid is None else solid.union(ball)
    return solid


def build_designed():
    """Every part the team designs, as an assembly with a named tree."""
    asm = cq.Assembly(name="volare_designed")
    counts = {}

    def add(group, name, solid, colour):
        asm.add(solid, name=f"{group}/{name}", color=cq.Color(*colour))
        counts[group] = counts.get(group, 0) + 1

    # --- frame ---------------------------------------------------------
    for p in FG.build():
        if p["kind"] == "box":
            s = box_solid(p["centre"], p["size"])
        else:
            s = cylinder_solid(p["centre"], p["od"], p["length"], p["axis"],
                               p.get("bore", 0.0))
        add("FRAME", p["name"], s, (0.95, 0.55, 0.15, 1.0))

    # --- powertrain ----------------------------------------------------
    if POWERTRAIN_JSON.is_file():
        with open(POWERTRAIN_JSON, "r", encoding="utf-8") as f:
            pt = json.load(f)

        for part in pt.get("parts", []):
            name = part["name"]
            size = part["size_mm"] if "size_mm" in part else part["size"]
            centre = part["centre_mm"] if "centre_mm" in part else part["centre"]
            solid = box_solid(centre, size)
            if name in CLASHING:
                add("CLASH", name, solid, (0.90, 0.10, 0.10, 1.0))
            else:
                group = ZONE_GROUP.get(part.get("zone", ""), "POWERTRAIN_OTHER")
                add(group, name, solid, (0.55, 0.60, 0.65, 1.0))

        for cab in pt.get("cables", []):
            pts = cab["points_mm"] if "points_mm" in cab else cab["points"]
            solid = capsule_chain(pts, cab["od_mm"])
            if solid is not None:
                add("CABLES", cab["name"], solid, (0.95, 0.70, 0.10, 1.0))

    return asm, counts


# --- supplied geometry --------------------------------------------------------

def _match_size(size, key, fields, tol):
    want = sorted(V.BASELINE[key][f] for f in fields)
    return all(abs(a - b) <= tol for a, b in zip(sorted(size), want))


def split_supplied():
    """Connected components of the assembly STL, transformed and labelled.

    Returns (components, notes). Each component is a dict with its label, the
    file it belongs in, its triangles in the canonical frame, and its measured
    box. Labelling is by measured size against volare.BASELINE, never by
    triangle index, so a re-exported STL with a different component order still
    lands in the right file.
    """
    raw = SA.read_stl(ASSEMBLY_STL)
    verts, faces = SA.weld(raw)
    label, ncomp = SA.components(verts, faces)

    comps = []
    for i in range(ncomp):
        tri = raw[label == i]
        _, area = SA.tri_normals_areas(tri)
        if area.sum() / 1e6 < SHARD_AREA_M2:
            continue
        pts = V.asm_to_boat(tri.reshape(-1, 3))
        lo, hi = pts.min(0), pts.max(0)
        size = hi - lo

        name, dest = "fitting", "supplied"
        for lbl, target, _n, sig, tol in SUPPLIED_MATCH:
            if sig is None:
                if all(abs(a - b) <= tol
                       for a, b in zip(sorted(size), sorted(PAD_SIZE_MM))):
                    name, dest = lbl, target
                    break
            elif _match_size(size, sig[0], sig[1], tol):
                name, dest = lbl, target
                break
        else:
            # Long, slender and roughly 104 mm square in section: a supplied pole.
            if size.max() > 1500.0 and abs(size[0] - V.BEAM_DIAMETER) <= 1.0:
                name, dest = "beam", "supplied"

        comps.append({
            "label": name, "file": dest, "tris": pts.reshape(-1, 3, 3),
            "min": lo, "size": size, "centre": 0.5 * (lo + hi),
            "area_m2": area.sum() / 1e6,
        })
    return comps


def write_binary_stl(path, tris, header):
    """Binary STL. Normals recomputed from the vertices, not carried over."""
    tris = np.asarray(tris, np.float64)
    rec = np.zeros(len(tris), dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"),
                                              ("a", "<u2")]))
    nr = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    norm = np.linalg.norm(nr, axis=1, keepdims=True)
    rec["n"] = nr / np.where(norm < 1e-20, 1.0, norm)
    rec["v"] = tris.reshape(-1, 9)
    with open(path, "wb") as f:
        f.write(header.encode("ascii", "replace")[:80].ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        f.write(rec.tobytes())


def beam_outer_radius(comps):
    """Measure the supplied poles' outer radius about the axis the frame uses."""
    out = {}
    for which in ("fwd", "aft"):
        b = V.BASELINE[f"beam_{which}"]
        cz = (b["z_bottom"] + b["z_top"]) / 2.0
        best = None
        for c in comps:
            if c["label"] != "beam":
                continue
            if abs(c["centre"][0] - b["x"]) < 5.0:
                best = c
        if best is None:
            continue
        p = best["tris"].reshape(-1, 3)
        out[which] = float(np.hypot(p[:, 0] - b["x"], p[:, 2] - cz).max())
    return out


def check_shared_frame(comps, designed_bb=None):
    """The two files overlay only if the frame definition actually holds.

    Re-measures the transformed supplied mesh instead of trusting the
    transform, which is the rule in CLAUDE.md: verify by measuring.
    """
    ok = True
    hulls = [c for c in comps if c["label"] == "hull"]
    print("\n shared-frame checks (measured on the transformed mesh)")

    if len(hulls) != 2:
        print(f"   FAIL  expected 2 hulls, labelled {len(hulls)}")
        return False

    lo = np.minimum(hulls[0]["min"], hulls[1]["min"])
    hi = np.maximum(hulls[0]["min"] + hulls[0]["size"],
                    hulls[1]["min"] + hulls[1]["size"])
    mid_x = 0.5 * (lo[0] + hi[0])
    for what, value, want, tol in (
        ("hull mid-length on X=0", mid_x, 0.0, 0.5),
        ("keel bottom on Z=0", lo[2], 0.0, 0.5),
        ("centreline on Y=0", 0.5 * (lo[1] + hi[1]), 0.0, 0.5),
        ("hull y centre", hi[1] - V.BASELINE["hull"]["beam"] / 2.0,
         V.BASELINE["hull"]["y_centres"][0], 1.0),
    ):
        good = abs(value - want) <= tol
        ok &= good
        print(f"   {'ok  ' if good else 'FAIL'}  {what:<24} {value:9.2f} mm "
              f"(want {want:.1f} +/- {tol})")

    radii = beam_outer_radius(comps)
    st = FG.stack_heights()
    bore_r = 0.5 * (V.BEAM_DIAMETER + 2 * FG.GASKET_MM)
    for which, r in sorted(radii.items()):
        gap = bore_r - r
        good = abs(gap - FG.GASKET_MM) <= 0.5
        ok &= good
        print(f"   {'ok  ' if good else 'FAIL'}  clamp bore over {which} pole  "
              f"{gap:9.2f} mm radial (want {FG.GASKET_MM:.1f})")

    lift = st["pod_floor"] - V.BASELINE["pod"]["z_floor"]
    print(f"   note  v2 lifts the pod floor {lift:+.1f} mm, clearing the "
          f"{V.RAIL_POD_INTERFERENCE:.1f} mm interference in the supplied frame")

    if designed_bb is not None:
        overlap = (designed_bb[1] > lo[0] and designed_bb[0] < hi[0])
        ok &= overlap
        print(f"   {'ok  ' if overlap else 'FAIL'}  designed X "
              f"{designed_bb[0]:.0f}..{designed_bb[1]:.0f} overlaps supplied "
              f"{lo[0]:.0f}..{hi[0]:.0f}")
    return ok


def export_designed():
    """Write the B-rep STEP and its tessellation. Returns (counts, bbox)."""
    asm, counts = build_designed()
    step_path = OUT / "volare_designed.step"
    asm.export(str(step_path))

    compound = asm.toCompound()
    stl_path = OUT / "volare_designed.stl"
    cq.exporters.export(compound, str(stl_path), tolerance=0.1, angularTolerance=0.2)

    bb = compound.BoundingBox()
    print("=" * 70)
    print(" VOLARE -- DESIGNED GEOMETRY, TRUE B-REP SOLIDS")
    print("=" * 70)
    print(" frame: X fwd, Y port, Z up; origin centreline x mid-length x keel")
    print(" units: mm\n")
    for group in sorted(counts):
        print(f"   {group:<22} {counts[group]:3d} solid(s)")
    print(f"   {'TOTAL':<22} {sum(counts.values()):3d}")
    print(f"\n bounding box  X {bb.xmin:9.1f} .. {bb.xmax:9.1f}"
          f"   ({bb.xlen:.1f} mm)")
    print(f"               Y {bb.ymin:9.1f} .. {bb.ymax:9.1f}"
          f"   ({bb.ylen:.1f} mm)")
    print(f"               Z {bb.zmin:9.1f} .. {bb.zmax:9.1f}"
          f"   ({bb.zlen:.1f} mm)")
    print(f"\n volume        {compound.Volume() / 1e9:.6f} m3")
    if "CLASH" in counts:
        print(f"\n {counts['CLASH']} component(s) in group CLASH intersect the pod shell.")
        print(" They are grouped, not hidden. See cad/blender/build_full_assembly.py.")
    return counts, bb


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # --- designed -------------------------------------------------------
    step_path = OUT / "volare_designed.step"
    stl_path = OUT / "volare_designed.stl"
    if HAVE_CADQUERY:
        _counts, bb = export_designed()
        designed_x = (bb.xmin, bb.xmax)
    else:
        designed_x = None
        print("=" * 70)
        print(" VOLARE -- DESIGNED GEOMETRY: SKIPPED, cadquery is not installed")
        print("=" * 70)
        print(" pip install cadquery  (pulls in OCP, ~400 MB) to write the STEP.")
        print(" The supplied-geometry export below is pure numpy and still runs.")

    # --- supplied -------------------------------------------------------
    print("\n" + "=" * 70)
    print(" VOLARE -- SUPPLIED GEOMETRY, TESSELLATED (ENERGY_REQ_3: DO NOT MODIFY)")
    print("=" * 70)
    comps = split_supplied()

    ok = True
    tally = {}
    for c in comps:
        tally[c["label"]] = tally.get(c["label"], 0) + 1
    for lbl, _dest, want, _sig, _tol in SUPPLIED_MATCH + [("beam", "", 2, None, 0)]:
        got = tally.get(lbl, 0)
        if got != want:
            print(f"   FAIL  labelled {got} {lbl}(s), expected {want}")
            ok = False

    written = []
    for dest, fname, title in (
        ("supplied", "volare_supplied.stl", "hulls, beams, pod shell"),
        ("frame", "volare_supplied_frame.stl", "original rails and pads"),
    ):
        tris = np.concatenate([c["tris"] for c in comps if c["file"] == dest])
        path = OUT / fname
        write_binary_stl(path, tris, f"Volare {title}; canonical boat frame, mm")
        written.append((path, len(tris), sorted(
            {c["label"] for c in comps if c["file"] == dest})))

    for lbl in sorted(tally):
        n = tally[lbl]
        area = sum(c["area_m2"] for c in comps if c["label"] == lbl)
        dest = next(c["file"] for c in comps if c["label"] == lbl)
        print(f"   {lbl:<10} {n:2d}  {area:8.4f} m2  -> {dest}")

    ok &= check_shared_frame(comps, designed_x)

    print()
    for path, ntri, labels in written:
        print(f" wrote {path.name:<28} {ntri:6d} triangles, "
              f"{path.stat().st_size / 1e6:.2f} MB  [{', '.join(labels)}]")
    if HAVE_CADQUERY:
        print(f" wrote {step_path.name:<28} "
              f"{step_path.stat().st_size / 1e6:.2f} MB")
        print(f" wrote {stl_path.name:<28} "
              f"{stl_path.stat().st_size / 1e6:.2f} MB")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
