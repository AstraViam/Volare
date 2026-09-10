"""Whole-boat drag/mass optimisation for the Volare cockpit.

The thing note 00 and note 01 do not do jointly: every fairing that removes
aerodynamic drag adds mass, and mass costs hull resistance. Note 01 section 3
gives the exchange rate for a planing hull at Fn_grad 6.6:

    dR = (R/W) * dW,   R/W ~ 0.10-0.12

So the objective is not drag, it is total resistance:

    R_eff = D_aero(x) + (R/W) * g * m_added(x)

Optimising drag alone drives every fairing to its slenderest, heaviest form. With
the mass term in, the answer moves - and it moves away from note 01's 4:1
recommendation.

    python scripts/optimise.py
    python scripts/optimise.py --pareto        # sweep the mass budget
"""
import json
import sys
from pathlib import Path

import numpy as np
# scipy is imported lazily inside solve(): Blender's bundled Python does not
# ship it, and the Blender scripts only need the MODEL (evaluate/COMPONENTS), not
# the solver. Keeping the import out of module scope lets them share this file.

sys.path.insert(0, str(Path(__file__).parent))
import aero
import parametric as PM
import volare as V

OUT = Path(__file__).resolve().parents[2] / "cad" / "out"
G = 9.81
R_OVER_W = 0.12          # planing-hull resistance/weight, note 01 section 3

# Fairing spans. The crossbeams are only worth fairing where they are in clear
# air; outboard of the inner hull faces they are in the hull's own blockage.
SPAN_BEAM = V.BASELINE["hull"]["clear_gap"]          # 1581 mm

# Packaging limits, from the measured layout.
CHORD_MAX_FWD = 700.0    # fwd pole sits under the pod nose; chord is boxed in
CHORD_MAX_AFT = 900.0    # aft pole is 1100 mm clear of the pod tail

# --- component drag endpoints -------------------------------------------------
# C_D at zero treatment -> C_D fully treated. The treated values are note 00's
# own optimised table, back-converted from its C_D.A entries.
COMPONENTS = {
    "pilot":    {"A": 0.150, "cd0": 0.90, "cd1": 0.060 / 0.150, "mass_kg": 2.9},
    "brackets": {"A": 0.072, "cd0": 1.10, "cd1": 0.022 / 0.072, "mass_kg": 0.8},
    "rails":    {"A": 0.028, "cd0": 0.90, "cd1": 0.004 / 0.028, "mass_kg": 1.5},
}

# Pod recontour: redistributing the aft body to hold <=12 deg without lengthening
# costs a little laminate. Areal density from note 03 (28.9 kg over 4.58 m2).
POD_AREAL_KG_M2 = 28.9 / 4.5803
POD_RECONTOUR_AREA_M2 = 0.15

VARS = [
    ("tc_fwd",  0.15, 0.55, "fwd beam fairing thickness ratio"),
    ("tc_aft",  0.15, 0.55, "aft beam fairing thickness ratio"),
    ("w_pilot", 0.0,  1.0,  "windscreen + shoulder fairing completeness"),
    ("w_brack", 0.0,  1.0,  "bracket blending completeness"),
    ("w_rail",  0.0,  1.0,  "rail fairing completeness"),
    ("closure", 8.0,  15.59, "pod aft closure angle, deg"),
]
BOUNDS = [(lo, hi) for _, lo, hi, _ in VARS]
NAMES = [n for n, _, _, _ in VARS]


