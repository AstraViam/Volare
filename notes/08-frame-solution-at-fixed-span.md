---
tags: [volare, structures, frame, aluminium]
status: supersedes sizing in note 02
---

# 08 — Frame Solution at Fixed Span

Parent: [[00 - Master Brief]] · Supersedes the rail/crossbeam sizing in [[02 - Support Frame Design]] §2–4 and the relocation advice in [[07 - Why Beam Position Beats Beam Size]] §3–4

**Constraint accepted:** crossbeam stations on the hulls are fixed at X = −1056 and +1942 mm. Span = **2998 mm, non-negotiable.** Relocation is off the table.

> **Partly superseded by the Technical Rules — see [[09 - Rules Audit and Open Questions]] Part A.**

## 1. What the fixed geometry actually reveals

My earlier sizing assumed a uniform load across the whole span. That was wrong. The real load only exists where the pod is (X = −1696 to +842), and the pod sits **870 mm forward of the span midpoint**. Solving the actual beam:

| Quantity | Value |
|---|---|
| Load per rail (174 kg suspended × 3g / 2) | 2560 N |
| UDL over the pod footprint only | 1009 N/m |
| **Forward crossbeam reaction** | **2023 N (79%)** |
| **Aft crossbeam reaction** | **537 N (21%)** |
| Max bending moment | 940 N·m at X = +309 mm |
| **Forward cantilever (pod nose beyond fwd crossbeam)** | **640 mm** |
| Aft rail length carrying no pod load | 1100 mm |

Two corrections follow:

**(a) The forward crossbeam is under-sized in note 02.** I specced 100 × 50 × 3 for both, assuming 1324 N each. It actually sees 2023 N.

**(b) The aft crossbeam is massively over-sized** for the cockpit load — it only sees 537 N.

### Corrected crossbeam sizing

| Section | I | Sag | σ | FoS | Mass |
|---|---|---|---|---|---|
| **Forward (2023 N/rail, M = 1195 N·m)** | | | | | |
| 100 × 50 × 3 | 112 cm⁴ | 3.93 mm (L/403) | 53.3 MPa | 4.9 | 5.37 kg |
| **120 × 60 × 4** | **255 cm⁴** | **1.73 mm (L/916)** | **28.1 MPa** | **9.3** | **8.54 kg** |
| **Aft (537 N/rail, M = 317 N·m)** | | | | | |
| **100 × 50 × 3** | **112 cm⁴** | **1.04 mm (L/1516)** | **14.1 MPa** | **18.4** | **5.37 kg** |

FoS 4.9 on a 3g nominal case in a marine structure is thinner than I'd accept — the 3g is a design assumption, not a measured number. Upsize the forward beam; leave the aft one small.

## 2. Route 1 — deeper, not thicker (do this today, zero risk)

The mass-efficient move at fixed span is to grow section **depth** at constant wall thickness. Second moment scales as h³ while mass scales roughly as (h + b), so depth is cheap in mass and expensive in stiffness. Narrowing at the same time is free stiffness *and* less fairing frontal area.

| Section | I | kg/m | Pair mass | In-span sag | Nose tip | σ |
|---|---|---|---|---|---|---|
| 100 × 50 × 3 | 112 cm⁴ | 2.33 | 13.86 kg | 11.19 mm | 8.14 mm | 41.9 MPa |
| 120 × 60 × 4 *(my earlier spec)* | 255 cm⁴ | 3.72 | 22.07 kg | 4.91 mm | 3.58 mm | 22.1 MPa |
| **150 × 50 × 3** | **311 cm⁴** | **3.14** | **18.67 kg** | **4.03 mm** | **2.93 mm** | **22.6 MPa** |
| 180 × 50 × 3 | 498 cm⁴ | 3.63 | 21.56 kg | 2.52 mm | 1.83 mm | 17.0 MPa |
| 200 × 50 × 3 | 656 cm⁴ | 3.95 | 23.48 kg | 1.91 mm | 1.39 mm | 14.3 MPa |

**150 × 50 × 3 beats 120 × 60 × 4 on every count: 22% stiffer, 16% lighter, 10 mm narrower.** Even 180 × 50 × 3 — nearly double the stiffness — is lighter than the 120 × 60 × 4 I originally specified.

### Local buckling check (deep-narrow webs need it)

Elastic plate buckling, web in bending, k = 23.9:

