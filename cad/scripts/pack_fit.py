"""
pack_fit.py -- which pack grid arrangements actually fit the boat?

    python scripts/pack_fit.py

The 26S21P pack is 546 cells in 26 groups of 21, stacked two layers deep and
laid out on a 4 x 4 grid of group slots. That grid makes the pack 687 x 311 mm,
and its container 757 x 381 x 218.

The container does not fit.

    the pod is 218 mm tall or more only forward of X = -550
    ENERGY_REQ_50 puts the bulkhead at X = 120, and HV must stay aft of it
    so the container has 670 mm of usable length, and it is 757 mm long

That is not a placement problem a solver can work around -- it is 87 mm of
length that does not exist. The grid has to change.

WHAT THIS SWEEPS
----------------
Every rows x columns grid that can hold the required number of group slots,
with the cell, the group and the clearances held fixed. Changing the grid
changes only how the 26 groups are ARRANGED; it does not change the cell
count, the series count, the stored energy or the compliance position on
ENERGY_REQ_7.

What it does change is the series path length, and therefore the interconnect
resistance -- so a grid that fits the boat but doubles the busbar loss is not
an improvement. Both are reported.

WHAT IT DOES NOT DECIDE
-----------------------
Cooling. The end-plate architecture assumes two layers with three cold plates,
and a grid that changes the plate area changes the thermal answer. Any grid
this recommends has to go back through P50B_ThermalDesign before it is real.
"""

from __future__ import annotations

import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pod_envelope import Envelope       # noqa: E402
import powertrain as PT                 # noqa: E402


def pack_size_mm(P: dict, grid_rows: int, grid_cols: int) -> np.ndarray:
    """External container-less pack envelope for a given group grid.

    Mirrors P50B_Geometry's arithmetic for the grid only. The group itself,
    the cell pitch and the enclosure allowances are unchanged, so this is a
    rearrangement rather than a redesign -- which is why it is safe to
    compute here rather than round-tripping through MATLAB for every
    candidate.
    """
    cell = P["cell"]
    pack = P["pack"]

    pitch = (cell["diameter_m"] + pack["cell_clearance_m"]) * 1000.0

    grp_w = pack["group_cols"] * pitch
    grp_d = pack["group_rows"] * pitch

    cells_w = grid_cols * (grp_w + pack["group_clearance_x_m"] * 1000.0) \
        - pack["group_clearance_x_m"] * 1000.0
    cells_d = grid_rows * (grp_d + pack["group_clearance_y_m"] * 1000.0) \
        - pack["group_clearance_y_m"] * 1000.0

    cells_h = (pack["n_layers"] * cell["height_m"] * 1000.0
               + (pack["n_layers"] - 1) * pack["layer_gap_m"] * 1000.0)

    wall = pack["enclosure_wall_m"] * 1000.0
    clear = pack["enclosure_clear_m"] * 1000.0

    return np.array([
        cells_w + 2 * (wall + clear),
        cells_d + 2 * (wall + clear),
        cells_h + pack["enclosure_lid_m"] * 1000.0
        + pack["enclosure_base_m"] * 1000.0 + 2 * clear,
    ])


def series_path_mm(P: dict, grid_rows: int, grid_cols: int,
                   n_groups: int) -> float:
    """Boustrophedon path through the occupied slots, both layers.

    The interconnect follows the groups in series order, so the path length
    is what the busbars have to span. A tall narrow grid has a longer path
    than a square one and pays for it in resistance.
    """
    pack = P["pack"]
    pitch = (P["cell"]["diameter_m"] + pack["cell_clearance_m"]) * 1000.0

    px = pack["group_cols"] * pitch + pack["group_clearance_x_m"] * 1000.0
    py = pack["group_rows"] * pitch + pack["group_clearance_y_m"] * 1000.0

    per_layer = int(np.ceil(n_groups / pack["n_layers"]))

    pts = []
    for i in range(per_layer):
        r, c = divmod(i, grid_cols)
        if r % 2:
            c = grid_cols - 1 - c
        pts.append((c * px, r * py))

    pts = np.array(pts, float)

    if len(pts) < 2:
        return 0.0

    step = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))

    # Both layers in series, plus the link between them.
    return step * pack["n_layers"] + py


