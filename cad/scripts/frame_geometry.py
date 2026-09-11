"""Frame v2 geometry as primitive solids, shared by Blender and the CAD export.

    import frame_geometry as FG
    parts = FG.build()        # list of primitive dicts
    st = FG.stack_heights()   # the vertical stack-up

WHY THIS MODULE EXISTS

The frame was defined inside `cad/blender/frame_redesign.py`, which put
geometry maths in the Blender layer. CLAUDE.md is explicit that
`cad/blender/` consumes `cad/scripts/` and never reimplements it, and the
reason is drift: the moment a second consumer needs the same frame, either it
duplicates the numbers or it imports Blender to get them. The STEP exporter is
that second consumer.

So the maths lives here, in pure numpy, and both the Blender scene and the
CAD export read it. Change a dimension once and both follow.

WHAT A PRIMITIVE IS

Each part is a dict describing a shape a solid modeller can build exactly:

    {"name", "kind", "centre", "group", "note", ...}

    kind "box"      -> "size" (length X, width Y, height Z), mm
    kind "cylinder" -> "od", "length", "axis" (0=X, 1=Y, 2=Z), mm

Boxes and cylinders, nothing else. That is not a limitation of the exporter,
it is what the frame actually is: rectangular hollow section, round clamps
around round poles, flat packers.

A NOTE ON THE RAILS

They are specified 100 x 50 x 3 RHS in note 02 section 4, which is a HOLLOW
section. This module reports them as solid boxes, matching the Blender model,
because that is the decision recorded for the current export. `wall_mm` is
carried on the primitive so a consumer can build the true hollow section
without guessing the wall thickness. Building them hollow changes the steel
mass by roughly a factor of three, so it matters for the mass budget even
though it does not for clash checking.

Team Volare / ICT Mumbai.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import params  # noqa: E402
import volare as V  # noqa: E402

__all__ = ["build", "stack_heights", "CONSTANTS"]

# --- the redesign, note 02 section 4 -----------------------------------------
RAIL_W = 100.0          # mm, RHS width
RAIL_H = 50.0           # mm, RHS height
RAIL_WALL = 3.0         # mm, RHS wall. The section is hollow; see the docstring.
PAD_MM = 10.0           # standoff pad, pod floor onto rail top
CLAMP_W = 60.0          # mm, >= 50 required by ENERGY_REQ_38
GASKET_MM = 2.0         # mm, >= 1 required
CLAMP_WALL = 8.0        # mm
KEEL_W, KEEL_H = 60.0, 40.0     # centreline keel beam, frame.py option B
KEEL_LENGTH = 1200.0
KEEL_X_FROM_NOSE = 1250.0
RAIL_X_CENTRE = -485.3

CONSTANTS = {
    "RAIL_W": RAIL_W, "RAIL_H": RAIL_H, "RAIL_WALL": RAIL_WALL,
    "PAD_MM": PAD_MM, "CLAMP_W": CLAMP_W, "GASKET_MM": GASKET_MM,
    "CLAMP_WALL": CLAMP_WALL, "KEEL_W": KEEL_W, "KEEL_H": KEEL_H,
}


def rail_y() -> float:
    """Half the clamp spacing, so the rails sit at +/- this in Y.

    Driven by ENERGY_REQ_38's minimum clamp spacing, which comes from the
    parameter file rather than being written here.
    """
    return params.get("rules.clamp_min_spacing_mm") / 2.0


def stack_heights() -> dict:
    """Work UP from the beams. The rail height is not a free choice.

    The clamps wrap the poles, the rails sit on the clamps, and the pod sits on
    pads on the rails. The two poles are at different heights, the forward one
    lower, so a level rail has to be shimmed at the forward station. The beam
    step is not cosmetic; it sets the whole stack.
    """
    od = V.BEAM_DIAMETER + 2 * (GASKET_MM + CLAMP_WALL)
    tops = {}
    for which in ("fwd", "aft"):
        b = V.BASELINE[f"beam_{which}"]
        tops[which] = (b["z_bottom"] + b["z_top"]) / 2.0 + od / 2.0
    rail_bottom = max(tops.values())
    return {
        "clamp_od": od,
        "clamp_top": tops,
        "shim_fwd_mm": rail_bottom - tops["fwd"],
        "rail_bottom": rail_bottom,
        "rail_top": rail_bottom + RAIL_H,
        "pod_floor": rail_bottom + RAIL_H + PAD_MM,
    }


def build() -> list[dict]:
    """Every frame v2 part as a primitive, in the canonical boat frame."""
    st = stack_heights()
    ry = rail_y()
    rail = V.BASELINE["rail"]
    out: list[dict] = []

    # 1. rails, sitting on top of the clamps
    rail_cz = st["rail_top"] - RAIL_H / 2.0
    for side, sgn in (("port", +1), ("stbd", -1)):
        out.append({
            "name": f"rail_{side}", "kind": "box", "group": "FRAME",
            "centre": [RAIL_X_CENTRE, sgn * ry, rail_cz],
            "size": [rail["length"], RAIL_W, RAIL_H],
            "wall_mm": RAIL_WALL,
            "rule": "ENERGY_REQ_38",
            "note": (f"{RAIL_W:.0f}x{RAIL_H:.0f}x{RAIL_WALL:.0f} RHS at "
                     f"Y={sgn * ry:+.0f}. Modelled solid; the real section is "
                     f"hollow, see wall_mm"),
        })

    # 2. two clamps per beam, symmetric, enveloping the full circumference
    for which in ("fwd", "aft"):
        b = V.BASELINE[f"beam_{which}"]
        cz = (b["z_bottom"] + b["z_top"]) / 2.0
        for side, sgn in (("port", +1), ("stbd", -1)):
            out.append({
                "name": f"clamp_{which}_{side}", "kind": "cylinder",
                "group": "FRAME",
                "centre": [b["x"], sgn * ry, cz],
                "od": st["clamp_od"], "length": CLAMP_W, "axis": 1,
                "bore": V.BEAM_DIAMETER + 2 * GASKET_MM,
                "rule": "ENERGY_REQ_38",
                "note": (f"{CLAMP_W:.0f} mm wide, envelops D"
                         f"{V.BEAM_DIAMETER:.0f} + {GASKET_MM:.0f} mm gasket"),
            })

            # the forward pole sits lower, so a level rail needs a packer
            if which == "fwd" and st["shim_fwd_mm"] > 1.0:
                out.append({
                    "name": f"shim_fwd_{side}", "kind": "box", "group": "FRAME",
                    "centre": [b["x"], sgn * ry,
                               st["clamp_top"]["fwd"] + st["shim_fwd_mm"] / 2.0],
                    "size": [CLAMP_W, RAIL_W, st["shim_fwd_mm"]],
                    "note": (f"{st['shim_fwd_mm']:.1f} mm packer; the forward "
                             "pole sits that much lower than the aft one"),
                })

    # 3. centreline keel beam, also the seat mount
    out.append({
        "name": "keel_beam", "kind": "box", "group": "FRAME",
        "centre": [V.BASELINE["pod"]["x_nose"] - KEEL_X_FROM_NOSE, 0.0,
                   st["pod_floor"] + KEEL_H / 2.0],
        "size": [KEEL_LENGTH, KEEL_W, KEEL_H],
        "note": "halves the floor span 750 -> 375 mm; doubles as the seat mount",
    })
    return out


def _selftest() -> bool:
    ok = True
    st = stack_heights()
    parts = build()
    print("frame_geometry.py selfcheck")
    print(f"  clamp spacing (c-c)   {2 * rail_y():.1f} mm "
          f"(ENERGY_REQ_38 needs >= {params.get('rules.clamp_min_spacing_mm'):.0f})")
    print(f"  clamp OD              {st['clamp_od']:.1f} mm")
    print(f"  forward shim          {st['shim_fwd_mm']:.1f} mm")
    print(f"  rail top / pod floor  {st['rail_top']:.1f} / {st['pod_floor']:.1f} mm")
    print(f"  parts                 {len(parts)}")

    if 2 * rail_y() < params.get("rules.clamp_min_spacing_mm"):
        print("  FAIL  clamp spacing below the rule minimum")
        ok = False
    if not (0.0 < st["shim_fwd_mm"] < 200.0):
        print(f"  FAIL  implausible shim {st['shim_fwd_mm']}")
        ok = False

    names = [p["name"] for p in parts]
    if len(names) != len(set(names)):
        print("  FAIL  duplicate part names")
        ok = False

    for p in parts:
        if p["kind"] == "box" and any(d <= 0 for d in p["size"]):
            print(f"  FAIL  {p['name']} has a non-positive dimension")
            ok = False
        if p["kind"] == "cylinder" and p["od"] <= p.get("bore", 0):
            print(f"  FAIL  {p['name']} bore is not smaller than its OD")
            ok = False

    # The clamps must actually wrap the pole they clamp.
    for p in parts:
        if p["kind"] == "cylinder" and p.get("bore", 0) < V.BEAM_DIAMETER:
            print(f"  FAIL  {p['name']} bore {p['bore']} is smaller than the "
                  f"{V.BEAM_DIAMETER} mm pole")
            ok = False

    print(f"  {'OK' if ok else 'FAIL'}    geometry is self-consistent")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if _selftest() else 1)
