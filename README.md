# MEBC Energy Class — Coaxial Contra-Rotating Propulsor Design Tool

MATLAB design and optimisation framework for the contra-rotating propulsor of a
5 m, 250 kg catamaran at 20 knots. Written for Team Volare, ICT Mumbai.

The objective is **minimum electrical energy per nautical mile**, not maximum
propeller efficiency. Everything from hull resistance to battery current is in
one chain, and every unmeasured input is declared, configurable and swept.

---

## 1. Modelling architecture

```
config.m ──► params  (single source of truth for every engineering number)
                │
   resistance_model ──► hull_interaction ──► required thrust T = R/(1-t)
                │
   propeller_geometry ──► hydrofoil_polar ──► bem_rotor ──┐
                                                          ├─► crp_interaction
   surface_piercing_model / submerged_model ──────────────┘   (coupled, iterative)
                │
   gearbox_model ──► motor_model ──► electrical power ──► Wh/nm
                │
   cavitation_model + structural_model + constraints
                │
   objective_function ──► optimization_driver ──► postprocess / export / plots
```

### 1.1 What is actually solved

**Blade element momentum, per rotor** (`bem_rotor.m`). Standard propeller
convention, `U_a = V_a(1+a)`, `U_t = Ωr(1−a′) + V_t`, Prandtl tip *and* hub
losses, 24 cell-centred radial stations. The coupled `(a, a′)` system is reduced
to **one scalar equation per station in the inflow angle φ** and solved by
Illinois (bracketed false position), which converges unconditionally. A
fixed-point iteration on `(a, a′)` was tried first and is unstable at high
solidity; that is why it is not used.

The radial grid is **cell-centred**, deliberately. A station exactly at `r = R`
puts the Prandtl factor at zero, drives the momentum-derived induction to
infinity, forces the solver onto its clamp, and leaves spurious load on an
element that physically carries none.

**Contra-rotating coupling** (`crp_interaction.m`). The rotors are *not* solved
independently:

| Effect | Model |
|---|---|
| Front → rear axial | `g_dn = 1 + Δx/√(Δx²+R_F²)` ≈ 1.25 at 50 mm — the front's induction is only ~25 % developed at the rear disk |
| Rear → front axial | `g_up = 1 − Δx/√(Δx²+R_R²)` ≈ 0.75 — the rear's induction is felt strongly upstream |
| Slipstream contraction | discrete mass conservation, `r₂² = r₂,prev² + u₁(r₁²−r₁,prev²)/u_dn` |
| Swirl transport | `v_θ2 = 2a′₁Ω₁r₁·(r₁/r₂)` — circulation conserved through contraction |
| Swirl recovery | positive `flow.Vt` on the rear rotor, so recovery falls out of the momentum balance — it is **not** an applied efficiency factor |
| Upstream swirl | zero, correctly: an actuator disk induces no tangential velocity ahead of itself |

The coupling is **positive feedback** — more rear loading raises the axial
velocity at the front disk, which unloads the front, which weakens the swirl
feeding the rear. Near lightly loaded operating points the loop gain exceeds
one, the fixed point is *repelling*, and no under-relaxation factor converges.
The coupling is therefore reduced to a single scalar (the interference
amplitude `u`) and solved by secant with a guaranteed-bracket bisection
fallback. This is documented in the file header because it is not obvious and
it will bite anyone who tries to "simplify" it back to a relaxed iteration.

**Speed is not a free variable.** For every candidate design the solver finds
the rotational speed that delivers exactly the required thrust, using a
two-term `T(n) = A n² + B n` model-based secant. The thrust equality constraint
therefore disappears from the optimiser: every evaluated design satisfies it by
construction, or is reported infeasible with a reason.

**Surface piercing** (`surface_piercing_model.m`) is deliberately two-level:

- *Level 1, cycle-averaged*: immersion duty `duty(r) = 1 − acos(h/r)/π`
  multiplies **both** the blade-element force and the annulus momentum area.
  The duty cancels in the induction relations, so partial immersion does not
  change `a` at a given speed — it cuts the thrust, so the solver raises the
  speed, which *then* raises `a`. That is precisely the reduced-disk-area
  induced-loss penalty, obtained from the momentum balance rather than applied
  as a fudge.
- *Level 2, azimuthal*: instantaneous loads reconstructed over one revolution
  for peak/mean/cyclic torque, which is what the shaft, gearbox and blade root
  have to survive.

