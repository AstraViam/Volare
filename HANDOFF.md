# Handoff

**Read this file first.** It is the single source of truth for where the project
stands. Anyone, human or AI, should be able to read this page and start work
without reading the rest of the repository.

Last updated: 2026-09-10 (second session) · Branch: `claude/epic-lovelace-36k14r`

---

## 1. Sixty-second orientation

Team Volare, ICT Mumbai. Monaco Energy Boat Challenge 2026, Energy Class.
A 5 m, 250 kg catamaran. The design objective is **minimum electrical energy
per nautical mile**, not maximum propeller efficiency.

There are four independent codebases in this repository. They share parameters
through one file and are otherwise separate.

| Subsystem | Language | Status |
|---|---|---|
| `powertrain/` — 26S21P battery pack, drivetrain, mission, compliance | MATLAB | Structured; blocked on 2 measured data files |
| `cad/` — geometry, frame, aero, optimisation, Blender scenes | Python | 14 of 16 modules self-test green |
| `propulsor/` — contra-rotating propulsor optimiser | MATLAB | **Incomplete: core solver files were never uploaded** |
| `notes/`, `docs/` — design record and competition rules | Markdown | Complete |

---

## 2. Repository map

```
Volare/
├── HANDOFF.md              this file
├── README.md               project overview and quick start
├── CLAUDE.md               working rules for AI assistants and new contributors
│
├── notes/                  00-09, the original design discussion
│                           PARTLY SUPERSEDED — where a note and a script
│                           disagree, the script wins
├── docs/
│   ├── design/             ARCHITECTURE, DRIVETRAIN, HYDRODYNAMICS, COMPLIANCE,
│   │                       BUSBAR_DESIGN, OPTIMISATION, DATA_PROVENANCE,
│   │                       WHY_THIS_ARCHITECTURE
│   ├── reference/          Monaco 2026 rules, notice of challenge, cell datasheet
│   └── decisions/          architecture decision records
│
├── powertrain/             MATLAB pack + drivetrain project (its own root)
│   ├── RUN_EVERYTHING.m    full run, a few minutes
│   ├── SMOKE_TEST.m        fast check during development
│   ├── TEST_ALL.m          regression suite
│   ├── P50B_BUILD.m        builds the Simscape battery library
│   ├── 00_common/          parameter plumbing, provenance, project root
│   ├── 01_cell/            cell data, OCV, DCIR
│   ├── 02_pack/            21P → 13S21P → 26S21P assembly
│   ├── 03_mechanical/      geometry, cell coordinates, busbars, layout
│   ├── 04_data/            measured input tables
│   ├── 05_tests/           electrical and busbar tests plus fixtures
│   ├── 06_drivetrain/      motor, inverter, harness, gearbox, propeller
│   ├── 07_simulation/      mission profile, mission run, thermal
│   ├── 08_compliance/      Monaco compliance, mass budget, verification
│   ├── 09_hydro/           hull model, boat dynamics, boat performance
│   ├── models/             Simulink and Simscape models (.slx)
│   ├── output/             generated artefacts (tracked, see section 6)
│   ├── params/             volare_params.json — the single source of truth,
│   │                       read by MATLAB, the volare package AND cad/scripts.
│   │                       cells/ holds p50b.json and p50b_derived.json
│   ├── python/volare/      coupled electro-thermal pack, boat dynamics, race
│   │                       simulator, mission control dashboard builder.
│   │                       Runs flat from inside the folder, and is also
│   │                       importable as `volare.*` from powertrain/
│   ├── tools/              crosscheck, export_cell_tables,
│   │                       build_mission_control, optimise_layout.
│   │                       All resolve _ROOT as the parent of this folder
│   └── web/                mission_control.html shell that the builder fills
│
├── cad/
│   ├── scripts/            pure numpy/scipy. No bpy. Physics and geometry maths
│   ├── blender/            bpy scripts. Consume scripts/, never reimplement
│   ├── freecad/            FreeCAD STEP export
│   └── out/                generated .blend, .json, .csv
│       └── figures/        rendered PNGs
│
├── propulsor/              contra-rotating optimiser (incomplete)
├── source_documents/       supplied cockpit STLs, not to be modified
└── tools/                  repo utilities  ← two scripts MISSING, see section 5
```

---

## 3. How to run each subsystem

**Python geometry and analysis.** Every module in `cad/scripts/` self-tests and
exits non-zero on failure.

```bash
python -m venv .venv && .venv/bin/pip install numpy scipy matplotlib
.venv/bin/python cad/scripts/mass.py          # any module runs standalone
for f in cad/scripts/*.py; do .venv/bin/python "$f" || echo "FAIL $f"; done
```

