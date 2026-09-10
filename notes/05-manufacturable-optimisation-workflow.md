---
tags: [volare, optimisation, fea, composites]
---

# 05 — Manufacturable Optimisation Workflow

Parent: [[00 - Master Brief]] · Structure defined in [[03 - Composite Structure]]

## 1. Why classical topology optimisation is the wrong tool here

You asked for topological optimisation. Density-based (SIMP) topology optimisation solves:

$$\min_{\rho} \ c(\rho)=\mathbf{u}^T\mathbf{K}(\rho)\mathbf{u} \quad \text{s.t.} \quad \frac{V(\rho)}{V_0}\le f,\quad E_e = E_0\rho_e^p$$

and returns a continuous 3D density field, which post-processing turns into an organic, variable-thickness solid. That output is manufacturable by casting, machining or metal AM. It is **not manufacturable by hand layup on a female mould**, where the only design variables you actually control are:

1. Number of plies at each location (integer, and each ply must be a contiguous piece of fabric)
2. Fibre orientation of each ply (in practice 0/90 or ±45 for woven roving)
3. Core thickness (discrete — 10, 15, 20, 25 mm stock)
4. Where local doublers and inserts go

Feeding SIMP output to a wet-layup shop produces a shape they will quote, decline, or approximate badly. **Use the formulation whose design variables match the process.**

## 2. The correct three-stage route

### Stage 1 — Topology optimisation used as a *diagnostic*, not a geometry generator

Still run it, but read it as a load-path map.

- Model: shell FE of the pod, uniform 20 mm sandwich, Ansys Mechanical
- Load cases: LC-1 pilot 3g, LC-2 self-mass 3g, LC-O rollover 2354 N at the crown, LC-R racking via prescribed rail displacement
- Objective: minimise compliance, 40% mass fraction
- **Read the result as: where do stiffeners and doublers belong?** The high-density ribbons are your reinforcement paths.

Manufacturing constraints to apply so the answer is at least interpretable: symmetry about the centreline, minimum member size 60 mm, and a pull-direction (extrusion) constraint aligned with the mould axis.

### Stage 2 — Convert load paths into a zoned, discrete build

Translate the ribbons into a physical layup you can actually specify:

| Optimiser output | Wet-layup realisation |
|---|---|
| High-density ribbon | Extra 600 gsm WR doubler, 150 mm wide, along the ribbon |
| Dense node | Solid insert, core removed, 3:1 chamfer |
| Dense region under seat | Core step 15 → 20 mm |
| Low-density region | Drop to 10 mm core, minimum skin |

Ply-drop rules from [[03 - Composite Structure]] §8 apply to every one of these transitions — 20:1 taper, staggered ≥ 25 mm, ≤ 2 plies at a time.

### Stage 3 — Parametric sizing optimisation (this is where the mass actually comes out)

This is the stage that replaces SIMP and is fully manufacturable. Set up in Ansys ACP + Mechanical, driven by DesignXplorer.

**Design variables (all discrete, all buildable):**

| Variable | Range | Step |
|---|---|---|
| n_WR outer skin, zone 1–4 | 1–3 plies | 1 |
| n_WR inner skin, zone 1–4 | 1–2 plies | 1 |
| Core thickness, zone 1–4 | 10 / 15 / 20 / 25 mm | discrete |
| Doubler width, 3 paths | 100–250 mm | 25 mm |
| Rail insert pitch | 150–400 mm | 50 mm |

**Objective:** minimise shell mass.

**Constraints:**

| Constraint | Limit | Source |
|---|---|---|
| Floor deflection under LC-1 | ≤ 2.0 mm (L/200) | [[03 - Composite Structure]] §3 |
| Skin strain, any ply, any LC | ≤ 3000 µε | wet-layup fatigue allowable |
| Core shear stress | ≤ 0.38 MPa (H60, FoS 2) | H60 τ_ult 0.76 MPa |
| Skin wrinkling | no wrinkling at 1.5× LC | §3 below |
| Roll crown deflection under LC-O | ≤ 25 mm | helmet clearance |
| Global torsional stiffness | ≥ baseline | LC-R |

Use Response Surface Optimisation with a Central Composite design — the variable count is small enough that you get a good surrogate in ~60 solves, each a few minutes on the 4050. Then verify the optimum with a direct solve.

**Realistic outcome:** 15–20% off the uniform-schedule 28.9 kg, i.e. **24–25 kg** for the shell.

## 3. Failure modes the optimiser will exploit if you do not constrain them

Sandwich optimisers reliably converge to thin skins over thick core, which fails in modes a shell FE will not report unless you add them explicitly:

**Skin wrinkling** (local skin instability on the core):
$$\sigma_{wr} = 0.5\left(E_f E_c G_c\right)^{1/3}$$
For E_f = 10 GPa, H60 (E_c = 60 MPa, G_c = 20 MPa): σ_wr = 0.5 × (10⁹ × 6 × 10⁷ × 2 × 10⁷)^(1/3) ≈ **53 MPa**. Your working skin stress is 8 MPa, so FoS ≈ 6.6 — safe at the current schedule, but it drops as the optimiser thins the skins. **Add it as an explicit constraint** or you will get a 1-ply skin that wrinkles.

**Intracell dimpling** — only relevant if you switch to honeycomb. Not an issue with foam or cork.

**Core crushing at inserts** — H60 compressive strength 0.9 MPa. Any bolt not going through a solid insert will crush the core over a season of slamming. This is the single most common failure in student-built composite hulls.

## 4. Sequencing

Do these in order — later stages depend on earlier ones and you cannot parallelise them:

1. Weigh the hulls. Get bulkhead stations. Read the rule text. *(blocks everything)*
2. Fix the frame layout — crossbeam positions, rail span ([[02 - Support Frame Design]] §3.1). *This changes the pod's boundary conditions, so the FE model is not valid until it is frozen.*
3. Resolve the 83 mm rail interference and the opening size.
4. Run CFD case 1 to validate the drag budget. If the beams really are 77% of it, everyone on the team stops arguing about pod curvature.
5. Build fairings and recontour the aft body → CFD cases 2–8.
6. FE Stage 1 and 2 in parallel with the CFD.
7. Stage 3 sizing optimisation. Freeze the laminate.
8. Send the moulder the ply book and the radius/draft schedule.

Step 4 before step 5 matters: you want the baseline number measured, not assumed, because the whole priority ordering in [[00 - Master Brief]] rests on it.
