# Optimisation pass

What was measured, what was changed, and what is still on the table.

Everything here was found by profiling or sweeping, not by guessing. Where a
change is a judgement call rather than a fix, it says so.

---

## 1. Performance

`P50B_CellData` was taking **8.8 seconds per call**, and it is called from
almost everywhere. The cost is constructing the Simscape Battery cell object.

Two problems compounded it:

- **`P50B_Geometry` called it just to read three numbers** — cell diameter,
  height and mass — paying nine seconds for an object it never touched. It now
  reads them from `params/volare_params.json` directly. Same single source of
  truth, no Simscape.
- **Nothing was cached.** `P50B_CellData` and the four drivetrain parameter
  sets are pure functions of the parameter file, and every call rebuilt them.
  All five now cache against the file's timestamp, so editing
  `volare_params.json` still takes effect immediately.

| Function | Before | After | Speedup |
|---|---:|---:|---:|
| `P50B_CellData` | 8795 ms | 1.7 ms | **5200×** |
| `P50B_Geometry` | 997 ms | 4.9 ms | **200×** |
| `P50B_MotorData` | — | 2.2 ms | cached |
| `P50B_DrivetrainModel` | 500 ms | 13.5 ms | **37×** |
| `P50B_ThermalDesign` | 1147 ms | 50 ms | **23×** |
| `P50B_Verification` | 2284 ms | 134 ms | **17×** |
| `P50B_MonacoCompliance` | 2338 ms | 89 ms | **26×** |

`TEST_ALL` went from ~40 s to **27.7 s**, and that residue is mostly the one
unavoidable cold Simscape construction.

The drivetrain figure matters most in practice: a mission is thousands of time
steps, and 500 ms each would have made any sweep unusable.

---

## 2. A parameter that disagreed with its own data

`cell.Ea_over_R_K` — the Arrhenius activation governing how cell resistance
falls with temperature — was **2500 K, tagged ASSUMPTION**.

Fitting it from the digitised temperature-series discharge curves in
`p50b.json` gives **1255 K**. The assumption was almost exactly double the
value the project's own data implies.

This is not a small parameter. It sets the strength of the
hotter → lower R → more current → hotter feedback loop, which is the entire
subject of the current-hogging study. It is now `DIGITISED` and carries the
fitted value, with the fit restricted to 0–60 °C — one exponent cannot span
−40 to +60 °C, because the low-temperature rise is a different mechanism and
drags the fit badly.

**How this was missed:** the fitted value was already being computed and
written into `p50b_derived.json`, but nothing compared it against the assumed
scalar in the parameter file. Two numbers for the same quantity, in two files,
never checked against each other.

---

## 3. Mission Control features that were silently absent

The dashboard was being rebuilt from the unified parameters, but the builder
was passing only a fraction of what the page can display. Four whole features
were dark:

| Feature | Symptom | Fixed by |
|---|---|---|
| **Race course** | Circuit card blank, `trkName` empty | passing `track=` |
| **Pacing strategy** | Strategy view empty | passing `strategy=` |
| **Digital-twin observer** | Twin toggle inert | passing `observer=` |
| **Course selector** | Could not switch event | passing `courses=` (all 5) |
| **Cycle life** | Degradation view empty | attaching `_cycle_curves` |
| **Cell population** | Perfectly uniform cells | passing `cap_mult`/`res_mult` |

All five Monaco courses are now exported — endurance, qualifying, championship
outer and inner, slalom — each with its own pacing strategy.

The audit that found these was mechanical rather than clever: enumerate every
`M.<key>` the page reads, check each against what the builder emits. That is
worth repeating whenever the exporter changes.

### A range error worth catching

The builder was passing the **10 kWh regulatory limit** as the pack's energy
instead of the actual **9.828 kWh**. Every range and pacing number was
computed against energy the boat does not have.

Only 1.7% — but it is 1.7% in the optimistic direction on the single quantity
that decides whether you finish. Both numbers are now exported separately:
`packEnergyKWh` for pacing, `ruleEnergyCapKWh` for the REQ_7 gauge.

---

