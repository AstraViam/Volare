---
tags: [volare, powertrain, battery, solar, competr]
---

# 06 — Powertrain Integration, Pack Chemistry and Solar

Parent: [[00 - Master Brief]]
Source: COMPETR technical datasheet, rev 06/25

> **Partly superseded by the Technical Rules — see [[09 - Rules Audit and Open Questions]] Part A.**

## 1. What the datasheet forces

| Competr spec | Value | Consequence |
|---|---|---|
| Outboard nominal / max power | 26.9 / **42 kW** | See §2 — 42 kW is only reachable near max pack voltage |
| Max torque | 100 N·m | Reaction torque into the drive beam |
| Outboard mass | 25 kg | Stern-mounted, plus 10 kg trim assembly |
| Outboard envelope | 300 × 210 × 800 mm, 705 tall × 546 long | Fits a stern beam mount |
| Transom mounting height | 400 mm at **14° transom angle** | **Your hull transom angle must be measured** |
| Trim range | −5° / +30° | |
| Steering | −40° / +40°, hydraulic | Side force, §5 |
| Pack nominal / max voltage | 96 V / **109 V** | §3 — this is the problem |
| Pack max current | **375 A continuous** | §3 — this is the other problem |
| Pack configuration | 26S | Implies NMC/NCA at 4.2 V/cell |
| **Pack mass** | **192 kg** | **Unusable. 77% of your entire 250 kg cap** |
| Pack envelope | 960 × 330 × 430 mm | 430 mm tall — will not fit under the rails |
| Aux DC/DC | 12 V 1 kW, **inside the Competr pack** | Lost if you build your own pack. §6 |
| BMS | Integrated, isolation monitoring, CAN1 to VCU | §6 — CAN protocol is an integration risk |
| Control unit | 260 × 160 × 90 mm, IP67, mass TBD | Fits the aft bay |
| Pump loads | trim 40 A, rudder 40 A, bilge 15 A, cooling 15 A @ 12 V | **110 A peak = 1.3 kW.** Sizes the DC/DC |

**The 192 kg pack settles the question: building your own pack is not an optimisation, it is mandatory.** Your existing 26S21P Molicel plan is the right instinct.

## 2. Power required — how much motor you actually need

First-order resistance model: ITTC-57 friction with (1+k) = 1.15, residuary at 30% of frictional, aero from the [[00 - Master Brief]] budget, η_prop 0.53–0.60, η_motor+inverter 0.90.

| Speed | S_wet assumed | R_total | P_effective | P_shaft | **P_electrical** |
|---|---|---|---|---|---|
| 55 km/h | 3.30 m² | 1345 N | 20.5 kW | 34.2 kW | **38.1 kW** |
| 45 km/h | 3.90 m² | 1094 N | 13.7 kW | 23.6 kW | **26.2 kW** |
| 35 km/h | 4.60 m² | 809 N | 7.9 kW | 14.1 kW | **15.6 kW** |
| 30 km/h | 5.00 m² | 661 N | 5.5 kW | 10.0 kW | **11.1 kW** |
| 25 km/h | 5.30 m² | 501 N | 3.5 kW | 6.6 kW | **7.3 kW** |

> **Caveat:** the wetted-area column is the weak link. It encodes an assumed dynamic-lift schedule (hulls unloading ~45% by 55 km/h). Treat these as ±25% until you have hull towing data or a VOF run. Everything downstream inherits that band.

**The aero fix is what makes the target speed reachable.** At 55 km/h with the bare square beams, required electrical power is **42.25 kW** — exactly at the motor's 42 kW ceiling, with zero margin. Faired, it drops to **38.05 kW**. The 4.2 kW the fairings recover is the difference between "at the limit" and "has headroom."

### Endurance runtime vs pack size

| Usable kWh | 55 km/h | 45 | 35 | 30 | 25 |
|---|---|---|---|---|---|
| 4 | 6 min | 9 | 15 | 22 | 33 |
| 6 | 9 | 14 | 23 | 32 | 49 |
| **8** | **13** | **18** | **31** | **43** | **66** |
| 10 | 16 | 23 | 38 | 54 | 82 |
| 12 | 19 | 27 | 46 | 65 | 99 |
| 14 | 22 | 32 | 54 | 75 | 115 |

Find the endurance event duration in the rulebook and read the pack size off this table. That is the sizing decision, and nothing else about the pack should be decided first.

## 3. The 100 V collision — the most important finding here

Your own MEBC V2026.1 compliance audit flagged that a **pack above 100 V requires Technical Committee pre-approval.** The Competr system's 26S configuration reaches **109.2 V at full charge.** So the supplied architecture lands you straight in that category.