Ventilated sections use linearised supercavitating theory, `Cl = k_sc·(π/2)·α`,
roughly **a quarter** of the wetted-section lift at the same incidence, plus
base drag. This is the dominant physical penalty of surface-piercing operation
and the reason SP propellers need high pitch. Cavitation and ventilation are
computed and reported **separately** — they are different phenomena with
different criteria and different consequences.

---

## 2. Findings that came out of the model, not out of the brief

**The motor specification is inconsistent in two ways, not one.** The brief
identified that 42 kW is unreachable at 100 N·m and 2500 rpm (ceiling
26.18 kW). The tool also flags that **25 kW cannot be produced at the quoted
1300 rpm nominal speed either** — at 1300 rpm and 100 N·m the ceiling is
13.6 kW, and 25 kW at 100 N·m needs at least 2387 rpm. Nothing supplied has
been altered; `P_available(n) = min(P_continuous, 2πnQ_max)` is enforced and
both inconsistencies are printed at the top of every report.

**The propulsor is profile-drag dominated, not induced-drag dominated.** At
20 kn with ~780 N of thrust on a 0.5 m disk the thrust loading coefficient is
`C_Th ≈ 0.07`, giving an ideal induced efficiency above 0.98. Almost the entire
loss is blade friction. The design therefore wants *low blade area and low
rotational speed*, and the optimum diameter is well below the 21 in limit —
which is the opposite of the usual "make it as big as it fits" instinct.

**The reference configuration is badly matched.** With equal diameters, equal
speeds and 26.5″/28.5″ pitch, the model puts almost all the load on the rear
rotor (the front's swirl raises the rear's incidence while the rear's upstream
induction unloads the front) and the rear massively over-corrects the swirl.
The baseline-versus-optimised table quantifies this.

**Surface piercing versus submerged at 20 kn is decided by drive-leg drag, not
by the propeller.** The ventilated sections give up a lot of L/D, but the SP
configuration removes most of the submerged leg. Both effects are modelled
explicitly and both are swept in the sensitivity analysis. Do not treat the
verdict as settled without CFD.

**The CFD reference set may be internally inconsistent.** `J = 0.60`,
`n = 4220 rpm` and `V_A = 3.4 m/s` imply a propeller diameter of **80.6 mm**.
`validation.m` reports this and asks for confirmation, because if the CFD model
was not an 81 mm propeller then one of the three numbers is wrong and the
reference set cannot be used. Thrust was not supplied, so `K_T` and `η₀` are
reported as *"Not available — requires CFD/experimental validation"* rather
than invented.

---

## 3. Running it

```matlab
cd mebc_crp
RES = main();                          % full run: both architectures, 4 blade combos
RES = main('quick', true);             % reduced optimiser budget, ~10x faster
RES = main('arch', 'sub');             % fully submerged only ('sp' for surface piercing)
RES = main('plots', false);            % no figures
RES = main('report', 'myrun.txt');     % also write the report to results/myrun.txt
```

Runtime is dominated by the coupled solver: roughly **1–1.5 s per candidate
design in MATLAB** (≈3 s in Octave). A full run is a few hours; `quick` mode is
tens of minutes. Start with `quick` while you are changing assumptions, then do
one full run.

**No toolbox is required.** The particle swarm and the pattern search in
`optimization_driver.m` are implemented in plain MATLAB and run on a base
licence and on GNU Octave. Set `params.optimization.useToolbox = true` to use
`particleswarm`/`fmincon` instead; the code checks at run time and falls back
silently if they are absent. The random stream is seeded from
`params.optimization.seed`, so runs are reproducible.


### Known state of this delivery

- Every one of the 35 files parses, and the full `main()` pipeline has been run
  end to end (submerged and surface-piercing, blade counts 3/3 and 4/4), with all
  fourteen sanity checks passing on the winning design.
- **Figures were never rendered.** They were generated on a machine whose
  headless Octave text renderer is broken. The *data* paths inside
  `plot_performance.m` (resistance sweep, open-water K_T/K_Q sweep, CRP-versus-speed
  sweep) were executed and verified; only the drawing calls are unexercised, and
  those are ordinary MATLAB. Expect them to work; check them on your first run.
- **The shipped `results/` came from a deliberately tiny optimiser budget**
  (7-particle x 3-iteration swarms, ~40 evaluations for an 18-variable problem)
  to fit inside an execution limit. They demonstrate the pipeline; they are NOT
  converged optima. The surface-piercing cases in particular came back
  infeasible and, in one instance, worse than their own baseline - a clear sign
  of a non-converged search rather than a physical result. Run `main()` with
  defaults before quoting any number.
- Only 3/3 and 4/4 were run for the shipped results. All four combinations are
  implemented and enumerated by default.

### Files produced (in `results/` and `figures/`)

