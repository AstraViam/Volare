# Hydrodynamics

How the boat moves, what it costs, and what the two teams' models found when
they were held against each other.

Until this merge the MATLAB side of the project had no boat in it. Missions
were written as shaft-power time series and motor speed was inferred from a
cube law, so nothing in MATLAB could answer *how fast does it go*, *how far
does it get*, or ENERGY_REQ_37, *does it make three knots*. Those questions
lived only in the Python model, and a question that only one of two models can
answer is a question that nothing cross-checks.

---

## What the models are

| | |
|---|---|
| `09_hydro/P50B_HullModel` | Resistance vs speed. Supplied curve by default, parametric as fallback. |
| `09_hydro/P50B_Propulsor` | The contra-rotating pair, from the BEM design. **Default.** |
| `09_hydro/P50B_Propeller` | Single-screw KT/KQ stand-in. Kept for comparison. |
| `09_hydro/P50B_BoatDynamics` | `(m + m_a) dv/dt = T(1-t) - R`, with both power and torque ceilings. |
| `09_hydro/P50B_BoatPerformance` | Top speed, drag breakdown, range, and the rules that depend on speed. |
| `09_hydro/P50B_MatchPropeller` | Diameter, pitch and gear ratio sweep for the single-screw case. |
| `09_hydro/P50B_GearboxStudy` | What ratio lets the boat use the power the rule allows. |
| `09_hydro/P50B_ShaftPowerCeiling` | The shaft power the 25 kW **electrical** cap actually permits. |

`python/volare/boat.py` carries the same physics on the Python side, including
`SuppliedResistance`, and `tools/crosscheck.py` compares eleven hydrodynamic
quantities between them.

---

## Five findings

### 1. The resistance model was applying a planing term to a hull that does not plane

The hydrodynamics team supplied a measured resistance curve. It disagrees with
the parametric model the project had been using — inherited from
`python/volare/boat.py` — by between 30 % and 400 %.

```
   speed      supplied      parametric
    5 kn          89 N          ~470 N
   10 kn         212 N          ~640 N
   15 kn         381 N          ~720 N
   20 kn         624 N          ~815 N
```

The error is a Savitsky planing term contributing a flat 585 N above 20 km/h
that simply is not there. Each demihull is about 5 m by 0.45 m — an L/B near
11, a slender semi-displacement form whose resistance climbs smoothly with no
wave-making hump worth the name.

Top speed barely moved, because the two curves happen to cross near it. What
moved was everything below: **the endurance strategy's predicted lap count
roughly doubled**, from 14.2 laps to 29.7, because an endurance race is run in
the speed range where the old model was worst.

The supplied curve is now the default in both languages. It stops at 20 knots,
and above that the model takes the larger of a fitted power law and the
parametric estimate — erring towards more drag, which is the correct direction
to be wrong in for a boat whose event is decided by whether the energy lasts.

### 2. The boat was being modelled 65 kg light

`boat.displacement_kg` was 250 kg, which is the ENERGY_REQ_48 limit on
everything **excluding** the hulls. The hulls and beams are a further 65 kg and
they float too. Both codebases had independently taken the rule's number as the
boat's displacement.

Floating mass is now 315 kg, built up line by line in `P50B_MassBudget`.

The supplied resistance curve was measured at 250 kg and the hydrodynamics
team's own report says the heavier case has no data and cannot be considered
validated. `Hull.DisplacementExcess_kg` reports the gap rather than papering
over it.

### 3. The single-screw propeller was the wrong machine

The Competr datasheet says the outboard has a contra-rotating propeller.
`P50B_Propeller` modelled one screw with a Wageningen-like fit, which reaches
an open-water efficiency of **0.45** at the boat's top speed. The
contra-rotating pair the hydrodynamics team designed reaches **0.77**. Half the
propulsive loss in the old model was an artefact of modelling the wrong thing.

The BEM design is reproduced by `P50B_Propulsor` to within 0.5 N of its own
design thrust. It is *not* extended by scaling a KT/KQ correlation — at this
propulsor's advance ratio of 1.91 with a pitch ratio of 1.995 the generic KT
form is **negative**, and scaling a real number by a negative one produces a
curve that looks like physics and is not. Momentum theory anchored on the BEM
point is used instead.

### 4. The gearbox ratio costs a third of the legal power

This one needed both models to see.

The propulsor was optimised at 20 knots, where it needs 9.9 kW and the motor
runs at 1300 rev/min and 75.8 N·m — comfortable on a 100 N·m machine. Its
gearbox ratio of 1.6079 was chosen for that point.

At top speed the front rotor turns about 1065 rev/min, so through that ratio
the motor sees only 1712 rev/min. Delivering the 22.8 kW that ENERGY_REQ_188
permits at that speed would take **131 N·m**, which the motor does not have.
The boat is therefore torque limited and can use about two thirds of the power
it is allowed.

```
   ratio   top speed   shaft power   motor      binding
   1.608     41.0 km/h   15.2 kW     1496 rpm   torque
   2.000     46.3        21.2        2076       torque
   2.200     47.5        23.1        2352       power
   3.000     47.5        23.1        3207       power
```

