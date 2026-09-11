# Handoff

**Read this file first.** It is the single source of truth for where the project
stands. Anyone, human or AI, should be able to read this page and start work
without reading the rest of the repository.

Last updated: 2026-09-11 (tenth session) · Branch: `claude/epic-lovelace-36k14r`

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
| `cad/` — geometry, frame, aero, optimisation, Blender scenes, CAD export | Python | 22 modules, 21 self-test green; `powertrain.py` fails on the real mass overrun |
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

**CAD export.** These need cadquery on top of the above. It pulls in OCP, a
~400 MB wheel, and nothing else in `cad/scripts` needs it — the exporters skip
cleanly rather than failing where it is absent.

```bash
.venv/bin/pip install cadquery
.venv/bin/python cad/scripts/export_assembly_step.py   # the whole boat, one STEP
.venv/bin/python cad/scripts/export_motor_step.py      # the propulsion unit
.venv/bin/python cad/scripts/export_supplied.py        # the Organiser's mesh
```

Outputs land in `cad/out/step/`, which has its own README explaining what each
file is for and what the assembly currently shows.

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

**Blocked on a person.**

1. **Rerun `P50B_MassBudget` and `P50B_ExportCompliance` in MATLAB.** The budget
   still carries an 80 kg pilot; the design value is 70 kg. That alone recovers
   10 kg and may close the 9.2 kg gap outright. No Claude session has MATLAB.
   The outboard envelope also changed this session, so the CAD-side mass has
   moved under it.
2. **Run `TEST_ALL.m` and `RUN_EVERYTHING.m` in MATLAB.** Neither has been run
   since the restructure. Largest remaining unknown.
3. **Take the 380 mm rotors to Competr.** The gearcase on their drawing is
   built around roughly 230 mm. Either they supply a gearcase and gearing for
   the design, or the propulsor is re-optimised against a diameter bound that
   the hardware can actually carry. This blocks ordering.

**From the new CAD, all measured and all open.**

4. **Decide which frame is real.** `frame_geometry.py` and the Onshape CAD
   describe different frames: rails 854 apart against 750, 104 × 45 against
   100 × 50, 2970 long against 3113, sloped rails against a 91.3 mm shim.
   `export_assembly_step.py` prints the diff every run. Until this is settled
   every rail-dependent mass and stiffness number is provisional, so it blocks
   items 7 and 8.
5. **Fix the 5.42 mm centreline mis-mate** in `Main_Assembly_v_scaled.step`.
   The hulls and forward pole are at Y = +5.42; everything else is at Y = 0.
   Referred to the hull centreline the clamps are 10.8 mm from symmetric.
6. **Move the clamps out 2.5 mm a side.** Clear gap between clamps is 745.0 mm
   against a 750 mm minimum. Centre-to-centre the rule passes with 104 mm
   spare, so this is 5 mm of insurance against the stricter reading.
7. **Model the pod as a shell.** It is a solid 0.66 m³ body, so interference
   inside the cockpit cannot be tested at all — only containment. Every clash
   answer about cockpit equipment is unavailable until this changes.
8. **Weigh the cooling pack now that it exists in CAD.** The finned exchanger
   and tray are the 3.7 kg the budget says is under-modelled. Measure the
   solids, do not estimate.
9. **Close the mass budget.** 9.2 kg over. Dropping the solar array saves about
   10 kg and is decided; cooling eats most of it. Items 1 and 8 both move this.
10. **Act on the 2027 rule changes.** Reserve the 220 × 111 × 80 mm waterproof
    sensor volume (ENERGY_REQ_195), design the motor seat to 200 N·m
    (ENERGY_REQ_194), check the monitoring connector part number against the
    revised ENERGY_REQ_184 list, decide the post-August-2028 cell chemistry
    (ENERGY_REQ_193). All in `docs/reference/RULES_CHANGES_2026_to_2027.md` §7.

**Propulsor — PAUSED at the user's request. Resume from here.**

11. **Widen the pitch search bounds before the first optimisation run.**
    Efficiency has not turned over by P/D = 2.2 and the bounds stop at 1.52, so
    the optimiser would pin against the upper bound and call it converged.
    `propulsor/DESIGN.md` §9c. Item 3 may change the diameter bound too.
12. **Stage 5: couple the rotors through `crp_interaction.m`.** The gate is that
    rear-rotor inflow strictly exceeds the free-stream advance speed and that
    swirl recovery is positive.

**Housekeeping.**

13. **Do Git LFS.** `volare_assembly.step` is 23 MB. The repository is past the
    point where this is optional. See `docs/data-management.md`.
14. **Resolve the cockpit STL path.** One canonical location, make
    `volare_params.json` agree, remove the fallback in `boat.py`.
15. Work `DATA_NEEDED.md`, which ranks the remaining estimates by accuracy
    gained per unit of effort.

---

## 8. Session log

Append one entry per working session. Newest first. Keep entries short: what
changed, what broke, what is next.

### 2026-09-11 (tenth session) — exporters consolidated, frame conflict surfaced

Consolidation, not new capability. Three exporters had grown three copies of
the same primitives and two competing pictures of the boat.

