# Data provenance

Which numbers in this model are real, which are estimates, and how to replace
the estimates.

Run `P50B_ProvenanceReport` for the live version of this, generated from the
code itself. This document explains the reasoning behind the tags and gives the
measurement procedure for each gap.

---

## Why this exists

A model that mixes datasheet values with invented ones, without distinguishing
them, produces results that look equally authoritative regardless of whether
they mean anything. The previous revision of this project had a cell resistance
of `0.012` and a thermal resistance of `1.0` with `% Placeholder ONLY` beside
them — honest in the source, invisible in the output.

Every parameter now carries a source tag, and the report prints a warning block
for anything unverified.

---

## Source tags

| Tag | Confidence | Meaning |
|---|---|---|
| `MEASURED` | 1 | Measured in-house on this project's hardware |
| `DATASHEET` | 2 | Direct from a manufacturer datasheet in `04_data/` |
| `PUBLISHED_TEST` | 3 | Third-party published characterisation |
| `CALCULATED` | 4 | Derived from other parameters in this project |
| `DESIGN_CHOICE` | 5 | A value the team selected, not a physical constant |
| `ASSUMPTION` | 6 | Engineering estimate, defensible but unverified |
| `PLACEHOLDER` | 7 | Invented to let the model run — **not quotable** |

`TEST_ALL` fails if any `PLACEHOLDER` parameter exists.

---

## What is solid

### Cell — Molicel INR-21700-P50B

All from the manufacturer datasheet:

| Parameter | Value |
|---|---|
| Typical capacity | 5.0 Ah |
| Minimum capacity | 4.85 Ah |
| Nominal voltage | 3.6 V |
| Charge voltage | 4.2 V |
| Discharge cut-off | 2.5 V |
| Max continuous discharge | 60 A (12 C, to a 70 °C cut-off) |
| Max charge current | 25 A (5 C) |
| AC impedance at 1 kHz | 6.5 mΩ |
| DC internal resistance | 12.8 mΩ |
| Nominal energy | 18 Wh |
| Envelope | 21.55 mm × 70.15 mm |

**A warning about the two impedance figures.** The 6.5 mΩ AC value is a
production screening measurement. It is roughly half the DC value and it must
never be used for loss or thermal work — doing so halves your predicted heat.
The model records both specifically so the wrong one cannot be picked up by
accident.

### Drivetrain — Competr outboard

All from `New_Datasheet Competr_0625.pdf`:

| Parameter | Value |
|---|---|
| Nominal power | 26.9 kW (40 HP) |
| Maximum power | 42 kW |
| Maximum torque | 100 Nm |
| Motor type | Axial-flux PMSM, water cooled |
| Mass | 25 kg (outboard), +10 kg trim assembly |
| Battery configuration | 26S |
| Bus nominal / maximum | 96 V / 109 V |
| Maximum continuous current | 375 A |
| Aux DC/DC | 12 V, 1 kW |
| Trim / steering pump drivers | H-bridge, 12 V, 40 A each |
| Bilge / cooling pump drivers | Low side, 12 V, 15 A each |
| Position sensor | SSI absolute encoder |
| Motor temperature sensor | Analog PTC |
| Trim range | −5° to +30° |
| Steering range | −40° to +40° |

---

## What needs measuring

Ordered by how much the result depends on it.

### 1. Inverter — not selected at all

The Competr datasheet section 5 lists the inverter as *"On request"* with the
note *"Higher current rating required to reach full output power"*.

Every inverter loss number in this model is against a representative 650 V SiC
module, not a real part. `P50B_InverterData` derives what the real part must
satisfy:

| Requirement | Value | Driven by |
|---|---|---|
| Blocking voltage | ≥147 V | 109 V bus × 1.35 overshoot |
| DC current, nominal bus | 267 A | 25 kW cap ÷ 93.6 V |
| DC current, worst case | 385 A | 25 kW cap ÷ 65 V minimum bus |
| Device current rating | ≥418 A | peak phase current × 1.25 margin |

All of these follow from the **25 kW Monaco cap**, not from the outboard's 42 kW
hardware peak, which is not a permitted operating point. Sizing against 42 kW
instead would demand a 725 A device.

**To replace:** select a device and substitute its `Rds_on`, `Eon`, `Eoff`,
`Erec`, reference test conditions and thermal resistances.

### 2. Motor electrical parameters

Not in the datasheet. Currently `ASSUMPTION`:

- Pole pairs (10)
- Ld (85 µH), Lq (95 µH)
- Rated peak phase current (400 A)
- Iron loss, windage and constant-loss coefficients
- Peak efficiency (95.5%)
- Gearbox ratio (2.0) and efficiency (97%)
- Maximum speed (4000 rpm)

Flux linkage and phase resistance are both *back-calculated* rather than assumed
independently:

- **Flux linkage** from the 100 Nm torque rating via `T = 1.5·p·λ·Iq`, so torque,
  current and flux stay mutually consistent.
- **Phase resistance** (1.96 mΩ at 20 °C) from the peak-efficiency target, so the
  loss model actually reproduces the efficiency the data struct claims.

