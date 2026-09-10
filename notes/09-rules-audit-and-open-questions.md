---
tags: [volare, rules, compliance, questions]
status: audit against Technical Rules V2026.1 + NoC V1.0
---

# 09 — Rules Audit and Open Questions

Parent: [[00 - Master Brief]]
Sources: Monaco Energy Class Technical Rules **V2026.1** (issued 08/09/2025), Notice of Challenge **V1.0** (10/09/2025)

---

## PART A — What the rules change in work already done

### A1. The beams are the organiser's, and they are round carbon

Annex I: the hull package is **2 hulls + 2 beams, round carbon fibre poles, Ø104 mm, 3 m apart, 65 kg total.** ENERGY_REQ_3: *teams shall not modify the hulls and beams provided.*

The 104 × 104 mm "square crossbeams" in the STL are those round poles, modelled as boxes. So:

- **Everything in [[02 - Support Frame Design]] and [[08 - Frame Solution at Fixed Span]] about designing crossbeams is void.** They are supplied, fixed at 3 m, and untouchable.
- What we actually design is: the **rails**, the **clamps**, and the **cockpit structure**.
- The frame mass estimate drops — no crossbeams to build.

**Drag recompute.** A round Ø104 cylinder at Re = 1.06 × 10⁵ has C_D ≈ 1.2, not the 2.05 I used for a sharp square. Revised budget at 55 km/h (q = 143 Pa):

| Item | C_D·A | D |
|---|---|---|
| Fwd beam (round) | 0.287 | 41.0 N |
| Aft beam (0.85 wake) | 0.244 | 34.9 N |
| Exposed pilot + cavity | 0.135 | 19.3 N |
| Flag mast + flag (REQ_150/151) | 0.067 | 9.6 N |
| Pod shell | 0.034 | 4.8 N |
| Clamps ×4 | 0.029 | 4.1 N |
| Rails ×2 | 0.025 | 3.6 N |
| **Total** | **0.820** | **117 N → 1.79 kW** |

Faired: 0.197 → 0.43 kW. **Saving 1.36 kW**, down from the 2.27 kW I claimed. Still the largest single aero item, still worth chasing — but the number was inflated and I'm correcting it.

Note the **flag** is now a real drag item (REQ_150: flown ≥2 m above water, ≥30 cm wide) at ~9.6 N — more than the pod shell.

### A2. ENERGY_REQ_38 forces the rails 750 mm apart, not 400 mm

> *"at least two clamps or jaws per beam, continuously enveloping the entire circumference of the beam, over a minimum width of 50 mm per clamp/jaw, installed symmetrically either side of the ship's centreline with a **minimum spacing of 750 mm**... rubber gasket... minimum thickness 1 mm."*

The STL has the rails at **400 mm apart (±200 mm)**. That is non-compliant. They must go to **≥750 mm (±375 mm)**.

Floor deflection scales as L⁴, so this is a **12.4× penalty**:

| Span | Core | Skin | Deflection |
|---|---|---|---|
| 400 mm (as drawn) | 20 mm | 1.5 mm | 1.80 mm (L/223) |
| **750 mm (compliant)** | 20 mm | 1.5 mm | **9.20 mm (L/81)** ✗ |
| 750 mm | 30 mm | 2.5 mm | 2.83 mm (L/265) ✓ |
| 750 mm | 30 mm | 3.0 mm | 2.40 mm (L/313) ✓ |

So the floor schedule in [[03 - Composite Structure]] §3 is under-built. Either go to **30 mm core with 2.5 mm skins**, or add a **centreline keel beam / transverse frames** to halve the effective span. The keel is lighter and it doubles as the seat mount.

Silver lining: wider rails mean a wider, more stable base and a better lever arm for the box-girder action in [[08 - Frame Solution at Fixed Span]] §3.

### A3. The under-floor battery position is illegal