- **`cad/scripts/solids.py` is new.** `box_solid`, `cylinder_solid`,
  `capsule_chain`, `as_shape`, `intersects` and `write_binary_stl` live in one
  place. The copies had already diverged: one returned a `Workplane`, the other
  a `Shape`, and the intersection test silently returned zero for whichever it
  was not handed. Six self-checks, including a boolean that has to find exactly
  500 000 mm³ between two half-overlapped boxes.
- **`export_step.py` became `export_supplied.py` and does one job.** It writes
  the Organiser's supplied mesh, split and labelled, as the ENERGY_REQ_3
  reference. The designed-parts half it used to carry is now
  `export_assembly_step.py`'s, done better against real CAD. Its outputs
  `volare_designed.step` and `volare_designed.stl` are deleted, not
  regenerated: they described frame v2 against the old supplied pod, which is
  neither the frame the team drew nor the cockpit they drew it in.
- **One script, one job.** `export_assembly_step.py` builds the boat,
  `export_motor_step.py` builds the propulsion unit and is imported by the
  assembly rather than repeated, `export_supplied.py` writes the supplied
  reference.

**The consolidation surfaced a real conflict.** `frame_geometry.py` holds the
frame the repository proposed; the Onshape file holds the frame the team drew.
They are not the same frame, and the exporter now prints the diff every run:

| | CAD | frame v2 |
|---|---|---|
| rail spacing c-c | 854.0 | 750.0 |
| rail section | 104 × 45 | 100 × 50 |
| rail length | 2970.2 | 3112.6 |
| clamp width | 109.0 | 60.0 |
| forward station | rails sloped to follow the pole step | shimmed level, 91.3 mm |

Until somebody picks one, every mass and stiffness number that leans on the
rails is provisional.

**A max() in my first version of that comparison was wrong.** Taking max(|Y|)
over both sides looks harmless and is not: once the hull pair defines the
origin, the cockpit sub-assembly is 5.42 mm off it, the two sides stop being
mirror images, and max(|Y|) reports the further one as if it were both. It
inflated clamp spacing to 864.8 mm and the clear gap to 755.8 mm, turning a gap
that misses ENERGY_REQ_38 into one that passes. The real figures are 854.0 c-c
and **745.0 clear**, 5 mm short on the clear-gap reading. Referred to the hull
centreline the clamps land at +432.4 and −421.6, which is 10.8 mm from
symmetric, and the rule asks for symmetry about the ship's centreline by name.

`tools/run_python_selftests.py`: 22 modules, 21 pass, `powertrain.py` fails on
the 9.2 kg mass overrun as expected. Repo hygiene clean at 268 tracked files.

### 2026-09-11 (ninth session) — the team's CAD arrived; whole boat in one STEP

The user pushed `cad/blender/Main_Assembly_v_scaled.step` (Onshape, AP242) and
supplied the Competr outboard datasheet. Both changed what the repository
believes about the boat.

**`cad/out/step/volare_assembly.step`** is the whole boat in one file, 47 true
B-rep solids: hulls, both poles, pod, rails, clamps, the cooling pack, the
powertrain boxes, seven cable runs, the outboard and both rotors. No STL
anywhere. `cad/out/step/volare_motor.step` is the propulsion unit alone.

**The frame is derived, not hard-coded.** The Onshape file has its own origin
and its X points aft. `export_assembly_step.py` measures the hulls and derives
the transform from them, so a re-export with a moved origin lands correctly
instead of shifting the boat silently.

**What the CAD revealed, all measured:**

- The hull pair sits **5.42 mm off** the cockpit centreline. Rails, clamps, pod
  and aft pole are symmetric about Y = 0; the hulls and the forward pole are
  both at Y = +5.42. One sub-assembly is mis-mated. ENERGY_REQ_38 measures
  clamp symmetry against the ship's centreline, which the hulls define.
- The rails give **750.0 mm clear** between inner faces, centres at ±427.0. The
  clamps are 109 mm wide on those centres, so the clear gap between clamps is
  **745.0 mm**. Centre-to-centre the rule passes with 104 mm spare; as a clear
  gap it is 5 mm short. Moving the clamps out 2.5 mm a side settles both
  readings.
- The poles are **round D104 × 2 mm wall tubes**, not square. Vertex radii
  about the pole axis take exactly two values, 50.0 and 52.0 mm.
  `BASELINE["beam_*"]["section_mm"] = (104, 104)` is a bounding box and had
  been read as a section.
- The two unnamed Onshape solids are a **finned heat exchanger and its tray**,
  595 × 515 × 82 in a 621 × 526 × 100 tray, mid-boat under the pod. The cooling
  system the budget says is under-modelled by 3.7 kg now exists in CAD.

