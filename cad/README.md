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
