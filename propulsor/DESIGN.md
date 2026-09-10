# Propulsor design framework — architecture and build plan

Coaxial contra-rotating propulsor for the Team Volare MEBC Energy Class
catamaran. Design point 20 knots, 250 kg, seawater.

Status: **planning document.** No new code written yet. This is the structure
we build against.

---

## 1. Verdict: salvage, do not delete

You asked whether to delete `propulsor/` and start fresh. **Do not.** The
existing 2,491 lines already implement the harder half of your specification,
and they implement it well.

Evidence, from reading the code rather than the README:

- **`bem_rotor.m` is not toy code.** It reduces the coupled `(a, a')` system to
  one scalar equation per station in the inflow angle and solves it with
  Illinois bracketing, which converges unconditionally, having explicitly
  rejected fixed-point iteration as unstable at high solidity. It uses a
  cell-centred radial grid so no station sits at `r = R` where the Prandtl
  factor vanishes and the induction diverges. It shows that the immersion duty
  factor cancels in the induction terms but not in the loads, which is the
  correct physical statement of the surface-piercing disk-area penalty. That is
  the reasoning your spec section 19 asks for, already done.
- **`optimization_driver.m` already contains `pso_local` and `pattern_search`.**
  Your spec section 32 asks for "a fallback version that does not require
  proprietary optimization toolboxes." It exists.
- **`objective_function.m` already contains** `manufacturability_penalty` and
  `robustness_penalty` (spec section 30).
- **`surface_piercing_model.m` already contains** `immersion`, `ventilation`
  and `cyclic` (spec sections 14 and 36).
- **`crp_interaction.m` already contains** `interp_slipstream` for contraction
  (spec section 15).
- **`config.m` already carries an assumption ledger** via `add_assumption`
  (spec section 53).

What is missing is the *surrounding* layer: 19 files, mostly the simpler ones.
Deleting would throw away the BEM solver, the CRP coupling and the
surface-piercing kinematics — precisely the parts that are hard to get right —
and rebuild them from scratch at the same design.

**Plan: keep the four solver files and `config.m`, write the missing 19 around
them, and refactor only where the new spec genuinely conflicts.**

---

## 2. The MATLAB environment — the real answer

This is the question with the largest effect on how fast this goes.

### The problem

Claude Code sessions have no MATLAB and never will. Nothing in `powertrain/`
or `propulsor/` has ever been executed in a session. A 22-file BEM and
optimiser framework that has never been run is, with near certainty, broken.
Writing more MATLAB that nobody can execute until you open it on your laptop
is the slowest possible loop.

### The fix: GNU Octave as the development and CI runtime

Octave 8.4 is now installed in this environment, and **every existing
`propulsor/*.m` file parses cleanly in it.** The code contains zero
MATLAB-only constructs: no `arguments` blocks, no `string()`, no `classdef`,
no `dictionary()`. It was written portably, whether or not that was deliberate.

That means the numerical core can be developed test-first, run on every push
in CI, and only taken to real MATLAB for the things Octave genuinely cannot do.

### What Octave cannot do, and what to do about it

| Need | Octave | Plan |
|---|---|---|
| `particleswarm`, `ga`, `patternsearch` | Absent (Global Optimization Toolbox) | Use the existing `pso_local` and `pattern_search`. Call the toolbox only when `exist('particleswarm','file')` says it is there. |
| `fmincon` | Absent | `sqp` in Octave's `optim` package, or a penalty formulation on top of the existing local search. Keep behind the same capability check. |
| `optimoptions` | Absent | Wrap in a thin `opt_options()` shim that returns a plain struct under Octave. |
| Simulink / Simscape | Absent | Not needed here. This is `powertrain/`'s problem, and it stays on your machine. |
| `pchip` (spec section 3) | **Present** | Use directly. |

Two of the existing files use name=value call syntax, which Octave 8 accepts
but older versions do not. Prefer `'name', value` pairs for portability.

### Recommended split

- **Here and in CI:** Octave. Every solver, every unit test, every sanity check
  from spec section 49, the full toolbox-free optimisation path.
- **On your machine:** MATLAB. Toolbox optimisers for the final production runs,
  plotting for report figures, and anything touching Simulink.
