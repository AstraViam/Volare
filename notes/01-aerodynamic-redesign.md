---
tags: [volare, aero, cfd, geometry]
---

# 01 — Aerodynamic Redesign

Parent: [[00 - Master Brief]]

## 1. Flow regime

$$V = 15.28\ \text{m/s},\quad q_\infty = \tfrac12\rho V^2 = 143.0\ \text{Pa},\quad Re_{pod} = \frac{VL}{\nu} = 2.59\times10^6$$

Fully turbulent over the pod. Hand-laid gelcoat has Ra ≈ 5–20 µm → equivalent sand-grain roughness k_s ≈ 50–100 µm, giving k_s⁺ = k_s·u_τ/ν ≈ 2–4. That is at the edge of hydraulically smooth, so **model the surface as smooth but run one roughness sensitivity case** (see [[04 - Fluent CFD Setup]] §5).

Hull Froude number Fn = V/√(gL) = **2.18**, volumetric Fn_∇ = 6.65 — fully planing. The hulls will be running on a small aft wetted patch at top speed, which is *why* the aero terms matter so much relative to hydrodynamic drag here.

## 2. Why "reduce eddy viscosity" is not an objective

Eddy viscosity ν_t is the closure variable in the Boussinesq hypothesis:

$$-\overline{u_i'u_j'} = \nu_t\left(\frac{\partial U_i}{\partial x_j}+\frac{\partial U_j}{\partial x_i}\right)-\tfrac23 k\delta_{ij}$$

It is a property of your *turbulence model*, not of the boat. A body with high ν_t in its shear layer is not necessarily draggier — an attached turbulent boundary layer has high ν_t and *low* drag; a separated wake has high ν_t and high drag. Minimising ν_t as an objective would push you toward laminar separation, which is worse.

**Use these as the actual objectives:**

| Objective | Metric | Where to read it |
|---|---|---|
| Minimise pressure drag | C_D·A per component | Fluent force reports, split by wall zone |
| Suppress separation | zero reversed-flow regions | surface skin-friction lines, τ_w < 0 patches |
| Minimise wake losses | total pressure deficit ∫(p₀∞ − p₀)dA | wake plane 1 m aft |
| Avoid vortex shedding on struts | Strouhal peak absent | transient probe, or steady residual oscillation |
| Zero net lift | C_L ≈ 0 ± 0.02 | force report, Z direction |

ν_t is a *diagnostic* — plot it to check your prism layer is resolving the boundary layer (ν_t/ν should peak at 100–500 in the log layer and fall to ~1 at the wall).

## 3. Lift derivation — why to design for zero lift

Lifting-line for a very low aspect ratio body:

$$AR = \frac{b^2}{S} = \frac{0.700^2}{1.518} = 0.323$$

$$C_{Di} = \frac{C_L^2}{\pi\, AR\, e},\qquad e\approx 0.60\ \text{(bluff planform)}$$

At C_L = 0.30: C_Di = 0.09/(π·0.323·0.60) = 0.148, so induced drag is **half the lift** (L/D = 2.03). Lift is 65.1 N; induced drag is 32.1 N.

The lift buys you displacement reduction. For a planing hull, resistance scales roughly R ≈ Δ·(R/W) with R/W ≈ 0.10–0.12 at Fn_∇ ≈ 6.6, so:

$$\Delta R \approx 0.12 \times 65.1\,\text{N} \times 0.6 \approx 4.7\ \text{N}$$

**Net penalty ≈ 27 N.** Structural mass reduction dominates by an order of magnitude: 10 kg removed is 98 N of displacement at *every* speed, with zero drag penalty and no trim moment. That is the lever, and it is why [[03 - Composite Structure]] and [[05 - Manufacturable Optimisation Workflow]] are the high-value notes, not this one.

**Design rule: target C_L = 0 ± 0.02 at 0° and ±3° pitch.** Achieve it with a symmetric-in-Z aft body and a slight negative camber over the coaming to cancel the nose-up moment from the forward deck.

## 4. Pod contour changes (ranked)

### 4.1 Windscreen and pilot fairing — 10.7 N recovered
The exposed pilot is the second largest item in the budget. Add:
- Wraparound windscreen at the forward coaming, **35–40° rake**, top edge at pilot eye level minus 30 mm (pilot looks over it — no optical distortion, no wiper problem)
- Screen top edge radius ≥ 8 mm, side edges swept back 25° so the shed vortex passes outboard of the shoulders
- Shoulder fairings blending the coaming into the headrest peak — this closes the open cavity

Target C_D on pilot frontal: 0.90 → 0.40.

### 4.2 Aft-body recontour — separation control
Current closure angle **15.6°** (deck drops 336 mm over 1200 mm behind the peak). For an attached turbulent boundary layer at this Re, hold the local surface slope **≤ 12°** and the equivalent conical half-angle **≤ 10°**.

Practical fix without lengthening the pod: move the peak aft by ~150 mm and redistribute the taper so curvature is continuous (G2) from the coaming to the tail. Check with the Stratford criterion — the pressure recovery should satisfy:

$$C_p(x)\ \text{such that}\ \left(C_p \frac{dC_p}{d(x/L)}\right)^{1/2} \le 0.39\left(10^{-6}Re\right)^{1/10}$$

Evaluate this along the top centreline from the Cp plot. If it is violated, the aft body separates before the tail.

### 4.3 Nose
L/D_eq = 4.26 is already close to the minimum-drag optimum for a body of revolution (4–6). **Leave the nose alone** apart from making sure the stagnation region has a minimum radius of 25 mm — a sharper nose gains nothing at this Re and creates a laminar separation bubble at low speed.

### 4.4 Tail truncation
If the moulder cannot pull a fully closed tail, keep the base **sharp-edged and flat** (not rounded). A sharp base fixes the separation line; a rounded truncation lets it wander and adds ~30% to base drag. Base area is small (~0.05 m²) so this is a 1–2 N item.

### 4.5 Interference
Three junctions need attention, and they are where CFD earns its keep:
- **Pod-to-rail:** the 83 mm interference (see [[00 - Master Brief]] §1) creates a channel between pod floor and rail top. Close it with a full-length seal fairing or lift the pod clear.
- **Beam-to-hull:** horseshoe vortex at each of the 4 junctions. Taper the fairing chord to ~60% over the last 150 mm before the hull and add a 40 mm fillet radius.
- **Pod-to-beam:** the forward crossbeam sits under the pod nose. Check whether it is in the pod's stagnation upwash — if so, set the fairing at 2–3° nose-down incidence.

## 5. What to measure in CFD

Report these separately by wall zone so you can see where the drag actually is:

```
/report/forces/wall-forces yes 1 0 0 no    ; drag, X direction
  zones: pod-shell, pod-opening, windscreen,
         beam-fwd-fairing, beam-aft-fairing,
         rail-port, rail-stbd, bracket-*, hull-above-wl
/report/forces/wall-forces yes 0 0 1 no    ; lift, Z direction
/report/forces/wall-moments ...            ; pitching moment about LCG
```

Plus: surface Cp, wall-shear-stress vector field (separation lines), Q-criterion isosurface at Q = 5000 s⁻², and a total-pressure-deficit plane 1.0 m aft of the transom.
