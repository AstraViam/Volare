# Monaco Energy Class compliance

Rules: **Monaco Energy Class Technical Rules, Version 2026.1**, issued 08/09/2025
by the Yacht Club de Monaco. Copy held in `04_data/`.

Run the live check:

```bash
matlab -batch "addpath(genpath(pwd)); P50B_MonacoCompliance"
```

`TEST_ALL` fails if any quantifiable rule is violated.

**94 checks: 55 pass, 0 violations, 14 to action, 24 on the inspection
checklist.** 70 of the 94 are computed; the rest are physical or procedural.

To push the result to Mission Control's Compliance tab:

```bash
matlab -batch "addpath(genpath(pwd)); P50B_ExportCompliance"
python tools/build_mission_control.py
```

---

## How a rule becomes a check

Most of the 2026 rules are a number and a direction — *at least 30 mm*, *no
more than 50 mm*, *at least 500 cm²*. They are checked at scrutineering by a
person with a tape measure, which used to mean they sat on a checklist here and
nothing more.

That was a missed opportunity. A rule with a number in it is a number the team
has to commit to **before** the tape measure comes out. The `cockpit` section
of `params/volare_params.json` records the intended value for each one, and the
compliance module compares it against the limit and reports the margin.

This turns "verify at inspection" into "we intend 40 mm against a 30–50 mm
window, and here are the four items with less than 5% margin". It is not
evidence — it is a design the team has written down and can be held to. When a
value is measured on the boat its tag changes from `DESIGN_CHOICE` to
`MEASURED` and the same check becomes evidence.

The comparison helpers are deliberately three, not one:

| | |
|---|---|
| `addMin` | at-least rules; flags anything with under 5% margin |
| `addMax` | at-most rules |
| `addExact` | rules stating a **value**, like the 90 mm yellow circle — meeting it exactly is compliance, not a thin margin, so it does not nag |

Getting the direction backwards is the one mistake in a compliance checker that
really matters: a reversed comparison reports PASS on a boat that fails. Taking
the value, the limit and the direction once, in a helper, is how that is
avoided.

---

## The two rules that reshaped this design

### ENERGY_REQ_188 — motor nominal power ≤ 25 kW

> *"The total nominal power consumption of the motor(s) shall not exceed 25 kW."*

New for 2026 (see the change history on page 5 of the rules).

**The Competr outboard is rated 26.9 kW nominal and 42 kW peak. As delivered it
does not comply.** The hardware is 1.9 kW over the limit on its nominal rating
alone.

The fix is a hard cap in the inverter configuration, and it is enforced
throughout this model rather than merely flagged:

| Where | What it does |
|---|---|
| `P50B_MotorData` | `ConfiguredPowerLimit_W = 25 kW` |
| `P50B_DrivetrainModel` | Bisects on shaft power so motor electrical input never exceeds the cap; reports `PowerLimit.Active` |
| `P50B_InverterData` | All current sizing derives from 25 kW, not 42 kW |
| `P50B_MissionProfile` | Shaft-power cap derived from the 25 kW electrical limit |
| `P50B_Busbars` | Operating points rebased on the cap; 42 kW retained only as a fault case |
| `TEST_ALL` | Asserts a 60 kW demand is capped, not delivered |

**Read carefully: the cap is on electrical power *consumed*, not shaft power.**
Setting a 25 kW cap at the propeller shaft would demand about 26.9 kW of motor
input and break the rule. The model applies it at the motor's electrical
terminals, which is the stricter and correct reading.

With the cap active, a 25 kW shaft request yields **23.1 kW at the shaft** and
exactly 25.0 kW of motor input.

**Still to do:** compliance depends entirely on the derate. Get a written
statement from Competr confirming the unit can be limited to 25 kW nominal, and
be able to show the setting in the inverter configuration at scrutineering.

#### A side benefit

Capping at 25 kW roughly halves the inverter the drivetrain needs:

| Sized against | Device current rating required |
|---|---|
| 42 kW hardware peak | 725 A |
| 25 kW rule cap | **418 A** |