- **REQ_25:** energy container ≥ **500 mm** from the Pilot (including secondary containers)
- **REQ_26:** energy container **shall not** be inside the area where the Pilot is seated
- **REQ_50/52/54:** a bulkhead shall isolate propulsion and energy storage from the driver's compartment and protect the pilot from an explosion **in any direction**
- **REQ_51:** that bulkhead must be **A1 fire resistant to Euroclass** — that is *non-combustible*. GFRP is not A1. This has to be steel, aluminium, or mineral board, and it is new mass I had not budgeted.

My recommendation to put a flat pack under the pilot's floor is dead. The pack goes **aft of a bulkhead, ≥500 mm from the pilot** — which brings back the stern-heavy CG concern from [[06 - Powertrain, Battery and Solar]] §5, now as a constraint rather than a choice.

Also **REQ_186**: no cockpit appendix may contact the water. A low-slung pack or a deep fairing is out.

### A4. Battery container requirements I had not accounted for

| Req | Requirement |
|---|---|
| 155 | Certified, adequately sized **overpressure valve** oriented toward the back of the boat |
| 56 | **Fire extinguisher port on the port side**, accessible to external personnel |
| 189 | **External charging interface** — rechargeable without opening the container |
| 182 | **3.2 mm pass-through hole** letting the organiser put a temperature probe *in contact with cells at the core* |
| 171/172/173 | W026 symbol ≥10 cm, capacity and composition in ≥2 cm letters |
| 27 | Any ventilation from the energy source must blow **away from the Pilot** |

REQ_182 is the awkward one for a custom pack: a sealed IP67 enclosure with a probe channel to the core. Design the channel in from the start — retrofitting it means cutting into a finished pack.

### A5. Motor power — the Competr outboard is non-compliant as specified

**ENERGY_REQ_188 (new for 2026): total nominal power consumption of the motor(s) shall not exceed 25 kW.**

Competr nominal = **26.9 kW**. That is over the cap on the nameplate.

- At 25 kW electrical, my resistance model gives **~44 km/h**, not 55.
- At 42 kW peak, ~55 km/h — *if* peaks are permitted, which the rule's wording does not settle.

This is the single biggest open item in the whole project. See Q-TC-1.

### A6. The energy cap makes hydrogen structurally advantaged

**REQ_7: E_tot = Σ E_i × f_i ≤ 10 kWh**, with battery f = 1.0 and **hydrogen f = 0.35**.

| Split | H₂ mass | Electrical energy available | Est. system mass |
|---|---|---|---|
| 10 kWh batt, no H₂ | — | 9.60 kWh | 55 kg |
| 6 kWh batt + 11.4 kWh H₂ | 0.343 kg | 10.90 kWh | 66 kg |
| 4 kWh batt + 17.1 kWh H₂ | 0.515 kg | 11.55 kWh | 59 kg |
| **2 kWh batt + 22.9 kWh H₂** | **0.686 kg** | **12.21 kWh** | **51 kg** |
| 0 kWh batt + 28.6 kWh H₂ | 0.858 kg | 12.86 kWh | 44 kg |

(FC at 50% LHV efficiency with 10% BoP parasitics, 700 bar type IV tank at 4.5 wt%, ~20 kg stack.)

**Hydrogen-heavy is both lighter and higher-energy** — up to **34% more usable energy at 20% less mass**. That is why your hybrid architecture is the right call, and it means the ECMS work has a real optimum to find rather than a marginal one.

The catch is packaging. The H₂ rules are geometrically brutal on a 5 m boat:
- REQ_159: piping above 10 bar **≥1 m from the Pilot**
- REQ_120: vent release point **≥1.5 m above the hulls**, oriented upward (REQ_119)
- REQ_165: natural-ventilation outlet **50 cm above the driver's head**
- REQ_117: FC air exhaust rejected aft and **≥1.5 m from the Pilot**
- REQ_156: a *dedicated* bulkhead isolating gas storage from electrical components — so potentially **two** bulkheads
- REQ_128: cylinder gripping tulip withstanding **1000 N in all axes**
- REQ_163: ventilation justified by calculation to stay below 50% LEL

### A7. Mass — revised against the actual rule

