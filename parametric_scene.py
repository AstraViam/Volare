"""Turn the optimiser's design vector into actual geometry, then check it back.

    blender -b -P cad/blender/parametric_scene.py
    blender -b -P cad/blender/parametric_scene.py -- --drag-only
    blender -b -P cad/blender/parametric_scene.py -- --tc 0.30 --closure 11

optimise.py answers "what shape should it be" with six numbers. This builds the
shape those numbers describe and then measures it, so the analytical optimum has
to survive contact with real geometry.

The check that matters is at the bottom: the optimiser assumes a frontal area for
each treated component, and this reports what the built geometry actually
presents. If those disagree the optimum is scoring a shape nobody is building.

Design variables (optimise.py VARS):
    tc_fwd, tc_aft   crossbeam fairing thickness ratios
    w_pilot          windscreen + shoulder fairing completeness, 0-1
    w_brack          bracket blending completeness, 0-1  (not modelled - see below)
    w_rail           rail fairing completeness, 0-1
    closure          pod aft-body max surface slope, deg
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "cad" / "scripts"))
sys.path.insert(0, str(HERE))

import build_scene as BS      # noqa: E402
import frame_redesign as FR   # noqa: E402
import geom                   # noqa: E402
import optimise as O          # noqa: E402
import parametric as PM       # noqa: E402
import volare as V            # noqa: E402

COLL = "PARAMETRIC"
C_FAIR = (0.20, 0.62, 0.86, 1.0)
C_SCREEN = (0.55, 0.80, 0.92, 0.35)
C_POD = (0.86, 0.84, 0.76, 1.0)

# windscreen, note 01 section 4.1
SCREEN_RAKE_DEG = 37.5        # 35-40 deg
SCREEN_HEIGHT_MM = 260.0
SCREEN_WIDTH_MM = 520.0
SCREEN_SWEEP_DEG = 25.0       # side edges swept back so the vortex passes outboard


# geometry generators live in scripts/parametric.py so they can be swept
# from plain Python; Blender just consumes them.
recontour_pod = PM.recontour_pod
windscreen_mesh = PM.windscreen_mesh


# ----------------------------------------------------------------------- build


def build(x, report):
    coll = BS.get_collection(COLL)
    tc_f, tc_a, w_p, w_b, w_r, closure = x
    made = {}

    # 1. crossbeam fairings, wrapped on the supplied poles
    span = O.SPAN_BEAM
    for tag, tc in (("fwd", tc_f), ("aft", tc_a)):
        b = V.BASELINE[f"beam_{tag}"]
        chord = PM.min_chord_for_pole(tc)
        cen = (b["x"], 0.0, (b["z_bottom"] + b["z_top"]) / 2.0)
        T = PM.fairing_mesh(tc, chord, span, cen, axis=1)
        ob = BS.add_tri_soup(f"fairing_beam_{tag}", T, coll, C_FAIR)
        BS.tag(ob, note=f"t/c {tc:.3f} ({1/tc:.1f}:1), chord {chord:.0f} mm",
               cfd_zone=f"beam-{tag}-fairing")
        made[ob.name] = {"tris": T, "chord_mm": chord, "tc": tc}

    # 2. pod, aft body recontoured to the optimiser's closure angle
    src = geom.read_stl(ROOT / "source_documents" / "Cockpit_V1_3.stl")
    pod = V.pod_to_boat(src.reshape(-1, 3)).reshape(-1, 3, 3)
    Td, info = recontour_pod(pod, closure)
    # Sit on the ENERGY_REQ_38 frame, not the non-compliant baseline. Without
    # this the recontoured pod keeps the 85.7 mm rail interference and the rail
    # fairings run straight through its floor.
    st = FR.stack_heights()
    lift = st["pod_floor"] - V.BASELINE["pod"]["z_floor"]
    Td = Td.copy()
    Td[:, :, 2] += lift
    info["pod_raised_mm"] = float(lift)
    ob = BS.add_tri_soup("pod_shell_recontoured", Td, coll, C_POD)
    BS.tag(ob, note=f"aft body held to {closure:.1f} deg max slope")
    made[ob.name] = {"tris": Td}
    report["recontour"] = info

    # 3. windscreen + shoulder fairing, scaled by the optimiser's completeness
    if w_p > 0.05:
        b = V.BASELINE["pod"]
        Ts = windscreen_mesh(Td, x_base=info["x_peak"] + 260.0,
                             half_w=SCREEN_WIDTH_MM / 2 * w_p,
                             height=SCREEN_HEIGHT_MM * w_p,
                             rake_deg=SCREEN_RAKE_DEG, sweep_deg=SCREEN_SWEEP_DEG)
        ob = BS.add_tri_soup("windscreen", Ts, coll, C_SCREEN, alpha=0.35)
        BS.tag(ob, note=f"{SCREEN_RAKE_DEG:.0f} deg rake, completeness {w_p:.2f}; "
                        f"massing model only - not a CFD surface")
        made[ob.name] = {"tris": Ts}

    # 4. rail fairings
    if w_r > 0.05:
        for side, sgn in (("port", +1), ("stbd", -1)):
            cen = (-485.3, sgn * FR.RAIL_Y,
                   st["rail_top"] - FR.RAIL_H / 2.0)
            T = PM.fairing_mesh(0.40, 250.0, V.BASELINE["rail"]["length"],
                                cen, axis=0)
            ob = BS.add_tri_soup(f"fairing_rail_{side}", T, coll, C_FAIR)
            BS.tag(ob, note=f"completeness {w_r:.2f}", cfd_zone=f"rail-{side}-fairing")
            made[ob.name] = {"tris": T}

    if w_b > 0.05:
        report["not_modelled"] = (
            f"bracket blending at completeness {w_b:.2f} is in the drag and mass "
            f"budget but has no geometry here - the brackets themselves are only "
            f"a bbox in the source STL, so there is nothing to blend yet")
    return made, closure


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    report = {"parts": []}

    # Prefer the stored optimum. Solving needs scipy, which Blender's Python does
    # not have - and re-solving here would also let the scene drift from the
    # result the rest of the package reports.
    key = "drag_only" if "--drag-only" in argv else "drag_plus_mass"
    stored = ROOT / "cad" / "out" / "optimisation.json"
    if stored.exists():
        x = list(json.loads(stored.read_text())[key]["x"])
        print(f"  design vector from {stored.name} [{key}]")
    else:
        x = list(O.solve(r_over_w=0.0 if "--drag-only" in argv else None)[0])
    if "--tc" in argv:
        x[0] = x[1] = float(argv[argv.index("--tc") + 1])
    if "--closure" in argv:
        x[5] = float(argv[argv.index("--closure") + 1])
    r = O.evaluate(x)

    print("=" * 74)
    print("PARAMETRIC SCENE - building the optimiser's design vector")
    print("=" * 74)
    for n, v in r["vars"].items():
        print(f"  {n:<10}{v:>10.4f}")
    print(f"\n  predicted: {r['D_N']:.1f} N aero, {r['mass_kg']:.1f} kg added, "
          f"{r['R_eff_N']:.1f} N effective, {r['P_W']:.0f} W")

    BS.reset_scene()
    for name in BS.COLLECTIONS:
        BS.get_collection(name)
    plist = BS.build_supplied_and_frame(report)
    BS.build_reference(report)
    FR.supersede_baseline()
    FR.build()                      # compliant rails, clamps, shims, keel beam
    orig = bpy.data.objects.get("pod_shell")
    if orig:
        orig.hide_render = True
        orig.display_type = "WIRE"
        orig["superseded_by"] = "pod_shell_recontoured"

    made, closure = build(x, report)
    bpy.context.view_layer.update()

    ri = report["recontour"]
    print("\nAFT-BODY RECONTOUR")
    print(f"  run                    {ri['run_mm']:8.1f} mm aft of the crown")
    print(f"  drop  {ri['drop_before_mm']:8.1f} -> {ri['drop_after_mm']:.1f} mm"
          f"   (tail raised {ri['tail_raised_mm']:+.1f} mm)")
    print(f"  max surface slope      {ri['max_slope_deg']:8.2f} deg  "
          f"(target {ri['target_deg']:.2f}, was 41.2 at the base edge)")
    print(f"  mean slope             {ri['mean_slope_deg']:8.2f} deg  (was 15.59)")
    print(f"  pod raised             {ri['pod_raised_mm']:8.1f} mm onto the "
          f"ENERGY_REQ_38 frame")
    print(f"  base area  {ri['base_area_before_m2']:.4f} -> {ri['base_area_after_m2']:.4f} m2"
          f"   ({(ri['base_area_after_m2'] / ri['base_area_before_m2'] - 1) * 100:+.0f}%)")
    # Raising the tail buys the slope and costs base area. That trade IS in the
    # model now (aero.CD_BASE_SHARP x parametric.base_area_for_closure), fitted
    # to measurements of this very deformation - so the geometry built here has
    # to agree with the fit the optimiser scored, or the optimum is fiction.
    fit = PM.base_area_for_closure(closure)
    built = ri["base_area_after_m2"]
    err = abs(built - fit) / fit * 100.0
    print(f"\n  Raising the tail buys the slope and costs base area:")
    print(f"    base area the optimiser priced   {fit:.4f} m2")
    print(f"    base area actually built         {built:.4f} m2   ({err:.1f}% off)")
    print("    " + ("OK - the optimum was scored on the shape being built"
                    if err < 3.0 else
                    "MISMATCH - refit parametric.base_area_for_closure()"))

    # --- the check that matters ---------------------------------------------
    print("\nBUILT GEOMETRY vs WHAT THE OPTIMISER ASSUMED")
    print(f"  {'component':<24}{'assumed A':>11}{'built A':>10}{'delta':>9}")
    print("  " + "-" * 56)
    rows = []
    for tag in ("fwd", "aft"):
        nm = f"fairing_beam_{tag}"
        T = made[nm]["tris"]
        built = geom.projected_area(T, 0, 2.0)
        tc = made[nm]["tc"]
        assumed = made[nm]["chord_mm"] * tc / 1000.0 * O.SPAN_BEAM / 1000.0
        rows.append((nm, assumed, built))
    for nm, a, b in rows:
        print(f"  {nm:<24}{a:>11.4f}{b:>10.4f}{(b - a):>9.4f}")
    ws = made.get("windscreen")
    if ws is not None:
        b = geom.projected_area(ws["tris"], 0, 2.0)
        print(f"  {'windscreen':<24}{O.COMPONENTS['pilot']['A']:>11.4f}{b:>10.4f}"
              f"{b - O.COMPONENTS['pilot']['A']:>9.4f}")
        print(f"\n  The windscreen's built frontal area is a MASSING number - the")
        print(f"  0.150 m2 the optimiser uses is the exposed pilot, not the screen.")
        print(f"  These are not the same quantity and should not be reconciled.")

    report["design"] = r
    report["built"] = {n: {k: v for k, v in d.items() if k != "tris"}
                       for n, d in made.items()}
    out = ROOT / "cad" / "out" / "volare_parametric.blend"
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    out.with_suffix(".json").write_text(json.dumps(report, indent=2, default=float))
    print(f"\n  saved {out}")
    print(f"  saved {out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