**About 2.2:1 rather than 1.6079:1, worth roughly +16 % on top speed.** Past
the knee there is nothing left to win while motor speed keeps climbing toward a
limit nobody has confirmed.

The recommendation is robust to the open motor-speed question (finding 5):
2352 rev/min sits inside both circulating figures.

The hydrodynamics tool has the propulsor but optimises at 20 knots, where the
ratio is fine. The electrical model has the rule cap and the motor envelope but
had no propulsor. The constraint only appears when the two are evaluated
against each other.

> Changing the ratio moves the rotor speed the propulsor sees, so rerun the BEM
> tool at the new ratio before committing to a gearbox. This study says the
> ratio is worth revisiting and roughly where to look; it does not settle the
> blade design.

### 5. The motor specification cannot be true as written

**The Competr datasheet states no motor speed anywhere.** It gives 26.9 kW
nominal, 42 kW maximum and 100 N·m, and stops. Two different speeds are in
circulation:

- **4000 rev/min** — this project, back-solved from the datasheet's own 42 kW
  peak, which needs 4011 rev/min at 100 N·m.
- **2500 rev/min** with 1300 nominal — the hydrodynamics team's brief. At
  2500 rev/min the ceiling is 26.18 kW, so 42 kW is unreachable; at 1300 it is
  13.61 kW, so even the 25 kW the rules allow cannot be produced there.

Two teams reached the same conclusion from opposite ends of the drivetrain.
`P50B_MotorSpecAudit` prints both every time it runs and nothing has been
quietly reconciled.

ENERGY_REQ_188 is unaffected either way — the cap is on electrical input and is
enforced by bisection regardless of what the machine can turn.

> **One email to Competr settles this.** Ask for the torque-speed envelope and
> the maximum continuous speed. It gates the gearbox ratio, which gates the
> propeller, which gates the boat speed.

---

## The power ceiling is not 25 kW of shaft power

ENERGY_REQ_188 caps *"the total nominal power consumption of the motor(s)"*.
Consumption is electrical input. A boat set up to deliver 25 kW at the shaft
would draw about 26.9 kW to do it and would be in breach.

`P50B_ShaftPowerCeiling` solves for the shaft power whose electrical input
lands exactly on the limit: **22.8 kW**, or 91 % of the cap. It is mildly speed
dependent, because iron and windage losses are, so it is solved at the
operating point rather than fixed once, and the speed it was solved at is
reported with it.

---

## What the boat does

With the supplied hull, the contra-rotating propulsor and both drivetrain
ceilings enforced:

| | |
|---|---|
| Shaft power available | 22.8 kW (from the 25 kW electrical cap) |
| Top speed | **41.0 km/h** (22.1 knots), torque limited |
| Top speed at a 2.2:1 gearbox | **47.5 km/h** (25.6 knots), power limited |
| Design target in the parameter file | 55 km/h — **not reachable under the cap** |
| ENERGY_REQ_37, three knots | 403 W, 1.8 % of the ceiling |
| ENERGY_REQ_32, reverse | 612 N astern against 33 N, 18× margin |
| Furthest | 64.6 km at 9 km/h |
| At 20 km/h | 165 Wh/km, 50.8 km range |

`boat.target_speed_kmh` is a `DESIGN_CHOICE` the Python pilot model and the
dashboard both steer towards. It is 14 km/h above what the boat can do. Either
lower it or note that every strategy built on it is pacing against a speed that
does not exist.

---

## What is still assumed

Ranked by the hydrodynamics team's own sensitivity analysis, by influence on
Wh/nm:

| | |
|---|---|
| 14.7 % | **wake fraction** — the highest-value hydrodynamic measurement available |
| 14.4 % | **thrust deduction** |
| 8.7 % | gearbox efficiency |
| 7.6 % | motor efficiency |
| 5.2 % | controller efficiency |
| 4.0 % | appendage strut span |

Beyond those:

- **The section polars** are a provisional analytical model, not data. The
  hydrodynamics team calls this the single largest source of uncertainty in the
  absolute efficiency numbers.
- **The resistance curve beyond 20 knots**, and at anything other than 250 kg.
  Towing tank work.
- **Drive-leg drag**, 81.6 N at 20 knots, is unvalidated and it is unknown
  whether the supplied 624 N already includes it. Their model adds it, so ours
  adds it.
- **Rotor-rotor interaction at 50 mm spacing** is strongly unsteady and needs
  sliding-mesh transient CFD; the steady actuator superposition used cannot
  capture blade passing.
- **Blade natural frequencies are not computed at all.**

---

## Sources

- `04_data/hydrodynamics/` — the team's delivery: README, `design_report.txt`,
  and the front and rear blade geometry CSVs for CAD and Ansys.
- `04_data/geometry/Cockpit V1.3.stl` — 22 082 triangles, the source of every
  `MEASURED` cockpit dimension. Its silhouette along the direction of travel is
  0.2755 m², against the 0.42 m² previously assumed.
- `params/volare_params.json`, section `hydro` — every number above, tagged.
