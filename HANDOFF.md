# Handoff

**Read this file first.** It is the single source of truth for where the project
stands. Anyone, human or AI, should be able to read this page and start work
without reading the rest of the repository.

Last updated: 2026-09-11 (seventh session) · Branch: `claude/epic-lovelace-36k14r`

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
| `propulsor/` — contra-rotating propulsor optimiser | MATLAB | **PAUSED at the user's request.** Stages 0-4 built and gated, 147 checks green, BEM runs end to end. Stages 5-12 remain; see `propulsor/DESIGN.md` |
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
├── propulsor/              contra-rotating optimiser. INCOMPLETE but planned;
│                        read DESIGN.md before touching it
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

**MATLAB sources, without MATLAB.** GNU Octave runs the numerical core, and
CI uses it. Every `propulsor/*.m` file parses in Octave today.

```bash
sudo apt-get install -y --no-install-recommends octave
octave --no-gui --quiet tools/octave_check.m     # parse + portability gate
cd propulsor && octave --no-gui --quiet tests/ci.m   # build-stage gates
```

In MATLAB the same suite runs as `cd propulsor/tests; run_tests`.

Write to the MATLAB/Octave intersection: no `arguments` blocks, no `string()`,
no `classdef`, no `dictionary()`, and guard every toolbox call. The check above
fails the build otherwise. Reasoning is in `propulsor/DESIGN.md` section 2.

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

1. **Close the mass budget.** It is 9.2 kg over. Dropping the solar array
   saves about 10 kg and is decided, but the CAD says cooling is under-modelled
   by 3.7 kg, which eats most of it. Needs either the component-by-component
   hunt through frame, shell and mounting hardware, or the pack-to-6-kWh and
   carbon-rail levers back on the table.
2. **Rerun `P50B_MassBudget` and `P50B_ExportCompliance` in MATLAB.** The
   budget still carries an 80 kg pilot; the design value is now 70 kg. That
   alone recovers 10 kg and may close the gap outright. Cannot be done from a
   Claude session, there is no MATLAB.
3. **Act on the 2027 rule changes.** Reserve the 220 x 111 x 80 mm waterproof
   sensor volume (ENERGY_REQ_195), design the motor seat to 200 N·m
   (ENERGY_REQ_194), check the ordered monitoring connector part number against
   the revised ENERGY_REQ_184 list, and decide the post-August-2028 cell
   chemistry (ENERGY_REQ_193). All listed in
   `docs/reference/RULES_CHANGES_2026_to_2027.md` section 7.
2. **Widen the pitch search bounds before the first optimisation run.**
   Efficiency has not turned over by P/D = 2.2 and the configured bounds stop
   at 1.52, so the optimiser would pin against the upper bound and report it
   as converged. `DESIGN.md` section 9c has the numbers.
3. **Stage 5: couple the rotors through `crp_interaction.m`.** Both wrappers
   and the single-rotor solver are in place; what remains is verifying the
   coupled loop converges and that the rear rotor genuinely recovers swirl.
   The gate is that rear-rotor inflow strictly exceeds the free-stream
   advance speed and that swirl recovery is positive.
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

### 2026-09-11 (seventh session) — design checks fixed, CAD now param-driven
Propulsor work paused at the user's request; this session was structure and
design.

**The three failing powertrain.py checks were not what they looked like.** Two
were bugs in the checks, one was a real physical error, and the genuine
engineering problem was hidden behind them.

- Stale geometry export was a false alarm of my own making: the check compared
  file modification times, so annotating a comment in volare_params.json
  tripped it. It was also silent the other way. It now compares the 12 values
  the export was built from and names the parameter that moved.
- The phase-U cable asked for a 37 mm bend radius in a cable rated 132 mm. The
  route climbed over the outboard and hairpinned, and the inverter sits only
  90 mm above the outboard top, so LENGTHENING the legs made it worse: 105 mm
  at a 152 mm leg falling to 82 mm at 232 mm. A monotonic descent gave 237 mm
  and a SHORTER run, 545 to 336 mm, which also helps EMC.