That is a materially cheaper, smaller and cooler inverter.

---

### ENERGY_REQ_7 — stored energy under 10 kWh

> *"At any moment, the maximum energy stored by a boat shall remain under 10 kWh."*

The rule prescribes the calculation exactly, with a battery energy factor of 1.0:

```
quantity of cells × cell nominal voltage × cell nominal capacity
      546         ×        3.6 V         ×        5.0 Ah        = 9828 Wh
```

| | |
|---|---|
| Stored energy | **9828 Wh** |
| Limit | 10 000 Wh |
| Margin | **172 Wh — 1.72%** |
| Maximum cells this rule permits | **555** |

**COMPLIANT, but with almost no margin.** You have 9 cells of headroom against a
546-cell pack.

Two things to be careful about:

1. **Nominal values only.** The rule says explicitly *"Only nominal/typical values
   will be considered (not minimal / maximal)"*, so the 5.0 Ah typical applies,
   not the 4.85 Ah datasheet minimum. That works in your favour here.

2. **The rule text says "cell nominal current"** where it can only mean capacity
   in Ah — that is the sole reading that yields an energy. If the Technical
   Committee interprets it differently, the number changes. Worth confirming at
   registration, given how thin the margin is.

The calculation must be submitted to the Technical Committee before the event.

---

## Rules that pass

| Requirement | Result |
|---|---|
| ENERGY_REQ_7 | 9828 Wh of 10 000 Wh |
| ENERGY_REQ_23 — cells within datasheet ratings | 17.9 A/cell at the bus maximum, against a 60 A rating — 30% utilisation |
| ENERGY_REQ_57 — wire gauge | 150 mm² cable, 459 A derated, against 385 A worst legal draw |
| ENERGY_REQ_59 — protection coordination | 400 A fuse below both the 450 A busbar and 459 A cable |
| ENERGY_REQ_93 — exposed parts below 60 °C | Highest modelled steady cell temperature **35 °C** (was 54 °C — see below) |
| ENERGY_REQ_154 — steering ≥40° each side | Competr ±40° — *exactly at the limit, no margin* |

### How ENERGY_REQ_59 drove the whole HV path

> *"The continuous current rating of the overcurrent protection shall not be
> greater than the continuous current rating of any electrical component."*

This is easy to get backwards. The instinct is to size the fuse *above* peak
load; the rule sizes it *below* the weakest conductor. Both must hold at once,
which pins the design:

```
385 A worst legal draw  <  400 A fuse  ≤  450 A busbar  ≤  459 A cable
```

Getting there required three changes from the original design:

| Component | Was | Now | Why |
|---|---|---|---|
| HV cable | 70 mm² (214 A derated) | **150 mm²** (459 A) | 70 mm² could not carry the current at all |
| Series busbar | 20 × 2 mm (40 mm²) | **30 × 3 mm** (90 mm²) | Sized against 267 A, not the real worst case |
| Collector rail | 6 × 1.5 mm (9 mm²) | **8 × 1.5 mm** (12 mm²) | Became the binding constraint once the links were fixed |
| Fuse | 500 A | **400 A** | 500 A violated REQ_59 against every conductor |

Note the sizing driver is **25 kW at the 65 V minimum bus = 385 A**, not 25 kW at
nominal voltage. The cap fixes power, so current is highest when the pack is
nearly empty.

### Why ENERGY_REQ_93 moved from 54 °C to 35 °C

Not because the design changed. Because the model was cooling the wrong pack.

`P50B_ThermalDesign` carried a hard-coded 5.0 K/W cell-to-coolant resistance,
with a comment describing conduction *"through holder and TIM"* from the bottom
of the cell. That is an accurate description of the flat, side-cooled layout
this project started with and then abandoned. The pack is cooled on the cell
**ends** now, both of them, through three cold plates, and the resolved value
is **0.909 K/W** — the figure the README had been quoting all along.

The mission integrator drove cell temperature through the stale number, so
every MATLAB temperature rise was about 5.5× too pessimistic. Python had the
right value; nothing compared them.

