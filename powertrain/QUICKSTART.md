# Quickstart

```bash
pip install numpy scipy matplotlib      # only dependencies
python3 run.py                          # build everything
python3 verify.py                       # run every check
```

Then open **`figures/mission_control.html`**.

Individual tasks:

| Command | What it does |
|---|---|
| `python3 run.py cell` | Cell characterisation: load curves, extract R0(SOC,T), fit Arrhenius, cycle life |
| `python3 run.py geometry` | Build the 3D pack, report hydraulics, warn about uncooled cells |
| `python3 run.py boat` | Hull, resistance breakdown, propeller matching, power-speed curve |
| `python3 run.py bench` | Real-time factor benchmark |
| `python3 run.py race` | Coupled boat+pack race, writes the interactive dashboard |
| `python3 run.py charge` | CC-CV charging, pack heat, between-race turnaround table |
| `python3 run.py modules` | Module layout: place and rotate blocks of cells |
| `python3 run.py live` | **Live interactive simulator** — verify scheme, write HTML |
| `python3 run.py studies` | The six thermal investigations + figures |

### Verification

| Command | What it checks |
|---|---|
| `python3 verify.py` | **All four layers below, one command** |
| `python3 invariants.py` | Physics properties swept across the parameter space |
| `python3 audit.py` | The dashboard as an artefact — ids, controls, class writers |
| `python3 functest.py` | Every control fired, every view drawn, in every theme |

Every layer has been validated by deliberate sabotage — 12 defects introduced,
12 caught. See `SABOTAGE.md`.

Two HTML outputs, both self-contained (no server, no internet):

| File | What it is |
|---|---|
| **`figures/live_simulator.html`** | **Drive it.** Real physics in the browser — throttle, autopilot, live coolant flow / sea temp / ambient / headwind. 128 KB. |
| `figures/race_simulator.html` | Pre-computed replay of 4 scenarios, scrub through time. 6 MB. |

### Mission Control — the six views

| View | Key | What it's for |
|---|---|---|
| Telemetry | `1` | Track map, timing tower, live delta, traces, boat, alarms, arbitration |
| Thermal | `2` | Physical pack layout, 8 channels, coolant circuits, energy balance, measured R₀, digital twin |
| Strategy | `3` | Pace-vs-distance, distance-against-clock projection, lap log |
| Engineering | `4` | Current sharing, drivetrain thermal, drag breakdown, provenance |
| Setup | `5` | Cooling trade sweep, manifold distribution, cell degradation |
| Analysis | `6` | Energy flow, limiter share, lap-over-lap, sensitivity |

**Controls:** `W`/`S` throttle · `X` cut · `SPACE` hold · `A` autopilot ·
`R` reset · `F` fullscreen · `D` daylight · `P` provenance · `[` `]` replay ·
`Ctrl+K` command palette (48 commands) · click any cell to inspect it.

### The live simulator

Runs the *actual* model in JavaScript: same electro-thermal pack, same hull
resistance, same propeller, same 25 kW cap. Verified to **0.099 K RMS** against
the implicit reference solver before it is written (`run.py live` prints the
check — if it ever exceeds 0.5 K it warns).

Why a different numerical scheme in the browser: only the coolant nodes are
stiff (τ ≈ 2×10⁻⁵ s, because their thermal mass is genuinely negligible), and
the coolant chain is a DAG. Solving coolant as a steady forward sweep in flow
order removes the stiffness entirely, after which explicit Euler at dt = 0.5 s
is comfortably stable for everything else (the tightest remaining limit is the
can node at dt < 8.5 s).

Controls:
- **throttle** — manual power demand, hard-clamped to 25 kW in one place
- **autopilot** — speed-following with corner speed caps from the course radii
- **time** — 1× to 100× compression
- **live environment** — change coolant flow, sea temperature, ambient and
  headwind *mid-run* and watch the pack respond

The boat view shows the hull below the waterline and the cockpit above it,
with airflow streamlines whose density and speed scale with boat speed, spray
at the bow, and a wake that grows with v². The hull rises as it planes.

---

## Everything is configured in one place

Open `run.py` and edit `CONFIG` at the top. You never need to touch model code.

```python
CONFIG['pack']['n_series']    = 26      # voltage
CONFIG['pack']['n_parallel']  = 21      # capacity
CONFIG['pack']['n_layers']    = 2       # stack depth (must divide n_series)
CONFIG['pack']['tube_every']  = 2       # tube in every Nth row gap
CONFIG['pack']['n_circuits']  = 3       # parallel hydraulic circuits
CONFIG['coolant']['flow_L_per_min'] = 8.0
CONFIG['hull']['stl']         = 'volare.stl'      # your hull
CONFIG['cell']['dataset_folder'] = 'celldata/'    # your traced curves
```

---

## Your data is already loaded

Two real inputs are wired in by default:

| Input | File | Status |
|---|---|---|
| Cell characterisation | `celldata/p50b.json` | Built from your three datasheet plots |
| Cockpit geometry | `Cockpit_V1_3.stl` | 2532 × 700 × 486 mm, real frontal area |
| Demihull geometry | — | **Still parametric — send the hull STL** |

Regenerate the cell dataset any time with:
```
python build_p50b_dataset.py
```
The traced point arrays live at the top of that file — edit them directly if
you want to refine a curve.

### What came out of your plots

Sustained resistance, extracted from the rate family at 23 °C and offset
across the temperature sweep:

| T (°C) | R at 50 % SOC |
|---|---|
| −40 | 53.64 mΩ |
| 0 | 20.64 mΩ |
| 10 | 16.64 mΩ |
| **23** | **11.64 mΩ** |
| 45 | 10.64 mΩ |
| 60 | 8.64 mΩ |