**REQ_48: "The overall weight excluding the hulls shall not exceed 250 kg."** Note: weighed *with* hulls and pilot; hulls assumed 65 ±1 kg.

| Item | kg |
|---|---|
| Cockpit shell (zoned) | 27.0 |
| Rails ×2 | 18.7 |
| Clamps ×4 (enveloping Ø104) | 6.0 |
| Beam fairings | 4.0 |
| Seat + headrest | 5.0 |
| A1 bulkhead | 6.0 |
| Competr outboard | 25.0 |
| Trim assembly | 10.0 |
| Control unit | 3.0 |
| Inverter | 10.0 |
| Hydraulics, pumps, fluid | 12.0 |
| Pack 10 kWh + compliant container | 62.0 |
| DC/DC 96→12 V | 3.0 |
| Harness, contactors, IMD, HVIL | 8.0 |
| Solar 4 m² + MPPT | 10.0 |
| Safety kit (paddle, hook, flag, towline, extinguisher) | 6.0 |
| Monitoring bay, Amphenol, hi-vis tape, flag mast | 4.0 |
| **Subtotal, excl. hulls and pilot** | **219.7** |
| **+ 60 kg pilot** | **279.7 → +30 kg over** |

Better than my last estimate (the crossbeams are free), but still over on the strict reading. Whether the pilot counts is Q-TC-2 and it is worth 60 kg.

### A8. Solar is now clearly worth carrying

My earlier break-even said skip it for a short race. **NoC §9.1 changes that:** paddock charging is **Type F, 16 A, 220 V = 3.5 kW maximum**. A 10 kWh pack needs ~3 hours of shore charging. With racing on three consecutive days (NoC §3.2), charge time is the binding constraint, not energy. Solar's 0.5 kW average recovers 1.5–2 kWh between heats **for free and in parallel**.

Also **REQ_30** permits replenishing from a *secondary* energy source during a race, and REQ_2 defines secondary as "energy produced during the race" — so solar generation in-race is explicitly legal.

One conflict to design around: **REQ_93 — exposed parts shall not exceed 60 °C.** Panels bonded to a dark composite deck reach 70–80 °C in July. Use light gelcoat under the array, a ventilated backing gap, or expect to fail inspection.

### A9. Other requirements that touch the structure

| Req | Impact |
|---|---|
| 44 | Pilot must **evacuate in 5 seconds**, demonstrated by test. Your 455 × 445 mm opening needs a real rehearsal |
| 45 | Pilot **not fully enclosed**; no hatch may need opening before evacuation |
| 46 | **No restraints, no safety belts.** This changes the roll-structure logic — an unrestrained pilot in a roll hoop is a different problem |
| 41 | Feet in front of the body, free of hazards |
| 42 | Seat **shall include a headrest** |
| 43 | Clear field of view and **unobstructed hearing** — constrains the windscreen and any shoulder fairing |
| 47 | Cockpit **self-draining** (already designed) |
| 49 | Hi-vis tape: 500 cm² port, 500 cm² starboard, 250 cm² fore, 250 cm² aft |
| 81/85/86 | E-stop **starboard side, in front of the pilot, within 1 m of the starboard side, oriented outward** (not up), reachable seated **and** by external personnel |
| 62 | Electronics in **IP56** compartment, cooled |
| 185 | Free volume **190 × 150 × 122 mm** for the organiser's monitoring device — **open to the sky, outside all closed compartments**, x-y plane parallel to boat trim. Plus an organiser camera |
| 184 | Amphenol LTW BD-02BFFA-LL7001 connector, 10–28 V, 30 W |
| 170 | Cockpit must look professional; **design approved by the Design Jury in January** |
| 90 | No sharp edges — conflicts with the sharp-base tail I proposed in [[01 - Aerodynamic Redesign]] §4.4 |

### A10. The schedule risk nobody has costed

**NoC §3.2: Energy Class Hull Handover is 11am on Monday 6 July. Technical inspection closes 6pm Wednesday 8 July. Racing starts Thursday 9 July.**

