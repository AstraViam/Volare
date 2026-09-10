---
tags: [volare, cfd, fluent, meshing]
---

# 04 — Fluent CFD Setup

Parent: [[00 - Master Brief]] · Objectives defined in [[01 - Aerodynamic Redesign]] §2

Hardware: RTX 5080 (16 GB, 84 SM) + RTX 4050 (6 GB, 20 SM).

## 1. Licence and GPU reality check

The Fluent native GPU solver has been available since 2023 R1 and requires a CFD Enterprise licence (2023 R1+) or CFD HPC Ultimate (2025 R1 SP2+). Licensing is by **streaming multiprocessor count, with 40 SMs included in CFD Enterprise**; beyond that you need HPC add-ons.

Consequences for you:
- Your **RTX 5080 has 84 SMs** — more than the 40 included. Check with your Ansys contact whether you can use all of them or will be capped at 40. Either way it runs.
- **Do not run the two cards together.** Mixed-GPU jobs are limited by the slowest card and the smallest VRAM, and load imbalance kills the speedup. Solve on the 5080, use the 4050 for pre/post.
- **VRAM budget: ~1.2–3 GB per million cells** depending on physics. On 16 GB single-precision steady SIMPLE, plan for **8–12 M cells**. That is enough for this model if you use the symmetry plane.
- Verify your Fluent release supports Blackwell (sm_120) — 2025 R1 or later is the safe assumption. Confirm before you build a 12 M cell mesh you cannot solve.

Fall back to the CPU pressure-based coupled solver if the licence blocks GPU; the meshes below are still tractable, just slower.

## 2. Domain

Boat is symmetric about the centreline (Y = −948.5 mm) → **model half the boat.** This halves the cell count and is the difference between fitting in 16 GB and not.

With L = 5.0 m (hull length):

| Boundary | Distance | Type |
|---|---|---|
| Inlet | 3L = 15 m upstream | velocity-inlet, 15.278 m/s, I = 0.5%, ℓ = 0.1 m |
| Outlet | 7L = 35 m downstream | pressure-outlet, 0 Pa gauge |
| Side (outboard) | 4L = 20 m | symmetry |
| Top | 4L = 20 m | symmetry |
| Centreline | Y = −948.5 mm | symmetry |
| **Water surface** | at design waterline Z | **symmetry** |

**On the water surface:** for the aero study, treat the free surface as a flat **symmetry** plane at the design waterline. Zero shear is correct here — in the boat's reference frame the water moves *with* the boat, so there is no relative velocity and no boundary layer. Using a no-slip wall would fabricate a boundary layer that does not exist and overpredict the beam drag (the beams sit only ~190 mm above the static waterline, so they are inside that fictional layer).

Set the waterline from your hydrostatics: at 320 kg all-up, 0.156 m³ per demihull vs 0.593 m³ moulded → ~27% immersion → static waterline ≈ **Z = −667 mm**. Run a second case at the planing attitude (bow-up 3°, waterline 100 mm lower) as a sensitivity.

## 3. Boundary layer resolution

$$Re_{pod} = 2.59\times10^6,\quad C_f = \frac{0.026}{Re^{1/7}} = 0.00315,\quad \tau_w = 0.451\ \text{Pa},\quad u_\tau = 0.607\ \text{m/s}$$

| Target | First layer height |
|---|---|
| **y⁺ = 1** | **0.0247 mm** |
| y⁺ = 30 (wall functions) | 0.742 mm |

Boundary layer thickness δ = 0.37L/Re^0.2 = **49 mm**.

| Growth rate | Layers to cover δ |
|---|---|
| 1.15 | 41 |
| **1.20** | **33** |
| 1.25 | 28 |

**Strategy — hybrid, to fit the memory budget:**
- **y⁺ < 1, 30 prism layers at 1.2 growth** on: pod shell, windscreen, beam fairings, rail nose cones. These are where you need separation prediction, and SST is only trustworthy with a resolved wall.
- **y⁺ 30–100, 12 layers** on: hull above waterline, brackets, everything else.
- Fluent's SST uses automatic wall treatment so the blend is legal — but never leave a surface in the 3 < y⁺ < 15 buffer-layer range, which is the one place both treatments are wrong. Check with a y⁺ contour plot on every wall zone before you trust a result.

