# Working in this repo

Team Volare, Monaco Energy Boat Challenge 2026. Read `README.md` first — it has
the map, the frozen rule constraints, and the five corrections to the notes.
`cad/README.md` is the engineering record.

## Non-negotiables

**The `notes/` folder is partly superseded.** It is the original design
discussion, not ground truth. Where a note and a script disagree, the script
wins — every number in `cad/scripts/` was re-derived or re-measured from the
STLs, and the scripts self-check. Check `README.md`'s corrections table before
quoting any note figure.

**Separate cockpit mass from supplied mass before comparing to 250 kg.** The cap
includes the pilot and excludes the 65 kg of hulls and beams. Note 06 conflates
these and overstates the overage by ~80 kg. Use `mass.py`.

**Never modify the supplied hulls or beams** (ENERGY_REQ_3). They are locked in
`build_scene.py` via `lock()` and belong to the SUPPLIED collection.

## Canonical frame

**X forward, Y port, Z up. Origin = centreline × hull mid-length × keel bottom.**
Millimetres everywhere except Blender scenes, which are metres (`BS.MM`).

Neither source STL uses this frame, and the two do not agree with each other —
`cad/scripts/volare.py` holds both transforms and self-checks them against three
numbers derived independently in the notes. Always go through it; never
hand-transform STL coordinates.

## Architecture — keep this separation

- `cad/scripts/` is pure numpy/scipy. No `bpy`. Every module has a `_selftest()`
  and exits non-zero on failure. This is where physics and geometry maths live.
- `cad/blender/` **consumes** `scripts/`, never reimplements it. If a Blender
  script needs geometry maths, put the maths in `scripts/` and import it — that
  is why `recontour_pod` and `windscreen_mesh` live in `parametric.py`.
- Blender's Python has no scipy. Keep heavy solver imports lazy.

## Verify by measuring, not by re-reading parameters

Both scene builders check themselves against independent measurement of the
built meshes, and both caught real bugs that parametric checks could not:

- `build_scene.py` re-measures every part's area inside Blender and fails if it
  disagrees with numpy by >0.01%.
- `frame_redesign.py` measures the built stack-up. This caught a pod that was
  never actually raised, and then a stale `matrix_world` (Blender caches it —
  call `bpy.context.view_layer.update()` after moving anything before reading
  world coordinates).
- `parametric_scene.py` checks the built base area against the fit the optimiser
  scored, so the optimum cannot drift from the shape being built.

Add a measured check whenever you add geometry. A passing parametric check on
wrong geometry is worse than no check.

## Running things

```bash
python cad/scripts/<name>.py                                  # all self-check
blender -b -P cad/blender/<name>.py                           # scenes
```

`powertrain.py` exits non-zero because 3 of its 15 **design** checks fail — those
are real open issues, not a broken script. Do not "fix" it by loosening a check.

## Conventions

- Report outcomes faithfully. If a check fails, say so with the number.
- When a computed result contradicts a note, say which note and why, and leave a
  comment at the site of the correction.
- Prefer clearances over booleans: "5 mm to the pod edge" beats "no clash".
