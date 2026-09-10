# tools/ — repository utilities

**Two expected scripts are missing from the repository.** Both are referenced by
working MATLAB code:

| Script | Referenced by | Purpose |
|---|---|---|
| `crosscheck.py` | `P50B_ArchitectureAudit.m`, `P50B_ThermalDesign.m` | Cross-check parameter values between the MATLAB and Python sides |
| `export_cell_tables.py` | `SMOKE_TEST.m` (via `params/cells/p50b_derived.json`) | Derive cell lookup tables from the measured HPPC CSVs |

See `HANDOFF.md` section 5.
