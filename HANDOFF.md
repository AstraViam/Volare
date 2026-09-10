# Handoff

**Read this file first.** It is the single source of truth for where the project
stands. Anyone, human or AI, should be able to read this page and start work
without reading the rest of the repository.

Last updated: 2026-09-10 · Branch: `claude/epic-lovelace-36k14r`

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
│   └── params/             shared parameter file  ← MISSING, see section 5
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

These are genuine gaps, not breakage from the restructure. Each one blocks
something specific.

| Missing file | Needed by | Blocks |
|---|---|---|
| `powertrain/params/volare_params.json` | `P50B_LoadParams.m`, `cad/scripts/powertrain.py`, `layout.py` | The shared parameter file. Blocks `powertrain.py` and `pack_fit.py`, and the MATLAB parameter checks. **Highest priority.** |
| `powertrain/04_data/P50B_OCV_SOC.csv` | `01_cell/P50B_OCV.m` | Measured open-circuit voltage against state of charge. Produce from an HPPC pulse sequence. |
| `powertrain/04_data/P50B_DCIR_SOC_T.csv` | `01_cell/P50B_DCIR.m` | Measured DC internal resistance against SOC and temperature. Same HPPC run. |
| `powertrain/params/cells/p50b_derived.json` | `SMOKE_TEST.m`, `01_cell/P50B_CellData.m` | Generated by `tools/export_cell_tables.py`, which is also missing. |
| `tools/export_cell_tables.py` | the above | Derives cell tables from the measured CSVs. |
| `tools/crosscheck.py` | `P50B_ArchitectureAudit.m`, `P50B_ThermalDesign.m` | Cross-check between MATLAB and Python parameter values. |
| `propulsor/` core solver | `main.m` | `config.m`, `bem_rotor.m`, `resistance_model.m`, `motor_model.m`, `propeller_geometry.m`, `postprocess.m`, `evaluate_design.m`, `design_space.m`, `pareto_front.m`, `sensitivity_analysis.m` and others. **`main.m` cannot run at all.** The root `README.md` from the upload described this tool in detail, so the code exists somewhere; it was simply not part of the upload. |

Two files listed as "missing" by a naive scan are **not** missing: 
`P50B_MechanicalGeometry.mat` and `TEST_BusbarSizing.csv` are written by the
code on first run.

---

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

1. **Supply `volare_params.json`.** It unblocks the most code for the least
   effort, on both the MATLAB and Python sides.
2. **Upload the missing `propulsor/` solver files**, or delete the folder if
   that tool has been abandoned. Right now it is nine files that cannot run,
   and the reader cannot tell which.
3. **Supply the two measured cell CSVs**, or record in `docs/design/DATA_PROVENANCE.md`
   that they are pending and which numbers currently stand in for them.
4. Run `TEST_ALL.m` in MATLAB and record the result in section 8 below. It has
   not been run since the restructure, because this environment has no MATLAB.
5. Consider enabling Git LFS before the repository grows further. See
   `docs/data-management.md`. It is not urgent at 49 MB.

---

## 8. Session log

Append one entry per working session. Newest first. Keep entries short: what
changed, what broke, what is next.

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