| Section | web b/t | σ_cr | Working σ | FoS |
|---|---|---|---|---|
| 150 × 50 × 3 | 48 | 661 MPa | 22.6 MPa | 29 |
| 180 × 50 × 3 | 58 | 452 MPa | 17.0 MPa | 27 |
| 200 × 50 × 3 | 65 | 364 MPa | 14.3 MPa | 25 |

By Eurocode 9 classification a 3 mm web at 150 mm depth is technically class 4 (slender), but that governs full-yield capacity. At our working stress of 22.6 MPa the buckling margin is 29×. **Not a constraint here.** Closed RHS is also immune to lateral-torsional buckling, so the deep-narrow section carries no hidden penalty.

**Packaging limit:** the rail currently occupies Z = −372 to −236 and the pod floor is at Z = −319. Growing depth upward turns the existing 83 mm interference into a moulded floor tunnel. At 150 mm deep the rail top reaches Z = −222, i.e. a 97 mm tunnel into the pod interior — acceptable. At 200 mm it's a 147 mm tunnel, which fouls the seat pan. **150 mm is the practical ceiling under the pilot; 180–200 mm is fine in the aft electronics bay** if you want a stepped-depth rail.

## 3. Route 2 — let the pod shell carry the span (the real prize)

The pod is 700 mm wide and ~400 mm deep with a 20 mm sandwich wall. As a closed thin-walled box girder, idealising both skins as a 2.7 mm membrane at E = 10 GPa:

$$I_{pod} \approx 2\left(b\,t\,\left(\tfrac{d}{2}\right)^2\right) + 2\left(\frac{t\,d^3}{12}\right) = 1.8\times10^{-4}\ \text{m}^4 = 18{,}000\ \text{cm}^4$$

$$EI_{pod} = 1800\ \text{kN·m}^2$$

The rail pair needs **173 kN·m²** to hold 10 mm of sag. **The shell is 10.4× stiffer than the entire rail pair needs to be — and it already exists.**

Even with the 455 × 445 mm cockpit opening cutting the top flange down to a 255 mm strip, the section retains **13,194 cm⁴, or 73%** of the closed value.

So the rails don't have to be beams. They can be mounting rails, and the shell can be the structure.

**What this requires:**

1. **Continuous shear transfer, not point bolts.** Bolts at 150 mm pitch through moulded inserts into the rail's top face, with close-fitting or shear-pinned holes. Clearance holes will let the joint slip and the girder action never develops.
2. **A reinforced coaming ring.** The cutout sits where the bending moment is largest. Treat it like a car's door aperture: a closed-section coaming rail all the way around the opening, tied into the roll hoop from [[03 - Composite Structure]] §6 acting as a transverse frame.
3. **Bolted, not bonded.** A 3 m aluminium-to-GRP bondline sees 1.2 mm of differential movement over a 30 K swing (23 vs 10 µε/K). Bolt it with elastomer grommets.
4. **Moulded rail tunnels** in the floor, which resolves the 83 mm interference and forms the girder's bottom flange in one move.

**Honest risk assessment:** this makes a wet hand-laid shell into primary structure, with a large cutout at peak moment, depending on joint quality that is the hardest thing to control in a student-built boat. Shell damage becomes structural damage. Also check whether any MEBC clause requires the cockpit to be a survival cell — structural duty may conflict.

Note this partly contradicts [[03 - Composite Structure]] §5. Both can hold: **local** pilot load still goes through inserts directly into the rails; **global** span load goes through the shell. Keep those two paths separate in the FE model.

## 4. Route 3 — composite top-hat (the low-risk middle)

Don't make the shell the whole girder — just let the floor act as a top flange on each rail. Transformed-section calculation with modular ratio n = E_al/E_GRP = 6.9:

| | I | Sag |
|---|---|---|
| 100 × 50 × 3 alone | 112 cm⁴ | 11.19 mm |
| + pod floor as transformed top flange | **187 cm⁴ (1.7×)** | **6.71 mm** |

A 1.7× gain from a joint you have to build anyway. Less than Route 2 but with far less riding on layup quality. This is the sensible first step: build it, measure the deflection with the pilot in, and only chase Route 2 if you need more.

## 5. Route 4 — internal tied arch / king post

Add one mid-span support inside the pod and the rail becomes a two-span continuous beam: δ ≈ 0.0054wℓ⁴/EI with ℓ = L/2, a **39× reduction**.