**Blender scenes.** These add `cad/scripts` to `sys.path` themselves.

```bash
blender -b -P cad/blender/build_scene.py -- --out cad/out/volare_baseline.blend
blender -b cad/out/volare_baseline.blend -P cad/blender/render_views.py
```

**The volare Python package** (pack thermal, boat, race, dashboard).

```bash
cd powertrain/python/volare
python run.py                 # build everything
python verify.py              # all 5 verification layers
python invariants.py          # physics properties only
```

Outputs land in `powertrain/python/volare/figures/`, which is git-ignored
because `verify.py` rebuilds it in about eight seconds.

**MATLAB pack project.** Open MATLAB at `powertrain/` and run:

```matlab
SMOKE_TEST          % fast, use during development
RUN_EVERYTHING      % full run, a few minutes, use before a review
TEST_ALL            % regression suite
```

`RUN_EVERYTHING.m` calls `addpath(genpath(...))` on its own folder, so the
numbered subfolders resolve automatically. Do not flatten them: `TEST_ALL.m`
asserts this exact layout and `P50B_ProjectRoot.m` derives the project root
from its own position inside `00_common/`.

---

## 4. What was done in the last session (2026-09-10)

The repository was a flat dump of 202 files at the root. It is now structured.

- **Restored the layout both codebases already expected.** The structure was not
  invented. `TEST_ALL.m` contains a 23-entry manifest of required paths, and the
  Python modules resolve data through `Path(__file__).parents[2]`. Both now
  resolve correctly, with **zero code changes** to either project.
- **Fixed a live path bug.** `P50B_ProjectRoot()` returns the parent of its own
  folder. Flat at the repo root, it was resolving to `/home/user`, outside the
  repository, so every data load was pointing at the wrong place. It now
  resolves to `powertrain/`.
- **Fixed a hardcoded Windows path.** `cad/scripts/powertrain.py` defaulted
  `P50B_ROOT` to `C:\Users\aryam\OneDrive\...`, which meant the repo only worked
  on one machine. It now defaults to `<repo>/powertrain` and still honours the
  `P50B_ROOT` environment variable.
- **Removed 11.7 MB of regenerable duplicates**: 18 `.pyc`, 5 Blender `.blend1`
  autosave backups, 1 FreeCAD `.FCBak`, 1 build log. Your `.gitignore` already
  listed these patterns, so they had been force-added before it existed.
- **Renamed the design notes** from `00 - Master Brief.md` to
  `00-master-brief.md` and updated every reference to them.
- Split `cad/scripts/` (pure numpy) from `cad/blender/` (bpy), which is the
  separation `CLAUDE.md` requires and the Blender scripts' own docstrings assume.

Verified afterwards: 23/23 MATLAB manifest paths present, all 24 Python
cross-imports resolve, 14 of 16 `cad/scripts` modules pass their self-tests.

---

## 5. Blockers — files the code needs that are not in the repository

Most of the first session's blockers were cleared by the second upload.

### Resolved

`volare_params.json`, `p50b.json`, `p50b_derived.json`, `crosscheck.py` and
`export_cell_tables.py` are all now present. `cad/scripts/pack_fit.py` went
from blocked to passing, and `cad/scripts/powertrain.py` now reaches its design
checks instead of dying on a missing file.

`celldata/p50b.json` was not missing at all — `build_p50b_dataset.py`
generates it from curve data traced inside that script. It has been generated
and committed, so a fresh clone works without running anything first.

### Outstanding

| Missing | Needed by | Blocks |
|---|---|---|
| `propulsor/` solver, 19 files | `propulsor/main.m` | `resistance_model.m`, `hydrofoil_polar.m`, `gearbox_model.m`, `motor_model.m`, `propeller_geometry.m`, `postprocess.m`, `hull_interaction.m`, `cavitation_model.m`, `structural_model.m`, `submerged_model.m`, `evaluate_design.m`, `design_space.m`, `pareto_front.m`, `sensitivity_analysis.m`, `export_geometry.m`, `plot_geometry.m`, `plot_performance.m`, `manufacturability_penalty.m`, `robustness_penalty.m`. The second upload supplied `config.m`, `bem_rotor.m`, `crp_interaction.m` and `surface_piercing_model.m`; **`main.m` still cannot run.** |

### Known inconsistency, worked around

`volare_params.json` declares `boat.cockpit_stl` as
`04_data/geometry/Cockpit V1.3.stl`. That folder does not exist. The same
geometry is present once, at `source_documents/Cockpit_V1_3.stl`, where
`cad/scripts/geom.py` reads it. Meanwhile `run.py` and `invariants.py` name it
bare as `Cockpit_V1_3.stl`, which only resolved if the working directory
happened to hold a copy.