- The CAD-versus-budget mass comparison was wrong in sign and magnitude. It
  looked for a budget line "HV harness and switchgear"; the budget has two
  lines, "HV switchgear" and "HV harness (cable)". Nothing matched, 9.6 kg
  vanished, and the CAD looked 7.0 kg heavy when it is 2.1 kg light. Replaced
  with an explicit mapping plus a completeness check, because a membership test
  cannot fail loudly and a mapping can. Its tolerance was also structurally
  broken: abs(delta) <= margin_kg with margin_kg at -9.2 could never pass.

19 checks now, 1 failing, and that one is the real problem: the mass budget is
9.2 kg over the 250 kg cap.

**Per-line mass audit** now prints. The disagreement is concentrated in two
places: the CAD models only a heat exchanger and pump against a 7.0 kg cooling
allowance, 3.7 kg short and most likely coolant, hoses and cold plate; LV is
1.1 kg heavy.

**The CAD is now driven from volare_params.json.** Only 3 of 24 scripts read
it; the rest hardcoded, so a parameter edit silently failed to reach the
geometry. Added `cad/scripts/params.py`, standard library only so it works
under Blender and FreeCAD as well as CPython, and made `volare.py` derive its
rules and design constants from it. Verified by propagation: changing pilot
mass to 95 kg and beam diameter to 120 mm moved through to the CAD.

Pilot mass is a stated 70 kg design value, configurable, with a check that
fails loudly if `volare.py` and the parameter file drift; they did, 70 against
80. Added `motor.power_limit_W` at 25 kW as the enforced controller limit that
makes the outboard legal under ENERGY_REQ_188.

### 2026-09-11 (sixth session) — propulsor stages 3 and 4, solver running
Built `hydrofoil_polar.m`, `propeller_geometry.m`, `prandtl_loss.m`,
`bem_front_rotor.m` and `bem_rear_rotor.m`. **The blade element momentum
solver now runs end to end and converges at every advance ratio tested.**

Interface catch: `bem_rotor.m` calls
`hydrofoil_polar(alpha, Re, toc, foc, vent, params)` returning two plain
arrays, not the struct-returning signature written first. Rewritten to match
the existing caller, which also added the ventilated-section branch the
config already parameterises: linearised supercavitating theory gives a lift
slope of pi/2 per radian, a quarter of the wetted 2*pi, and the test confirms
the ratio at 4.25 against the thickness-corrected slope.

`crp_interaction.m` calls `bem_front_rotor` and `bem_rear_rotor` by name.
Rather than duplicate the solver, both are thin wrappers on `bem_rotor` that
add rotor-specific warnings: the front one warns if given pre-swirl, since an
actuator disc induces no tangential velocity upstream of itself; the rear one
warns if given none, since that would be two independent propellers rather
than a contra-rotating pair.

A real modelling error was caught by a symmetry test: the drag bucket was
centred on a single global `Cl_design`, which put minimum drag at a positive
angle of attack even for an uncambered section. It is now centred on the
section's own camber-derived design lift, so an uncambered section has its
drag minimum at zero incidence, as symmetry requires.

Three of my own tests were wrong rather than the code, and each taught
something: an absolute curvature threshold cannot distinguish a kink from
designed blend curvature (convergence under refinement can); 25 kW is
unreachable at 2000 rpm because the torque limit binds first; and increasing
rotation rate means decreasing advance ratio, so a trend assertion over the
sweep reads backwards unless sorted.

`round(x, n)` is MATLAB-only and Octave rejects it. Added it to
`tools/octave_check.m` along with `contains`, `strlength` and `isstring`.

First real result from the running model: at 20 knots the thrust loading is
only C_T = 0.072, and efficiency rises monotonically with pitch across the
whole searchable range without turning over. The supplied 26.5 inch reference
pitch is P/D = 1.35 and sits near the bottom. **The configured pitch search
bounds of 22 to 30 inches are probably too narrow.** See `DESIGN.md`
section 9c.

147 checks green.

### 2026-09-10 (fifth session) — 2027 rules adopted
Replaced the 2026 Technical Rules and Notice of Challenge with the 2027
editions (2027.1, issued 07/09/2026). The 2026 documents moved to
`docs/reference/archive-2026/` rather than being deleted, because decisions
already recorded in `notes/` were made against them.

Compared both documents requirement by requirement: 174 in each year, with
**4 new, 4 withdrawn and 11 revised**. Full record in
`docs/reference/RULES_CHANGES_2026_to_2027.md`.