You get the hulls and beams **two days before racing**, having never touched them. Every clamp, every interface, every clearance must be right first time, against a drawing with a ±2 mm build tolerance.

**Build a jig** that replicates the two Ø104 beams at exactly 3 m centres and the hull deck geometry from Annex II, and do the entire fit-up, evacuation test and weigh-in on that jig at ICT before shipping.

---

## PART B — Questions for the Technical Committee

These are genuine ambiguities in the rule text, not things you should guess at.

**Q-TC-1 — REQ_188, "nominal power consumption."** Does the 25 kW cap apply to (a) the motor's nameplate continuous rating, (b) instantaneous electrical draw at any moment, or (c) some averaged consumption over a race? The Competr unit is 26.9 kW nominal / 42 kW peak. Is a peak above 25 kW permitted if nominal is at or below it? **This decides whether the boat does 44 or 55 km/h, and whether this powertrain is usable at all.**

**Q-TC-2 — REQ_48, does the 250 kg include the pilot?** The rule says "excluding the hulls"; the note says the boat is weighed with hulls and pilot and that hulls are 65 kg. Is the compliance figure (total weighed − 65) or (total weighed − 65 − pilot)? **Worth 60 kg.**

**Q-TC-3 — REQ_7 Note 1 capacity formula.** It reads *quantity of cells × cell nominal voltage × cell nominal current*. Volts × amps is power, not energy. Should "nominal current" read "nominal capacity in Ah"? For a 26S21P Molicel P50B pack, the Ah reading gives 9.83 kWh (compliant); any other reading gives a meaningless number. Please confirm the intended formula.

**Q-TC-4 — Are non-structural fairings over the organiser's beams permitted?** REQ_3 forbids modifying the beams. A clamped-on, non-load-bearing aerodynamic shell does not modify the beam but does enclose it. Given REQ_38 requires clamps to *continuously envelop the entire circumference*, is a separate fairing shell between or outboard of the clamps allowed? **Worth ~1.4 kW at top speed.**

**Q-TC-5 — REQ_38 clamp spacing.** Is the 750 mm minimum measured between clamp centrelines or between their inner faces? And does "symmetrically on either side of the ship's centreline" require exactly two clamps per beam symmetric about the centreline, or permit four (two pairs)?

**Q-TC-6 — REQ_51 A1 bulkhead.** Euroclass A1 is non-combustible, which excludes all GFRP. Is a thin steel or aluminium sheet acceptable, or is a certified A1 board required with documentation? And does REQ_52's "protect the pilot from an explosion in any direction" imply a specific test or areal density?

**Q-TC-7 — REQ_25/26 datum.** Is the 500 mm measured from the pilot's seat, from the extremity of the pilot's body in the seated position, or from the driver's compartment boundary? And with the energy container aft of a bulkhead, does the 500 mm still apply through the bulkhead?

**Q-TC-8 — REQ_182 on a custom pack.** For a team-built, IP67-sealed pack, does the exception apply (sensor on the external wall) or must we design a sealed probe channel into the core? A channel to the cell core in a watertight enclosure is a meaningful design constraint and we would rather build it in than retrofit it.

**Q-TC-9 — REQ_187 timing.** Approval for >100 V is obtained "during the registration phase" (Stage 1 closes 9 January). If we are still deciding between a 26S NMC pack at 109 V and a 27S LFP pack at 98.5 V, can the application be conditional, or must the architecture be frozen by January?

**Q-TC-10 — REQ_186 vs. the drive.** "No cockpit appendices in contact with the water, except for the motor and the water pump." Does the outboard's mounting bracket and any anti-ventilation plate count as part of "the motor"?

**Q-TC-11 — REQ_150 flag.** Must the flag fly ≥2 m above water *while racing*, or only when stationary? A 2 m mast at 55 km/h is ~10 N of drag and a real structural load.