`tools/crosscheck.py` compares it now.

### Rules the boat model settled

ENERGY_REQ_37 and ENERGY_REQ_32 used to be checklist items, because MATLAB had
no boat in it. It has one now.

| Requirement | Result |
|---|---|
| **ENERGY_REQ_37** — at least 3 knots | 403 W at the shaft, **1.8%** of the ceiling. Top speed 22.1 knots. |
| **ENERGY_REQ_32** — forward and reverse | 612 N astern against 33 N of resistance at 2 knots, **18× margin** |

The Technical Committee still judges manoeuvrability by watching the boat at
the sea certification test. But a design that cannot make three knots on paper
will not make them on the water either, and finding that out in Monaco is
expensive.

See [`HYDRODYNAMICS.md`](HYDRODYNAMICS.md).

---

## Items needing action

These are not design faults. They are gates that must be cleared.

| Requirement | Action |
|---|---|
| **ENERGY_REQ_187** | Pack reaches 109.2 V at full charge. Any system above 100 V needs **Technical Committee approval during registration**. Without it the boat cannot race. |
| **ENERGY_REQ_191** | Everyone working on the pack needs a **high voltage training certificate**. Checked at technical inspection. |
| **ENERGY_REQ_188** | Obtain Competr's written confirmation of the 25 kW derate. |
| **ENERGY_REQ_68** | Set the BMS temperature warning to **63 °C** (90% of the 70 °C cell maximum). |
| **ENERGY_REQ_67** | Confirm the BMS temperature channel reaches the pilot display, including the telemetry battery. |
| **ENERGY_REQ_182** | Add a **3.2 mm pass-through** so the organiser's sensor can reach the cells at the pack core. The three empty slots in the 4×4 grid give a natural route. |
| **ENERGY_REQ_58** | Confirm the physical fuse sits immediately after the pack terminals, and that the telemetry battery has one too. |

### Mass — ENERGY_REQ_48 and ENERGY_REQ_135

> *"The overall weight excluding the hulls shall not exceed 250 kg."*
> *"The boat will be weighted with the hulls and the pilot. The hulls are
> supposed to be 65 ± 1 kg."*

So the test on the day is `(scales, hulls and pilot included) − 65 ≤ 250`, and
**the pilot counts against the 250**. That is easy to get wrong in the
optimistic direction, because "excluding the hulls" reads like an invitation to
exclude the pilot too. It is not.

`P50B_MassBudget` builds it line by line:

| Item | kg | Source |
|---|---|---|
| Pilot, ready to sail | 80.0 | assumption |
| Battery pack | 51.6 | model |
| Cockpit structure | 32.0 | allowance |
| Outboard | 25.0 | datasheet |
| Trim assembly | 10.0 | datasheet |
| Cooling system | 7.0 | allowance |
| Inverter / ESC | 6.5 | allowance |
| Steering and controls | 6.0 | allowance |
| Safety equipment | 6.0 | allowance |
| Contingency | 6.0 | reserve |
| Seat | 4.5 | allowance |
| HV harness and switchgear | 4.0 | allowance |
| LV system | 3.5 | allowance |
| Beam clamps and fasteners | 3.0 | allowance |
| Organiser equipment | 2.5 | allowance |
| **Excluding hulls** | **247.6** | limit 250 |
| **Margin** | **2.4 kg (1.0%)** | |

The scales will read **312.6 kg** with the 65 kg of hulls.

**This is the second tightest constraint in the project after stored energy,
and unlike stored energy it is made of two dozen estimates rather than one
exact calculation.** 30% of the budget is allowances rather than weighed parts.
An overweight boat is not allowed in the water at all.

> **Action:** put the pack, the cockpit shell and the outboard on a scale as
> soon as each exists.

ENERGY_REQ_135 requires the pilot at 60 kg minimum ready to sail — with
overalls, helmet, lifejacket, shoes and communications. At 80 kg no ballast is
needed, but every kilogram a lighter pilot is under 60 becomes ballast that
also counts against the 250. Size it on the **lightest** pilot entered, as the
rule says. Run `P50B_MassBudget("PilotMass_kg", 58)` to see the effect.

