# `cad/out/step/` — the boat as CAD

```bash
python cad/scripts/export_assembly_step.py   # the whole boat, one STEP
python cad/scripts/export_motor_step.py      # the propulsion unit alone
python cad/scripts/export_supplied.py        # the Organiser's supplied mesh
```

Everything is in the **canonical boat frame**: X forward, Y to port, Z up,
origin at centreline × hull mid-length × keel bottom, **millimetres**. Load any
combination and they overlay exactly. That is checked by re-measuring the
transformed geometry, not assumed from the transform.

| File | What | Format |
|---|---|---|
| `volare_assembly.step` | **the whole boat** — hulls, poles, pod, frame, cooling, powertrain, cables, outboard, rotors. 47 solids | STEP, B-rep |
| `volare_motor.step` | the Competr outboard from its drawing, with the team's contra-rotating rotors. 12 solids | STEP, B-rep |
| `volare_supplied.stl` | hulls, both poles, pod shell, hull fittings, exactly as the Organiser supplied them | binary STL |
| `volare_supplied_frame.stl` | the original rails and pads that frame v2 replaces | binary STL |

## One script, one job

- **`export_assembly_step.py`** builds the boat. It reads the team's Onshape
  model, the powertrain solved from the parameter file, and the motor, and
  writes one STEP.
- **`export_motor_step.py`** builds the propulsion unit. The assembly imports
  it rather than repeating its dimensions.
- **`export_supplied.py`** writes the ENERGY_REQ_3 reference: the Organiser's
  mesh, split and labelled, so the team's CAD can be laid over what was
  actually supplied. It is a mesh, and it ships as one, because wrapping a
  tessellation in a STEP shell gives a file that is large, slow and impossible
  to mate to while looking like a solid model.
- **`solids.py`** holds the primitives all three share. They used to be copied
  into two of them, and the copies had already diverged.

## Where the geometry comes from

| Source | Gives |
|---|---|
| `cad/blender/Main_Assembly_v_scaled.step` | hulls, both poles, pod, rails, clamps, cooling pack |
| `cad/out/powertrain.json` | powertrain boxes and cable runs, solved from the parameter file |
| Competr datasheet 06/25 | the outboard, dimensioned |
| `hydro.*` in the parameter file | both rotors |

The Onshape file has its own origin and its X points aft. The exporter measures
the hulls and derives the transform from them, so a re-export with a moved
origin still lands correctly instead of silently shifting the boat.

## What the assembly currently shows

- **The hull pair sits 5.42 mm off the cockpit centreline.** Rails, clamps, pod
  and aft pole are symmetric about the file's Y = 0; the hulls and the forward
  pole are at +5.42. One sub-assembly is mis-mated. Referred to the hull
  centreline, the clamps land at +432.4 and −421.6, which is 10.8 mm from
  symmetric — and ENERGY_REQ_38 asks for symmetry about the ship's centreline
  by name.
- **Clamp spacing is 854.0 mm centre-to-centre and 745.0 mm clear.** Read
  centre-to-centre the 750 mm minimum passes with 104 mm spare; read as a clear
  gap it is 5 mm short. Moving the clamps out 2.5 mm a side settles both.
- **The CAD frame and frame v2 are different frames.** Rails 854 apart against
  750, 104 × 45 against 100 × 50, 2970 long against 3113, and the CAD slopes
  the rails to follow the pole step where v2 shims the forward station level by
  91.3 mm. One of the two has to go; the exporter prints the diff every run.
- **The poles are round D104 × 2 mm wall tubes.** Vertex radii about the pole
  axis take exactly two values, 50.0 and 52.0 mm.
- **No designed part clashes with the structure.** The pod is excluded from
  that test on purpose: it is a solid 0.66 m³ body, not a shell, so everything
  in the cockpit "intersects" it. Containment is what a solid can answer, and
  every cockpit part is inside its envelope.
- **The designed rotors are 380 and 361 mm** against a Competr gearcase drawn
  around roughly 230 mm. About 65 per cent too large for the stock gearcase.

## Size

`volare_assembly.step` is 23 MB, most of it the Onshape hull and pod surfaces.
It is tracked so teammates without cadquery can open the boat. The repository
is now past the point where Git LFS is worth doing rather than worth
considering.