- **MATLAB in CI, now worth doing.** You have confirmed MATLAB access for
  anyone with an institute email, which means a Campus-Wide Licence. Those
  normally permit CI through `matlab-actions/setup-matlab` with a batch
  licensing token. The steps:

  1. Ask IT for a MATLAB batch licensing token for CI, or check whether the
     Campus-Wide Licence already covers `matlab-actions`.
  2. Store it as a repository secret named `MATLAB_BATCH_TOKEN`.
  3. Add a job mirroring the Octave one, running `tests/ci.m` under MATLAB.

  Keep **both** jobs. Octave is the fast gate that runs on every push in
  seconds; MATLAB is the fidelity gate that proves the code behaves
  identically on the runtime the team actually uses, and is the only way to
  exercise the toolbox optimiser path. If the two ever disagree, that
  disagreement is itself the bug worth finding.

### MATLAB Online

Also available to anyone with the institute email, at matlab.mathworks.com.
Useful for a teammate without a local install to open a `.slx` model or run a
one-off script. Not useful for development here, because it has no access to
this repository's working tree.

### The rule this imposes on new code

**Write to the MATLAB/Octave intersection.** Concretely: no `arguments`
blocks, no `string` type (use char arrays and cellstr), no `classdef` unless
genuinely needed, no `dictionary`, no `containers.Map` in hot paths, and every
toolbox call guarded. A CI job will enforce this by running the suite in
Octave, so a violation fails the build rather than surfacing three weeks later.

---

## 3. Architecture

Data flows one way. Every stage is a pure function of `params` plus its
upstream inputs, so any stage can be tested alone.

```
config.m ──► params  (every engineering number originates here)
    │
    ├─► load_inputs.m        external data replaces assumptions in-place
    │
    ▼
resistance_model.m   pchip over the supplied 5-point curve  ──► R_T(V)
    │
    ▼
hull_interaction.m   w, t, eta_R  ──► T_required = R_T/(1-t),  V_A = V(1-w)
    │
    ▼
propeller_geometry.m  spline-parameterised blade  ──► g_front, g_rear
    │                 (chord, pitch, camber, thickness, skew, rake vs r/R)
    ▼
hydrofoil_polar.m     Cl(alpha,Re), Cd(alpha,Re)  ──► section data
    │
    ▼
┌───────────────────── crp_interaction.m (coupled, iterative) ─────────────┐
│  bem_rotor(front) ──► a, a', slipstream contraction, swirl               │
│         │                                                                │
│         ▼  axial acceleration + swirl transported to the rear disk        │
│  bem_rotor(rear)  ──► recovers swirl as useful thrust                    │
│         │                                                                │
│         └──► iterate to convergence on the coupled induction field       │
└──────────────────────────────────────────────────────────────────────────┘
    │                                    │
    │  surface_piercing_model.m          │  submerged_model.m
    │  immersion, ventilation, cyclic    │  baseline comparison
    ▼                                    ▼
cavitation_model.m + structural_model.m   constraint feasibility
    │
    ▼
gearbox_model.m   n_motor, ratios, torque split  ──► required transmission
    │
    ▼
motor_model.m     P_available(n) = min(P_cont, 2*pi*n*Q_max),  eta_motor
    │
    ▼
objective_function.m   ──►  Wh per nautical mile   ◄── THE metric
    │
    ▼
optimization_driver.m  4 stages: coarse global ► refine ► local ► robustness
    │
    ▼
postprocess.m ─► plot_performance.m, plot_geometry.m, export_geometry.m,
                 sensitivity_analysis.m, validation.m
```

### The one architectural rule

**The rear rotor never sees boat speed.** Its inflow is the front rotor's
slipstream: accelerated axially, contracted radially, and carrying swirl that
the rear rotor is there to recover. Any code path that passes `V_A` straight to
the rear rotor is a bug, not a simplification.

---

## 4. File plan

22 files. Status is measured, not guessed.

### Keep as-is, or refactor lightly

