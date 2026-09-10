r"""
tools/optimise_layout.py
========================

Sweep pack arrangements and report which ones are actually better.

WHY
---
The 4 x 4 slot grid was chosen early and never revisited. It holds 13 groups
in 16 slots and gives a 687 x 311 mm footprint at 32.8% packaging efficiency,
which is low for a cylindrical-cell pack. That number is a symptom, not a
verdict -- some of the loss is the enclosure, some is square packing, some is
the three empty slots -- so the question is whether a different arrangement is
genuinely better or just differently shaped.

This sweeps every grid that can hold the groups, plus every way of splitting
21 cells into a rectangle, and scores each on the things that actually matter:

  footprint          must fit the cockpit
  volume             sets packaging efficiency
  series path        sets interconnect copper and resistance
  longest link       a long link is a heavy, lossy, awkward busbar
  adjacency          every series link should join neighbours

It does NOT pick a winner. Several of these trade against each other and the
choice depends on where the pack sits in the hull, which is not a thing a
script knows. It prints the Pareto set and the reasoning.

USAGE
-----
    python tools/optimise_layout.py
    python tools/optimise_layout.py --apply 5x3     # write a choice back

CONSTRAINT
----------
The organiser hull is 2.53 m long and 0.70 m wide (Monaco ENERGY_REQ_1/2), and
the pack has to sit inside the cockpit with the bulkhead, seat and controls.
Any arrangement wider than the hull is rejected outright.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "python"))

from volare.params import load                                 # noqa: E402
from volare.layout3d import TwoLayerLayout                     # noqa: E402


PARAMS = os.path.join(_ROOT, "params", "volare_params.json")


def evaluate(P, group_rows, group_cols, grid_rows, grid_cols):
    """Build one candidate and measure it. Returns None if infeasible."""
    n_par = int(P.pack.n_parallel)

    if group_rows * group_cols != n_par:
        return None

    groups_per_layer = int(P.pack.n_series) // int(P.pack.n_layers)

    if grid_rows * grid_cols < groups_per_layer:
        return None

    try:
        lay = TwoLayerLayout(
            n_series=int(P.pack.n_series),
            n_parallel=n_par,
            n_layers=int(P.pack.n_layers),
            group_rows=group_rows,
            group_cols=group_cols,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            cell_diameter_m=P.cell.diameter_m,
            cell_height_m=P.cell.height_m,
            cell_clearance_m=P.pack.cell_clearance_m,
            group_clearance_x_m=P.pack.group_clearance_x_m,
            group_clearance_y_m=P.pack.group_clearance_y_m,
            layer_gap_m=P.pack.layer_gap_m,
            tubes_per_plate=int(P.cooling.tubes_per_plate),
            n_circuits=int(P.cooling.n_circuits),
            tube_id_m=P.cooling.tube_id_m,
            R_can_plate_KW=P.cooling.R_can_plate_KW,
            R_plate_tubewall_KW=P.cooling.R_plate_tubewall_KW,
            gap_filler_k_WmK=P.cooling.gap_filler_k_W_mK,
            gap_contact_frac=P.cooling.gap_contact_frac,
        )
    except Exception:
        return None

    # --- series path along G1 -> G26 ---------------------------------
    gx, gy, gz = lay.group_x, lay.group_y, lay.group_z
    steps = np.sqrt(np.diff(gx)**2 + np.diff(gy)**2 + np.diff(gz)**2)

    max_adjacent = 1.01 * np.sqrt(
        lay.group_pitch_x_m**2 + lay.group_pitch_y_m**2 +
        (lay.cell_height_m + lay.layer_gap_m)**2)

    n_far = int(np.sum(steps > max_adjacent))

    # --- envelope ----------------------------------------------------
    ext_w = lay.pack_width_m + 2*(P.pack.enclosure_clear_m +
                                  P.pack.enclosure_wall_m)
    ext_d = lay.pack_depth_m + 2*(P.pack.enclosure_clear_m +
                                  P.pack.enclosure_wall_m)

    stack_h = (int(P.pack.n_layers) * lay.cell_height_m +
               (int(P.pack.n_layers) - 1) * lay.layer_gap_m +
               (int(P.pack.n_layers) + 1) * P.cooling.plate_thickness_m)

    ext_h = stack_h + P.pack.enclosure_base_m + P.pack.enclosure_lid_m + \
        P.pack.enclosure_clear_m

    vol = ext_w * ext_d * ext_h

    cell_vol = (np.pi * (lay.cell_diameter_m/2)**2 * lay.cell_height_m *
                lay.n_cells)

    # --- hull fit ----------------------------------------------------
    hull_w = P.boat.hull_width_m
    hull_l = P.boat.hull_length_m

    # the pack may be rotated, so the smaller dimension must clear the beam
    fits = (min(ext_w, ext_d) <= hull_w) and (max(ext_w, ext_d) <= hull_l)

    return dict(
        label=f"{grid_cols}x{grid_rows}",
        group=f"{group_rows}x{group_cols}",
        grid_rows=grid_rows, grid_cols=grid_cols,
        group_rows=group_rows, group_cols=group_cols,
        empty_slots=grid_rows*grid_cols - groups_per_layer,
        width_mm=ext_w*1e3, depth_mm=ext_d*1e3, height_mm=ext_h*1e3,
        footprint_m2=ext_w*ext_d,
        volume_L=vol*1e3,
        pack_eff=cell_vol/vol,
        path_m=float(steps.sum()),
        longest_link_mm=float(steps.max()*1e3),
        non_adjacent=n_far,
        fits=fits,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", default=None,
                    help="write a chosen grid back to the parameter file, "
                         "e.g. --apply 5x3 (cols x rows)")
    ap.add_argument("--group", default=None,
                    help="group shape to apply, e.g. 3x7 (rows x cols)")
    args = ap.parse_args()

    P = load()

    n_par = int(P.pack.n_parallel)
    groups_per_layer = int(P.pack.n_series) // int(P.pack.n_layers)

    # every rectangle that makes 21 cells
    group_shapes = [(r, n_par // r) for r in range(1, n_par + 1)
                    if n_par % r == 0]

    results = []
    for gr, gc in group_shapes:
        for rows in range(1, groups_per_layer + 1):
            for cols in range(1, groups_per_layer + 1):
                if rows * cols < groups_per_layer:
                    continue
                if rows * cols > groups_per_layer + 4:
                    continue          # more than 4 wasted slots is silly
                r = evaluate(P, gr, gc, rows, cols)
                if r:
                    results.append(r)

    current = evaluate(P, int(P.pack.group_rows), int(P.pack.group_cols),
                       int(P.pack.grid_rows), int(P.pack.grid_cols))

    print()
    print("=" * 92)
    print(" PACK ARRANGEMENT SWEEP")
    print("=" * 92)
    print(f" {len(results)} feasible arrangements of "
          f"{groups_per_layer} groups per layer, {n_par} cells per group")
    print(f" hull limit: {P.boat.hull_width_m*1e3:.0f} mm beam, "
          f"{P.boat.hull_length_m*1e3:.0f} mm length")
    print()

    print(" CURRENT DESIGN")
    print(f"   grid {current['label']}, group {current['group']}: "
          f"{current['width_mm']:.0f} x {current['depth_mm']:.0f} x "
          f"{current['height_mm']:.0f} mm, {current['volume_L']:.1f} L, "
          f"{current['pack_eff']*100:.1f}% cell")
    print(f"   series path {current['path_m']:.2f} m, longest link "
          f"{current['longest_link_mm']:.0f} mm, "
          f"{current['empty_slots']} empty slot(s)")
    print()

    # ---- only arrangements that fit and keep the serpentine intact ----
    viable = [r for r in results if r["fits"] and r["non_adjacent"] == 0]

    print(f" {len(viable)} fit the hull AND keep every series link between "
          f"neighbours")
    print()

    # ---- Pareto front on volume and series path ----------------------
    def dominated(a, b):
        return (b["volume_L"] <= a["volume_L"] and
                b["path_m"] <= a["path_m"] and
                (b["volume_L"] < a["volume_L"] or b["path_m"] < a["path_m"]))

    pareto = [a for a in viable if not any(dominated(a, b) for b in viable)]
    pareto.sort(key=lambda r: r["volume_L"])

    print(" PARETO SET  (nothing else is better on BOTH volume and path)")
    print()
    print(f"   {'grid':>6} {'group':>6} {'W x D x H mm':>22} {'vol L':>7} "
          f"{'cell%':>6} {'path m':>7} {'link mm':>8} {'free':>5}")
    print("   " + "-" * 84)

    for r in pareto[:14]:
        mark = " <- current" if (r["label"] == current["label"] and
                                 r["group"] == current["group"]) else ""
        print(f"   {r['label']:>6} {r['group']:>6} "
              f"{r['width_mm']:7.0f} x{r['depth_mm']:6.0f} x{r['height_mm']:5.0f} "
              f"{r['volume_L']:7.1f} {r['pack_eff']*100:5.1f}% "
              f"{r['path_m']:7.2f} {r['longest_link_mm']:8.0f} "
              f"{r['empty_slots']:5d}{mark}")

    # ---- how the current design compares ------------------------------
    best_vol = min(viable, key=lambda r: r["volume_L"])
    best_path = min(viable, key=lambda r: r["path_m"])

    print()
    print(" HOW THE CURRENT DESIGN COMPARES")
    print()
    dv = 100*(current["volume_L"] - best_vol["volume_L"])/current["volume_L"]
    dp = 100*(current["path_m"] - best_path["path_m"])/current["path_m"]

    print(f"   smallest volume : grid {best_vol['label']} group "
          f"{best_vol['group']}  {best_vol['volume_L']:.1f} L "
          f"-- {dv:.1f}% SMALLER than current")
    print(f"     {best_vol['width_mm']:.0f} x {best_vol['depth_mm']:.0f} mm, "
          f"path {best_vol['path_m']:.2f} m")
    print()
    print(f"   shortest path   : grid {best_path['label']} group "
          f"{best_path['group']}  {best_path['path_m']:.2f} m "
          f"-- {dp:.1f}% SHORTER than current")
    print(f"     {best_path['width_mm']:.0f} x {best_path['depth_mm']:.0f} mm, "
          f"{best_path['volume_L']:.1f} L")

    # ---- is the current design on the front at all? -------------------
    beaters = [r for r in viable
               if r["volume_L"] < current["volume_L"]
               and r["path_m"] < current["path_m"]]

    print()
    if beaters:
        b = min(beaters, key=lambda r: r["volume_L"])
        print(" THE CURRENT 4x4 GRID IS DOMINATED")
        print()
        print(f"   {len(beaters)} arrangement(s) are better on BOTH volume")
        print(f"   and series path. The strongest is grid {b['label']} "
              f"group {b['group']}:")
        print()
        print(f"     volume       {b['volume_L']:.1f} L  vs "
              f"{current['volume_L']:.1f} L   "
              f"({100*(current['volume_L']-b['volume_L'])/current['volume_L']:.0f}% less)")
        print(f"     series path  {b['path_m']:.2f} m vs "
              f"{current['path_m']:.2f} m  "
              f"({100*(current['path_m']-b['path_m'])/current['path_m']:.0f}% less)")
        print(f"     footprint    {b['width_mm']:.0f} x {b['depth_mm']:.0f} mm "
              f"vs {current['width_mm']:.0f} x {current['depth_mm']:.0f} mm")
        print()
        print("   Less series path is less copper carrying full pack current,")
        print("   so it is also less interconnect resistance and less loss.")
        print()
        print("   BEFORE ACTING ON THIS, note what the sweep does NOT score:")
        print("     - longitudinal weight distribution and trim. A 1058 mm")
        print("       pack sits very differently in a 2.53 m hull than a")
        print("       687 mm one, and trim is worth real time on the water.")
        print("     - cold-plate hydraulics. A long thin plate needs a")
        print("       different serpentine, and pressure drop scales with")
        print("       the length of each pass.")
        print("     - structural support and mounting to the beams.")
        print("     - where the bulkhead, seat and controls have to go.")
        print()
        print("   The sweep says the current grid is not on the efficient")
        print("   frontier. It does not say the alternative is better overall.")
    else:
        print(" The current grid is on the efficient frontier: nothing in the")
        print(" sweep beats it on both volume and series path.")

    print()
    print(" READING THIS")
    print("   Volume and series path pull in opposite directions. A long thin")
    print("   pack has the smallest bounding box but the longest serpentine,")
    print("   and every extra metre of path is copper carrying full pack")
    print("   current. A square pack is the reverse.")
    print()
    print("   Packaging efficiency barely moves across the whole set: it is")
    print("   dominated by square cell packing and the enclosure, not by the")
    print("   grid. Chasing it by reshaping the grid is not worth much --")
    print("   hexagonal cell packing would buy far more.")
    print()
    print("   The empty slots are not waste. They hold the BMS, contactor,")
    print("   fuse and pre-charge, which otherwise need their own enclosure")
    print("   volume that this sweep does not count.")

    print()
    print("=" * 92)

    # ---- optionally write a choice back -------------------------------
    if args.apply:
        try:
            cols, rows = (int(v) for v in args.apply.lower().split("x"))
        except Exception:
            print(f"ERROR: --apply expects COLSxROWS, got '{args.apply}'")
            return 1

        gr, gc = int(P.pack.group_rows), int(P.pack.group_cols)
        if args.group:
            gr, gc = (int(v) for v in args.group.lower().split("x"))

        chk = evaluate(P, gr, gc, rows, cols)
        if chk is None:
            print(f"ERROR: {args.apply} / group {gr}x{gc} is not feasible.")
            return 1
        if not chk["fits"]:
            print(f"ERROR: {args.apply} does not fit the hull "
                  f"({chk['width_mm']:.0f} x {chk['depth_mm']:.0f} mm).")
            return 1
        if chk["non_adjacent"]:
            print(f"ERROR: {args.apply} breaks the serpentine "
                  f"({chk['non_adjacent']} non-adjacent link(s)).")
            return 1

        with open(PARAMS, "r", encoding="utf-8") as f:
            raw = f.read()

        for key, val in (("grid_rows", rows), ("grid_cols", cols),
                         ("group_rows", gr), ("group_cols", gc)):
            import re
            pat = re.compile(r'("' + key + r'":\s*\{\s*"v":\s*)\d+')
            raw, n = pat.subn(lambda m: m.group(1) + str(val), raw, count=1)
            if not n:
                print(f"ERROR: could not update '{key}' in the parameter file.")
                return 1

        json.loads(raw)                      # refuse to write invalid JSON

        with open(PARAMS, "w", encoding="utf-8") as f:
            f.write(raw)

        print(f" applied grid {cols}x{rows}, group {gr}x{gc} "
              f"to params/volare_params.json")
        print(" now run:  python tools/build_mission_control.py")
        print("           matlab -batch TEST_ALL")
        print("           python tools/crosscheck.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