An earlier draft assumed 8 mΩ phase resistance *and* separately declared 95.5%
efficiency. The two contradicted each other — the loss model produced 89% — and
nothing caught it. The assumption is now the efficiency, which is the honest
place for it.

Both inherit the uncertainty of the pole-pair and rated-current assumptions.

**To replace:** ask Competr for pole pairs, Ld, Lq, permanent-magnet flux
linkage, phase resistance at 20 °C, gearbox ratio, and an efficiency map. This
single request would move most of the motor model to `DATASHEET`.

### 3. Cell OCV curve

One anchor point is real (4.2 V at 100% SOC). The rest is a representative NMC
21700 shape, tagged `ASSUMPTION`.

**To replace:** run a C/20 or slower discharge, or a GITT pulse-relaxation
sequence. Write:

```
04_data/P50B_OCV_SOC.csv
```

with columns `SOC` (0 to 1) and `OCV_V`, strictly increasing in both. The model
loads it automatically and reports the source as `MEASURED`. No code change.

The curve must be monotonic — `P50B_OCV` asserts this, because a non-monotonic
OCV makes the inverse SOC(OCV) map ill-posed and produces silent nonsense.

### 4. Cell DCIR surface

Anchored at the datasheet 12.8 mΩ (50% SOC, 25 °C). Variation around that anchor
uses typical NMC multipliers:

| Temperature | Multiplier vs 25 °C |
|---|---|
| −10 °C | 3.00 |
| 0 °C | 2.10 |
| 10 °C | 1.45 |
| 25 °C | 1.00 |
| 40 °C | 0.82 |
| 55 °C | 0.75 |

| SOC | Multiplier vs 50% |
|---|---|
| 5% | 1.55 |
| 10% | 1.32 |
| 20% | 1.12 |
| 50% | 1.00 |
| 90% | 1.02 |
| 100% | 1.08 |

Independent bench testing has reported P50B units at or below 19 mΩ, which is
consistent with this surface at the cold and low-SOC corners.

**To replace:** run an HPPC pulse sequence across SOC and temperature. Write:

```
04_data/P50B_DCIR_SOC_T.csv
```

with columns `SOC`, `Temp_C`, `DCIR_Ohm` on a full rectangular grid. The model
asserts the grid is complete — gaps are rejected rather than interpolated over.

### 5. Cell-to-coolant thermal resistance

Assumed **5.0 K/W per cell**. Published values for bottom-cooled 21700 cells
through a holder and thermal interface range from 3 to 8 K/W. That factor of
2.7 propagates directly into every steady-state temperature in the model.

**To replace:** build a prototype module, apply a known current, measure cell
surface temperature and coolant inlet/outlet, and solve for the resistance.

### 6. Weld resistance

Assumed **0.2 mΩ per weld**, 2 welds per joint, 2 joints per cell.

This matters more than it looks: there are **1092 joints and 2184 welds** in the
pack, and they contribute a large share of total interconnect resistance —
comparable to the collector rails themselves. It is the term most often omitted
from first-pass models, which is why those models are optimistic.

**To replace:** four-wire measurement across a sample welded joint on a scrap
cell. Cheap and quick, high value.

### 7. Cell mass

Datasheet-class, but published values range 68–71 g. Across 546 cells that
3 g spread is 1.6 kg — significant for a boat.

**To replace:** weigh a sample lot.

### 8. Cell temperature limits

The summary datasheet available to this project does not state the operating
temperature window numerically, so −20/+60 °C discharge and 0/+45 °C charge are
recorded as `ASSUMPTION` from typical high-power NMC practice. The 70 °C cut-off
associated with the 60 A rating **is** from the datasheet.

**To replace:** confirm against the controlled datasheet before any design
review.

---

## Design choices, not measurements

These are decisions, recorded so they can be revisited:

| Parameter | Value | Rationale |
|---|---|---|
| Cell-to-cell clearance | 2.0 mm | Holder wall + thermal isolation vs density |
| Group-to-group clearance | 12 mm | Must insulate series links at pack potential |
| Layer gap | 10 mm | Inter-layer cooling plate |
| Busbar rail | 8 × 1.5 mm | Carries 3 cells' worth at the centre feed |
| Series link | 30 × 3 mm | Sized for 385 A at 5 A/mm² |
| HV cable | 150 mm² | 459 A derated, against 385 A worst legal draw |
| Fuse | 400 A | Below busbar (450 A) and cable (459 A) per ENERGY_REQ_59 |
| Motor power cap | 25 kW | Monaco ENERGY_REQ_188, enforced in the model |
| Switching frequency | 10 kHz | Ripple and noise vs switching loss |
| Design cell temperature | 45 °C | Cycle life target, not a safety limit |
| Usable SOC window | 10–95% | Life at the top, reserve at the bottom |

---

## Adding your own measured data

1. Drop the CSV into `04_data/` with the exact filename above.
2. Re-run `TEST_ALL`.
3. Run `P50B_ProvenanceReport` and confirm the tag flipped to `MEASURED`.

No code changes are needed. The loader functions check for the file first and
fall back to the estimate only if it is absent.
