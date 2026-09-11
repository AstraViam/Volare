# Working in this repo

Team Volare, ICT Mumbai. Monaco Energy Boat Challenge 2026, Energy Class.

**Read [`HANDOFF.md`](HANDOFF.md) first.** It carries current state, every known
blocker, and what to do next. `README.md` has the map and the conventions.

---

## Before you finish: update the handoff

**Any session that changes this repository must update `HANDOFF.md` before it
ends.** This is not optional housekeeping — it is how work continues across
sessions, across people, and across parallel branches.

At minimum:

- Change the **Last updated** date and branch at the top.
- Update **section 1** if a subsystem's status changed.
- Update **section 5** if a blocker was resolved or a new one appeared.
- Rewrite **section 7** so the next person knows what to do first.
- Add one entry to **section 8**. Never delete an old entry.

Keep it accurate rather than flattering. A handoff that overstates progress is
worse than none, because the next person will trust it and lose a day.

---

## Non-negotiables

**The `notes/` folder is partly superseded.** It is the original design
discussion, not ground truth. Where a note and a script disagree, the script
wins — every number in `cad/scripts/` was re-derived or re-measured from the
supplied STLs, and the scripts self-check.

**Separate cockpit mass from supplied mass before comparing to 250 kg.** The cap
includes the pilot and excludes the 65 kg of hulls and beams. Note 06 conflates
these and overstates the overage by about 80 kg. Use `cad/scripts/mass.py`.

**Never modify the supplied hulls or beams** (ENERGY_REQ_3). They are locked in
`cad/blender/build_scene.py` via `lock()` and belong to the SUPPLIED collection.

**Do not flatten either numbered tree.** `powertrain/TEST_ALL.m` asserts its
exact folder layout, and `P50B_ProjectRoot.m` derives the project root from its
own position inside `00_common/`. The Python modules resolve data through
`Path(__file__).parents[2]`, so `cad/scripts/` must stay exactly two levels
below the repository root. Flattening this tree has already broken the project
once.

---

## Canonical frame

**X forward, Y port, Z up. Origin = centreline × hull mid-length × keel bottom.**
Millimetres everywhere except Blender scenes, which are metres (`BS.MM`).

Neither source STL uses this frame, and the two do not agree with each other —
`cad/scripts/volare.py` holds both transforms and self-checks them against three
numbers derived independently in the notes. Always go through it; never
hand-transform STL coordinates.

---

## Architecture — keep this separation

- `cad/scripts/` is pure numpy/scipy. No `bpy`. Every module has a self-test and
  exits non-zero on failure. This is where physics and geometry maths live.
- `cad/blender/` **consumes** `cad/scripts/`, never reimplements it. If a Blender
  script needs geometry maths, put the maths in `scripts/` and import it — that
  is why `recontour_pod` and `windscreen_mesh` live in `parametric.py`.
- Blender's Python has no scipy. Keep heavy solver imports lazy.
- `powertrain/` is self-contained MATLAB. It shares numbers with the Python side
  only through `powertrain/params/volare_params.json`. Never duplicate a
  constant across the two languages; read it from the shared file.
- **Every engineering number lives in the parameter file.** `cad/scripts/`
  reads it through `cad/scripts/params.py`, which is standard library only so
  it works unchanged under Blender and FreeCAD. Use
  `params.get("section.name")`; never add a literal to a script. A missing
  parameter raises rather than defaulting, because a CAD model built on
  invented dimensions looks authoritative and is not.
- The STL-derived numbers in `volare.py` are the exception and stay literal.
  They are measurements of supplied geometry, self-checked in that module, not
  design choices anybody may vary.

---

## Verify by measuring, not by re-reading parameters

Both scene builders check themselves against independent measurement of the
built meshes, and both caught real bugs that parametric checks could not:

- `build_scene.py` re-measures every part's area inside Blender and fails if it
  disagrees with numpy by more than 0.01%.
- `frame_redesign.py` measures the built stack-up. This caught a pod that was
  never actually raised, and then a stale `matrix_world` (Blender caches it —
  call `bpy.context.view_layer.update()` after moving anything before reading
  world coordinates).
- `parametric_scene.py` checks the built base area against the fit the optimiser
  scored, so the optimum cannot drift from the shape being built.

Add a measured check whenever you add geometry. A passing parametric check on
wrong geometry is worse than no check.

---

## Running things

```bash
python cad/scripts/<name>.py                          # all self-check
blender -b -P cad/blender/<name>.py                   # scenes
```

```matlab
% MATLAB, opened at powertrain/
SMOKE_TEST ; RUN_EVERYTHING ; TEST_ALL
```

`cad/scripts/powertrain.py` exits non-zero because 1 of its 19 **design**
checks fails: the MATLAB mass budget is 9.2 kg over the 250 kg cap
(ENERGY_REQ_48). That is a real open engineering issue, not a broken script.
Do not "fix" it by loosening a check; close the budget.

The other two failures that used to appear here were modelling bugs and are
gone. The geometry-freshness check compared file modification times, so a
comment-only edit tripped it; it now compares the values the export was built
from and names the parameter that moved. The phase-U cable asked for a 37 mm
bend radius in a cable rated 132 mm, because the route climbed over the
outboard and hairpinned; it now descends monotonically.

---

## Conventions

- Report outcomes faithfully. If a check fails, say so with the number.
- When a computed result contradicts a note, say which note and why, and leave a
  comment at the site of the correction.
- Prefer clearances over booleans: "5 mm to the pod edge" beats "no clash".
- Generated artefacts in `cad/out/` and `powertrain/output/` are tracked so that
  teammates without Blender or MATLAB can still use them. Commit a regenerated
  file only when its input actually changed; otherwise discard the churn.