| File | Lines | Notes |
|---|---:|---|
| `bem_rotor.m` | 206 | The core. Illinois solver, cell-centred grid, duty factor. Spec section 19 wants `bem_front_rotor.m` and `bem_rear_rotor.m` as separate files; **resist that.** One rotor solver called twice is correct; two copies drift apart. |
| `crp_interaction.m` | 337 | Coupled front/rear. Verify the positive-feedback handling the README describes. |
| `surface_piercing_model.m` | 211 | Immersion, ventilation, cyclic loading. |
| `config.m` | 343 | Extend to the full schema in section 5 below. |
| `objective_function.m` | 110 | Confirm the objective is Wh/nm, not efficiency. |
| `constraints.m` | 97 | Extend to the full section 33 list. |
| `optimization_driver.m` | 244 | Add the toolbox capability check. |
| `validation.m` | 140 | Wire to the CFD reference point. |
| `load_inputs.m` | 163 | External data override path. |
| `main.m` | 301 | Orchestration; update once the missing pieces land. |

### To write

| File | Purpose | Difficulty |
|---|---|---|
| `units.m` | Unit conversion table. **Blocks `config()` right now.** Write first. | Trivial |
| `resistance_model.m` | `pchip` over the 5 supplied points. Must tag results interpolated / extrapolated / supplied. | Easy |
| `hull_interaction.m` | `w`, `t`, `eta_H`, `eta_R`. All configurable, all registered as assumptions. | Easy |
| `motor_model.m` | The envelope, including the 42 kW inconsistency report. | Easy |
| `gearbox_model.m` | Ratios, torque split, required capacity. Pure algebra from the optimum. | Easy |
| `print_assumptions.m` | Section 53's mandatory output block. | Easy |
| `submerged_model.m` | Fully submerged baseline for comparison. | Moderate |
| `cavitation_model.m` | Cavitation number, min pressure coefficient. **Must keep cavitation and ventilation separate.** | Moderate |
| `structural_model.m` | Centrifugal plus bending, safety factor. Label as screening, not FEA. | Moderate |
| `propeller_geometry.m` | Spline-parameterised blade with smoothness constraints. | **Hard** |
| `hydrofoil_polar.m` | `Cl(alpha,Re)`, `Cd(alpha,Re)` with an external-data interface. | **Hard** |
| `sensitivity_analysis.m` | The section 45 sweep. | Moderate |
| `postprocess.m` | Assemble the report. | Easy |
| `plot_performance.m` | Section 41 plots. | Easy |
| `plot_geometry.m` | Blade geometry plots. | Easy |
| `export_geometry.m` | `front_blade_geometry.csv`, `rear_blade_geometry.csv`. | Easy |
| `export_results.m` | Machine-readable run record. | Easy |

### Deliberate deviations from your file list

Your spec section 38 lists `bem_front_rotor.m` and `bem_rear_rotor.m`. **One
`bem_rotor.m` called twice is better.** The rotors differ only in inflow and
rotation sense, both already arguments. Two files would duplicate the solver
and let the copies diverge silently, which is exactly how a rear-rotor bug
survives review.

Everything else in your list is adopted as written.

---

## 5. The `params` schema

One struct, built in `config.m`, threaded everywhere. No number appears
anywhere else. Every unsupplied value registers through `add_assumption()`.

```
params.meta            title, version, created, git commit
params.assumptions     ledger: {field, value, source, effect_if_wrong}
params.units           conversion constants (from units.m)

params.vessel          type, L_hull_m 5.0, spacing_m 2.5, disp_kg 250,
                       disp_worst_kg 300, LCG_m 1.8, V_design_kn 20
params.resistance      V_kn [0 5 10 15 20], R_N [0 89 212 381 624],
                       method 'pchip', source 'supplied', curve_300kg []
params.water           rho, nu, p_vapour, T_C, salinity
params.hull            w, t, eta_R          <- ALL ASSUMPTIONS, flagged
params.motor           P_nom 25e3, P_max_spec 42e3, Q_max 100,
                       n_nom_rpm 1300, n_max_rpm 2500, eta 0.95,
                       V_system 96, eta_map []      <- eta_map replaces eta later
params.propeller.front D_m, Z, P_m, hub_m, chord/camber/thickness splines
params.propeller.rear  same
params.propeller.common D_max_m 0.5334, gap_m 0.05, L_shaft_m 0.5,
                       beta_shaft_deg [-5 5], n_stations 30
params.surfacePiercing shaft_depth, immersion_fraction, waterline,
                       ventilation_model, vent_loss_coeff   <- ALL ASSUMPTIONS
params.gearbox         eta (assumption), ratio_front, ratio_rear, counter_rot
params.material        rho, E, nu, sigma_y, sigma_u, sigma_fatigue, sigma_allow
params.optimization    algorithm, bounds, seed, stage budgets, weights
params.competition     E_stored_kWh 10
params.validation      cfd_ref: J 0.6, n 4220 rpm, Va 3.4, Q 1.06, P 460
params.numerics        tol, max_iter, relaxation, nan_policy
```

