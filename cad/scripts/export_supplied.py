"""Split the Organiser's supplied assembly mesh into labelled STL files.

    python cad/scripts/export_supplied.py

Writes into cad/out/step/:

    volare_supplied.stl        hulls, both poles, pod shell, hull fittings
    volare_supplied_frame.stl  the original rails and pads, which frame v2 replaces

WHAT THIS IS FOR, NOW THAT THE TEAM HAS ITS OWN CAD

`cad/blender/Main_Assembly_v_scaled.step` is the team's Onshape model and it is
what `export_assembly_step.py` builds the boat from. This script is not that.
It is the ENERGY_REQ_3 reference: the geometry the Organiser actually supplied,
in the canonical frame, so anyone can lay the team's CAD over it and see where
the two disagree. They do disagree -- the hull spacing differs by 32 mm and the
cockpit is a different body altogether -- and that comparison is only possible
while both exist.

The supplied geometry only ever existed as a mesh. Wrapping a tessellation in
a STEP shell gives a file that is large, slow and impossible to mate to, while
looking like a solid model. STL is what a mesh is, labelled honestly.

WHY THE ORIGINAL FRAME IS A SEPARATE FILE

The supplied assembly carries rails and pads that frame v2 replaces. Dropping
them would hide what changed; merging them into the supplied file would put two
rails in the same place and read as a modelling error. They get their own file.

LABELLING IS BY MEASUREMENT, NOT BY INDEX

Each connected component is matched against `volare.BASELINE`, so a re-exported
STL with a different component order still lands in the right file, and a
component that stops matching the measured baseline fails loudly instead of
being mislabelled. Counts are asserted.

Team Volare / ICT Mumbai.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np  # noqa: E402

import frame_geometry as FG  # noqa: E402
import solids as S  # noqa: E402
import stl_audit as SA  # noqa: E402
import volare as V  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cad" / "out" / "step"
ASSEMBLY_STL = ROOT / "source_documents" / "FULLCOCPITV1_3.stl"

# Connected components matched on their measured bounding box in the canonical
# frame. Target sizes come from volare.BASELINE, so this table cannot drift
# away from the measured baseline without the match failing.
#         label,   file,        count, (BASELINE key, fields), tol mm
SUPPLIED_MATCH = [
    ("hull", "supplied", 2, ("hull", ("length", "beam", "depth")), 1.0),
    ("pod", "supplied", 1, ("pod", ("length", "beam_max", "height")), 1.0),
    ("rail", "frame", 2, ("rail", ("length", "width", "height")), 1.0),
    ("pad", "frame", 6, None, 1.0),
]
PAD_SIZE_MM = (16.5, 139.0, 50.4)      # volare.BASELINE["pads"]["size_mm"]
SHARD_AREA_M2 = 1e-3                   # below this a component is a stray shard


def _match_size(size, key, fields, tol):
    want = sorted(V.BASELINE[key][f] for f in fields)
    return all(abs(a - b) <= tol for a, b in zip(sorted(size), want))


def split_supplied():
    """Connected components of the assembly STL, transformed and labelled."""
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
            # Long, slender, and 104 mm across in section: a supplied pole.
            if size.max() > 1500.0 and abs(size[0] - V.BEAM_DIAMETER) <= 1.0:
                name, dest = "beam", "supplied"

        comps.append({"label": name, "file": dest,
                      "tris": pts.reshape(-1, 3, 3), "min": lo, "size": size,
                      "centre": 0.5 * (lo + hi), "area_m2": area.sum() / 1e6})
    return comps


def beam_outer_radius(comps):
    """Measure the supplied poles' outer radius about the axis the frame uses."""
    out = {}
    for which in ("fwd", "aft"):
        b = V.BASELINE[f"beam_{which}"]
        cz = (b["z_bottom"] + b["z_top"]) / 2.0
        best = next((c for c in comps if c["label"] == "beam"
                     and abs(c["centre"][0] - b["x"]) < 5.0), None)
        if best is None:
            continue
        p = best["tris"].reshape(-1, 3)
        out[which] = float(np.hypot(p[:, 0] - b["x"], p[:, 2] - cz).max())
    return out


