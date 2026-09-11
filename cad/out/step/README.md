# `cad/out/step/` — the boat as CAD

```bash
python cad/scripts/export_assembly_step.py    # the whole boat, one file
python cad/scripts/export_motor_step.py       # the propulsion unit alone
python cad/scripts/export_step.py             # designed parts + supplied STL
```

Everything is in the **canonical boat frame**: X forward, Y to port, Z up,
origin at centreline × hull mid-length × keel bottom, **millimetres**. Load any
combination and they overlay exactly. That is checked by re-measuring the
transformed hull box, not assumed from the transform.

| File | What | Solids |
|---|---|---|
| `volare_assembly.step` | **the whole boat** — hulls, poles, pod, frame, cooling, powertrain, cables, outboard, rotors | 47 |
| `volare_motor.step` | the Competr outboard built from its drawing, with the team's contra-rotating rotors | 12 |
| `volare_designed.step` | frame v2 and powertrain only, against the *supplied STL* baseline | 35 |
| `volare_designed.stl` `volare_supplied.stl` `volare_supplied_frame.stl` | the older mesh-based pairing, kept because it records the supplied geometry | — |

## Where the geometry comes from

Three sources, kept visibly separate in the assembly tree.

- **`cad/blender/Main_Assembly_v_scaled.step`** — the team's Onshape model:
  hulls, both poles, the pod, the rails and clamps, and the cooling pack. Its
  13 solids are recognised by volume, not by index, and the expected count of
  each is asserted.
- **`cad/out/powertrain.json`** — boxes and cable runs solved by
  `cad/scripts/powertrain.py` from `powertrain/params/volare_params.json`.
- **`cad/scripts/export_motor_step.py`** — the outboard, built from the
  dimensioned Competr drawing, with the rotors generated from the converged
  propulsor design.

## The frame is derived, not hard-coded

The Onshape file has its own origin and its X points aft. The exporter measures
the hulls and derives the transform from them, so a re-export from Onshape with
a moved origin still lands correctly instead of silently shifting the boat.

## What the assembly currently shows

- **The hull pair sits 5.42 mm off the cockpit centreline.** The rails, clamps,
  pod and aft pole are all symmetric about Y = 0; the hulls and the forward
  pole are both at Y = +5.42. One of the two sub-assemblies is mis-mated by
  that much. Small, but real, and it is the ship's centreline that
  ENERGY_REQ_38 measures clamp symmetry against.
- **The rails give 750.0 mm clear between their inner faces**, centres at
  ±427.0. The clamps are 109 mm wide on the same centres, so the clear gap
  between clamps is 745.0 mm. Read as centre-to-centre, ENERGY_REQ_38's 750 mm
  minimum passes with 104 mm to spare; read as a clear gap it is 5 mm short.
  Moving the clamps out 2.5 mm a side settles it either way.
- **The poles are round D104 × 2 mm wall tubes.** Vertex radii about the pole
  axis take exactly two values, 50.0 and 52.0 mm. `BASELINE["beam_*"]
  ["section_mm"] = (104, 104)` is a bounding box and had been read as a square
  section.
- **No designed part clashes with the structure.** The pod is excluded from
  that test on purpose: in this CAD it is a solid 0.66 m³ body rather than a
  shell, so everything in the cockpit "intersects" it. Containment is the
  question the solid can answer, and every cockpit part is inside its envelope.
  A shell is needed before interference means anything there.
- **The designed rotors are 380 and 361 mm.** The Competr gearcase on the
  drawing is built around a roughly 230 mm propeller. The pair is about 65 per
  cent larger and will not fit the stock gearcase or its gearing.

## Size

`volare_assembly.step` is 23 MB, most of it the Onshape hull and pod surfaces.
It is tracked so teammates without cadquery can open the boat, but the
repository is now at the point where Git LFS is worth doing rather than worth
considering.