Series count against both constraints:

**NMC (3.60 / 4.20 / 2.50 V per cell)**

| S | V_nom | V_max | ≤100 V? | I at 42 kW |
|---|---|---|---|---|
| 23 | 82.8 | 96.6 | **yes** | 507 A |
| 24 | 86.4 | 100.8 | no | 486 A |
| **26** | **93.6** | **109.2** | **no** | **449 A** |

**LFP (3.20 / 3.65 / 2.50 V per cell)**

| S | V_nom | V_max | ≤100 V? | I at 42 kW |
|---|---|---|---|---|
| 26 | 83.2 | 94.9 | yes | 505 A |
| **27** | **86.4** | **98.5** | **yes** | **486 A** |
| 28 | 89.6 | 102.2 | no | 469 A |
| 30 | 96.0 | 109.5 | no | 438 A |

Two things fall out:

1. **LFP at 27S is the only configuration that both stays under 100 V and lands near the inverter's 96 V nominal.** 86.4 V nominal, 98.5 V at full charge. And LFP's flat discharge curve means it *holds* 84–86 V for most of the run instead of sagging like NMC — you already characterised that sag on the P50B.
2. **Staying under 100 V costs you top speed.** At 375 A continuous and 82.8–86.4 V, the inverter can deliver **31–32 kW**, not 38. Interpolating the power table, that caps you at roughly **49 km/h**, not 55.

So the choice is explicit:

| Route | Top speed | Compliance |
|---|---|---|
| 26S NMC, 109 V | 55 km/h reachable | Requires TC pre-approval — a schedule and paperwork risk you already identified |
| 27S LFP, 98.5 V | ~49 km/h | No pre-approval needed |
| 23S NMC, 96.6 V | ~49 km/h | No pre-approval, but you lose LFP's flat curve *and* NMC's safety margin — worst of both. Reject |

## 4. Chemistry trade at 8 kWh usable (8.9 kWh nameplate, 90% DoD)

| Chemistry | Config | Cells | Cell kg | **Pack kg** | Wh/kg |
|---|---|---|---|---|---|
| Molicel P50B 21700 | 26S20P | 520 | 36.4 | **51.7** | 181 |
| Molicel P45B 21700 | 26S22P | 572 | 40.0 | 56.9 | 163 |
| LFP prismatic 50 Ah | 27S3P | 81 | 72.9 | 88.9 | 146 |
| LFP prismatic 105 Ah | 27S1P | 27 | 52.9 | **64.6** | 141 |

(Overhead factors: 1.42 for cylindrical — holders, nickel, fusing; 1.22 for prismatic — simpler busbars, compression fixture.)

### Current capability is where LFP breaks

| Chemistry | Peak (42 kW) per cell | Cell limit | Endurance per cell | Verdict |
|---|---|---|---|---|
| Molicel P50B 26S20P | 22.4 A | 45 A | 5.9 A | comfortable |
| Molicel P45B 26S22P | 20.4 A | 45 A | 5.4 A | comfortable |
| LFP 50 Ah 27S3P | 162 A (3.2C) | ~150 A | 43 A | **exceeds** |
| LFP 105 Ah 27S1P | 486 A (4.6C) | ~315 A | 129 A | **exceeds badly** |

Standard prismatic LFP is a 1C-continuous / 2–3C-peak cell. To supply 486 A you would have to oversize the pack for *current*, not energy — roughly 150 kg of LFP to get 42 kW out. That kills it.

**But you have supercapacitors in the architecture already**, and this is exactly the problem they solve. Sizing check: if the pack supplies 15 kW and the supercaps cover the remaining 27 kW:

- 10 s transient burst: 270 kJ = 0.075 kWh → **~12.5 kg** of supercap module at 6 Wh/kg
- 30 s burst: 810 kJ = 0.225 kWh → **~37 kg**

So supercaps make LFP viable for *slalom transients and acceleration*, where bursts are a few seconds. They do **not** rescue LFP for a sustained speed-record run, where the battery has to carry the full load for the whole pass. Decide based on how long the timed run actually is.

### Heat

| Chemistry | Q at peak | Q at endurance | Adiabatic ΔT over a 90 s sprint |
|---|---|---|---|
| Molicel P50B 26S20P | 3272 W | 230 W | 8.1 K |
| Molicel P45B 26S22P | 2618 W | 184 W | 5.9 K |
| LFP 105 Ah 27S1P | 3190 W | 224 W | 5.4 K |

**Thermal management conclusion: you do not need a liquid loop.**