| File | Contents |
|---|---|
| `design_report.txt` | The full report: assumptions, motor audit, optimised design, gearbox spec, sanity checks, sensitivity, limitations |
| `front_blade_geometry.csv` | **→ CAD/Ansys.** Per radial station: r/R, r, chord, pitch, pitch angle, camber, thickness, skew, rake, reference-line and LE/TE Cartesian coordinates, plus the local hydrodynamic state |
| `rear_blade_geometry.csv` | Same, rear rotor |
| `design_summary.csv` | One-line-per-quantity summary for spreadsheets |
| `optimisation_results.mat` | Full result structure for further analysis |
| `opt_sub.mat`, `opt_sp.mat` | Per-architecture optimiser output, reusable via `main('load',true)` |
| `figures/01..09_*.png` | Resistance, open-water curves, CRP performance, motor envelope, radial loading, optimisation history, SP cyclic loads, blade geometry, blade outline |

**Take into CAD/Ansys:** the two `*_blade_geometry.csv` files. They carry the
blade reference line and LE/TE coordinates at every station, plus a header
block recording D, Z, P/D, EAR, hub diameter, rpm, thrust, torque, axial gap
and shaft angle, so an exported blade is always traceable to the run that made
it. The tool does **not** emit section offsets, because no hydrofoil family has
been specified — once you choose one, generate the offsets from the `t/c` and
`f/c` columns.

---

## 4. Reading the report

Work through it in this order:

1. **ASSUMPTIONS AND UNVERIFIED INPUTS** — everything the answer is conditional
   on. If a number here matters to your decision, measure it before trusting
   the result.
2. **MOTOR SPECIFICATION AUDIT** — the torque-speed-power consistency check.
3. **OPTIMISED DESIGN** — geometry, operating point, splits, efficiency chain.
   Note that `η₀` printed per rotor is the *isolated* rotor efficiency and is
   **not** the CRP system efficiency; use `η_CRP`.
4. **MOVEMENT AWAY FROM THE REFERENCE PITCH** — if a variable sits on its search
   bound, the bound is setting the answer, not the physics. Widen it and rerun.
5. **BLADE-COUNT COMPARISON** and the Pareto set.
6. **REQUIRED GEARBOX SPECIFICATION** — hand this to whoever designs the box.
7. **ENGINEERING SANITY CHECKS** — 14 automatic checks, each with its numbers.
8. **SENSITIVITY ANALYSIS** — ranked by influence on Wh/nm. This tells you where
   to spend measurement effort.
9. **MODEL LIMITATIONS AND REQUIRED VALIDATION** — read this before quoting any
   number to anyone.

---

## 5. Replacing assumptions with data

Every one of these is a `config.m` edit; none requires touching the solver.

| When you obtain | Set |
|---|---|
| Motor efficiency map | `params.motor.etaMap = @(rpm,Q) ...` |
| Measured wake / thrust deduction | `params.hull.w`, `params.hull.t`, `params.hull.eta_R` |
| CFD wake field | `params.hull.wakeField = [rR(:), w(:)]`, `useWakeField = true` |
| 300 kg resistance curve | `params.resistance.speed_kn_300`, `R_total_N_300` |
| Gearbox data | `params.gearbox.eta`, `ratio_min/max`, `serviceFactor` |
| Stainless grade | `params.material.*` (density, E, ν, yield, ultimate, fatigue) |
| Hydrofoil polars | `params.polar.external` (fields `alpha, Re, Cl, Cd`), `useExternal = true` |
| Shaft immersion | `params.surfacePiercing.hShaft_over_R` |
| SP CFD | `params.surfacePiercing.k_sc`, `Cd_base`, `entryAngle_deg`, `entryEfficiency` |
| Propeller CFD for validation | `params.validation.cfd.*` and `params.validation.geometry` |

---

## 6. Honest statement of what this is

This is a **transparent, parameterised preliminary design and trade-study
framework** whose every assumption is declared and replaceable, suitable for
iterative refinement through Ansys CFD and physical testing.

It is **not** a validated performance prediction. Blade element momentum theory
with empirical corrections is not equivalent to CFD. The surface-piercing
corrections in particular — water entry and exit, spray sheet, added mass,
cavity closure, ventilated section polars — are the weakest link, and the
Level-2 cyclic loads reconstruct immersion *kinematics* only, so peak loads are
**underestimated**. Blade natural frequencies are not computed at all, and they
matter for a propeller that is impulsively loaded once per revolution.

Nothing in the output is fabricated. Where data is missing, the tool says
*"Not available — requires CFD/experimental validation"* and carries on.