def evaluate(x, r_over_w=None):
    """Design vector -> full breakdown. The single source of truth for the model.

    `r_over_w` is the hull resistance/weight exchange rate. Pass 0.0 to score a
    design as if mass were free - that is what optimising drag alone assumes.
    """
    r_over_w = R_OVER_W if r_over_w is None else r_over_w
    tc_f, tc_a, w_p, w_b, w_r, closure = x
    out = {"vars": dict(zip(NAMES, map(float, x))), "items": [], "infeasible": []}

    # --- crossbeam fairings ---------------------------------------------------
    for tag, tc, wake, cmax in (("beam_fwd", tc_f, 1.0, CHORD_MAX_FWD),
                                ("beam_aft", tc_a, 0.85, CHORD_MAX_AFT)):
        chord = PM.min_chord_for_pole(tc)
        f = aero.beam_fairing(tc, span_mm=SPAN_BEAM, wake=wake, chord_mm=chord)
        # violation in mm, kept as a smooth quantity so the polish step has a
        # differentiable surface to work on
        viol = max(0.0, chord - cmax)
        if viol > 0.0:
            out["infeasible"].append(f"{tag} chord {chord:.0f} > {cmax:.0f} mm")
        out["violation_mm"] = out.get("violation_mm", 0.0) + viol
        out["items"].append({"name": tag, "D_N": f["D_N"], "mass_kg": f["mass_kg"],
                             "chord_mm": chord, "C_D": f["C_D"]})

    # --- linearly-treated components -----------------------------------------
    for tag, w in (("pilot", w_p), ("brackets", w_b), ("rails", w_r)):
        c = COMPONENTS[tag]
        cd = c["cd0"] + w * (c["cd1"] - c["cd0"])
        out["items"].append({"name": tag, "D_N": cd * c["A"] * aero.Q,
                             "mass_kg": w * c["mass_kg"], "C_D": cd})

    # --- pod shell ------------------------------------------------------------
    b = V.BASELINE["pod"]
    frac = (15.59 - closure) / (15.59 - 8.0)
    extra_area = frac * POD_RECONTOUR_AREA_M2
    # Holding a shallower slope raises the tail and grows the base. Measured
    # relationship, not an assumption - see parametric.base_area_for_closure.
    p = aero.pod_shell_drag(b["frontal_m2"], b["surface_area_m2"] + extra_area,
                            closure, b["length"],
                            base_area_m2=PM.base_area_for_closure(closure))
    out["items"].append({"name": "pod_shell", "D_N": p["D_N"],
                         "mass_kg": extra_area * POD_AREAL_KG_M2, "C_D": p["C_D"]})

    out["D_N"] = sum(i["D_N"] for i in out["items"])
    out["mass_kg"] = sum(i["mass_kg"] for i in out["items"])
    out["R_mass_N"] = r_over_w * G * out["mass_kg"]
    out["R_eff_N"] = out["D_N"] + out["R_mass_N"]
    out["P_W"] = out["R_eff_N"] * aero.VD
    return out


def objective(x, r_over_w=None):
    """Smooth, always-finite. A step penalty makes trust-constr's Hessian blow up."""
    r = evaluate(x, r_over_w)
    v = r.get("violation_mm", 0.0)
    val = r["R_eff_N"] + 0.05 * v + 1e-3 * v ** 2
    return val if np.isfinite(val) else 1e9


def mass_of(x):
    return evaluate(x)["mass_kg"]


def solve(mass_budget=None, r_over_w=None, seed=1, maxiter=400):
    from scipy.optimize import differential_evolution, NonlinearConstraint
    cons = ()
    if mass_budget is not None:
        cons = (NonlinearConstraint(mass_of, -np.inf, mass_budget),)
    # polish uses trust-constr when constraints are present, and that needs a
    # smooth objective; DE alone is accurate enough here with a 6-variable space
    res = differential_evolution(lambda x: objective(x, r_over_w), BOUNDS,
                                 seed=seed, maxiter=maxiter, tol=1e-8,
                                 polish=(mass_budget is None), constraints=cons)
    return res.x, evaluate(res.x)


def baseline_untreated():
    """Everything bare: the corrected round-pole baseline, no fairings, no mass."""
    rows, _ = aero.corrected_baseline(shadowed=True)
    tab, tot = aero.budget(rows)
    return tot