| Rail | I | Sag | Pair mass |
|---|---|---|---|
| **60 × 40 × 3** | **27 cm⁴** | **1.46 mm** | **9.05 kg** |
| 80 × 40 × 3 | 56 cm⁴ | 0.71 mm | 10.97 kg |

The support is a compression arch (or king post) spanning crossbeam to crossbeam above the rails, with the rails acting as the tension tie — self-equilibrating, no external reaction needed.

| Arch rise | Thrust into rail as axial tension |
|---|---|
| 200 mm | 4061 N |
| 250 mm | 3249 N |
| **300 mm** | **2708 N** |

At 2708 N through a 60 × 40 × 3 section (A = 5.64 cm²) that's 4.8 MPa — trivial. Geometrically it works: at a 300 mm rise the arch is only ~89 mm above the rail at the forward edge of the cockpit opening, peaking at X ≈ +443 which is inside the electronics bay, clear of the pilot.

Biggest saving of the four, but it adds two joints per rail and a compression member that must not buckle. Only worth it if Routes 1–3 leave you short.

## 6. Mass roll-up

| Configuration | Frame mass |
|---|---|
| As first specced (120×60×4 rails, 100×50×3 beams) — *and structurally wrong at the fwd beam* | 32.8 kg |
| **Route 1: 150×50×3 rails + 120×60×4 fwd + 100×50×3 aft** | **32.6 kg** |
| Route 2/3: pod-assisted, 100×50×3 rails + rebalanced beams | **27.8 kg** |
| Route 4: arch, 60×40×3 rails + rebalanced beams | **23.0 kg** |
| *+ if the drive mounts on the aft crossbeam (150×75×6)* | *+10.5 kg* |

Route 1 lands at the same mass as my original spec — but that original spec had an under-sized forward crossbeam. **So Route 1 is a strictly better structure for the same weight**, and it is a pure purchase-order change. Routes 2/3 are where the ~5 kg lives, and Route 4 where ~10 kg lives.

## 7. Pod fore-aft position — counter-intuitive result

I expected centring the pod on the span to help. It doesn't:

| Shift aft | Ra / Rb | M_max | Sag | Nose tip | Pod LCG vs hull mid |
|---|---|---|---|---|---|
| **0 (as drawn)** | **2023 / 537** | **940 N·m** | **4.03 mm** | **2.93 mm** | **−384 mm** |
| 200 mm | 1852 / 708 | 983 | 4.19 | 2.04 | −184 mm |
| 400 mm | 1682 / 879 | 1027 | 4.39 | 1.15 | +16 mm |
| 870 mm (centred) | 1280 / 1280 | 1107 | 4.80 | 0 | +486 mm |

Centring makes the moment and the sag **worse**, not better. With the load sitting close to the forward support the moment arm is short; centring it recreates the classic maximum-moment case. Centring only helps the nose cantilever and the reaction balance.

**Leave the pod where it is** — one fewer thing to change. But note that a **400 mm aft shift puts the pod LCG at hull mid-length** for 9% more moment and 0.36 mm more sag. That is a cheap trade if trim work later says you need it, especially given the stern-heavy concern from [[06 - Powertrain, Battery and Solar]] §5.

## 8. Recommendation

1. **Now:** rails to **150 × 50 × 3**, forward crossbeam to **120 × 60 × 4**, aft crossbeam stays **100 × 50 × 3**. Pure BOM change, fixes the forward-beam margin, 4.03 mm sag, 2.93 mm nose deflection.
2. **In the design:** build the pod-to-rail joint as a proper shear connection with moulded tunnels and a reinforced coaming ring, so Route 3 comes for free and Route 2 stays available.
3. **Verify, don't assume:** the 174 kg suspended mass and the 3g factor are both assumptions. Weigh the finished pod and instrument the rails with strain gauges on the first water test before you trust any of this.

## 9. Open question this raises

If only two hull stations exist, the outboard cannot have its own dedicated stern beam — it has to hang off the aft crossbeam at X = +1942, which sits **509 mm forward of the hull transoms** at X = +2451. That beam would then carry 2800 N of thrust, 1974 N·m of overturning moment and 1800 N of steering side load on top of the cockpit reaction, forcing it to 150 × 75 × 6 and **+10.5 kg**.

**Where is the drive actually mounting?** Options: (a) on the aft crossbeam via a cantilever bracket, (b) clamped directly to the two hull transoms with its own bridging structure, (c) a third station that does exist for the drive specifically. This is worth more mass than anything else in this note.
