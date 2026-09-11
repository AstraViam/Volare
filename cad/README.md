# cad/ — geometry, structure and optimisation

The engineering record for everything geometric. Pure Python maths is separated
from Blender scene building on purpose, and that separation is enforced by
review rather than by tooling, so keep it.

| Folder | Runtime | Rule |
|---|---|---|
| `scripts/` | numpy, scipy | No `bpy`, ever. All physics and geometry maths lives here. Every module self-tests and exits non-zero on failure. |
| `blender/` | Blender's Python | Consumes `scripts/`, never reimplements it. Adds `cad/scripts` to `sys.path` itself. Blender has no scipy, so keep heavy imports lazy. |
| `freecad/` | FreeCAD's Python | STEP export only. |
| `out/` | — | Generated `.blend`, `.json`, `.csv`. `out/figures/` holds rendered PNGs. Tracked, so teammates without Blender still have them. |

## Parameters drive the geometry

Every engineering number comes from `powertrain/params/volare_params.json`.
Change it and the change reaches the CAD without anybody editing code. That is
what lets design work and analysis run in parallel.

```
powertrain/params/volare_params.json      the single source of truth
        |
        |  cad/scripts/params.py           stdlib-only loader, works under
        |                                  CPython, Blender and FreeCAD alike
        v
  cad/scripts/volare.py                    shared constants, now derived
        |                                  (mass cap, pilot mass, beam
        |                                   diameter, clamp limits, air)
        +--> parametric.py, frame.py, mass.py, aero.py, ...
        |
  cad/scripts/powertrain.py                computes the layout
        |
        v
  cad/out/powertrain.json                  the one geometry both builders read
        |
        +--> cad/blender/*        meshes, renders, the .blend
        +--> cad/freecad/*        B-rep solids, the STEP a supplier can open
```

Blender and FreeCAD consume the same JSON, so they cannot disagree about where
anything is. Neither reads a parameter directly, which is deliberate: one place
computes the layout, everything downstream consumes it.

The cost of that is staleness, so the FreeCAD build refuses to run when
`cad/out/powertrain.json` is older than the parameter file, rather than writing
a STEP that looks authoritative and describes the previous design. Override
with `VOLARE_ALLOW_STALE=1` only when you mean it.

**What stays hardcoded, on purpose.** The STL-derived numbers in `volare.py`
are measurements of supplied geometry, re-derived from the files and
self-checked at the bottom of that module. They are not design choices anybody
may vary, so they are not parameters.

**Adding a number.** Put it in the parameter file with a provenance tag, then
read it with `params.get("section.name")`. Never add a literal to a script. A
missing parameter raises rather than falling back to a plausible default,
because a CAD model built on invented dimensions looks authoritative and is
not.

## Path contract

Modules resolve the repository root as `Path(__file__).resolve().parents[2]`.
That means **`cad/scripts/` must stay exactly two levels below the repository
root**. Moving it breaks every data path at once. The same applies to
`cad/blender/`.

From that root the modules expect `cad/out/`, `cad/out/figures/` and
`source_documents/`.

## Running

```bash
.venv/bin/python cad/scripts/mass.py
for f in cad/scripts/*.py; do .venv/bin/python "$f" || echo "FAIL $f"; done

blender -b -P cad/blender/build_scene.py -- --out cad/out/volare_baseline.blend
blender -b cad/out/volare_baseline.blend -P cad/blender/render_views.py
```

`powertrain.py` and `pack_fit.py` currently fail on a missing shared parameter
file. See `HANDOFF.md` section 5.
