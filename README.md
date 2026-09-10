# Team Volare — Monaco Energy Boat Challenge 2026

Everything for the cockpit, frame, powertrain and aero work lives in this one
folder. Racing is **9–11 July 2026**; hull handover 6 July, technical inspection
closes 8 July.

```
notes/              10 markdown notes from the original claude.ai session (00 is the index)
source_documents/   the supplied STLs, the rulebook, the Competr datasheet
cad/                all analysis, geometry and optimisation built since   <- the work
cad/scripts/        pure numpy/scipy - runs anywhere, self-testing
cad/blender/        Blender 5.2 scene builders - consume scripts/, never duplicate them
cad/freecad/        FreeCAD 1.1 STEP export
cad/out/            generated: .blend, .step, .json, figures, renders
```

## Start here

```bash
python cad/scripts/volare.py     # frame + frozen constraints, self-checks
cat cad/README.md                # the engineering record: every number and why
```

`cad/README.md` is the substantive document. This file is just the map.

## Ground truth — read before trusting the notes

The notes in `notes/` are the original design discussion and are **partly
superseded**. Five corrections came out of re-measuring the STLs and re-deriving
the numbers. Each is reproducible by running the script named:

| # | Correction | Where |
|---|---|---|
| 1 | **The 250 kg cap includes the pilot and excludes hulls.** Note 06's "+102 kg over" compares a hull-inclusive 282 kg subtotal against a cap that excludes hulls. Cockpit is 202 kg; +70 kg pilot = 272 kg. **Real gap: 22 kg**, which is closable. | `mass.py` |
| 2 | **Crossbeam drag was overcharged ~41%.** The STL models the supplied round Ø104 poles as square boxes, so note 00 charges C_D 2.05 instead of ~1.2. Baseline drops 168.8 N → 91–113 N. Beams stay priority #1 but at 57% of the budget, not 77%. | `aero.py` |
| 3 | **The aft-body target should be ~13°, not ≤12°.** Holding a shallower slope means raising the tail, and base area grows 0.0096 m²/deg — measured, not assumed. Once base drag is priced there is an interior optimum at **13.0°**; going below 12° costs more than it saves. | `optimise.py` |
| 4 | **The 91.4 mm pole height step is structural.** A level rail needs a 91.3 mm packer at the forward station, which carries 79% of the load (note 08 §1). Not a washer. | `frame_redesign.py` |
| 5 | **Note 09's floor-span "12.4× penalty" is wrong** (its own table says 5.1×). Core shear carries 31% of deflection at 400 mm and 11% at 750 mm — the real ratio is **9.6×**. The floor is under-built, but the fix is cheaper than note 09 implies. | `frame.py` |

## Frozen constraints (rulebook, not assumptions)

- Hulls + beams **supplied, 65 kg, do not modify** (ENERGY_REQ_3). Round Ø104 mm
  poles, 3.0 m apart.
- Cockpit clamps **≥750 mm apart**, ≥50 mm wide, enveloping the beam, ≥1 mm
  gasket (ENERGY_REQ_38). The STL has them at 400 mm — non-compliant.
- Cockpit **≤250 kg including the pilot**, excluding hulls (ENERGY_REQ_48).
- Stored energy ≤10 kWh (ENERGY_REQ_7) · Motor **≤25 kW nominal**
  (ENERGY_REQ_188) · Solar ≤4 m² (ENERGY_REQ_28).
- Energy container ≥500 mm from the pilot, behind an A1 non-combustible bulkhead
  (ENERGY_REQ_25/26/50/51/52).

## The two things blocking everything else

1. **The Competr outboard is 26.9 kW nominal against a 25 kW cap.** A compliance
   failure independent of mass. If it forces a different outboard, the 38 kg
   powertrain block and the 10 kg inverter question reopen and every mass plan
   in `mass.py` is invalidated. **Settle this first.**
2. **Weigh the supplied hulls** and get their bulkhead stations. Note 05 says
   this blocks the frame freeze, which blocks the FE model.

## Environment

Blender 5.2.1 (`C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`),
FreeCAD 1.1.3, Python 3.14 with numpy/scipy/matplotlib.

Blender's bundled Python has **no scipy**, so `optimise.py` imports it lazily
inside `solve()` — Blender uses the model, never the solver, and reads the stored
optimum from `cad/out/optimisation.json`.

> This folder is inside OneDrive. That is good for backup, but OneDrive can hold
> a lock on `.blend` files mid-sync — if Blender reports a save error, retry.