def evaluate(P: dict, env: Envelope, grid_rows: int, grid_cols: int) -> dict:
    """Does this grid's container fit aft of the bulkhead?"""
    pt = P["powertrain"]

    pack = pack_size_mm(P, grid_rows, grid_cols)

    wall = pt["pack_container_wall_mm"]
    container = pack + 2 * wall + np.array([40.0, 40.0, 30.0])

    x_max = min(pt["bulkhead_x_mm"],
                pt["pilot_seat_x_mm"] - P["rules"]["container_min_from_pilot_mm"])

    # Slide the container aft from the limit and take the first position
    # that fits. Aft is preferred: it moves mass away from the pilot and
    # leaves the cockpit clear.
    best = None

    for x_fwd in np.arange(x_max, x_max - 700.0, -5.0):
        c = np.array([x_fwd - container[0] / 2.0, 0.0, 0.0])
        x0 = c[0] - container[0] / 2.0

        if x0 < env.x_min:
            break

        hw, floor, crown = env.slot(x0, x_fwd)

        if hw <= 0 or (crown - floor) < container[2]:
            continue
        if container[1] / 2.0 > hw:
            continue

        c[2] = floor + container[2] / 2.0
        ok, _ = env.fits(c, container)

        if ok:
            best = c
            break

    n_groups = int(P["pack"]["n_series"])
    slots = grid_rows * grid_cols * P["pack"]["n_layers"]

    return dict(
        rows=grid_rows, cols=grid_cols,
        slots_per_layer=grid_rows * grid_cols,
        total_slots=slots,
        spare_slots=slots - n_groups,
        pack_mm=pack, container_mm=container,
        fits=best is not None,
        centre=best,
        path_mm=series_path_mm(P, grid_rows, grid_cols, n_groups),
    )


def main() -> int:
    P = PT.load_params()
    env = Envelope.load()

    n_groups = int(P["pack"]["n_series"])
    layers = int(P["pack"]["n_layers"])

    need_per_layer = int(np.ceil(n_groups / layers))

    rows = []

    for r, c in itertools.product(range(1, 9), range(1, 9)):
        if r * c < need_per_layer:
            continue
        if r * c > need_per_layer + 6:      # absurdly wasteful grids
            continue
        rows.append(evaluate(P, env, r, c))

    current = (int(P["pack"]["grid_rows"]), int(P["pack"]["grid_cols"]))

    base = next((x for x in rows
                 if (x["rows"], x["cols"]) == current), None)

    base_path = base["path_mm"] if base else None

    print()
    print("=" * 78)
    print(" PACK GRID -- WHAT FITS THE BOAT")
    print("=" * 78)
    print(f" {n_groups} groups over {layers} layers, so {need_per_layer} "
          f"slots per layer are needed")
    print(f" container must fit aft of X = "
          f"{min(P['powertrain']['bulkhead_x_mm'], P['powertrain']['pilot_seat_x_mm'] - P['rules']['container_min_from_pilot_mm']):.0f} mm "
          f"(ENERGY_REQ_50 and 25)")
    print("=" * 78)

    print(f"\n {'grid':>7}{'spare':>7}{'container mm':>22}{'path mm':>10}"
          f"{'vs now':>9}  fit")

    rows.sort(key=lambda x: (not x["fits"], x["path_mm"]))

    for x in rows:
        tag = "  <- current" if (x["rows"], x["cols"]) == current else ""
        cm = (f"{x['container_mm'][0]:.0f}x{x['container_mm'][1]:.0f}"
              f"x{x['container_mm'][2]:.0f}")

        if base_path:
            rel = f"{100*(x['path_mm']/base_path - 1):+.0f}%"
        else:
            rel = "-"

        print(f" {x['rows']}x{x['cols']:<5}{x['spare_slots']:>7}{cm:>22}"
              f"{x['path_mm']:>10.0f}{rel:>9}  "
              f"{'yes' if x['fits'] else 'NO'}{tag}")

    good = [x for x in rows if x["fits"]]

    print()
    print("=" * 78)

    if base and not base["fits"]:
        print(f" The current {current[0]}x{current[1]} grid does NOT fit.")
        cm = base["container_mm"]
        print(f" Its container is {cm[0]:.0f} mm long and there are only "
              f"{670:.0f} mm")
        print(f" of pod that is both tall enough and aft of the bulkhead.")

    if good:
        best = min(good, key=lambda x: x["path_mm"])
        print(f"\n Shortest series path among grids that fit: "
              f"{best['rows']}x{best['cols']}")
        cm = best["container_mm"]
        print(f"   container {cm[0]:.0f} x {cm[1]:.0f} x {cm[2]:.0f} mm, "
              f"centred at X = {best['centre'][0]:.0f} mm")
        print(f"   series path {best['path_mm']:.0f} mm", end="")
        if base_path:
            print(f", {100*(best['path_mm']/base_path - 1):+.0f}% against "
                  f"the current grid")
        else:
            print()
        print(f"   {best['spare_slots']} spare slot(s) for the BMS, "
              f"contactor and fuse")
        print()
        print(" Changing the grid changes the series path and therefore the")
        print(" interconnect resistance, and it changes the cold-plate area.")
        print(" Rerun P50B_Busbars and P50B_ThermalDesign before adopting it.")
    else:
        print("\n NO grid in the swept range fits. The pack has to get")
        print(" smaller, the bulkhead has to move, or the pod has to change.")

    print("=" * 78)

    out = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "out", "pack_fit.json")

    with open(out, "w", encoding="utf-8") as f:
        json.dump([{k: (list(map(float, v)) if isinstance(v, np.ndarray)
                        else (float(v) if isinstance(v, (np.floating,))
                              else v))
                    for k, v in x.items() if k != "centre"}
                   | {"centre": (list(map(float, x["centre"]))
                                 if x["centre"] is not None else None)}
                   for x in rows], f, indent=1)

    print(f"\n written {out}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
