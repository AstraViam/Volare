---
tags: [volare, mebc, cockpit, cfd, structures]
status: v1 - baseline audit
---

# 00 — Cockpit Optimisation Master Brief

> **READ [[09 - Rules Audit and Open Questions]] FIRST.** The Technical Rules V2026.1 supersede parts of every note below: the crossbeams are the organiser's round Ø104 carbon poles (not ours to design), clamps must be ≥750 mm apart (rails move from 400 mm), the energy container may not sit under the pilot, and the Competr outboard's 26.9 kW nominal exceeds the new 25 kW cap in ENERGY_REQ_188.

**Boat:** Team Volare catamaran, MEBC Energy Class
**Design speed:** 55 km/h = **15.28 m/s** (29.7 kn) — speed record; endurance lower
**Mass cap:** 250 kg | **Pilot:** 60 kg nominal, 70 kg design | **Slam:** 3g
**Process:** wet hand layup, E-glass / polyester or vinylester, foam or cork core
**Drive:** COMPETR electric outboard, 26.9 kW nom / 42 kW max, 96 V nominal · **Solar:** 4 m² limit

Notes: [[01 - Aerodynamic Redesign]] · [[02 - Support Frame Design]] · [[03 - Composite Structure]] · [[04 - Fluent CFD Setup]] · [[05 - Manufacturable Optimisation Workflow]] · [[06 - Powertrain, Battery and Solar]] · [[07 - Why Beam Position Beats Beam Size]] · [[08 - Frame Solution at Fixed Span]] · [[09 - Rules Audit and Open Questions]]

---

## 1. Geometry audit (measured from `Cockpit_V1_3.stl` / `FULLCOCPITV1_3.stl`)

| Item | Measured |
|---|---|
| Pod envelope | 2538 × 700 × 497 mm |
| Pod surface area | **4.5803 m²** (this is your laminate area) |
| Pod enclosed volume | 320.6 L |
| Pod frontal / planform / profile | 0.279 / 1.518 / 0.758 m² |
| Pod fineness ratio | L/D_eq = **4.26** |
| Cockpit opening | hexagonal, 455 (fore-aft) × 445 mm (athwart) |
| Demihull | 4989 × 454 × 573 mm, 593 L moulded, L/B = 11.0 |
| Hull spacing | 2035 mm c-c, clear gap 1581 mm, S/L = 0.41 |
| Crossbeams | 2 × **104 × 104 mm square**, 2300 / 2190 mm, at X = +1942 / −1056 (3.0 m apart) — **positions FIXED by hull suspension stations** |
| Rails | 2 × **104 × 135 mm**, 2970 mm, 400 mm apart c-c, on centreline |
| Pod longitudinal position | centroid 384 mm forward of hull mid-length |
| Pod incidence | ≈ 0.3° (essentially level) |

### Geometry defects found

1. **Rail–shell interference of 83 mm.** Rail tops sit at Z = −236; pod floor plane at Z = −319. The rails pass *through* the floor with no recess modelled. Must be resolved as either (a) recessed rail channels moulded into the floor, or (b) raise the pod 83 mm and mount on discrete pads. Option (b) is preferred — see [[02 - Support Frame Design]].
2. **455 × 445 mm opening is marginal for 70 kg egress.** Check against the MEBC quick-exit clause. Recommend widening to ≥ 500 mm athwart.
3. **Aft-body closure ≈ 15.6°** measured from the coaming peak (X = −364) to the tail. That is at the separation threshold; target ≤ 12°.
4. **Truncated tail** at X = +842 produces a base-drag patch. Either close it or accept a small, sharp-edged base (a *sharp* base separates cleanly; a rounded truncation is worse).

---

## 2. Drag budget at 15.28 m/s (q = 143.0 Pa)

Baseline, as-modelled:

| Item | A [m²] | C_D | C_D·A | D [N] |
|---|---|---|---|---|
| Crossbeam fwd (square, crossflow) | 0.239 | 2.05 | 0.490 | 70.1 |
| Crossbeam aft (0.85 wake factor) | 0.239 | 1.74 | 0.417 | 59.6 |
| Exposed pilot + open cavity | 0.150 | 0.90 | 0.135 | 19.3 |
| Corner brackets ×4 | 0.072 | 1.10 | 0.080 | 11.4 |
| Pod shell | 0.279 | 0.12 | 0.034 | 4.8 |
| Rails ×2 (blunt face) | 0.028 | 0.90 | 0.025 | 3.6 |
| **TOTAL** | | | **1.181** | **168.8 N → 2.58 kW** |

Optimised target:

| Item | C_D·A | D [N] |
|---|---|---|
| Faired crossbeams (100×50 tube in 4:1 fairing) | 0.028 | 3.9 |
| Pilot behind windscreen + shoulder fairing | 0.060 | 8.6 |
| Pod shell (aft body recontoured) | 0.028 | 4.0 |
| Blended brackets | 0.022 | 3.1 |
| Faired rails | 0.004 | 0.6 |
| **TOTAL** | **0.141** | **20.2 N → 0.31 kW** |

**Saving: ΔC_D·A = 1.04 m² (−88%), ΔP = 2.27 kW at 55 km/h, 0.37 kW at 30 km/h.**

> Priority order is therefore: **beam fairings → pilot fairing → brackets → pod shell**. Perfecting the pod contour is worth ~10 W. Do not spend your CFD budget there first.

### On the lift idea

Pod planform 1.518 m², span 0.700 m → **AR = 0.32**. At C_L = 0.30 and q = 143 Pa:

- Lift = 65.1 N = 6.64 kgf (2.1% of the 320 kg all-up displacement)
- Induced drag = C_L²/(π·AR·e) · q · S = **32.1 N** → L/D = 2.03
- Hull resistance recovered from 6.6 kg less displacement ≈ 4.7 N

**Net −27 N.** Deliberate aerodynamic lift is a losing trade at this aspect ratio and speed, and it adds a nose-up trim moment plus a much worse crosswind heeling case in Monaco harbour. Design the pod for **zero net lift** and put the effort into mass and beam drag instead. Full derivation and the alternative (mass-driven wetted-area reduction) in [[01 - Aerodynamic Redesign]].

---

## 3. Mass budget — SUPERSEDED

The Competr datasheet changes this materially. **See [[06 - Powertrain, Battery and Solar]] §8 for the current budget.** Headline: **282 kg excluding the pilot, 32 kg over cap**, driven by a 25 kg outboard, 10 kg trim assembly and a pack that cannot be the supplied 192 kg unit.

The governing unknown is now: **does the 250 kg cap include the pilot, and does it include energy storage?** Until that is answered nothing else can be closed out.

## 4. Open items blocking final release

- [ ] Weigh the supplied demihulls
- [ ] Hull internal bulkhead / frame positions — sets legal clamp locations
- [ ] MEBC rule text on: cockpit egress dimensions, self-draining, battery retention g-factor, rollover requirement
- [ ] Confirm whether drilling the supplied hulls is permitted (drives clamp concept, see [[02 - Support Frame Design]] §5)
- [ ] Moulder's answer on minimum radius, draft angle and split line
- [ ] Fluent licence tier — GPU solver needs CFD Enterprise 2023 R1+ or CFD HPC Ultimate 2025 R1 SP2+
- [ ] **Does the 250 kg cap include pilot and/or energy storage?** (blocks the entire mass budget)
- [ ] Endurance event duration — sets pack size off the table in [[06 - Powertrain, Battery and Solar]] §2
- [ ] Is there an energy cap on the pack, and is solar-harvested energy outside it? (decides the solar question)
- [ ] Ask COMPETR for the battery CAN DBC file before committing to a custom pack
- [ ] Resolve whether the 42 kW inverter is included or "on request"
- [ ] Measure your hull transom angle against the datasheet's 14° assumption
- [ ] Decide the 100 V route: TC pre-approval for 26S NMC (55 km/h) vs 27S LFP under 100 V (~49 km/h)