def check_frame(comps):
    """The canonical frame holds only if the transformed mesh says it does.

    Re-measures instead of trusting the transform, which is the rule in
    CLAUDE.md: verify by measuring.
    """
    ok = True
    hulls = [c for c in comps if c["label"] == "hull"]
    print("\n frame checks (measured on the transformed mesh)")
    if len(hulls) != 2:
        print(f"   FAIL  expected 2 hulls, labelled {len(hulls)}")
        return False

    lo = np.minimum(hulls[0]["min"], hulls[1]["min"])
    hi = np.maximum(hulls[0]["min"] + hulls[0]["size"],
                    hulls[1]["min"] + hulls[1]["size"])
    for what, value, want, tol in (
            ("hull mid-length on X=0", 0.5 * (lo[0] + hi[0]), 0.0, 0.5),
            ("keel bottom on Z=0", lo[2], 0.0, 0.5),
            ("centreline on Y=0", 0.5 * (lo[1] + hi[1]), 0.0, 0.5),
            ("hull y centre", hi[1] - V.BASELINE["hull"]["beam"] / 2.0,
             V.BASELINE["hull"]["y_centres"][0], 1.0)):
        good = abs(value - want) <= tol
        ok &= good
        print(f"   {'ok  ' if good else 'FAIL'}  {what:<24} {value:9.2f} mm "
              f"(want {want:.1f} +/- {tol})")

    bore_r = 0.5 * (V.BEAM_DIAMETER + 2 * FG.GASKET_MM)
    for which, r in sorted(beam_outer_radius(comps).items()):
        gap = bore_r - r
        good = abs(gap - FG.GASKET_MM) <= 0.5
        ok &= good
        print(f"   {'ok  ' if good else 'FAIL'}  frame v2 clamp bore over the "
              f"{which} pole {gap:6.2f} mm radial (want {FG.GASKET_MM:.1f})")

    lift = FG.stack_heights()["pod_floor"] - V.BASELINE["pod"]["z_floor"]
    print(f"   note  frame v2 lifts the pod floor {lift:+.1f} mm, clearing the "
          f"{V.RAIL_POD_INTERFERENCE:.1f} mm")
    print( "         interference measured in the supplied assembly")
    return ok


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ok = True

    print("=" * 74)
    print(" VOLARE -- SUPPLIED GEOMETRY (ENERGY_REQ_3: DO NOT MODIFY)")
    print("=" * 74)
    print(" frame: X fwd, Y port, Z up; origin centreline x mid-length x keel")
    print(f" source: {ASSEMBLY_STL.name}\n")

    comps = split_supplied()
    tally = {}
    for c in comps:
        tally[c["label"]] = tally.get(c["label"], 0) + 1
    for lbl, _d, want, _s, _t in SUPPLIED_MATCH + [("beam", "", 2, None, 0)]:
        got = tally.get(lbl, 0)
        if got != want:
            print(f"   FAIL  labelled {got} {lbl}(s), expected {want}")
            ok = False

    written = []
    for dest, fname, title in (
            ("supplied", "volare_supplied.stl", "hulls, poles, pod shell"),
            ("frame", "volare_supplied_frame.stl", "original rails and pads")):
        tris = np.concatenate([c["tris"] for c in comps if c["file"] == dest])
        path = OUT / fname
        S.write_binary_stl(path, tris,
                           f"Volare {title}; canonical boat frame, mm")
        written.append((path, len(tris),
                        sorted({c["label"] for c in comps
                                if c["file"] == dest})))

    for lbl in sorted(tally):
        n = tally[lbl]
        area = sum(c["area_m2"] for c in comps if c["label"] == lbl)
        dest = next(c["file"] for c in comps if c["label"] == lbl)
        print(f"   {lbl:<10} {n:2d}  {area:8.4f} m2  -> {dest}")

    ok &= check_frame(comps)

    print()
    for path, ntri, labels in written:
        print(f" wrote {path.name:<28} {ntri:6d} triangles, "
              f"{path.stat().st_size / 1e6:.2f} MB  [{', '.join(labels)}]")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