def show(title, r):
    print(f"\n{title}")
    print(f"  {'item':<12}{'C_D':>8}{'D  N':>9}{'mass kg':>10}{'chord mm':>10}")
    print("  " + "-" * 49)
    for i in r["items"]:
        chord = f"{i['chord_mm']:>10.0f}" if "chord_mm" in i else f"{'-':>10}"
        print(f"  {i['name']:<12}{i['C_D']:>8.3f}{i['D_N']:>9.1f}"
              f"{i['mass_kg']:>10.2f}{chord}")
    print("  " + "-" * 49)
    print(f"  {'TOTAL':<12}{'':>8}{r['D_N']:>9.1f}{r['mass_kg']:>10.2f}")
    print(f"  aero drag        {r['D_N']:>8.1f} N")
    print(f"  mass penalty     {r['R_mass_N']:>8.1f} N  "
          f"({r['mass_kg']:.2f} kg x {R_OVER_W} x g)")
    print(f"  EFFECTIVE TOTAL  {r['R_eff_N']:>8.1f} N   -> {r['P_W'] / 1000:.2f} kW")
    if r["infeasible"]:
        print(f"  INFEASIBLE: {'; '.join(r['infeasible'])}")


def main():
    pareto = "--pareto" in sys.argv
    base = baseline_untreated()
    print(f"Volare cockpit optimisation   V = {aero.VD} m/s, q = {aero.Q:.1f} Pa")
    print(f"exchange rate: 1 kg of fairing = {R_OVER_W * G:.2f} N of hull resistance"
          f"  (R/W = {R_OVER_W}, note 01 s3)")
    print(f"\nBARE BASELINE (round poles, nothing faired): {base['D_N']:.1f} N "
          f"-> {base['P_W'] / 1000:.2f} kW")

    # 1. drag-only optimum, the answer note 00/01 implicitly gives
    x_d, _ = solve(r_over_w=0.0)
    r_d = evaluate(x_d)                       # re-score with mass counted
    show("1. DRAG-ONLY OPTIMUM, re-scored with the mass penalty applied", r_d)

    # 2. the real optimum
    x_o, r_o = solve()
    show("2. DRAG + MASS OPTIMUM", r_o)

    print("\nDESIGN VARIABLES")
    print(f"  {'variable':<10}{'drag-only':>11}{'drag+mass':>11}   description")
    for i, (n, lo, hi, desc) in enumerate(VARS):
        print(f"  {n:<10}{x_d[i]:>11.3f}{x_o[i]:>11.3f}   {desc}")

    print(f"\n  effective resistance  drag-only {r_d['R_eff_N']:.1f} N   "
          f"drag+mass {r_o['R_eff_N']:.1f} N   "
          f"({r_d['R_eff_N'] - r_o['R_eff_N']:+.1f} N by accounting for mass)")
    print(f"  added mass            drag-only {r_d['mass_kg']:.2f} kg   "
          f"drag+mass {r_o['mass_kg']:.2f} kg")
    print(f"  saving vs bare        {base['D_N'] - r_o['R_eff_N']:.1f} N "
          f"= {(base['D_N'] - r_o['R_eff_N']) * aero.VD / 1000:.2f} kW "
          f"({(1 - r_o['R_eff_N'] / base['D_N']) * 100:.0f}%)")

    report = {"baseline_bare_N": base["D_N"],
              "drag_only": {"x": list(map(float, x_d)), **{k: v for k, v in r_d.items() if k != "items"}},
              "drag_plus_mass": {"x": list(map(float, x_o)), **{k: v for k, v in r_o.items() if k != "items"}},
              "exchange_rate_N_per_kg": R_OVER_W * G}

    if pareto:
        print("\n3. PARETO FRONT - effective resistance vs added-mass budget")
        print(f"  {'budget kg':>10}{'mass kg':>9}{'D aero N':>10}{'R_eff N':>10}"
              f"{'tc_fwd':>8}{'tc_aft':>8}")
        front = []
        for mb in (0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15):
            xm, rm = solve(mass_budget=mb, maxiter=250)
            front.append({"budget_kg": mb, **{k: v for k, v in rm.items() if k != "items"}})
            print(f"  {mb:>10.1f}{rm['mass_kg']:>9.2f}{rm['D_N']:>10.1f}"
                  f"{rm['R_eff_N']:>10.1f}{xm[0]:>8.3f}{xm[1]:>8.3f}")
        report["pareto"] = front

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "optimisation.json").write_text(json.dumps(report, indent=2, default=float))
    print(f"\nwrote {OUT / 'optimisation.json'}")


if __name__ == "__main__":
    main()