The important one: **ENERGY_REQ_188 went from v1.0 to v1.1**, changing "total
nominal power" to "sum of instantaneous power consumption of all motors" with
an explicit note that no peak may exceed 25 kW. Our cap was already correct,
but it had been attributed to a team decision. It is a competition rule, and
`config.m` now says so.

New and relevant: **ENERGY_REQ_194** requires the motor seat to withstand 200%
of maximum motor torque, so 200 N·m. **ENERGY_REQ_195** requires a waterproof
220 x 111 x 80 mm volume per traction chain. **ENERGY_REQ_186** now bans
hydrofoils outright. **ENERGY_REQ_193** requires LFP or solid-state cells from
August 2028, and the Molicel P50B is NMC, so the pack is fine for 2027 and not
beyond it without Technical Committee approval.

Withdrawn: ENERGY_REQ_174, 175 and 176, the bulkhead hole specification. Our
compliance code checked two of them; they are now marked WITHDRAWN rather than
deleted, which downstream FAIL counters ignore, so the audit trail survives.

Unchanged and load-bearing: the 250 kg mass limit, the 10 kWh energy cap and
every energy factor, the 4 m2 solar limit.

Added `tests/test_stage2b_rules.m`, 22 checks pinning every rules-derived
constant to its requirement id. One of them caught a bug in my own test rather
than the code: 25 kW at 2000 rpm would need 119.4 Nm against a 100 Nm limit,
because below the 2387.3 rpm corner the motor is torque limited.

69 checks green. Event dates: racing 1-3 July 2027.

### 2026-09-10 (fourth session) — propulsor stages 0-2 built and gated
Team decision applied: **the motor is capped at 25 kW at all times, peak equal
to continuous.** `params.motor.P_cap_W` is the enforced ceiling; the supplied
42 kW datasheet peak stays recorded with `usePeakSpec = false` so nothing
supplied is silently altered. Envelope: torque limited at 100 N·m up to
2387.3 rpm, power limited above it, so 2500 rpm yields only 95.5 N·m.

Built and gated:
- `units.m`, which unblocked `config()`. It could not run at all before.
- `resistance_model.m`, pchip over the 5 supplied points, refusing to
  extrapolate unless asked and refusing outright to fabricate the 300 kg curve.
- `motor_model.m` plus `motor_consistency_report.m`.
- `tests/` harness: `run_tests.m` for MATLAB, `tests/ci.m` for headless CI.

45 checks green. Verified the gates are not vacuous by injecting two
regressions: raising the cap to 42 kW failed 8 checks, and swapping pchip for
linear initially passed, which exposed a real gap. Added a slope-continuity
discriminator (pchip leaves 0.001 N/kn of jump at a knot, linear leaves 14.8)
and the swap now fails.

MATLAB CI is now worth setting up, since a Campus-Wide Licence is confirmed.
Keep both jobs: Octave as the fast gate, MATLAB as the fidelity gate.

Next: stage 3, `hydrofoil_polar.m` and `propeller_geometry.m`.

### 2026-09-10 (third session) — propulsor planned, Octave adopted
Assessed whether to delete `propulsor/` and restart. **Salvage, not restart.**
Reading the code rather than the README: `bem_rotor.m` reduces the coupled
(a, a') system to one scalar equation per station and solves it with Illinois
bracketing on a cell-centred grid, having explicitly rejected fixed-point
iteration as unstable at high solidity. `optimization_driver.m` already carries
toolbox-free `pso_local` and `pattern_search`. Deleting would discard the hard
half and rebuild it at the same design.

Wrote `propulsor/DESIGN.md`: architecture, 22-file plan with measured status,
`params` schema, 12-stage build order, and the unknowns needing CFD.

Adopted **GNU Octave** as the development and CI runtime, because no session
and no runner has MATLAB, and unrun MATLAB is almost certainly broken MATLAB.
All 13 existing propulsor files parse in Octave with zero MATLAB-only
constructs. Added `tools/octave_check.m` plus a CI job; verified it exits 1 on
a violation and 0 when clean.

Confirmed the motor contradiction numerically: 42 kW needs either 160.4 N·m at
2500 rpm or 4010.7 rpm at 100 N·m, 60% beyond either hard limit.

Next: `units.m`, then build stages 1 and 2.

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
