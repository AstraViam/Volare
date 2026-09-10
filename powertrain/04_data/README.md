# powertrain/04_data/

Measured input tables. These are inputs a human or an instrument produced, not
solver output; solver output goes to `powertrain/output/`.

## Present

`P50B_BusbarLinks.csv`, `P50B_BusbarOperatingPoints.csv`,
`P50B_CellCoordinates.csv`, `P50B_GroupCoordinates.csv`, `P50B_ThermalTable.csv`,
`P50B_ParameterProvenance.csv`, `P50B_MonacoCompliance.csv`,
`P50B_VerificationChecks.csv`, and `hydrodynamics/design_report.txt`.

## Missing

| File | Read by | How to produce it |
|---|---|---|
| `P50B_OCV_SOC.csv` | `01_cell/P50B_OCV.m` | Measured open-circuit voltage against state of charge, from an HPPC pulse sequence |
| `P50B_DCIR_SOC_T.csv` | `01_cell/P50B_DCIR.m` | Measured DC internal resistance against SOC and temperature, from the same HPPC run |

Both are declared in `SMOKE_TEST.m`'s `dataFiles` manifest. Until they exist,
the cell model cannot be validated against measurement.
