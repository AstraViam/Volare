# Drivetrain

Motor, inverter, harness and auxiliary loads, and how the chain is solved.

Source: Competr technical datasheet `New_Datasheet Competr_0625.pdf`, held in
`04_data/`.

---

## The outboard

| | |
|---|---|
| Type | Axial-flux PMSM, water cooled |
| Propeller | Counter-rotating, tractive |
| Nominal power | 26.9 kW (40 HP) |
| Maximum power | 42 kW |
| Maximum torque | 100 Nm |
| Mass | 25 kg + 10 kg trim assembly |
| Dimensions | 300 × 210 × 800 mm |
| Shaft length | 500 mm |
| **Battery configuration** | **26S** |
| Bus nominal / maximum | 96 V / 109 V |
| Maximum continuous current | 375 A |
| Position sensor | SSI absolute encoder |
| Motor temperature sensor | Analog PTC |
| Trim / steering | ±30° / ±40°, hydraulic electroactuated |

### The pack is the right series count

The datasheet specifies 26S, and its 109 V maximum is exactly 26 × 4.2 V. The
P50B 26S21P is a correct match.

Two differences from the Competr stock pack are worth stating plainly:

| | Competr stock | This pack |
|---|---|---|
| Energy | 26 kWh | **9.83 kWh** (38%) |
| Nominal voltage | 96 V (≈3.69 V/cell) | 93.6 V (3.6 V/cell) |

The energy difference is an **endurance limit, not a capability limit**. The
2.5% lower bus voltage raises current slightly for the same power.

### Current is not the constraint

| | |
|---|---|
| 21P group capability | 21 × 60 A = **1260 A** |
| Outboard continuous | 375 A |
| Worst legal draw (25 kW at 65 V) | 385 A |
| **Margin** | **3.3×** |

At the 25 kW cap the cells run at 12.7–18.3 A each, 2.5–3.7 C, against a 60 A
(12 C) rating. **The cells are the least stressed part of this drivetrain.** The
constraints are energy, the interconnect, and the thermal path.

---

## The 25 kW cap

Monaco ENERGY_REQ_188 limits motor nominal power consumption to 25 kW. The
Competr hardware is 26.9 kW nominal, so a derate is mandatory. See
`COMPLIANCE.md` for the full treatment.

Enforced in `P50B_DrivetrainModel` by bisection on shaft power, applied at the
**motor's electrical terminals** — not the shaft, which would be too permissive.

| Request | Delivered shaft | Motor input | Capped |
|---|---|---|---|
| 20 kW | 20.0 kW | 21.6 kW | – |
| 23 kW | 23.0 kW | 24.8 kW | – |
| 25 kW | **23.1 kW** | **25.0 kW** | YES |
| 30 kW | 23.1 kW | 25.0 kW | YES |

---

## Motor loss model

Loss is split into the three physical mechanisms so each scales correctly with
operating point, rather than applying one flat efficiency:

| Mechanism | Scaling | At rated |
|---|---|---|
| Copper | I² | 620 W |
| Iron (hysteresis + eddy) | f and f² | 584 W |
| Windage | n³ | ~4 W |
| Bearing and seal | constant | 60 W |

### Phase resistance is derived, not assumed

This is worth explaining because it is a trap the first version of this model
fell into.

The datasheet gives no electrical machine parameters. An earlier draft assumed
8 mΩ phase resistance *and separately declared* 95.5% peak efficiency. Those two
numbers contradicted each other: the loss model actually produced 89%, while the
data struct claimed 95.5%. Nothing caught it, and the whole chain efficiency read
78.9%.

Phase resistance is now **back-solved** from the efficiency target so the loss
model reproduces it:

```
P_loss_budget = P_nominal × (1/η − 1)
P_copper      = budget − iron − windage − constant
R_phase(hot)  = P_copper / (3 · I_rms²)
```

giving **1.96 mΩ at 20 °C**, which is a sensible figure for a machine carrying
283 A RMS. The function errors out rather than returning a negative resistance if
the speed-dependent losses ever exceed the budget.

Flux linkage is treated the same way — back-calculated from the 100 Nm torque
rating via `T = 1.5·p·λ·Iq` — so torque, current and flux stay mutually
consistent instead of being three independent guesses.

**The assumption is now the efficiency, and it is tagged as such.** That is the
honest place for it.

### What to ask Competr for

Five numbers would move most of the motor model from estimate to measurement:

1. Pole pairs
2. Ld and Lq
3. Permanent-magnet flux linkage
4. Phase resistance at 20 °C
5. An efficiency map

Plus the gearbox ratio, which is currently assumed at 2.0.

---

## Inverter

**Not selected.** The Competr datasheet lists it as *"On request"*, noting only
that a higher current rating is needed to reach full output power. That note is
the single most consequential open item in the drivetrain, so
`P50B_InverterData` treats selection as a sizing problem.

