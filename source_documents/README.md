# source_documents/ — supplied geometry

Cockpit STLs supplied by the organisers. **Never modify these files, and never
modify the hulls or beams they describe** (ENERGY_REQ_3). They are locked in
`cad/blender/build_scene.py` via `lock()`.

`cad/scripts/geom.py` reads them from here by name. Neither STL uses the
project's canonical frame and the two do not agree with each other;
`cad/scripts/volare.py` holds both transforms and self-checks them. Always go
through it.

Competition rules and datasheets live in `docs/reference/`, not here.