---

## 6. Build order

Each stage ends with a runnable check. Nothing proceeds on an unverified stage.

| Stage | Deliverable | Gate |
|---:|---|---|
| 0 | `units.m`, then `config()` runs | **DONE.** 11 checks green |
| 1 | `resistance_model.m` | **DONE.** 16 checks green, including a discriminator that fails if pchip is swapped for linear |
| 2 | `motor_model.m` | **DONE.** 18 checks green, including the 25 kW cap held across 5001 speeds |
| 3 | `hydrofoil_polar.m`, `propeller_geometry.m` | Smooth geometry, no negative chord, monotonic radius |
| 4 | `bem_rotor.m` on a single submerged rotor | Converges; `eta_0` in (0,1); `K_T`, `K_Q` physically ordered |
| 5 | `crp_interaction.m` coupled | Rear-rotor inflow strictly exceeds `V_A`; swirl recovery positive |
| 6 | `surface_piercing_model.m` | Immersion in [0,1]; cyclic torque amplitude reported |
| 7 | `gearbox_model.m` | Ratios reproduce the rotor speeds from the motor speed |
| 8 | `cavitation_model.m`, `structural_model.m` | Flags fire on a deliberately bad design |
| 9 | `objective_function.m`, `constraints.m` | Baseline evaluates to a finite Wh/nm |
| 10 | `optimization_driver.m` | Beats the baseline; converges; reproducible under a fixed seed |
| 11 | `sensitivity_analysis.m` | Ranks the section 45 parameters |
| 12 | `export_geometry.m`, `validation.m` | CSVs reconstruct the blade; CFD point compared |

**Stage 4 is the one to be honest about.** If the single-rotor BEM does not
produce sane `K_T`/`K_Q` against any published open-water data, nothing
downstream means anything, and the optimiser will happily converge on a number
that is confidently wrong.

---

## 7. The motor inconsistency, resolved numerically

Your section 1 analysis is correct. Computed here:

| Quantity | Value |
|---|---:|
| Power at 2500 rpm and 100 N·m | 26.18 kW |
| Speed for 25 kW at 100 N·m | 2387.3 rpm |
| Torque needed for 42 kW at 2500 rpm | 160.4 N·m (60% over the 100 N·m limit) |
| Speed needed for 42 kW at 100 N·m | 4010.7 rpm (60% over the 2500 rpm limit) |

**42 kW is unreachable inside both hard limits.** It is not a marginal
overshoot; it needs 60% more torque or 60% more speed. `motor_model.m` will
implement `P_available(n) = min(P_cont, 2*pi*n*Q_max)`, keep the 42 kW figure
as a reported specification, and print the contradiction rather than
silently picking one number. Nothing gets altered on your behalf.

Most likely explanation, to check with the supplier: 42 kW is a short-duration
peak measured at a higher speed or a higher voltage than the 96 V bus, or the
100 N·m figure is continuous rather than absolute. **Ask them which.**

### A useful early result

At the design point, with illustrative efficiencies (`eta_0` 0.65,
`eta_gear` 0.95, `eta_motor` 0.95, `eta_ctrl` 0.97):

| Quantity | Value |
|---|---:|
| Effective hull power | 6.42 kW |
| Shaft power | 9.88 kW |
| Electrical power | 11.28 kW, 45% of continuous rating |
| Current at 96 V | 117.5 A |
| Energy per nautical mile | 564 Wh/nm |
| Range on 10 kWh | 17.7 nm, about 53 min at 20 kn |