The same figure is the boat's **floating mass**, which is what the
hydrodynamics needs. `boat.displacement_kg` was 250 kg — the rule's limit,
mistaken for the displacement, in both codebases independently.

---

## Telemetry — Annex III and Annex IV

The organiser requires a REST/JSON feed of pack temperatures, voltage, current
and position, and a 10–28 V / 30 W supply on a specified Amphenol LTW connector
to power their monitoring device.

Annex III says the API *"will be confirmed in February 2026"* and gives an
example payload. That example is treated as the contract until the final one is
published, so confirming it should be a one-line change rather than a rewrite.

Mission Control's **Compliance** tab builds the payload live from the running
boat, so the format can be checked against the organiser's endpoint before the
event rather than in the paddock. The three temperature channels carry hottest
cell, coldest cell and coolant outlet — the spread, not only the peak, because
a single maximum says the pack is fine right up until it is not.

> One thing to know before anyone "fixes" it: the Annex III example puts `lat`
> at 7.44 and `lon` at 43.74, which is Monaco with the two fields swapped. The
> payload follows the **example**, not the convention, because the organiser's
> parser is what has to accept it.

---

## Physical and procedural checklist

Twenty-four requirements cannot be evaluated from a model at all — bulkhead
fire rating, kill-cord behaviour, sharp edges, whether a component is actually
fixed down. `P50B_MonacoCompliance` lists them so they are not quietly
forgotten. Highlights for the pack in particular:

- **ENERGY_REQ_25** — energy container at least 500 mm from the pilot (relaxed
  from 1 m for 2026)
- **ENERGY_REQ_155** — container overpressure valve, certified and adequately
  sized, oriented aft
- **ENERGY_REQ_56** — fire extinguisher port on the **port** side of the container
- **ENERGY_REQ_189** — external charging interface so the battery can be recharged
  **without opening the container** (new for 2026)
- **ENERGY_REQ_61** — all wiring outside the enclosure orange
- **ENERGY_REQ_60** — no live part touchable with a 100 mm long, 6 mm probe
- **ENERGY_REQ_62** — electronics in an IP56 watertight, cooled compartment
- **ENERGY_REQ_55** — cable pass-throughs fitted with grommets
- **ENERGY_REQ_50/52** — bulkhead isolates the pilot and contains an explosion
- **ENERGY_REQ_181** — ESC input power wired for the organiser's sensing device

The following used to be on this list and are now **computed against a declared
intent**, with their margins reported: REQ_25, 38, 44, 45, 46, 47, 49, 51, 63,
71, 76, 77, 78, 79, 85, 96, 99, 101, 102, 103, 106, 137, 141, 142, 150, 151,
171, 172, 173, 174, 175, 182, 184, 185, 186.

Four of them have under 5% margin and are flagged for action: the four
high-visibility tape areas, the 1 kg fire extinguisher, and the two-clamps-per-beam
count. All are cheap to increase and none needs a design change.

---

## What a pass here does and does not mean

`P50B_MonacoCompliance` returning zero violations means **the rules this model
can evaluate are satisfied**. It is not a statement that the boat is compliant.

There are three tiers of confidence in the 94 checks, and they are not
interchangeable:

| Tier | Count | What a PASS means |
|---|---|---|
| **Computed** | ~35 | Derived from the model. Stored energy, currents, temperatures, speed, mass. As good as the model. |
| **Declared** | ~35 | Compared against a value the team wrote down. Says the *design* complies, not the boat. |
| **Checklist** | 24 | Not evaluated at all. Listed so it is not forgotten. |

A declared check passing is worth something — it means somebody chose a number
and it clears the rule — but it is not the same as a measurement. Replace the
`DESIGN_CHOICE` tags with `MEASURED` ones as the boat gets built, and the same
94 checks become progressively more like evidence.

Roughly a quarter of the technical rules are settled at scrutineering, not in
MATLAB, and the Technical Committee is the authority on all of them.
