# powertrain/ — Molicel P50B 26S21P pack and drivetrain

Self-contained MATLAB project. Open MATLAB **at this folder**, not at the
repository root.

```matlab
SMOKE_TEST        % fast check during development
RUN_EVERYTHING    % every entry point in dependency order, a few minutes
TEST_ALL          % regression suite
P50B_BUILD        % builds the Simscape battery library into output/
```

`RUN_EVERYTHING.m` calls `addpath(genpath(...))` on this folder, so the numbered
subfolders resolve automatically.

## Layout — do not flatten

`TEST_ALL.m` contains a 23-entry manifest asserting this exact structure, and
`P50B_ProjectRoot.m` derives the project root from its own position inside
`00_common/`. Both break if files are moved to the root.

| Folder | Contents |
|---|---|
| `00_common/` | Parameter plumbing, provenance, project root, architecture audit |
| `01_cell/` | Cell definition, OCV, DCIR |
| `02_pack/` | 21P → 13S21P → 26S21P assembly |
| `03_mechanical/` | Geometry, group layout, cell coordinates, busbars, plots |
| `04_data/` | Measured input tables. `hydrodynamics/` holds the hydro design report |
| `05_tests/` | Electrical and busbar tests plus their fixtures |
| `06_drivetrain/` | Motor, inverter, harness, auxiliary loads, gearbox, propeller |
| `07_simulation/` | Mission profile, mission run, thermal design |
| `08_compliance/` | Monaco compliance, mass budget, verification |
| `09_hydro/` | Hull model, boat dynamics, boat performance |
| `models/` | Simulink and Simscape models (`.slx`) |
| `output/` | Generated artefacts. Tracked so teammates without MATLAB have them |
| `params/` | Shared parameter file — **currently missing, see HANDOFF.md** |

## Sharing numbers with the Python side

`params/volare_params.json` is the single source of truth shared with
`cad/scripts/`. Never duplicate a constant across the two languages. If a number
matters to both, it belongs in that file.