## 4. Mesh

Fluent Meshing **watertight geometry workflow**, poly-hexcore:

| Region | Surface size |
|---|---|
| Beam fairing leading edge | 2 mm |
| Windscreen edges, coaming | 3 mm |
| Pod shell general | 6 mm |
| Rails, brackets | 5 mm |
| Hull above waterline | 15 mm |
| Far field | 400 mm growth-limited |

Bodies of influence:
- BOI-1: box enclosing pod + both beams + 0.5 m clearance, 20 mm max cell
- BOI-2: wake box from transom to 3 m aft, 60 mm max cell — you need this resolved or the total-pressure-deficit metric is meaningless
- BOI-3: 150 mm-radius cylinder along each beam fairing wake

Expected: **7–10 M cells** half-model. Curvature normal angle 12°, min size 1.5 mm, cells per gap 4.

Quality gates before solving: max skewness < 0.85, min orthogonal quality > 0.15, max aspect ratio < 500 in the prism layers.

## 5. Solver settings

```
Solver:        pressure-based, steady, single precision (GPU)
Scheme:        Coupled, pseudo-transient, length scale = 2.5 m
Turbulence:    k-omega SST, curvature correction ON,
               production limiter ON
Wall roughness: smooth baseline;
               sensitivity case at Ks = 75e-6 m, Cs = 0.5
Discretisation: pressure       -> Second Order
                momentum       -> Second Order Upwind
                k, omega       -> Second Order Upwind
                gradient       -> Least Squares Cell Based
Initialisation: Hybrid, then 200 first-order iterations,
                then switch to second order
Convergence:    residuals < 1e-5 AND
                C_D on pod-shell stable to <0.5% over 500 iters
Reporting:      average forces over final 500 iterations
```

**Turbulence model note:** run k-ω SST as baseline. Do *not* use k-ε for this — it systematically underpredicts separation on the aft body, which is precisely the thing you are trying to detect. If the aft body shows marginal separation, re-run with GEKO (C_SEP tuned to 1.0) as a cross-check. Ignore transition models: hand-laid gelcoat at Re 2.6 × 10⁶ is fully turbulent from the nose.

**If the residuals stall or C_D oscillates**, that is physical, not numerical — the bare square beams shed vortices. Either accept the oscillation and time-average, or switch that case to URANS (Δt = 0.002 s, 20 inner iterations). Once faired, the oscillation disappears, which is itself a useful result to show the jury.

## 6. Run matrix

| # | Case | Purpose |
|---|---|---|
| 1 | Baseline geometry, 15.28 m/s | Validate the 2.58 kW estimate in [[00 - Master Brief]] §2 |
| 2 | Beam fairings only | Isolate the 2.0 kW claim |
| 3 | Fairings + windscreen + shoulder fairing | Isolate the pilot term |
| 4 | Full optimised pod (recontoured aft body) | Final |
| 5 | Case 4 at 8.3 m/s (30 km/h) | Endurance-speed check |
| 6 | Case 4 at ±3° pitch | C_L and trim moment sensitivity |
| 7 | Case 4 with 6 m/s crosswind at 20° yaw | Heeling moment, Monaco harbour |
| 8 | Case 4, Ks = 75 µm | Surface finish sensitivity |

Cases 6 and 7 matter more than they look. Yaw is the realistic operating condition and a low-AR pod develops a large side force and yawing moment that the symmetric head-on case never shows.

## 7. Verification you must do before quoting numbers

1. **Mesh independence.** Three meshes at r = 1.5 refinement ratio (≈3 M, 7 M, 15 M cells if the 15 M fits; otherwise 2/4.5/10 M). Compute the Grid Convergence Index per Roache:
   $$GCI = \frac{F_s|\varepsilon|}{r^p-1},\quad F_s = 1.25$$
   Report C_D with its GCI band. A number without this is not a result.
2. **Benchmark case.** Mesh and solve an isolated square cylinder in crossflow at Re = 1.4 × 10⁵ with your exact settings. Literature C_D = 2.05–2.1. If you do not land inside that band, your beam drag numbers are wrong and everything downstream is too.
3. **Domain independence.** Rerun case 1 with the side and top boundaries at 6L. Blockage ratio should be < 1%; if C_D moves > 1%, the domain is too small.
