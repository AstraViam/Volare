# Volare — Coupled Electro-Thermal Pack Model

A spatially-resolved, coupled electro-thermal model of a cylindrical-cell pack
with a hydraulically-resolved coolant circuit. Configured for the Monaco
Energy Class **26S21P** Molicel P50B pack, but the geometry, wiring and
chemistry are all parameters.

**Current configuration**

| | |
|---|---|
| Topology | 26S21P, 546 cells |
| Declared energy (ENERGY_REQ_7) | **9.828 kWh** — compliant |
| Voltage | 93.6 V nominal, **109.2 V max** — see warning below |
| Capacity | 105 Ah |
| Cell mass | 38.2 kg |
| Cell array footprint | 494 × 611 mm |
| Pack DC resistance | 20.4 mΩ |
| Bus current @ 25 kW | 278 A → 13.2 A/cell (5.3 % of the P50B's 60 A rating) |
| Cooling | tube every 2nd gap (13 tubes), **3 hydraulic circuits** |

> **⚠ 109.2 V at full charge exceeds 100 V.** This triggers ENERGY_REQ_187
> (Technical Committee approval **during the registration phase**, not at
> inspection) and ENERGY_REQ_191 (HV training certification for everyone who
> works on the pack). It also pushes you out of the 100 V-class inverter
> ecosystem. This is a schedule dependency, not a technical one — but it is a
> hard deadline you cannot recover from if missed.

```
volare_thermal/
├── pack_thermal.py   core model  (cells, layout, hydraulics, batch solver)
├── simulator.py      stepper, digital-twin observer, race animation
├── studies.py        six investigations + figures
├── figures/          output plots
└── README.md         this file
```

Run with `python3 studies.py`. Needs only numpy, scipy, matplotlib. A full
20-minute race simulation of 546 cells takes **~0.8 s**, which is the whole
point: you can sweep twenty layouts in an afternoon.

---

## 1. Why this rather than a lumped model

A lumped model tells you the pack average temperature. It cannot tell you any
of the things that actually decide your design:

| Question | Needs |
|---|---|
| Where is the hotspot? | spatial resolution |
| Does the centre cell hog current and run away? | per-cell electrical solve |
| Is grading worth 40 hours of machine time? | cell-population statistics |
| How many tubes, and how should they be plumbed? | resolved hydraulics |
| Where do I put my thermistors? | all of the above |

This model resolves all four. The critical structural choice is that **cells
inside a parallel group are individual electrical entities**. They share a
terminal voltage, so current splits by impedance — it is *not* `I_pack / P`.
That opens the feedback loop everyone worries about:

```
hotter → lower R₀ → hogs more current → more heat → hotter        (destabilising)
more current → faster SOC drop → lower OCV → sheds current        (stabilising)
```

Their balance is what actually sets the hotspot, and you cannot see it without
solving both domains together.

---

## 2. Model structure

### Electrical — closed form, no iteration

Within one parallel group of `P` cells sharing terminal voltage `V_g`:

```
V_g = U_ocv,i(z_i) − I_i·R₀,i(T_i, z_i) − Σ_k V_RC,k,i
Σ I_i = I_pack
```

Let `a_i = (U_i − ΣV_RC,i)/R₀,i` and `b_i = 1/R₀,i`. Then

```
V_g = (Σa_i − I_pack) / Σb_i          I_i = a_i − b_i·V_g
```

Exact, one pass, no solver. The pack is affine in current, `V_pack = V_oc,eff
− I·R_eff`, so a constant-**power** demand reduces to a quadratic with a
closed-form root. This is why 2400 timesteps × 552 cells runs in under a
second.

### Heat generation — Bernardi (1985)

```
q_i = I_i·(U_ocv,i − V_g)  −  I_i·T_i·(∂U/∂T)_i
      └── irreversible ──┘     └── reversible (entropic) ──┘
```

The entropic term is ~15 % of the total at mid-SOC and changes sign near full
charge — at SOC = 1 the cells are briefly **endothermic**. The model reproduces
this (validation run: q/cell starts at 0.19 W and climbs to 0.56 W as the RC
branches charge over the first 120 s).

### Thermal — sparse RC network, implicit Euler

```
C·dT/dt = −G·T + q + s
```

Nodes: **2 per cell** (core + can) + 1 per busbar + 1 per coolant segment +
1 enclosure-air node. Ambient is a fixed boundary.

Solved semi-implicitly: diffusion implicit (unconditionally stable), heat
source explicit (slowly varying). `(C/dt + G)` is factorised **once** with
`scipy.sparse.linalg.splu` and back-substituted each step.

The core/can split matters: **your thermistor reads the can, your safety limit
applies to the core.** With `R_core→can = 2.0 K/W` (derived from
k_radial ≈ 0.6 W/m·K via `ΔT = q/(4πLk)`), the gradient runs 2.3–2.8 K at race
power. Add that offset to every threshold, and make it a function of measured
pack current, not a constant.

### Coolant — resolved hydraulics

This is the part most student models omit, and it dominates the answer.

Tubes lie in inter-row gaps. They are grouped into `n_circuits` **parallel**
hydraulic paths; within a circuit the tubes run in **series** (serpentine,
alternate tubes reversing direction). Per circuit the model computes:

- velocity, Reynolds number, flow regime
- `Nu = 3.66` (laminar) or Dittus-Boelter `0.023·Re⁰·⁸·Pr⁰·⁴` (turbulent)
- `h`, hence `R_conv` per cell, added **in series** with the wall/contact
  resistance
- Darcy-Weisbach pressure drop including bend losses

Coolant segments are chained along the flow path with an upwind advection term,
so **coolant heats up as it travels** and the last cells in a circuit see
warmer coolant than the first.

---

## 3. Validation

Every result below was checked against an independent analytic calculation
before being trusted. Run `study_validation()` to reproduce.

| Check | Result |
|---|---|
| Adiabatic rise vs `∫q dt / (m·c_p)` | 1.7 % (sampling error) |
| Core→can gradient vs `q·R` at true steady state | **0.08 %** |
| Kirchhoff: `Σ I_cell − I_pack` | 9×10⁻¹² A |
| Delivered power vs demand | exact |
| Timestep independence (dt 2.0 → 0.25 s) | T_max varies 0.015 K |

**A methodological note worth internalising.** My first steady-state check
failed by 17 %, and the model was right — the system never reaches steady
state because R₀ climbs as SOC falls, so the thermal gradient legitimately
lags `q·R`. Freezing SOC (via a 200× capacity multiplier) brought agreement to
0.05 %. When a validation fails, the assumption is as likely to be wrong as
the code.

---

## 4. Findings

### 4.1 The cooling architecture optimum is sharp, and pump head sets it

26S21P, endurance cycle, tube every 2nd gap (13 tubes), varying only how those
tubes are plumbed:

| Circuits | L/min each | Re | Regime | h [W/m²K] | **ΔP** | T_max |
|---|---|---|---|---|---|---|
| 1 | 8.00 | 11884 | turbulent | 9294 | **5.88 bar** | 34.8 °C |
| 2 | 4.00 | 5942 | turbulent | 5338 | **0.78 bar** | 35.0 °C |
| **3** | **2.67** | **3961** | **transitional** | **3777** | **0.24 bar** | **35.2 °C** |
| 4 | 2.00 | 2971 | transitional | 1350 | 0.11 bar | 36.0 °C |
| 5 | 1.60 | 2377 | transitional | 232 | 0.05 bar | 39.1 °C |
| 13 | 0.62 | 914 | laminar | 232 | 0.004 bar | 40.4 °C |

**Three circuits is the design point.** It sits just below the turbulent
transition (Re = 3961) with h = 3777 W/m²K, at 0.24 bar — comfortably inside
what a 12 V pump delivers. Going to 2 circuits buys 0.2 K for 3× the pressure.
Going to 4 costs 0.8 K; going to 5 falls off a cliff to 39.1 °C.

Three things fall out:

1. **The cliff between 4 and 5 circuits is the laminar transition.** Below
   Re ≈ 2300 the flow is fully laminar, `Nu = 3.66` is constant, and `h`
   becomes flow-independent. 5, 13 and 25 circuits all give essentially the
   same temperature. Splitting flow more finely past that point buys you
   literally nothing — you are just adding manifold complexity and leak paths.
2. **Tube-side convection dominates the contact resistance, and it is under
   your control.** At 3 circuits, `R_cell→coolant = 2.50 (wall/bond) + 0.60
   (convection) = 3.10 K/W`. At 5 circuits the convection term alone becomes
   9.7 K/W and swamps everything. Plumbing topology matters more than bond
   quality here.
3. **The glycol is costing you.** 50/50 glycol is ~3× the viscosity of water,
   which is what drags you toward laminar. Water + corrosion inhibitor, same
   geometry, same flow: **46.0 °C vs 46.7 °C** at sustained 25 kW, and it
   moves the laminar cliff further away. Freeze protection is not a
   requirement in Monaco in July. Corrosion inhibition is — buy that
   separately.

### 4.2 An orphaned edge row costs 3.9 K — and 26 rows avoids it for free

This was the most surprising result, and it is exactly what spatial modelling
is for.

| Layout | Tubes | Uncooled rows | T_max |
|---|---|---|---|
| 26 rows, tube every gap | 25 | none | 34.97 °C |
| **26 rows, tube every 2nd gap** | **13** | **none** | **35.94 °C** |
| 26 rows, tube every 3rd gap | 9 | 8, all interior | 37.89 °C |
| 26 rows, tube every 4th gap | 7 | 12, all interior | 39.55 °C |
| **25 rows (odd), tube every 2nd gap** | 12 | **[24]** — one, at the edge | **39.80 °C** |

Look at the last two rows. A 25-row pack with **one** uncooled row beats
nothing — it runs 3.9 K hotter than the 26-row version, and hotter even than a
26-row pack with **eight** uncooled interior rows.

The reason is geometric. Interior uncooled rows are sandwiched between cooled
neighbours and dump heat sideways through two paths. An edge row sits at the
pack boundary with one neighbour and no coolant, so it has half the escape
routes and nothing beyond it.

**26S21P is fortunate here: an even row count means tube-every-2nd-gap covers
all 26 rows with no orphan.** You get within 1 K of tube-every-gap for **half
the tubes, half the plumbing, half the manifold mass and half the leak paths.**

> **Design rule: always terminate the tube pattern so no row is orphaned at
> the pack boundary. Check row 0 and row N−1 explicitly.** With an odd row
> count you must add a tube at the final gap; with an even count the pattern
> closes itself.

### 4.3 Current hogging is a manufacturing problem, not a thermal one

Endurance cycle, 26S21P, varying only the cell population:

| Case | σ_Q | σ_R | Hog ratio | T_max | Spread | SOC spread |
|---|---|---|---|---|---|---|
| Identical cells (fiction) | 0 | 0 | 1.001 | 36.0 °C | 0.87 K | 0.03 % |
| **Ungraded batch** | 1.5 % | 6 % | **1.056** | 36.3 °C | 1.40 K | **2.89 %** |
| Graded ±1 % / ±5 % | 0.4 % | 1.7 % | 1.015 | 36.1 °C | 0.92 K | **0.61 %** |
| Graded + capacity-balanced | 0.4 % | 1.7 % | 1.016 | 36.1 °C | 1.00 K | 0.57 % |
| **Graded + thermal placement** | 0.4 % | 1.7 % | **1.009** | **35.9 °C** | **0.57 K** | 0.71 % |
| BAD batch (mixed sources) | 4 % | 15 % | **1.139** | 37.0 °C | 2.47 K | **5.85 %** |

Note that 21P is *less* forgiving than a wider parallel group: with fewer
cells sharing, one bad cell moves the group average more. The hog ratio is the
same (it is a per-group statistic) but the SOC divergence is worse — 2.89 %
ungraded, against 2.21 % for the same population at 24P.

A hog ratio of 1.139 means the worst cell in a group carries 14 % more current
and therefore **~30 % more ohmic heat** than its group average, for its entire
service life.

Now the decomposition — same ungraded population, with the Arrhenius
temperature dependence of R₀ switched off:

```
thermal feedback ON  (Ea/R = 2500)   hog 1.0571
thermal feedback OFF (Ea/R = 0)      hog 1.0576
```

**Essentially identical.** In a well-cooled pack with a 2 K spread, the
hotter→lower-R→more-current feedback contributes almost nothing. Hogging is
driven almost entirely by manufacturing spread in R₀.

Two consequences:

- **The thermal runaway feedback people worry about is not your problem** —
  provided the cooling holds. It becomes a problem only if cooling fails, and
  by then you have a larger one.
- **Grading is worth it, but for the right reason.** It buys you 0.4 K of peak
  temperature (negligible) and **3× less SOC divergence** (2.21 % → 0.68 %).
  SOC divergence is the thing that matters, because your Orion passive
  balancer moves ~150 mA and needs **6.7 hours to shift 1 % of a 100 Ah
  group** — and you have a 3.15 h charge window on 16 A shore power. You
  cannot balance your way out of a badly graded pack. You have to grade.

  A 5.9 % SOC spread from a mixed-source batch is unrecoverable and costs you
  roughly that fraction of your usable energy every single race.

### 4.4 Worst cases

Sustained 25 kW to empty (~22 min), 26S21P, tube every 2nd gap, 3 circuits:

| Scenario | T_max | >45 °C | >60 °C |
|---|---|---|---|
| Cooling OK, ambient 30 °C | 46.7 °C | yes | no |
| Hot day: ambient 40 °C, sea 33 °C | 50.6 °C | yes | no |
| **Half flow (partial blockage)** | **55.7 °C** | yes | no |
| **Pump dead (adiabatic bound)** | **66.4 °C** | yes | **YES** |
| Water + inhibitor instead of glycol | 46.0 °C | yes | no |

The pump-dead case exceeds 60 °C in **22 minutes**. This is the quantitative
justification for the coolant **flow sensor** in the sensor list — a dead pump
is indistinguishable from a working one until the pack is already over limit.
Half-flow costs 9 K, which is a blocked strainer you would otherwise never
notice.

### 4.5 Thermistor placement: buy precision, not quantity

Estimating `max(T_core)` from `N` can-mounted thermistors, with 0.5 K sensor
noise, **fitted on 8 realisations and evaluated on 4 held-out ones** (varied
population, ambient, flow, inlet temperature and drive cycle):

| Placement | RMS error | Worst-case error |
|---|---|---|
| 1 sensor, optimally placed | 0.665 K | 1.96 K |
| 1 sensor, naive | 0.827 K | 2.55 K |
| **4 sensors, optimally placed** | **0.458 K** | 1.54 K |
| 8 sensors, naive evenly spaced | 0.535 K | 1.96 K |
| **26 sensors, one per series group** | **0.431 K** | 1.19 K |
| 8 sensors, optimally placed | 0.413 K | 1.28 K |

**Four well-placed sensors match twenty-six naive ones.** Past about four,
you are sensor-noise-limited, not placement-limited — the floor sits at
~0.42 K regardless. Improving the NTC/ADC chain (precision reference, 16-bit
external ADC, oversampling, self-heating management) buys more than adding
thermistors.

The optimal positions cluster at rows 23–25 — the coolant-outlet end of
the circuits, which is exactly where you would put them if you thought about
it, and now you have a number attached.

**Redundancy check:** dropping any single sensor from the chosen eight and
refitting changes RMS error from 0.413 K to 0.422–0.429 K. The array is
strongly redundant, so a failed thermistor degrades gracefully rather than
blinding you. Worth demonstrating at technical inspection.

**For ENERGY_REQ_68 compliance:** your estimate can be ~1.3 K low in the worst
case (1.96 K with a single sensor). If the true limit is 60 °C and you must warn at 90 % (54 °C), set the
firmware threshold at **52 °C**, not 54 °C, and document the margin.

---

## 4B. Running it as a simulator

`simulator.py` turns the batch model into three things.

### 4B.1 `PackSimulator` — the stepper

The batch solver runs a whole race and hands back arrays. The stepper advances
**one timestep at a time**, driven by either a commanded power or a *measured*
pack current from the shunt:

```python
sim = PackSimulator(layout, cell, coolant, dt=1.0)

# offline / design
sim.step(power_W=13000)

# digital twin, driven by live CAN
sim.step(I_pack=meas.current,
         coolant_inlet_C=meas.t_in,
         flow_L_min=meas.flow)

sim.grid()            # (26, 21) spatial core-temperature field
sim.state_report()    # T_max, hotspot (row,col), SOC, Wh used, pack heat
```

It is **bit-identical** to the batch solver: `max |ΔT|` across all 546 cells
at the final step is exactly 0.00 K. Same physics, different control flow.

Coolant LU factorisations are cached per flow-rate bin, so a varying pump
speed does not force a ~10 ms re-factorisation every step.

**Speed:**

| dt | µs/step | Real-time factor |
|---|---|---|
| 0.25 s | 173 | **1442×** |
| 0.50 s | 180 | **2772×** |
| **1.00 s** | **170** | **5881×** |
| 2.00 s | 177 | 11308× |

170 µs per step for a 1183-node coupled electro-thermal solve. Three
consequences:

- Running in lockstep with the boat is trivially achievable.
- You can run **lookahead**: at any moment, simulate the remaining race in
  ~0.2 s and answer "if I hold 18 kW, do I finish, and does the pack exceed
  50 °C?" That is a race-strategy tool, not just a design tool.
- You can run **hundreds of Monte-Carlo laps** during a coffee break for
  robustness analysis.

### 4B.2 `EnsembleObserver` — the part that makes it a *simulator*

An open-loop model on the boat is a liability. The drive cycle, ambient,
sea temperature, pump flow and cell population are never exactly what you
assumed, and every one of those errors integrates.

The observer blends the model prediction with your live thermistor readings
and reconstructs the **whole** field, including the 540 cells you cannot
measure:

```
T_corrected = T_predicted + K (y_measured − H·T_predicted)
```

`K` is an ensemble Kalman gain, `K = Cov(x',y')[Cov(y',y')+R]⁻¹`, fitted
offline from 24 perturbed runs. Online it is a **fixed 546 × 6 matrix
multiply — 3276 multiply-accumulates**. On a Teensy 4.1 at 600 MHz that is
microseconds; you can run it at 1 Hz without noticing.

**The test that matters.** Truth run at 6.2 L/min flow, 32.5 °C sea, 38 °C
ambient, a 15 % longer and 12 % harder drive cycle, and a worse cell batch.
The model is given *none* of that — nominal 8 L/min, 28 °C sea, 30 °C
ambient, nominal cells. It is fed only the measured pack current and six
thermistor readings with 0.5 K noise.

| Metric | Open loop | **With observer** |
|---|---|---|
| RMS error over all 546 cells | 4.058 K | **0.218 K** |
| Worst-case field error | 4.725 K | **0.761 K** |
| Error in reported T_max, mean | 4.201 K | **0.209 K** |
| Error in reported T_max, worst | 5.039 K | **0.717 K** |

A **19× reduction**, but look at the failure mode rather than the ratio:

```
truth  T_max  38.45 °C
model  T_max  33.41 °C   ← open loop: reports "fine", is 5 K wrong
twin   T_max  38.18 °C   ← observer
```

The open-loop model tells you the pack is at 33 °C while it is actually at
38 °C. In a marginal case that is the difference between derating in time and
not. This is the argument for putting the observer on the boat rather than
just using the model in design.

It also changes how you read §4.5. Six thermistors *plus physics* estimate the
full field to 0.22 K. Six thermistors plus a linear regression estimated only
`T_max`, to 0.43 K, and told you nothing about where the heat was. The
physics is doing real work.

### 4B.3 `animate_race()` — the visual

Spatial field, hotspot tracker, power trace and energy-versus-REQ_7-cap, over
the full race. Written to `figures/race_animation.mp4`. Good for design
review, and good for the Tech Talk.

### 4B.4 A free improvement the animation revealed

The rendered field is **monotonic in row** — every circuit runs low-row to
high-row, so coolant enters cold at row 0 and leaves warm at row 25. Reversing
the tube order within alternate circuits gives counter-flow:

| Routing | T_max | Spread |
|---|---|---|
| Co-flow (all circuits same direction) | 35.08 °C | 0.95 K |
| **Counter-flow (alternate circuits reversed)** | 35.07 °C | **0.80 K** |

Peak temperature is unchanged — that is set by total heat removal, not by
distribution — but the spread drops 16 % for the cost of plumbing two of the
three circuits backwards. Take it: spread drives SOC divergence and
differential ageing.

Be honest about the size of this, though: the gain is small *because the
cooling is already good* and the total coolant ΔT is only ~1 K, so there is
little gradient to flatten. In a marginal design, or at 25 kW sustained where
coolant ΔT is 3–4 K, counter-flow would be worth considerably more. Re-check
it if the design gets tighter.

---

## 4C. Python or MATLAB?

You have MATLAB, so this deserves a straight answer rather than a preference.
The honest version is that they win at different stages, and the boundary is
sharp.

### Where Python is better — design and exploration

The core loop is a sparse linear solve. `scipy.sparse.linalg.splu` and
MATLAB's `\` are both SuiteSparse underneath, so **there is no speed
difference** — the 170 µs/step figure would be roughly the same in MATLAB.

The advantages are practical, not computational:

- **Free.** It runs on every team member's laptop and on next year's team's
  laptops, with no licence server and no toolbox entitlements.
- **Git-able.** Plain text, reviewable diffs. `.m` files are fine here too,
  but `.slx` models are binary and merge badly, which matters when four people
  are editing.
- **PyBaMM** is Python-native and is the best open cell-model library. When
  you want physics-based `q(t)` instead of an ECM, it is one import away.

### Where MATLAB is genuinely better — putting it on the boat

Three things, and they are all downstream of design:

1. **Embedded Coder.** If the observer runs on the VCU, you need C. Hand-porting
   is ~200 lines and entirely doable (the observer is one matrix multiply and
   the stepper is a sparse solve you would replace with a dense reduced-order
   one). But Embedded Coder generates it from a verified model, with
   traceability — which is worth real money when Rule 7.6 seals your
   electronics after inspection and you cannot patch anything.
2. **Simulink for hardware-in-the-loop.** Wrap the stepper as an S-function and
   run your *actual* torque-arbitration and thermal-derate firmware against it
   before it touches a cell. This is the highest-value thing MATLAB offers you,
   and it is the natural next step from `thermal_power_limit_W()`.
3. **Simscape Battery** gives you an independent second implementation to
   cross-check against. For a model this consequential — you are sizing a
   cooling system off it — a second opinion from a different codebase is worth
   having. Not as the primary tool; as a check.

### Recommendation

Keep design and exploration here. Use MATLAB for the HIL rig and, if you want
it, for generating the on-boat observer C.

The porting map, if you go that way:

| Python | MATLAB |
|---|---|
| `scipy.sparse.coo_matrix` | `sparse(i, j, v, n, n)` |
| `splu(M)` then `.solve(b)` | `dM = decomposition(M); dM \ b` |
| `np.interp` | `interp1` |
| `@dataclass` | `classdef ... properties` |
| `a.reshape(S, P).sum(axis=1)` | `sum(reshape(a, P, S), 1)` |

The one real trap is **column-major ordering** — every reshape in the
electrical solve needs its indices transposed. Get that wrong and the pack
silently wires itself 21S26P, which still runs and gives plausible-looking
nonsense.

### What to do *before* either

Neither language fixes the actual bottleneck, which is that the model is
unvalidated. The contact resistances cannot be calculated, and `q(t)` depends
on a drive cycle I invented. Build the instrumented module (§5), log a real
sea trial, and tune. A validated Python model beats an unvalidated Simulink
one, and vice versa.

---

## 5. Parametrising from your own cells

Everything above is structurally sound and numerically provisional. The
defaults are datasheet- and literature-derived, tagged in the source as
`[HIGH]` / `[MED]` / `[LOW]` confidence. The `[LOW]` ones are the RC branch
values and the entropic coefficient, and they are the ones that matter.

### HPPC campaign — the minimum useful version

You need three test types on ~5 representative cells:

**(a) OCV curve.** C/20 discharge, 25 °C, full to empty. Gives `ocv_soc` /
`ocv_v`. Do it in both directions and average to remove hysteresis. This curve
sets your SOC estimation accuracy and controls the OCV negative feedback that
limits hogging — it is the single highest-value measurement.

**(b) HPPC pulses.** At 10 % SOC intervals, apply a pulse train:
10 s discharge at 1 C → 40 s rest → 10 s at 3 C → 40 s rest → 10 s at 5 C.
Fit `R₀` from the instantaneous voltage step, and `R₁/τ₁`, `R₂/τ₂` from the
relaxation curve (two-exponential least squares). Repeat at **three
temperatures** (10, 25, 45 °C) — you need three points to fit `Ea_over_R_K`,
and that parameter is what governs the whole thermal-feedback question in
§4.3.

**(c) Entropic coefficient (optional, ~15 % of heat).** Set SOC, let the cell
equilibrate at 25 °C, measure OCV; step to 15 °C and 35 °C, waiting 4+ hours
at each; `dU/dT` is the slope. Tedious. If you skip it, keep the literature
curve and note the ~15 % uncertainty in heat generation.

**Free alternative:** [PyBaMM](https://pybamm.org) has parameter sets for
P50B-class cells and can generate `q(t)` from a physics-based DFN model, which
you then feed into this thermal network. Good for a Tech Talk slide; no
substitute for measuring your own cells for the grading study, since that
depends on *your batch's* spread, not on a reference cell.

### Thermal parameters — measure, do not calculate

`R_core→can`, `G_cell→cell` and `R_can→tubewall` are contact resistances. They
**cannot be calculated** to useful accuracy; the potting fill fraction and
bond-line thickness dominate and vary with your process.

Build one instrumented module: 15–20 thermocouples, including three at
model-predicted hotspots and one at a predicted cool spot. Run the drive cycle
on a load bank. Then tune `gap_filler_k_WmK`, `gap_contact_frac` and
`R_can_tubewall_KW` until the model matches. **An unvalidated thermal model is
a plausible-looking guess.**

Also instrument coolant inlet and outlet with PT1000s: `Q = ṁ·c_p·ΔT` gives
you a direct, independent measurement of total heat rejection to check the
model's energy balance against. Two €5 sensors close the loop on the whole
exercise.

---

## 6. Python vs MATLAB

You have MATLAB, so: the honest answer is that **Python is the better tool for
this particular job**, and MATLAB is the better tool for the job next door.

**Python wins here** because the model is a sparse linear solve in a loop.
`scipy.sparse.linalg.splu` and MATLAB's `\` are both LAPACK/SuiteSparse under
the hood — same speed. But this code is free to run on every team member's
laptop, free to hand to next year's team, versionable in git, and PyBaMM
(the best open cell-model library) is Python-native.

**Porting is direct** if you prefer MATLAB — the structure maps one-to-one:

| Python | MATLAB |
|---|---|
| `scipy.sparse.coo_matrix` | `sparse(i, j, v, n, n)` |
| `splu(M)` then `.solve(b)` | `dM = decomposition(M); dM \ b` |
| `np.interp` | `interp1` |
| `dataclass` | `classdef ... properties` |
| `reshape(S, P).sum(axis=1)` | `sum(reshape(a, P, S), 1)` (note: column-major!) |

The one real trap is **column-major ordering** — every `reshape` in the
electrical solve needs its indices transposed.

**Where MATLAB genuinely wins:** Simulink/Simscape for the *next* piece of
work, which is hardware-in-the-loop testing of your BMS and VCU logic. Take
this model's `q(t)` and `T(t)` outputs, wrap them as a Simulink block, and run
your actual torque-arbitration and thermal-derating code against it before it
ever sees a real cell. Simscape Battery also has good pre-built cylindrical
module blocks if you want a second independent implementation to cross-check
against — which, for a model this consequential, is worth doing.

---

## 7. Known limitations

Stated plainly, because a model whose limitations you cannot list is a model
you should not trust:

1. **2D, not 3D.** Cells are treated as a single layer. Stacking modules
   vertically adds a conduction path and a hot upper module that this does not
   capture. Extend by adding a z-index to `PackLayout._build_positions` and
   including vertical neighbours in the adjacency.
2. **No thermal runaway model.** This predicts normal operation. Propagation
   modelling needs a completely different formulation (Arrhenius decomposition
   kinetics, gas generation, radiative coupling) and is not what this is for.
3. **Uniform in-plane manifold assumption.** The model splits flow equally
   between circuits. Real manifolds maldistribute, sometimes badly. Build a 1D
   hydraulic resistance network of the header to check this — it is the failure
   mode this model structurally cannot see.
4. **Ageing is absent.** Cells diverge with cycling, and the hot cells diverge
   fastest, so the §4.3 spread numbers are a *lower bound* over pack life.
5. **Transitional flow (2300 < Re < 4000) is a linear blend.** Crude. The
   recommended 3-circuit design point sits at **Re = 3961**, at the very top of
   that band and almost turbulent, so `h = 3777 W/m²K` should be good to
   roughly ±20 % — better than the 4-circuit option at Re = 2971, which is
   mid-band and worth ±40 %. This is a second, independent reason to prefer
   3 circuits: it is not just colder, it is a point you can *predict* more
   confidently. If you want to remove the uncertainty entirely, go to
   2 circuits (Re = 5942, fully turbulent) and accept 0.78 bar.
6. **The drive cycle is invented.** `mebc_endurance_lap()` is a plausible
   guess. Replace it with logged data from sea trials the day you have any —
   it is the single largest source of uncertainty in every absolute
   temperature quoted above.