Rather than duplicate a 1 MB supplied file three ways, `boat.py` gained
`_resolve_stl()`, which falls back to `source_documents/` and to
`04_data/geometry/` (including the spaced spelling) when a bare name is not
found. **Decide which path is canonical and make the parameter file agree**;
the fallback is a bridge, not an answer.

### Not missing

`P50B_MechanicalGeometry.mat` and `TEST_BusbarSizing.csv` are written by the
code on first run.

## 6. Conventions that are easy to get wrong

- **Canonical frame: X forward, Y port, Z up.** Origin at centreline ×
  hull mid-length × keel bottom. Millimetres everywhere except Blender scenes,
  which are metres. Neither source STL uses this frame and the two disagree with
  each other; `cad/scripts/volare.py` holds both transforms and self-checks
  them. Always go through it. Never hand-transform STL coordinates.
- **Never modify the supplied hulls or beams** (ENERGY_REQ_3). They are locked
  in `cad/blender/build_scene.py` via `lock()`.
- **Separate cockpit mass from supplied mass** before comparing to the 250 kg
  cap. Note 06 conflates these and overstates the overage by about 80 kg. Use
  `cad/scripts/mass.py`.
- **`cad/scripts/powertrain.py` exits non-zero by design.** Three of its fifteen
  *design* checks fail. Those are real open engineering issues, not a broken
  script. Do not loosen a check to make it pass.
- **`powertrain/output/` and `cad/out/` hold generated files that are tracked**,
  because teammates without MATLAB or Blender still need them. A rerun will show
  them as modified. Commit a regenerated artefact only when its input actually
  changed; otherwise `git checkout -- <path>` to discard the churn.

---

## 7. Suggested next actions, in order

1. **Upload the 19 missing `propulsor/` solver files, or delete the folder.**
   It is now the only hard blocker. Thirteen files that cannot run are worse
   than none, because a reader cannot tell whether the tool is broken or
   simply absent.
2. **Resolve the cockpit STL path.** Pick one canonical location and make
   `volare_params.json` agree, then remove the fallback in `boat.py`.
3. **Run `TEST_ALL.m` and `RUN_EVERYTHING.m` in MATLAB** and record the result
   in section 8. Neither has been executed since the restructure; there is no
   MATLAB in the environment these sessions run in. This is the largest
   remaining unknown.
4. Work `DATA_NEEDED.md`, which ranks the measurements still standing in as
   estimates by accuracy gained per unit of effort.
5. Consider Git LFS. The repository is 51 MB; see `docs/data-management.md`.
   Still not urgent.

## 8. Session log

Append one entry per working session. Newest first. Keep entries short: what
changed, what broke, what is next.

### 2026-09-10 (second session) — second upload placed, blockers cleared
Merged 46 new files from `main`. Placed them by reading their own path
contracts: `params.py` resolves `project_root()` two levels up, and the four
tool scripts resolve `_ROOT` as their parent, so the package went to
`powertrain/python/volare/` and the tools to `powertrain/tools/`. That makes
one `powertrain/params/volare_params.json` serve MATLAB, the volare package
and `cad/scripts` at once, with no duplicated constants.

Verified: the volare suite passes all 5 layers (418 functional assertions, 0
failures; 0 invariant failures). `cad/scripts` is 16 of 16. `pack_fit.py`
went from blocked to passing.

Fixed: `boat.py` could not find the supplied cockpit STL under any of the
three names the project uses for it; added `_resolve_stl()`. Removed 9 more
`.pyc` files and `volare_params.json.bak`.

Still open: 19 `propulsor/` solver files, and no MATLAB run yet.

### 2026-09-10 — repository restructure
Flat 202-file dump reorganised into the layout both codebases expect. Removed
11.7 MB of regenerable backups. Fixed `P50B_ProjectRoot()` resolving outside the
repo, and a hardcoded Windows path in `powertrain.py`. No MATLAB available in
this environment, so `TEST_ALL.m` has not been run against the new layout;
the 23-path manifest it checks was verified by hand and all 23 are present.
Next: supply `volare_params.json`.

---

## 9. How to update this file

Update it at the end of any session that changes the repository. Specifically:

- Change the **Last updated** date and branch at the top.
- Update **section 1** if a subsystem's status changed.
- Update **section 5** whenever a blocker is resolved or a new one appears.
- Rewrite **section 7** so the next person knows what to do first.
- Add one entry to **section 8**. Do not delete old entries.

Keep it accurate rather than complete. A handoff that overstates progress is
worse than no handoff, because the next person will trust it.
