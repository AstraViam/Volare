# Volare

Full electronic, structural and hydrodynamic design code for **Team Volare**,
ICT Mumbai, competing in the **Monaco Energy Boat Challenge 2026**, Energy Class.

A 5 m, 250 kg catamaran. The design objective throughout is **minimum electrical
energy per nautical mile**, not maximum propeller efficiency, and every model
here serves that one number.

> **New here, or picking this up in a new session? Read [`HANDOFF.md`](HANDOFF.md) first.**
> It carries the current state, what is blocked, and what to do next.

---

## What is in here

Four codebases that share one parameter file and are otherwise independent.

### `powertrain/` — battery pack and drivetrain (MATLAB)

The Molicel P50B 26S21P pack, from cell data through busbar sizing and thermal
design to the mission simulation and Monaco compliance check. Numbered folders
`00_common` through `09_hydro` run in dependency order.

```matlab
% open MATLAB at powertrain/
SMOKE_TEST        % fast check
RUN_EVERYTHING    % full run, a few minutes
TEST_ALL          % regression suite
```

### `cad/` — geometry, structure and optimisation (Python)

`cad/scripts/` is pure numpy and scipy: hull geometry, frame sizing, mass
budget, hydrostatics, aerodynamics and the shape optimiser. Every module
self-tests and exits non-zero on failure.

`cad/blender/` consumes `cad/scripts/` to build and render scenes. It never
reimplements the maths.

```bash
python -m venv .venv && .venv/bin/pip install numpy scipy matplotlib
.venv/bin/python cad/scripts/mass.py
blender -b -P cad/blender/build_scene.py
```

### `propulsor/` — contra-rotating propulsor optimiser (MATLAB)

**Currently incomplete.** Core solver files are missing from the repository;
see `propulsor/README.md`.

### `notes/` and `docs/` — the design record

`notes/00` through `notes/09` are the original design discussion and are
**partly superseded**. Where a note and a script disagree, the script wins:
every number in `cad/scripts/` was re-derived or re-measured from the supplied
STLs, and the scripts check themselves.

`docs/design/` holds the current engineering records. `docs/reference/` holds
the Monaco 2026 rules and the cell datasheet.

---

## Layout

```
notes/              00-09 design notes (partly superseded)
docs/design/        current engineering records
docs/reference/     competition rules, datasheets
docs/decisions/     architecture decision records
powertrain/         MATLAB pack + drivetrain project
cad/scripts/        pure numpy/scipy geometry and physics
cad/blender/        bpy scene builders and renderers
cad/freecad/        FreeCAD STEP export
cad/out/            generated .blend, .json, .csv, figures/
propulsor/          contra-rotating optimiser (incomplete)
source_documents/   supplied cockpit STLs — never modify
tools/              repository utilities
```

The two numbered layouts are not cosmetic. `powertrain/TEST_ALL.m` asserts its
exact folder structure, and `P50B_ProjectRoot.m` derives the project root from
its own position inside `00_common/`. The Python modules resolve data through
`Path(__file__).parents[2]`. **Do not flatten either tree.**

---

## Conventions

**Frame.** X forward, Y port, Z up. Origin at centreline × hull mid-length ×
keel bottom. Millimetres everywhere except Blender scenes, which are metres.
Neither supplied STL uses this frame and the two disagree with each other;
`cad/scripts/volare.py` holds both transforms and self-checks them. Always go
through it.

**Supplied parts are locked.** The hulls and beams must not be modified
(ENERGY_REQ_3). `cad/blender/build_scene.py` enforces this.

**Verify by measuring, not by re-reading parameters.** The scene builders
re-measure the geometry they built and fail on disagreement. That has caught
real bugs that parametric checks could not. Add a measured check whenever you
add geometry.

**Report outcomes faithfully.** If a check fails, say so with the number. When a
computed result contradicts a note, say which note and why, and leave a comment
at the site of the correction.

---

## Status

| Subsystem | State |
|---|---|
| `powertrain/` | Structured and consistent. Blocked on two measured cell data files and the shared parameter file. |
| `cad/scripts/` | 14 of 16 modules pass their self-tests. The other two are blocked on the shared parameter file. |
| `cad/blender/` | Requires Blender; not exercised in CI. |
| `propulsor/` | Incomplete. Core solver files missing. |

Full detail, including every missing file and what it blocks, is in
[`HANDOFF.md`](HANDOFF.md).
