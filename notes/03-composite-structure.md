---
tags: [volare, composites, laminate, fea]
---

# 03 — Composite Structure and Laminate

Parent: [[00 - Master Brief]]
Target shell mass **23–35 kg** over **4.5803 m²** → allowable areal mass **5.02–7.64 kg/m²**.

> **Partly superseded by the Technical Rules — see [[09 - Rules Audit and Open Questions]] Part A.**

## 1. Why sandwich, from first principles

For a symmetric sandwich, flexural rigidity per unit width:

$$D = \frac{E_f t_f d^2}{2} + \frac{E_f t_f^3}{6} + \frac{E_c t_c^3}{12} \approx \frac{E_f t_f d^2}{2}$$

with d = t_c + t_f. Stiffness goes as **d²** while mass goes as roughly d⁰ (core density is low). A 3 mm single-skin panel and a 1.5/20/1.5 sandwich have similar areal mass; the sandwich is **~180× stiffer in bending**. There is no argument for single-skin anywhere on this pod except local hardpoints.

Wet hand layup resin ratios used below: CSM 1:2.5 glass:resin by weight, woven roving 1:1, cured laminate ρ ≈ 1.55 g/cm³.

## 2. Laminate schedules

| # | Schedule | Skins [mm] | Areal [kg/m²] | Shell [kg] | D [N·m²/m] |
|---|---|---|---|---|---|
| **A** | 300 CSM + 600 WR / **20 mm PVC H60** / 300 CSM + 450 WR | 1.45 / 1.26 | 6.30 | **28.9** | 3089 |
| B | 300 CSM + 450 WR / 20 mm PVC H60 / 300 CSM + 300 WR | 1.26 / 1.06 | 5.70 | 26.1 | 2600 |
| C | 300 CSM + 600 WR / **20 mm cork (150 kg/m³)** / 300 CSM + 450 WR | 1.45 / 1.26 | 7.95 | **36.4** | 3089 |
| D | 300 CSM + 600 WR / 15 mm PVC H60 / 300 CSM + 450 WR | 1.45 / 1.26 | 6.00 | 27.5 | 1812 |

(Includes 0.45 kg/m² gelcoat and core resin uptake.)

**Recommendation: Schedule A** as the baseline, Schedule B if the hulls weigh in heavy.

### On cork

You listed foam **or** cork. Cork at ~150 kg/m³ costs you **7.5 kg** over PVC H60 for identical stiffness — that is 3% of your entire 250 kg budget for zero performance return. Cork's real advantages (damping, impact tolerance, sustainability story, and it is a genuinely good MEBC innovation-jury narrative) are real but they are not free.

**Suggested compromise:** cork in the pilot floor and seat pan only (~0.8 m², +1.8 kg, where its damping and dent resistance actually help under a 3g slam), PVC H60 everywhere else. You keep the sustainability claim and 80% of the mass saving.

If cork is used, note **G_c ≈ 7 MPa** vs 20 MPa for H60 — shear deflection roughly triples (see §3).

## 3. Floor panel check — pilot at 3g

70 kg × 3g = **2060 N** over a 400 × 400 mm seat footprint = **12.9 kPa**. Rails 400 mm apart, so treat the floor strip as simply supported over L = 0.40 m.

$$\delta = \underbrace{\frac{5wL^4}{384D}}_{\text{bending}} + \underbrace{\frac{wL^2}{8S}}_{\text{shear}},\qquad S = \frac{G_c d^2}{t_c}$$

| Core | Skin | δ_bend | δ_shear | Total | Ratio | Skin σ | Core τ |
|---|---|---|---|---|---|---|---|
| 15 mm H60 | 1.35 | 2.38 | 0.72 | 3.10 mm | L/128 | 11.7 MPa | 0.158 MPa |
| **20 mm H60** | **1.50** | **1.24** | **0.56** | **1.80 mm** | **L/222** | **8.0 MPa** | **0.120 MPa** |
| 20 mm cork | 1.50 | 1.24 | 1.59 | 2.83 mm | L/141 | 8.0 MPa | 0.120 MPa |

**Answer to your open question on floor deflection: adopt L/200 (2.0 mm over the 400 mm rail spacing) as the acceptance criterion.** Below that, the pilot perceives the floor as solid; above L/150 it feels alive under slam and the seat mounts start to work.

Margins at the recommended 20 mm H60 / 1.50 mm build:
- Skin stress 8.0 MPa vs CSM/WR wet-layup UTS ≈ 110 MPa → **FoS 13.8**
- Core shear 0.120 MPa vs H60 τ_ult 0.76 MPa → **FoS 6.3** (cork ≈ 0.5 MPa → FoS 4.2)

Stiffness governs everywhere. This is the expected and correct result for a sandwich, and it means your topology work should be driven by **deflection constraints, not strength constraints** — see [[05 - Manufacturable Optimisation Workflow]].

## 4. Zoned schedule

Do not build the whole shell to one spec. Four zones:

| Zone | Area | Core | Skins | Rationale |
|---|---|---|---|---|
| Floor / seat pan | 1.1 m² | 20 mm (cork option) | 300 CSM + 600 WR both sides | 3g pilot + battery |
| Coaming / roll structure | 0.6 m² | 20 mm + local solid | +2 × 600 WR outer | LC-O, §6 |
| Sides / deck | 2.3 m² | 15 mm H60 | Schedule A | low load, stiffness only |
| Nose & tail cones | 0.6 m² | 10 mm H60 | 300 CSM + 300 WR | shape only, no load |

Estimated shell with zoning: **≈ 27 kg**, comfortably inside your 23–35 kg band.

## 5. Load path — keep the pilot out of the sandwich

**Do not bolt the seat frame to the sandwich skin.** Route pilot load directly into the rails:

- Four moulded-in load-spreading inserts through the floor, at the seat frame's own mounting pitch, positioned directly over the rails
- Insert = 60 mm dia aluminium or G10 plug, core removed and replaced with high-density (200 kg/m³) foam or a solid glass/epoxy puck, 3:1 chamfer to the surrounding core
- M8 A4-316 through-bolt into a captive threaded plate on the rail, with a compressible grommet
- Bearing: 2060 N / 4 inserts / (π × 30²) = **0.18 MPa** on the puck — trivial

This makes the shell a fairing plus a shear diaphragm, not a primary load member. It is what lets you hit 27 kg.

## 6. Rollover / capsize and battery containment

You asked for this specifically so the battery stays inert.

**Roll structure:** the pod's highest point (Z = +178 in assembly, the headrest peak at X = −364) is the inverted contact point. Sandwich alone is not a rollover structure. Add an **internal roll hoop**: 40 × 40 × 3 aluminium RHS, or a wet-laid GFRP box beam, arching under the coaming aft of the pilot's head and bolted down to both rails.

Design load LC-O = **2354 N** vertical at the crown. Treat as a 700 mm-span portal:
- M = 2354 × 0.35/2 ≈ 412 N·m
- 40×40×3 RHS: Z = 5.7 cm³ → σ = 72 MPa vs 260 MPa → **FoS 3.6** ✓
- Deflection under LC-O ≈ 6 mm — the crown must sit ≥ 50 mm above the pilot's helmet with the harness tight

**Battery compartment:**
- Separate sealed GRP box mounted **directly to the rails**, below the floor, forward of the pilot to help LCG
- Retention designed to **8g in all three axes** (not 3g): 50 kg pack → 3924 N per axis. Four M10 A4-316 mounts, each 981 N — trivial in shear, but the *box* must not deform, so 2 × 600 WR skins over 15 mm core with solid inserts at all mounts
- **Vent overboard, not into the cockpit.** A 50 mm dia duct from the box top, routed aft and exiting through the pod tail above the waterline, with a flame-arresting mesh
- Compartment sealed from the pilot volume with a 3 mm silicone gasket at the lid
- Thermal: 25 mm ceramic-fibre blanket between pack and the pilot-side wall of the box

## 7. Self-draining cockpit

Rules require it and you have the head to do it easily: pod floor sits at Z = −319, static waterline ≈ Z = −667. **348 mm of gravity head.**

- Floor sloped **2° aft** and cambered **3° to a 60 mm-wide centreline channel**
- Two 40 mm ID scuppers exiting through the pod's aft face, each with a duckbill non-return valve (elastomer, no moving parts, no corrosion)
- Drain rate: Torricelli, v = √(2gh) = √(2 × 9.81 × 0.348) = 2.61 m/s; through 2 × 40 mm (2 × 1257 mm²) with C_d = 0.62 → **4.1 L/s.** Clears a 30 L flooded cockpit in ~7 s. Comfortably compliant
- Scupper penetrations get solid-laminate inserts (core fully removed, 3:1 chamfer, 4 × 300 CSM local build-up) — a cored panel with an unsealed hole will wick water and delaminate

## 8. Wet-layup manufacturing rules

Give these to your moulder verbatim:

- **Minimum internal radius 12 mm** anywhere the laminate must conform; 20 mm preferred. CSM will not wet out into a sharper corner and you get a resin-rich crack initiator
- **Minimum draft 3°** on all mould-pull directions, 5° on textured surfaces
- **Ply drop-off 20:1 taper minimum**, drops staggered ≥ 25 mm apart, never more than 2 plies dropped at one station
- **Core chamfer 3:1** at every edge, insert and penetration
- **Grooved / perforated core** for hand layup so trapped air can escape; budget +0.45 kg/m² resin uptake (already in the tables above)
- Bond the core with a thickened resin paste, not neat resin — neat resin drains out of the bondline and you lose skin-to-core shear transfer
- Post-cure at 50 °C for 8 h if the polyester Tg allows; raises HDT and stops the shell creeping in a hot Monaco marina
- Wet layup Vf lands at 18–25%. All modulus values above (E_f = 10 GPa) assume this — **do not use datasheet infusion properties**
