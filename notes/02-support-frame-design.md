---
tags: [volare, structures, frame, aluminium]
---

# 02 — Support Frame Design (the rectangular rods)

Parent: [[00 - Master Brief]]

This is the note answering "recommend dimensions and material". Everything below is derived, not assumed.

> **SIZING SUPERSEDED.** Crossbeam stations are fixed by the hulls, and the real load distribution is 79/21 between forward and aft beams, not 50/50. Current sizing is in [[08 - Frame Solution at Fixed Span]]. The load cases, clamp design (§5), joint/racking work (§6) and fairing spec (§7) below all still stand.

> **Partly superseded by the Technical Rules — see [[09 - Rules Audit and Open Questions]] Part A.**

## 1. Load definition

Suspended mass carried by the frame:

| Item | kg |
|---|---|
| Cockpit shell | 30 |
| Pilot | 70 |
| Battery + electronics + seat | 80 |
| **Total suspended** | **180** |

At 3g: **W = 5297 N** total, split equally between the two crossbeams.

Additional cases:
- **LC-R (racking):** one hull on a crest, the other in a trough. Differential hull pitch of 3° over 2.035 m spacing torques the frame. This is the case that sizes the *joints*, not the beams.
- **LC-O (rollover):** inverted, 320 kg all-up. Design contact load on the pod roll structure = 1.5 × 0.5 × 320 × 9.81 = **2354 N**. Handled in [[03 - Composite Structure]] §6.
- **LC-B (battery retention):** treat separately at ≥ 8g in all three axes — cheap to satisfy and it is what "battery stays safe and inert" actually requires. Confirm the MEBC number.

## 2. Crossbeams — sizing

Clear span between hull inner faces = **1581 mm**. Two point loads of 1324 N at ±200 mm from midspan (the rail positions).

$$M_{max} = P\cdot a = 1324 \times 0.5905 = \mathbf{782\ N\!\cdot\!m}$$

$$\delta_{mid} = \frac{Pa(3L^2-4a^2)}{24EI} = \frac{198.9}{EI}$$

| Target | EI required | I for Al (69 GPa) | I for CFRP (100 GPa) |
|---|---|---|---|
| L/300 = 5.3 mm | 37.7 kN·m² | 54.7 cm⁴ | 37.7 cm⁴ |
| L/400 = 4.0 mm | 50.3 kN·m² | 72.9 cm⁴ | 50.3 cm⁴ |

## 3. Rails — sizing

Span between crossbeams **as currently drawn** = 2998 mm. UDL = 883 N/m.

$$M_{max} = \frac{wL^2}{8} = \mathbf{993\ N\!\cdot\!m},\qquad \delta = \frac{5wL^4}{384EI} = \frac{929.3}{EI}$$

| Target | EI required | I for Al |
|---|---|---|
| L/300 = 10.0 mm | 93.0 kN·m² | **134.8 cm⁴** |
| L/400 = 7.5 mm | 124.0 kN·m² | 179.7 cm⁴ |

### 3.1 SUPERSEDED — see [[07 - Why Beam Position Beats Beam Size]] §4

The relocation logic below is sound, but the COMPETR outboard (25 kg + 10 kg trim, ~2800 N thrust, 100 N·m reaction, ±40° steering) means the **aft crossbeam must stay at the stern**. Revised architecture is **three beams**: two light cockpit beams at ~1.8 m spacing (80×40×3) plus a dedicated stern drive beam (120×60×5, closed section, sized for torsion). Read §4 of note 07 before using the table below.

### 3.2 The span principle (still valid)

The aft crossbeam at X = +1942 sits 1.1 m behind the pod tail and carries nothing there. Deflection under UDL scales as WL³ for fixed total load, so shortening the rail span is cubically effective:

| Rail span | EI req (L/300) | Al I req |
|---|---|---|
| 3.00 m (as drawn) | 93.0 kN·m² | 135 cm⁴ |
| 2.40 m | 59.6 kN·m² | 86 cm⁴ |
| **1.90 m** | **37.4 kN·m²** | **54 cm⁴** |
| 1.70 m | 29.9 kN·m² | 43 cm⁴ |

Relocating the crossbeams to roughly X = −1250 and X = +550 (1.80 m apart, bracketing the pilot and battery mass) drops the rail from 120×60×4 to 100×50×3 and saves **~10 kg**. Subject to hull bulkhead positions — get those before committing.

## 4. Recommended sections

Aluminium **6082-T6** (or 6061-T6): E = 69 GPa, ρ = 2700 kg/m³, σ_y = 260 MPa, marine-acceptable with anodising.

| Section h×b×t | I [cm⁴] | A [cm²] | kg/m | Z [cm³] |
|---|---|---|---|---|
| 80×40×3 | 55.9 | 6.84 | 1.85 | 14.0 |
| **100×50×3** | **112.1** | **8.64** | **2.33** | **22.4** |
| 100×50×4 | 144.1 | 11.36 | 3.07 | 28.8 |
| 120×60×4 | 255.2 | 13.76 | 3.72 | 42.5 |
| 150×50×4 | 404.1 | 15.36 | 4.15 | 53.9 |

### Recommendation

| Member | Section | Length | Mass | Utilisation |
|---|---|---|---|---|
| Crossbeam ×2 | **100 × 50 × 3 mm RHS**, tall axis vertical | 2300 mm | 5.37 kg ea | I = 112 vs 55 req → 2.0× |
| Rail ×2 (frame relocated) | **100 × 50 × 3 mm RHS** | 2700 mm | 6.30 kg ea | I = 112 vs 54 req → 2.1× |
| **Frame total** | | | **23.3 kg** | vs 33.0 kg as drawn |