- **Sprint** is handled by cell thermal mass alone — under 10 K rise over 90 s at full power. No active cooling can respond that fast anyway.
- **Endurance** at 180–230 W continuous over 520 cells is 0.4 W/cell. Forced air at 2–3 m/s through a 21700 holder matrix removes 2–5 W/cell. **A single 12 V blower with a plenum is sufficient**, with the intake taken from inside the pod (dry) and exhausted through the tail.
- For LFP prismatic: bolt the cell stack to a 3 mm aluminium base plate acting as a conduction spreader to the enclosure floor. No fan needed at 224 W. Prismatic LFP is thermally the easier option by a wide margin, and it tolerates 55 °C where NMC does not.
- **Compression is not optional for prismatic LFP.** They need 300–1000 kPa of face pressure to hit rated cycle life. Budget a fixture: two 6 mm end plates and four M8 tie-rods with Belleville washers, ~2 kg. This is the detail most student teams miss.

## 5. Packaging — the aft bay, and a CG warning

You said the aft space is for electronics. Two problems if the *pack* also goes there:

1. **Longitudinal CG.** 35 kg of outboard and trim at the stern, plus 52–65 kg of pack in the pod tail, puts the LCG far aft. At Fn = 2.18 a stern-heavy slender catamaran is a porpoising candidate — a coupled pitch-heave oscillation that will cost you far more than any drag you saved.
2. **The Competr pack envelope is 430 mm tall.** A custom pack does not have to be.

**Recommended packaging:**

| Volume | Contents |
|---|---|
| **Under-floor, between rails** | Custom pack, **770 × 350 × 100 mm** (520 × 21700 upright, 22 mm pitch, 15 × 35 array, plus busbars). Clearance between rail bottom (Z = −372) and waterline (Z = −667) is 295 mm, so this fits with 195 mm to spare. Low CG, mid-length, out of the pilot compartment. Prismatic LFP packs even more naturally into this footprint. |
| **Aft bay** (pod-frame Y = 0 to +1200) | Inverter, control unit, DC/DC, contactors, fuses, IMD, telemetry. ~216 L available. This is the right home for electronics — they are light and heat-tolerant. |
| **Nose** (Y = −1332 to −455) | Pilot footwell. Keep clear. |

Under-floor pack requirements: **IP67 minimum**, sealed and vented aft (never into the cockpit), 3 mm sacrificial GRP bottom skin against slam and debris, and a faired lower surface so it does not add drag.

## 6. Integration risks that will bite you

1. **CAN protocol.** The Competr control unit expects specific CAN 2.0B messages from "Battery" on CAN1. A custom pack with your ADBMS6830B BMS must speak that protocol. **Ask Competr for the DBC file before you commit to a custom pack.** If they will not release it, you are reverse-engineering a safety-critical bus, which is a schedule risk, not an engineering one.
2. **The 12 V DC/DC lives inside the Competr pack.** Build your own pack and you lose it. Pump loads total 110 A at 12 V = 1.3 kW peak. Specify an isolated 96 V → 13.8 V, ≥1.2 kW converter, ~3 kg.
3. **Inverter contradiction in the datasheet.** §5.2 lists the power inverter as an included component; §5 "Recommended parts" lists Inverter as "on request" with a note that a higher current rating is needed for full output. **Resolve this** — a 42 kW / 450 A marine inverter is 8–15 kg and it is either in your budget or it is not.
4. **Control unit mass is listed as TBD.** Get the number.
5. **Transom angle.** The mounting-height figure assumes 14°. Measure your supplied hulls; if the transom is closer to vertical, the 400 mm figure and the whole trim range shift.
6. **PEMFC.** Nothing in this datasheet accommodates a fuel cell. Confirm how the FC feeds the DC bus — direct paralleling into a 96 V bus needs a boost stage and its own isolation monitoring.

## 7. Solar — 4 m² limit

### Technology and mass

| Technology | η | kg/m² | STC output | Realistic output* | Total installed** |
|---|---|---|---|---|---|
| Rigid glass mono | 20.5% | 11.0 | 820 W | 630 W | **46.3 kg** — reject outright |
| Semi-flex ETFE mono | 21.5% | 2.6 | 860 W | 661 W | 12.7 kg |
| **Semi-flex back-contact** | **23.0%** | **1.9** | **920 W** | **707 W** | **9.9 kg** |
| Bare back-contact cells laminated into the skin | 23.5% | 1.35 | 940 W | 722 W | 7.7 kg |

\* Monaco July, solar noon, cell at ~60 °C bonded to composite (−12.3% at −0.35%/K), soiling 3%, MPPT 3%, mismatch 2%.
\*\* Includes 1.3 kg MPPT and 1.0 kg wiring.