**Q-TC-12 — Which rules version applies?** These documents are V2026.1 / NoC V1.0 for the 8–11 July 2026 event, whose registration closed 9 January 2026. If we are targeting the next edition, is a V2027 draft available? REQ_188 (25 kW), REQ_38 (750 mm), REQ_186 and REQ_187 were all *added or modified* for 2026, so the changes history suggests this section of the rulebook is still moving.

---

## PART C — Questions for Competr

**Q-CM-1** Can the outboard be supplied or firmware-limited to **≤25 kW nominal** for REQ_188 compliance, with documentation the Technical Committee will accept? What is the resulting peak, and what speed does it give?

**Q-CM-2** Is the **inverter included or not?** §5.2 lists it as an included component; §5 "Recommended parts" lists it as "on request" with a note that a higher current rating is needed for full output. Mass and current rating, please.

**Q-CM-3** **Battery CAN DBC file** — we are building our own pack (the 192 kg unit is 77% of our entire mass allowance). What messages does the control unit expect from "Battery" on CAN1, at what rate, and will you release the DBC?

**Q-CM-4** The **12 V 1 kW aux DC/DC lives inside your pack.** With a custom pack we lose it. Our pump loads total ~110 A at 12 V. Do you supply a standalone DC/DC, or should we source one?

**Q-CM-5** **Control unit mass** is listed as TBD. Number please.

**Q-CM-6** Mounting height is specified for a **14° transom angle**. Our hulls are the YCM Energy Class hulls (Annex II). What is the correct mounting height and bracket interface for a **centre-mounted installation between two hulls**, rather than on a transom? Do you have a catamaran bracket, or do we design a mounting structure?

**Q-CM-7** REQ_36 requires steering to be **operable without power from the pilot seat with no modification**. Does the standard hydraulic manual steering satisfy this, and does the optional electric steering retain a manual fallback?

**Q-CM-8** What is the **thrust curve** — bollard pull and thrust at 20/30/40/50 km/h? I have been estimating from power and an assumed propulsive efficiency, and that assumption is the weakest link in the whole resistance model.

---

## PART D — What I need from you to go deeper

**Structure**

1. **Where does the outboard mount?** With only two organiser beams, both fixed, and no transom between the hulls, the drive has to hang off the aft Ø104 beam via a bracket, or off a structure you build. Which? This drives the largest single load case in the boat (~2800 N thrust, 1974 N·m overturning, 1800 N steering side load).
2. **Do you have the Hull Package CAD** from the Team Dashboard (Annex I references it)? I have been working from your STL; the official geometry would let me fix the beam positions, deck camber and clamp landing zones exactly.
3. **Seat frame** — procured from where, what mass, what mounting pitch? It sets the insert positions in the floor.
4. **Is the pod's fore-aft position adjustable** along the rails, or fixed by the current CAD? With the clamps now at ≥750 mm this is a free variable worth re-optimising for trim.
5. **What deflection have you actually measured or specified anywhere?** I have been assuming 3g and L/200. Both are my assumptions, not your requirements.

**Energy and powertrain**

6. **Is the PEMFC actually in the 2026 build, or aspirational?** The H₂ analysis above says hybrid is worth 34% more energy at 20% less mass, but the packaging rules (1 m standoff, 1.5 m vent height, dedicated second bulkhead) may not fit. If the FC is in, I want to lay out the H₂ zone before anything else is frozen.
7. **What is the actual race format?** Endurance duration, number of heats per day, gap between heats. Everything about pack sizing, solar value and the ECMS horizon depends on it, and I have been parameterising instead of solving.
8. **Supercapacitor bank** — sized yet? It is the thing that makes an LFP pack viable for slalom transients, and it changes the chemistry decision.
9. **What is the target for the 45% non-race score?** Innovation, Eco-Conception and Design carry as much weight as racing (NoC §4.4), and all Tech Talk material is open source (§8.3). If the CFD and topology work is also a Tech Talk deliverable, I should be structuring it for that from the start — different presentation, same engineering.
10. **Has anyone weighed a full BOM yet**, or is 250 kg still an aspiration? I have built three mass budgets from estimates. One real weigh-in of the components you already own would be worth more than all of them.
