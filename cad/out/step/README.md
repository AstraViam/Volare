# `cad/out/step/` — the boat as a CAD assembly

Regenerate with:

```bash
python cad/scripts/export_step.py          # needs cadquery for the STEP half
```

All four files are in the **canonical boat frame**: X forward, Y to port, Z up,
origin at centreline × hull mid-length × keel bottom, **millimetres**. Load any
combination and they overlay exactly. That is checked by re-measuring the
transformed hull box, not assumed from the transform.

| File | What | Format | Why |
|---|---|---|---|
| `volare_designed.step` | frame v2, powertrain boxes, cable runs | STEP AP214, true B-rep | 35 solids in a named tree; measurable edges, mateable faces |
| `volare_designed.stl` | the same, tessellated | binary STL | for viewers that cannot read STEP |
| `volare_supplied.stl` | hulls, both poles, pod shell, hull fittings | binary STL | supplied by the Organiser, **ENERGY_REQ_3: do not modify** |
| `volare_supplied_frame.stl` | the original rails and pads | binary STL | what frame v2 replaces; separate so an overlay is unambiguous |

## Why the supplied geometry is not in the STEP

It only ever existed as a mesh. Wrapping a tessellation in a STEP shell gives a
file that is large, slow, and impossible to mate to, while looking like a solid
model. STL is what a mesh is, labelled honestly.

## Reading the designed file

The assembly tree groups by function, and the group names carry the message:

```
FRAME               9   rails, clamps, forward shims, keel beam
POWERTRAIN_HV       9   high-voltage chain
POWERTRAIN_LV       3   low-voltage chain
POWERTRAIN_COOLING  1
STRUCTURE           1
CABLES              7   capsule chains, see the script docstring
CLASH               5   red. These intersect the pod shell.
```

`CLASH` is not a modelling error and not an accepted design. Those five
components currently interfere and the group exists so nobody has to rediscover
which five.

## What the overlay shows

- The clamps bore 108 mm over the measured 104.1 mm poles: **2.0 mm radial**,
  the design gasket thickness.
- Frame v2 lifts the pod floor **+103.7 mm**, clearing the 85.7 mm rail/pod
  interference measured in the supplied assembly (note 00 says 83 mm; the
  measured value wins, see `cad/scripts/volare.py`).
- Four sub-millimetre shards on the hull bows are dropped as tessellation
  noise; 101 514 of the source file's 105 174 triangles are carried through
  unmodified.