**Take the semi-flex back-contact modules bonded into moulded recesses, not cells laminated into a wet layup.** Styrene from polyester resin attacks EVA encapsulant, the exotherm can damage cells, and a bubble under a cell during hand layup is unrepairable. The 2.2 kg you save is not worth an unrepairable array.

Where the 4 m² goes: ~1.3 m² on the pod deck (planform 1.518 m² minus the opening), ~2.5 m² on the two hull decks. **Do not build a separate solar wing** — a horizontal panel above the pod adds drag, lift and a crosswind heeling moment, and you already established in [[01 - Aerodynamic Redesign]] that added lift is a losing trade.

### Break-even against carrying more cells instead

This is the calculation that actually decides it. 9.9 kg of solar versus the same 9.9 kg of Molicel pack at 181 Wh/kg:

- 9.9 kg of cells = **1.79 kWh stored, once**
- 9.9 kg of solar = **495 W race-average** (0.70 factor for tilt, cloud, time of day) = 0.49 kWh per hour of sun

$$t_{\text{break-even}} = \frac{1.79\ \text{kWh}}{0.495\ \text{kW}} = 3.6\ \text{hours of racing}$$

**For any race under ~3.6 hours, the same mass in cells beats the solar array.** As a during-race power source solar is marginal:

| Speed | Draw | Solar covers |
|---|---|---|
| 55 km/h | 38.1 kW | 1.3% |
| 35 km/h | 15.6 kW | 3.2% |
| 25 km/h | 7.3 kW | 6.8% |

### But solar is a recharging asset, and that is a different calculation

The array keeps working when the boat is not racing:

| Standby sun | Recovered | As % of an 8 kWh pack |
|---|---|---|
| 2 h | 0.99 kWh | 12% |
| 3 h | 1.48 kWh | 19% |
| 4 h | 1.98 kWh | 25% |
| 6 h | 2.97 kWh | 37% |

**So the verdict hinges on three rulebook questions, not on physics:**

1. Is there an **energy cap** on the pack? If yes, and solar-harvested energy sits outside that cap, fit the array — it is free energy against a hard ceiling and the break-even calculation is irrelevant.
2. Is **shore charging time limited** between heats? If yes, 1–2 kWh of trickle recovery has real value.
3. Do the **innovation / energy-efficiency scores** credit it? A working solar subsystem is cheap jury points.

If all three are no, and the race is a sub-hour endurance run, **skip the solar and carry 10 kg more cells.** That is the honest answer and it is the opposite of what most teams assume.

## 8. Revised mass budget

| Item | kg | Basis |
|---|---|---|
| Demihulls ×2 (supplied) | 80 | **UNKNOWN — weigh them** |
| Cockpit shell (zoned Schedule A) | 27 | calculated |
| Support frame, 3-beam revised | 26 | calculated |
| Beam + rail fairings | 6 | estimate |
| Hull clamps ×4 + hardware | 5 | estimate |
| Seat frame | 5 | your figure |
| Competr outboard | 25 | datasheet |
| Competr trim assembly | 10 | datasheet |
| Competr control unit | 3 | datasheet says TBD |
| Inverter (42 kW / 450 A class) | 10 | **confirm if included** |
| Trim + steering pumps, fluid, lines | 8 | estimate |
| Cooling + bilge pumps, plumbing | 4 | estimate |
| Custom pack, 8 kWh Molicel 26S20P | 52 | calculated |
| Isolated DC/DC 96 → 12 V, 1.2 kW | 3 | required |
| HV/LV harness, contactors, fuses, IMD/HVIL | 8 | estimate |
| Solar 4 m² + MPPT + wiring | 10 | calculated |
| **Boat subtotal, no pilot** | **282** | **+32 over cap** |
| + pilot | 352 | +102 over cap |

**You are over the cap before the pilot gets in.** With the Competr 192 kg pack instead: +172 kg over. 

This is now the governing question for the whole project: **does the 250 kg cap include the pilot, and does it include energy storage?** Many race classes exclude both. Until that is answered, the entire mass budget is unresolved and the topology optimisation in [[05 - Manufacturable Optimisation Workflow]] has no target to hit.

Levers if the cap really is 250 kg all-in:
- Drop solar: **−10 kg** (see §7 — it may cost you nothing)
- Pack from 8 → 6 kWh: **−13 kg** (costs 11 min at 30 km/h)
- Cockpit Schedule B instead of A: **−3 kg**
- Carbon rails instead of aluminium: **−9 kg** (costs money and needs galvanic isolation)
- Lighter hulls: unknown, and not yours to control