**The motor is not the binding constraint at 20 knots — the propeller is.**
That reframes the optimisation: there is headroom to trade motor operating
point for propeller efficiency, which is exactly what your section 51 argues
for. Every number above is illustrative until `eta_0` comes from the real BEM.

---

## 8. What we cannot know without CFD or testing

Stated now so no result later overclaims.

| Unknown | Current status | Needed |
|---|---|---|
| Wake fraction `w`, thrust deduction `t` | No measurement. Configurable assumptions. | CFD wake field or self-propulsion test |
| Surface-piercing ventilation | Analytical/empirical only | Free-surface CFD, then tank testing |
| Hydrofoil polars | Provisional model | XFOIL at section Re, or published propeller-section data |
| 300 kg resistance curve | **Does not exist.** Will be reported as unavailable, never extrapolated. | Towing tank or CFD at 300 kg |
| Blade stress | Analytical screening only | FEA |
| Motor efficiency map | Constant 0.95 | Dyno map from the supplier |
| Gearbox efficiency | Configurable assumption | Depends on an architecture not yet chosen |

The framework's job is to be *correct and honest*, not to be accurate before
the data exists. Every one of these slots into `config.m` later without the
solver being touched.

---

## 9. The 25 kW cap — a rule, not a preference

**ENERGY_REQ_188 v1.1, Technical Rules 2027.1:** "The sum of instantaneous
power consumption of all motors shall not exceed 25 kW." Note: "No power
exceeding 25 kW will be allowed, even during a peak."

The 2027 rules tightened this. The 2026 wording capped *nominal* power, which
left room to argue a brief peak was permissible. The 2027 wording caps
*instantaneous* power, summed over all motors, and rules out peaks explicitly.

So `P <= P_cap_W` is a hard feasibility constraint at every operating point,
never a soft penalty. A design that breaches it is not a worse design, it is
an illegal one.

`params.motor.P_cap_W = 25e3` is the enforced ceiling. The supplied 42 kW
datasheet peak stays recorded in `params.motor.P_max_spec_W` with
`usePeakSpec = false`, so the supplied specification is never silently
altered and the contradiction stays visible for the supplier conversation.

The resulting envelope:

| Region | Speed | Limit |
|---|---|---|
| Torque limited | up to 2387.3 rpm | 100 N·m, power rising with speed |
| Power limited | 2387.3 to 2500 rpm | 25 kW, torque falling as `P_cap/omega` |

**At 2500 rpm only 95.5 N·m is available, not 100.** That constraint is live in
`motor_model.m` and gated by `tests/test_stage2_motor.m`, which sweeps 5001
speeds and fails if any point exceeds the cap.

---

## 9b. New 2027 constraints on this subsystem

| Requirement | Constraint | Where it lands |
|---|---|---|
| ENERGY_REQ_194 v1.0 **(new)** | Motor seat must withstand **200% of maximum motor torque**, so **200 N·m** | `structural_model.m` when written, and the frame design |
| ENERGY_REQ_186 v1.1 **(revised)** | **Hydrofoils are not permitted** | Does *not* affect `hydrofoil_polar.m`, which concerns propeller blade sections, not lifting foils. The name collision is unfortunate |
| ENERGY_REQ_195 v1.0 **(new)** | Waterproof 220 × 111 × 80 mm per traction chain for the Organiser's power sensor | Cockpit layout, not this subsystem |

Full change record: `docs/reference/RULES_CHANGES_2026_to_2027.md`.

---

## 10. Immediate next steps

1. **Stage 3: `hydrofoil_polar.m` and `propeller_geometry.m`.** These are the
   two hard ones, and everything downstream depends on their quality.
2. Ask the motor supplier about the 42 kW figure. The cap makes it moot for
   design, but the answer tells you whether the 100 N·m is truly absolute.
3. Set up the MATLAB CI job, per section 2, now that the licence is confirmed.
4. Stage 4 is the honesty checkpoint: if the single-rotor BEM does not produce
   sane `K_T`/`K_Q` against published open-water data, nothing downstream
   means anything.