11.64 mΩ at 23 °C against the datasheet's 12.8 mΩ DC figure — close enough to
believe the extraction. Note how flat it is from 23 to 60 °C (only −26 %):
this is a power cell, and its temperature sensitivity lives almost entirely
below 10 °C. That is why a single Arrhenius exponent can't span −40 to +60 °C,
and why the model uses the measured 2D map directly rather than a fitted
exponential.

The temperature-sweep rate isn't printed on the datasheet, so it's inferred by
matching the 23 °C curve against the rate family — it came out at **2C**, with
an 18 mV match residual. If you know the real rate, set `TEMP_C_RATE` in
`build_p50b_dataset.py`, because R(T) scales inversely with it.

### Cycle life, and what it means for you

At 25 kW you draw 13.2 A/cell ≈ **48 W/cell**, which sits between the
datasheet's −1C (18 W) and −100 W curves:

| Discharge | Retention at 500 cycles |
|---|---|
| 1C (18 W) | 90.5 % |
| 100 W | 84.0 % |
| 150 W | 80.0 % |
| 200 W | 75.5 % |

So expect roughly **87–90 % at 500 cycles** at race power. Charge rate barely
matters by comparison (+1C to +5C costs only 3.5 points); discharge power
dominates fade.

---

## Using other cell data

Trace the datasheet graphs in [WebPlotDigitizer](https://automeris.io/WebPlotDigitizer/)
(free, browser-based). Export one CSV per curve into a folder, named so the
rate and temperature are in the filename:

```
celldata/
  discharge_0.2C_25C.csv      # x = Ah (or mAh), y = volts, no header
  discharge_1.0C_25C.csv
  discharge_5.0C_25C.csv
  discharge_1.0C_0C.csv
  discharge_1.0C_45C.csv
  cycle_1.0C_100DOD_25C.csv   # x = cycle number, y = retention (% or fraction)
```

Then set `CONFIG['cell']['dataset_folder'] = 'celldata/'`.

**You need at least two different C-rates at the same temperature** — that is
what makes the resistance extraction possible:

```
R_sustained(SOC, T) = (V_lowrate − V_highrate) / (I_high − I_low)
```

Three or more temperatures additionally give you the Arrhenius activation
energy, which controls the whole thermal-feedback question.

Twenty minutes of tracing replaces every `[LOW]`-confidence number in the
model with one that is yours.

---

## Using your own hull

```python
CONFIG['hull']['stl'] = 'volare.stl'
CONFIG['hull']['displacement_kg'] = 250.0
```

The loader reads binary or ASCII STL, auto-detects millimetres, bisects for
the waterline that displaces your mass, and clips every triangle at that
plane — so wetted area (below, in water) and dry area (above, in air) come
from real geometry rather than a guess. Wetted area is 60–80 % of your drag at
cruise, so this matters more than almost anything else you can measure.

---

## Modules — moving blocks of cells like MATLAB

```python
import geometry as gm

mods = [gm.Module(rows=13, cols=21, origin=(0, 0, 0),    series_offset=0,  name="fwd"),
        gm.Module(rows=13, cols=21, origin=(0.02, 0.36, 0), yaw_deg=6.0,
                  series_offset=13, name="aft")]

print(gm.check_module_clearance(mods))          # flags overlaps in mm
geom = gm.modules_to_geometry(mods, tube_every=2, n_circuits=3)
```

Each module carries its own cells, gets its own serpentine cooling circuits
generated in its local frame and rotated with it, and reports its footprint in
millimetres. `check_module_clearance` returns the gap between every pair of
co-planar modules and flags negatives as overlapping.

**Watch the circuit count.** Each module generates `n_circuits` circuits of its
own, so two modules at `n_circuits=3` gives you **six** total — halving flow per
circuit and pushing you toward laminar. Set it so the total stays near 3.

---

## Charging

```python
CONFIG['charging']['supply_A'] = 16      # shore outlet
CONFIG['charging']['cc_current_A'] = 2.5 # per cell
```

`run.py charge` gives the turnaround table — the only charging question that
matters between races:

| start SOC | after 1 h | 2 h | 3 h | 4 h |
|---|---|---|---|---|
| 5 % | 37 % | 67 % | 95 % | 100 % |
| 15 % | 47 % | 76 % | 100 % | 100 % |
| 30 % | 60 % | 89 % | 100 % | 100 % |
| 50 % | 79 % | 100 % | 100 % | 100 % |

Empty to full is **3.23 h**, and time in true constant-current is **0 %** — at
16 A shore the supply is the binding limit from 5 % to 100 %, so the CC-CV
shape never matters. Peak pack heat while charging is only 25 W, so trailer
charging without coolant flow is fine.

Charging is blocked outright below 0 °C (lithium plating is permanent, a
safety hazard, and invisible until the cell fails) and derated above 40 °C.

---

## Custom geometry beyond the stacked grid

`geometry.py` takes arbitrary 3D cell positions and arbitrary tube polylines:

```python
import numpy as np, geometry as gm

positions = np.array([[x, y, z], ...])        # any arrangement you like
series_id = np.array([0, 0, 0, 1, 1, 1, ...]) # which parallel group each is in

tubes = [gm.TubePath(np.array([[0,0,0], [0.5,0,0], [0.5,0.05,0]]), circuit=0)]

geom = gm.PackGeometry(positions=positions, series_index=series_id, tubes=tubes)
```

Or pack cells into a hull-constrained outline:

```python
outline = np.array([[0,0], [0.6,0], [0.55,0.4], [0.05,0.4]])
pts = gm.pack_into_outline(outline, pitch_x=0.0235, pitch_y=0.0235)
```

Cells couple to any tube segment within reach, with conductance falling off
linearly with distance — so serpentine, spiral, cross-layer and manifold-and-
rail routings all work without special-casing.