Stress at 3g: crossbeam σ = 34.9 MPa (**FoS 7.5**), rail σ = 23.3 MPa (**FoS 11.1**). Stiffness governs, not strength — which is the correct place to be, because it means the 2× stiffness margin is carrying your racking and rollover cases for free.

**Orientation matters:** 100 tall × 50 wide, *not* the square 104 you have. The tall-narrow section puts material where the bending load is and halves the frontal area presented to the airflow — a 2-for-1.

### Why aluminium over the alternatives

| Material | I req (rail, L/300) | Section needed | kg/m | Verdict |
|---|---|---|---|---|
| **Al 6082-T6** (69 GPa) | 135 cm⁴ | 120×60×4 | 3.72 | **Baseline.** Cheap, clampable, machinable, available in Mumbai |
| GFRP pultruded box (23 GPa) | 400 cm⁴ | 150×75×6 | 4.86 | Heavier despite lower density — E is too low. Reject |
| CFRP (≈100 GPa) | 93 cm⁴ | 100×50×3 | 1.38 | Half the mass. Upgrade path if budget allows |

If you go carbon: **you must electrically isolate it from every aluminium and stainless part.** Carbon is cathodic to aluminium; in salt spray the aluminium will pit within a season. Use 0.5 mm G10 isolation washers and phenolic bushings at every fastener, and a glass ply as the outermost layer of any carbon part.

## 5. Hull clamps — you said "clamped, no hardpoints"

**First check whether you are permitted to drill supplied hulls.** Assume not. That forces a non-penetrating clamp:

**Concept: saddle-and-yoke compression clamp**
- Upper saddle: aluminium plate contoured to the deck camber, **250 × 130 mm footprint**, 8 mm thick, with a 5 mm EPDM or neoprene interlayer
- Lower yoke: a strap or moulded GRP cradle passing under the hull, pulled up by 2 × M10 A4-316 tie-rods per clamp
- Beam sits in a bolted split collar on the saddle so the beam can be indexed fore-aft and rotated for fairing alignment

Bearing check: 1324 N over 250 × 130 mm = **0.041 MPa**. Trivial for GRP — the concern is not crushing but **peel and local deck panel bending**. Hence the large footprint and the elastomer, which spreads load and prevents point contact on a deck stiffener edge.

Friction retention against fore-aft slip: with EPDM on gelcoat, µ ≈ 0.6. Required tie-rod preload per clamp to resist a 3g surge of 1770 N: **F = 1770/0.6 ≈ 2950 N**, i.e. ~1500 N per M10 rod — well within an M10 A4-70 (proof load ~29 kN). Torque to 20 N·m and use nyloc + witness marks.

**Position the clamps over hull internal bulkheads.** Unsupported deck skin under a clamp will creep. Get the bulkhead stations from the organisers.

## 6. Joints and racking stiffness

A four-member ladder frame with bolted corners has poor torsional stiffness — under LC-R the corners rotate and the pod becomes the load path, which you do not want.

Three fixes, use at least two:

1. **Gusseted corner joints.** Replace the 166 × 109 × 162 mm blocks with welded aluminium corner castings or 8 mm gusset plates on both the top and bottom faces of each junction, developing full moment continuity.
2. **Horizontal diagonal bracing.** Two 40 × 40 × 3 RHS diagonals in the plane of the frame, from the forward crossbeam ends to the aft crossbeam centre. Adds ~2 kg, transforms racking stiffness. Cheapest fix available.
3. **Stressed floor panel.** Bolt the pod floor (which is a sandwich panel anyway) to both rails and both crossbeams on a 150 mm bolt pitch through moulded-in inserts. The floor then acts as a shear diaphragm. This is elegant and free in mass — but *only* do it if you use bolts with elastomer grommets, never a bonded aluminium-to-GRP joint (differential thermal expansion is 23 vs 10 µε/K; a 3 m bonded joint over a 30 K swing generates 1.2 mm of differential movement and will crack).

## 7. Beam fairings — the 2.3 kW item

Non-structural shells clamped around the RHS. This is where 77% of your superstructure drag lives.

**Section:** symmetric, 4:1 fineness. For a 50 mm wide beam → **200 mm chord × 50 mm thick**, i.e. a NACA 0025 at 200 mm chord, or simpler: a 60 mm-radius nose, straight taper, sharp 15° trailing edge.

**C_D on thickness-frontal:** 2.05 (bare square) → **0.12** (4:1 strut). Combined with the 104 → 50 mm width reduction, frontal area halves too.

**Construction (wet layup compatible):**
- Split the fairing on the horizontal plane through the beam centre
- 25 mm PVC foam or cork plug, hot-wire or CNC cut to the aerofoil, hollowed to clear the RHS
- 2 × 200 gsm plain-weave glass each half, wet laid over the plug in a female mould
- Join with a 25 mm-wide external glass tape strip on the low-curvature upper surface, or nylon quarter-turn fasteners for removability
- Mass ≈ 1.5 kg per beam per side → ~6 kg total for both beams and both rails

**Details that matter:**
- Chord tapers to 60% over the last 150 mm at each hull junction, with a 40 mm fillet — kills the horseshoe vortex
- Leading edge sealed against the beam so the fairing cannot pressurise internally
- Drain hole 6 mm at the lowest point of each fairing
- Set fairing incidence to 0° after checking the pod's upwash field in CFD (see [[01 - Aerodynamic Redesign]] §4.5)

**Rail fairings:** the rails are axial to the flow, so only the forward 200 mm needs a nose cone — a simple half-ogive cap, 150 mm long, glassed to the rail end. C_D 0.90 → 0.15 on the blunt end. 0.6 kg, 3 N.