### Requirements the chosen device must meet

| Requirement | Value | Driven by |
|---|---|---|
| Blocking voltage | ≥147 V | 109 V bus × 1.35 overshoot |
| DC current, nominal bus | 267 A | 25 kW ÷ 93.6 V |
| **DC current, worst case** | **385 A** | 25 kW ÷ 65 V minimum bus |
| Phase current RMS | 236 A | at the cap |
| **Device current rating** | **≥418 A** | peak phase × 1.25 margin |
| DC-link ripple current | 118 A RMS | ~0.5 × phase RMS |

Sizing against the 42 kW hardware peak instead would demand a **725 A** device.
The rules cap is worth 1.7× on the inverter.

### Loss model

Conduction is modelled as threshold plus resistance, `V_on(I) = Vce0 + R·I`, with
`Vce0 = 0` for a MOSFET channel. Switching energies scale linearly from their
datasheet reference conditions:

```
P_sw = 6 · f_sw · (Eon + Eoff + Erec) · (Vdc/Vref) · (Ipk/π)/Iref
```

At a 93.6 V bus against a 400 V reference, switching loss scales down by ~4.3×.
**A low-voltage traction drive is conduction-dominated, not switching-dominated**,
which is why SiC is assumed: on-resistance matters far more than switching energy
here.

On-resistance is taken **hot** (×1.6 at 125 °C junction). SiC on-resistance rises
steeply with temperature, and the cold value would understate loss by around 60%.

### Sensor interface constrains selection

The chosen inverter must speak **SSI** to the Competr encoder and read an **analog
PTC**, or an interface board is required. Recorded in `P50B_InverterData` so it is
not discovered late.

---

## Harness

Everything between the pack terminals and the inverter is series resistance in
the same circuit. Leaving it out makes the pack look better than the vehicle is.

| Element | Value |
|---|---|
| Cable | 150 mm², 2 × 1.2 m, tinned flexible copper |
| Cable resistance (hot, with stranding derate) | 0.41 mΩ |
| Fuse | 400 A, 0.15 mΩ |
| Contactor | 0.20 mΩ |
| 6 bolted joints | 0.12 mΩ |
| 2 mated connectors | 0.10 mΩ |
| **Total** | **0.91 mΩ** |

At 385 A that is 135 W and 0.35 V.

Bolted joints are assumed clean, correctly torqued and anti-oxidant treated. **A
loose or corroded joint can be 10–50× the modelled value and is a fire risk, not
just a loss.**

Cable ampacity is derated for bundling (×0.80) and engine-bay ambient (×0.85),
giving 459 A from a 4.5 A/mm² free-air base. Cross-check against ABYC E-11 or
ISO 13297 for the final build.

---

## Auxiliary loads

Everything on the 12 V bus comes from the traction pack through the Competr 1 kW
DC/DC. In an endurance run the propulsion load is intermittent; the auxiliary
load is not.

| Load | Power | Duty | Source |
|---|---|---|---|
| Control unit | 18 W | 100% | estimated |
| Cooling pump | 70 W | 85% | estimated |
| Instrumentation | 25 W | 100% | estimated |
| Bilge pump | 45 W | 5% | estimated |
| Steering actuator | 480 W peak | 8% | driver rating from datasheet |
| Trim actuator | 480 W peak | 1% | driver rating from datasheet |

| | |
|---|---|
| Duty-weighted average | 152 W |
| Referred to the pack (÷0.92 + standby) | **165 W** |
| Worst-case simultaneous | **1118 W** |

### A finding worth acting on

**Simultaneous trim and steering actuation exceeds the 1 kW DC/DC rating by
118 W.** Both drivers are rated 12 V / 40 A, and both firing together plus the
hotel load overruns the converter.

Either interlock them in control software, or size the 12 V battery to absorb the
overlap. It is flagged as a warning in `P50B_Verification`.

Over a one-hour run the auxiliary load costs 165 Wh — **1.7% of pack energy**,
drawn even while the boat sits on the start line.

---

## Chain efficiency

At 23 kW shaft, 60% SOC, 30 °C:

| Stage | Loss | Share |
|---|---|---|
| Cells (internal R) | 1263 W | 29% |
| Motor | 1226 W | 28% |
| Gearbox | 773 W | 18% |
| Inverter | 696 W | 16% |
| Auxiliary 12 V | 165 W | 4% |
| Busbars | 153 W | 4% |
| Harness | 78 W | 2% |

**Overall chain efficiency: 85.4%.**

The headline is that **the pack's own internal resistance is the single largest
loss** — larger than the motor. That is a direct consequence of a small pack
working hard: 9.83 kWh delivering 25 kW is a 2.5C draw, and 26 × 11 mΩ / 21 gives
14 mΩ of pack resistance carrying 270 A.

It also means DCIR is the highest-value cell measurement to make. See
`DATA_PROVENANCE.md`.