## 4. Two robustness bugs in the page

**The boot overlay was broken by the styling pass.** The refinement layer set
`#boot{position:relative;z-index:1}` to lift the chrome above the ambient light
field. `#boot` is a fixed full-screen overlay at `z-index:1000`, so this
dropped the loading screen behind the app entirely. Found by opening the page
and looking at it.

**The main loop stopped when the tab was backgrounded.** `requestAnimationFrame`
is suspended when the compositor is idle, which on a desk is a feature and on a
boat — screen dimmed, browser behind another window — means telemetry silently
stops advancing while still looking live.

A 1 Hz keepalive now watches for stalled frames and drives the loop manually
until they resume. The simulation is timestep-driven, so it stays correct at
whatever cadence it gets. Verified: in a non-compositing tab the sim now
advances past 22 s where it previously sat at 0 forever.

There is also an **immediate first paint** after boot, so the circuit map, pack
layout and charts are on screen straight away rather than waiting for the first
frame.

---

## 5. Pack arrangement — the current grid is not on the frontier

`tools/optimise_layout.py` sweeps every grid that can hold 13 groups and every
rectangular split of 21 cells, scoring footprint, volume, series path, longest
link and serpentine adjacency, and rejecting anything that will not fit the
organiser hull.

**The current 4 × 4 grid is Pareto-dominated.** Ten arrangements are better on
both volume and series path. The strongest:

| | 4 × 4 (current) | 1 × 13, group 3 × 7 |
|---|---|---|
| Volume | 42.5 L | **35.3 L** (17% less) |
| Series path | 3.71 m | **2.02 m** (46% less) |
| Footprint | 709 × 333 mm | 185 × 1058 mm |
| Packaging efficiency | 32.8% | 39.6% |

Less series path is less copper carrying full pack current, so it is also less
interconnect resistance and less loss.

**This is a finding, not a recommendation.** The sweep does not score:

- longitudinal weight distribution and trim — a 1058 mm pack sits very
  differently in a 2.53 m hull, and trim is worth real time on the water
- cold-plate hydraulics — a long thin plate needs a different serpentine and
  pressure drop scales with pass length
- structural support and mounting to the beams
- where the bulkhead, seat and controls have to go

Two things the sweep settled, though:

- **Packaging efficiency barely moves across the whole set.** It is dominated
  by square cell packing and the enclosure, not by the grid. Chasing it by
  reshaping the grid is not worth much; hexagonal cell packing would buy far
  more, at the cost of a harder busbar.
- **The three empty slots are not waste.** They hold the BMS, contactor, fuse
  and pre-charge, which otherwise need their own enclosure volume the sweep
  does not count.

To evaluate a candidate properly:

```bash
python tools/optimise_layout.py --apply 1x13 --group 3x7
```

then re-run `TEST_ALL`, `crosscheck.py` and the thermal studies. The tool
refuses to apply anything that breaks the serpentine or will not fit the hull.

---

## 6. Still open

Ranked by how much the answer moves.

1. **Inverter selection.** Still "on request" from Competr. Every inverter loss
   number is against a representative device.
2. **Motor electrical parameters.** Pole pairs, Ld, Lq, flux linkage, phase
   resistance, efficiency map.
3. **Cell-to-plate thermal resistance** (1.20 K/W assumed). Cannot be
   calculated — bond-line thickness and fill fraction dominate. One
   instrumented module settles it.
4. **Weld resistance** (0.2 mΩ assumed). 1092 joints, 16% of interconnect
   resistance. A four-wire measurement on one scrap joint is the cheapest
   high-value test in the project.
5. **Real drive cycle.** The mission profiles are representative shapes. This
   is the largest single uncertainty in every absolute temperature quoted.
6. **RC branch values** (`R1`, `tau1`, `R2`, `tau2`). Still assumed, and the
   only remaining cell parameters not backed by the digitised dataset. An HPPC
   campaign would close them and the plate resistance together.

118 parameters remain `ASSUMPTION`. That is not a failure — it is an honest
count of what has not been measured yet, and `P50B_ProvenanceReport` lists
every one.
