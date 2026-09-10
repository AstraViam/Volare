# Interconnect design

Everything between a cell terminal and the pack terminal: welds, collector rails,
manifolds and series links.

Model: `03_mechanical/P50B_Busbars.m`
Sizing study: `05_tests/Test_BusbarSizing.m`

---

## Result

| | |
|---|---|
| Total interconnect resistance | **1.538 mΩ** |
| Copper mass | 6.21 kg |
| Voltage drop at 385 A | 0.59 V (0.63% of nominal) |
| Loss at 385 A | 228 W |

### Where the resistance is

| Contributor | Resistance | Share |
|---|---|---|
| Series links (25) | 0.94 mΩ | **61%** |
| Collector rails + manifolds | 0.34 mΩ | 22% |
| Cell-to-busbar joints (1092) | 0.25 mΩ | 16% |

---

## Three resistances in series, not one

The previous model computed collector rail resistance only. That understated the
total by roughly a factor of two, because it omitted the two contributors that
sit either side of it.

### 1. Cell-to-busbar joints — the commonly forgotten one

Every cell connects to its collector through a joint at each end. With 546 cells
that is **1092 joints and 2184 welds**, and each one is in series with a cell.

```
R_per_cell  = jointsPerCell × (R_weld / weldsPerJoint)
R_per_group = R_per_cell / 21          (cells are in parallel)
R_total     = R_per_group × 26
```

At an assumed 0.2 mΩ per weld this comes to 0.25 mΩ — **16% of the total, and
comparable to the collector rails themselves**. It is the term most often left
out of first-pass models, which is why those models come out optimistic.

It is also the cheapest thing on this page to measure: a four-wire measurement
across one welded joint on a scrap cell would move it from `ASSUMPTION` to
`MEASURED`.

### 2. Collector rails — centre-fed, so not simply I²R

Each row of 7 cells feeds a rail that is collected at the centre. Segments nearer
the centre carry more current, so the loss is not the group current squared times
the rail resistance.

Numbering columns outward from the centre, each half carries 3i, 2i, i, giving a
loss coefficient of

```
2 × (3² + 2² + 1²) = 28
```

in units of i²·R_segment. The model computes this coefficient from the group
shape rather than hard-coding 28, so it stays correct if the group is ever
reshaped.

The equivalent resistance referred to group current is exact for a linear
network, not an approximation:

```
R_eq = Q_total / I_group²
```

### 3. Manifold

Three row rails feed a terminal at the centre row. The outer two rows carry their
full current one row pitch to reach it. Modelled with its own wider section
(12 × 1.5 mm) because it carries more than a row rail does.

---

## Copper at temperature, not at 20 °C

Resistivity is evaluated at **60 °C**, the assumed busbar operating temperature:

```
ρ(T) = ρ₂₀ × (1 + 3.93e-3 × (T − 20))
```

That is **15.7% more resistance** than the handbook 20 °C value. Busbars in a
sealed pack run hotter than people expect, and using the cold value quietly
flatters every loss number downstream.

---

## Ampacity is the constraint that actually rules options out

Resistance is only half of sizing. A conductor also has to survive the current
thermally. The model applies two limits:

| Duty | Limit | Rationale |
|---|---|---|
| Continuous | 5.0 A/mm² | Sustained current in still air with limited convection |
| Peak | 8.0 A/mm² | Momentary; needs a demonstrated short duty cycle |

These are engineering rules of thumb, not standards, and they are recorded as
such.

### The sizing driver is not what you would guess

The Monaco rules cap motor power at 25 kW. Power is fixed, so **current is highest
when the pack is nearly empty**:

```
25 kW ÷ 65 V minimum bus = 385 A
```

Not 25 kW ÷ 93.6 V = 267 A. Sizing against the nominal-voltage figure understates
the requirement by 44%, and that is exactly what the original design did.

### Operating points

| Case | Duty | Current | Loss | Links | Rails | OK |
|---|---|---|---|---|---|---|
| Monaco cap, nominal V | Continuous | 267 A | 110 W | 3.0 | 3.2 A/mm² | ✓ |
| **Monaco cap, minimum V** | Continuous | **385 A** | 228 W | 4.3 | 4.6 A/mm² | ✓ |
| Competr hardware continuous | Continuous | 375 A | 216 W | 4.2 | 4.5 A/mm² | ✓ |
| FAULT: cap failure at 42 kW | Peak | 646 A | 642 W | 7.2 | 7.7 A/mm² | ✓ |

The last row is not an operating point — the inverter is hard-capped at 25 kW.
It is retained to confirm the interconnect survives long enough for the fuse to
clear if the cap ever fails.

---

## What changed, and why

| Component | Was | Now | Reason |
|---|---|---|---|
| Series link | 20 × 2 mm (40 mm²) | **30 × 3 mm (90 mm²)** | 40 mm² ran at 9.4 A/mm² at the real worst case |
| Collector rail | 6 × 1.5 mm (9 mm²) | **8 × 1.5 mm (12 mm²)** | Became the binding constraint once the links were fixed |

The rail change is worth noting: fixing the series links exposed the rails as the
next limit. The rail segment beside the centre feed carries three cells' worth of
current — 55 A at the worst legal case — which needs 11 mm² at 5 A/mm². 9 mm²
was not enough.

Both are `DESIGN_CHOICE` parameters in `P50B_Geometry`, so they can be revisited.

---

## Routing factor

Straight-line centre-to-centre distance understates a real busbar, which must
clear cell tops and include bend radii. A **1.15 routing factor** is applied to
every series link length. It is an assumption and it moves the total resistance
proportionally — worth replacing with routed lengths once the busbar is drawn.

---

## What is not modelled

- **Skin and proximity effect.** Irrelevant at DC, but the ripple current from a
  10 kHz inverter is not DC. Second-order at these sections.
- **Busbar self-heating feedback.** Conductor temperature is an input, not a
  solved state. At 228 W spread over 6.2 kg of copper the steady rise is modest,
  but a proper thermal solve would close the loop.
- **Current sharing between the 21 parallel cells.** The model treats a group as
  a lumped equivalent. In reality cells at the ends of a row see slightly more
  resistance than those at the centre, so they share slightly less current. This
  is the main reason `ModelResolution="Detailed"` is kept on the Simscape
  parallel assembly.
- **Fuse element resistance rise.** Modelled as a cold value; it climbs
  substantially as the element heats.

---

## Sizing study

`Test_BusbarSizing` sweeps width and thickness against the real link lengths from
the layout — not a placeholder length — evaluates every operating point, and
reports which geometries satisfy loss, voltage drop and current density together.
It then names the lightest acceptable option.

It also prints the comparison that matters: what a geometry sized against 25 kW
at *nominal* voltage looks like when the pack is actually empty.
