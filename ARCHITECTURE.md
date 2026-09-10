# Architecture

How the modules fit together, and why the project is arranged this way.

---

## Data flow

```
                        P50B_CellData
                    (datasheet + OCV + DCIR)
                              |
        +---------------------+---------------------+
        |                                           |
   P50B_Geometry                              P50B_21P
  (all dimensions)                                  |
        |                                     P50B_13S21P
   P50B_GroupLayout                                 |
  (26 groups, 546 cells,                      P50B_26S21P
   pack envelope)                                   |
        |                                    Simscape Battery
   P50B_Busbars                               pack object
  (joints, rails, links,                            |
   ampacity, loss)                            buildBattery
        |                                           |
        +-------------------+                  output/*.slx
                            |
   P50B_MotorData ----+     |
   P50B_InverterData -+     |
   P50B_HarnessData --+-----+
   P50B_AuxiliaryLoads|     |
                      |     |
                 P50B_DrivetrainModel
              (solves one operating point)
                            |
              +-------------+-------------+
              |                           |
      P50B_RunMission            P50B_ThermalDesign
    (time-stepped mission)      (heat and temperature)
              |                           |
              +-------------+-------------+
                            |
              +-------------+-------------+
              |                           |
      P50B_Verification         P50B_MonacoCompliance
     (engineering checks)          (rules checks)
                            |
                 P50B_ProvenanceReport
                (which numbers are real)
```

Everything above is driven end to end by `P50B_26S21P_MASTER`.

---

## Folder layout

| Folder | Contents | Key idea |
|---|---|---|
| `00_common/` | Provenance helpers, project root | Every parameter carries its source |
| `01_cell/` | Cell definition, OCV, DCIR | Single source of truth for the cell |
| `02_pack/` | Simscape Battery construction | Builds the generated library |
| `03_mechanical/` | Geometry, layout, busbars | Single source of truth for dimensions |
| `04_data/` | Datasheets, measured CSVs | Drop measured data here; it loads automatically |
| `05_tests/` | Test scripts | `TEST_ELECTRICAL`, busbar sizing study |
| `06_drivetrain/` | Motor, inverter, harness, loads, chain solver | Where the 25 kW cap is enforced |
| `07_simulation/` | Mission profiles, time-stepped run | Energy and thermal over a mission |
| `08_compliance/` | Monaco rules check | Traceable to ENERGY_REQ numbers |
| `docs/` | This documentation | |
| `output/` | Generated CSV, MAT, SLX | Safe to delete; regenerated on every run |

---

## Design rules the project follows

### One source of truth per quantity

`P50B_Geometry` owns every dimension. `P50B_CellData` owns every cell property.
Nothing is restated anywhere else — `P50B_Geometry` even reads its cell
dimensions from `P50B_CellData` rather than repeating them, and
`P50B_MechanicalLayout` asserts that the cell struct it is handed matches the one
the geometry was built from.

This was not previously true. The project had **two independent layout
generators** with different origins, different Z datums, different group
ordering, and different output field names. `P50B_Verification` read fields that
only one of them produced, so it could not run. The duplicate implementation is
gone; `P50B_MechanicalLayout` is now a thin compatibility wrapper that delegates
to `P50B_GroupLayout`.

### Provenance on every number

No value that feeds a calculation is a bare literal. Each is wrapped by
`P50B_Param` with a unit, a source tag, and usually a note explaining the choice.
`P50B_ProvenanceReport` walks all of it and prints what is datasheet-backed,
what is estimated, and what is invented.

The model currently contains **no `PLACEHOLDER` parameters**, and `TEST_ALL` fails
if any are introduced. See `DATA_PROVENANCE.md`.

### Options, not edits

Every analysis function takes `"Plot"` and `"Verbose"` options so it can run
silently inside a sweep. Expensive objects — geometry, layout, busbars — are
built once and passed in, rather than rebuilt per call. `P50B_RunMission` builds
them once for thousands of time steps.

### Assertions where a bug would be invisible

Cell interference, group population, layer balance, OCV monotonicity, DCIR grid
completeness, series-path adjacency, and mission energy balance are all asserted.
These catch the class of error that otherwise produces a plausible-looking but
wrong pack.

The energy balance check is the strongest of them: shaft energy plus every
modelled loss must equal energy drawn from the cells, to within 0.5%. It
currently closes to 0.0000%.

---

## The chain solver

`P50B_DrivetrainModel` is the centre of the project. Given a shaft power demand,
motor speed, SOC and cell temperature, it works backwards through every loss:

```
propeller <- gearbox <- motor <- inverter <- DC link
          <- harness <- pack terminals <- series links
          <- collectors <- joints <- cells
```

Two things make it worth reading:

**The power cap is enforced, not reported.** Monaco ENERGY_REQ_188 limits motor
electrical input to 25 kW. Motor input rises monotonically with shaft power at
fixed speed, so the solver bisects to find the largest permissible shaft power
and reports `PowerLimit.Active`. A 60 kW demand produces a capped operating
point, not a 60 kW one.

**The pack solve is closed-form.** Pack current appears on both sides of the
problem: current causes voltage sag, and sag raises the current needed for a
given power. Rather than iterate, the terminal condition

```
I × (V_ocv − I·R_total) = P_bus
```

is solved directly as a quadratic. The physical root is the smaller one. A
negative discriminant means the demanded power exceeds what the pack can deliver
at this SOC and temperature — that is reported as infeasible, not silently
clamped.

---

## The serpentine layout

Groups are numbered along a boustrophedon path so that G(n) and G(n+1) are always
physically adjacent. Every one of the 25 series links is then a short hop rather
than a run across the pack.

Layer 2 is traversed in reverse row order *and* with its column direction chosen
so that its first group lands directly above the last group of layer 1. That
makes the inter-layer link a short vertical hop of 80 mm instead of a diagonal
run.

This was a real bug found by the layout's own adjacency assertion: layer 2
originally started at column 1 while layer 1 ended at column 4, so the G13→G14
link spanned three group pitches. `Layout.AllStepsAdjacent` now guards it.

Odd groups are positive-down, even groups positive-up, so every series link joins
two terminals on the same face, alternating between the top and bottom of the
pack. With 26 groups this also puts both pack terminals on the top face, so both
HV cables exit the same side.

Result: 3.71 m total series path, longest step 175 mm, all 25 links adjacent.