**The datasheet corrected the outboard.** The specification table reads
"300x210x800mm" and `motor.length_m = 0.8` was being used as an 800 mm
**fore-aft** length, which laid a 705 mm-tall outboard on its side with 800 mm
of it astern. The dimensioned drawing (section 6, page 7) says **322 fore-aft,
210 across, 705 cowling top to gearcase bottom**, 546 overall at propeller
level. `powertrain.py` now builds that box. The rotors are **tractive**,
forward of the leg, per datasheet section 5.1. Thirteen drawing dimensions went
into the parameter file with page references; `powertrain.vcu_size_mm` went
from the table's 260 × 160 × 90 to the drawing's 260 × **175** × 90. The 10 kg
that sat on a fictional 120 × 90 × 500 drive leg is now the transom bracket,
470 × 600 × 250, which is what the datasheet actually weighs. Vertical position
comes from the new `powertrain.motor_plate_z_mm`: the drawing dimensions
everything from the anti-ventilation plate, so the plate is the datum, at the
keel line. Blade tips end up 280 mm below the keel, which is what
`hydro.propulsor_type` "fully submerged" assumes.

**The rotors are the team's, and they do not fit.** Generated from the
converged design and the chord, thickness and camber shapes in
`propulsor/config.m`, then re-measured on the built solid: diameter, EAR and
P/D at 0.7R all read back exact. They are **380 and 361 mm** against a gearcase
drawn around roughly 230 mm. About 65 per cent too large for the stock gearcase
or its gearing. Raise it with Competr before ordering.

**Three of my own checks were wrong, not the geometry.** Swept diameter read
off a bounding box under-reads by several per cent, because three skewed tips
120° apart rarely put one on an axis; then read about the boat origin instead
of the shaft axis it over-reads by the mounting height. P/D was sampled at the
nearest station to 0.7R rather than interpolated to it. All three now measure
what they claim to.

**The clash list is computed, not remembered.** The old export carried five
clashing components copied out of a Blender run. Every designed part is now
intersected against the structure. Nothing clashes. The pod is excluded on
purpose: in this CAD it is a solid 0.66 m³ body, not a shell, so everything in
the cockpit "intersects" it. Containment is what a solid can answer, and every
cockpit part is inside its envelope.

`tools/run_python_selftests.py`: 21 modules, 20 pass, `powertrain.py` fails on
the 9.2 kg mass overrun as expected. Both new exporters skip cleanly rather
than failing where cadquery is not installed.

### 2026-09-11 (eighth session) — full boat exported as a CAD assembly

The deliverable is `cad/out/step/`, four files in one coordinate frame, plus a
README that explains what each is for.

- `cad/scripts/frame_geometry.py` is new. Frame v2 was defined inside
  `cad/blender/frame_redesign.py`, which put geometry maths in the Blender
  layer against the rule in CLAUDE.md. The STEP exporter was the second
  consumer, so the maths moved to `cad/scripts/` and both read it. Its
  self-check reproduces the Blender stack-up exactly: 750.0 mm clamp spacing,
  124.0 mm clamp OD, 91.3 mm forward shim, 671.4 / 681.4 mm rail top and pod
  floor, 9 parts.
- `cad/scripts/export_step.py` is new. It writes `volare_designed.step`
  (35 true B-rep solids in a named tree), its tessellation,
  `volare_supplied.stl` (hulls, both poles, pod shell, hull fittings) and
  `volare_supplied_frame.stl` (the original rails and pads that v2 replaces).
- **The supplied geometry is split by measured size, not by triangle index.**
  Each connected component of `FULLCOCPITV1_3.stl` is matched against
  `volare.BASELINE`, so a re-exported STL with a different component order
  still lands in the right file, and a component that no longer matches the
  measured baseline fails loudly instead of being mislabelled. Counts are
  asserted: 2 hulls, 2 poles, 1 pod, 2 rails, 6 pads, 4 fittings.
- **The shared frame is verified by measuring, not asserted.** After the
  transform the hull box lands on X = −0.04, Y = −0.04, Z = −0.05 mm, so the
  origin the frame claims is the origin the mesh actually has.
- **The poles are round tubes, not square.** Vertex radii about the pole axis
  take exactly two values, 50.0 and 52.0 mm: a D104 × 2 mm wall tube with open
  ends. `BASELINE["beam_*"]["section_mm"] = (104, 104)` is a bounding box and
  had been read as a square section. The v2 clamp bores 108 mm over it, giving
  the 2.0 mm radial gasket gap by design — now measured, not assumed.
- Frame v2 lifts the pod floor +103.7 mm, clearing the 85.7 mm rail/pod
  interference measured in the supplied assembly.
- Three defects fixed in the exporter while writing it: `cylinder_solid` built
  its solid twice and discarded the first, `Assembly.save` is deprecated in
  cadquery 2.8 in favour of `export`, and importing cadquery unconditionally
  would have broken `tools/run_python_selftests.py` on any machine without the
  400 MB OCP wheel. The cadquery import is now optional and the supplied half,
  which is pure numpy, still runs and still checks the frame without it.
- Five components remain in group `CLASH`, red, intersecting the pod shell.
  Grouped, not hidden, and not resolved.

`tools/run_python_selftests.py`: 19 modules, 18 pass, `powertrain.py` fails on
the 9.2 kg mass overrun as expected.

**Requested and not delivered:** the user asked for the whole motor to be built
from a scaled drawing. No image or file reached the repository, so nothing was
built. See section 7 item 3.

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
