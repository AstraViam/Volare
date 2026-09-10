"""Component drag model for the Volare cockpit - the objective function.

Two jobs:

1. Reproduce note 00 section 2's drag budget exactly, so the model is anchored
   to the number the team already agreed on.
2. Correct it. Note 00 charges the crossbeams C_D = 2.05, the value for a SQUARE
   section in crossflow, because the STL models them as 104 x 104 boxes. But
   ENERGY_REQ_3 supplies ROUND carbon poles of diameter 104 mm. A circular
   cylinder at Re = 1.06e5 is subcritical, C_D ~ 1.2. That is a 41% overcharge on
   the single biggest item in the budget.

Everything is C_D referred to frontal area: D = C_D * A * q.
"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import volare as V

Q = V.Q_DESIGN          # 143.0 Pa
VD = V.V_DESIGN         # 15.28 m/s
NU = V.NU_AIR


# ------------------------------------------------------------ drag primitives

def cf_turbulent(Re):
    """Flat-plate mean skin friction, Prandtl-Schlichting power law."""
    return 0.074 / np.maximum(Re, 1e4) ** 0.2


def cd_cylinder(Re):
    """Smooth circular cylinder in crossflow, C_D on frontal area.

    Piecewise fit to the standard experimental curve. The drag crisis sits at
    Re ~ 2e5; we run at 1.06e5, comfortably subcritical, so C_D ~ 1.2.
    """
    Re = np.asarray(Re, float)
    return np.where(Re < 1.0e5, 1.15,
           np.where(Re < 2.0e5, 1.2,
           np.where(Re < 4.0e5, 0.6, 0.4)))


CD_SQUARE_CROSSFLOW = 2.05      # sharp-edged square section, the note 00 value


def cd_streamlined_strut(t_over_c, Re_c):
    """Hoerner streamline-strut drag, C_D on FRONTAL area.

        C_D = 2 C_f (c/t) [1 + 2(t/c) + 60(t/c)^4]

    The bracket is form drag; the (c/t) factor converts wetted to frontal.
    Valid for attached flow, i.e. t/c up to about 0.35.
    """
    t_over_c = np.asarray(t_over_c, float)
    return 2.0 * cf_turbulent(Re_c) / t_over_c * (
        1.0 + 2.0 * t_over_c + 60.0 * t_over_c ** 4)


def reynolds(length_m, v=VD):
    return v * length_m / NU


# ----------------------------------------------------- note 00 baseline budget

NOTE00_BASELINE = [
    # name,                       A [m2], C_D
    ("crossbeam fwd (square)",     0.239, 2.05),
    ("crossbeam aft (0.85 wake)",  0.239, 1.74),
    ("exposed pilot + cavity",     0.150, 0.90),
    ("corner brackets x4",         0.072, 1.10),
    ("pod shell",                  0.279, 0.12),
    ("rails x2 (blunt face)",      0.028, 0.90),
]

NOTE00_OPTIMISED = [
    ("faired crossbeams",          None,  None, 0.028),
    ("pilot behind windscreen",    None,  None, 0.060),
    ("pod shell recontoured",      None,  None, 0.028),
    ("blended brackets",           None,  None, 0.022),
    ("faired rails",               None,  None, 0.004),
]


def budget(rows):
    """rows of (name, A, C_D) -> list with C_D.A and D, plus totals."""
    out = []
    for name, A, cd in rows:
        cda = A * cd
        out.append({"name": name, "A_m2": A, "C_D": cd,
                    "CDA_m2": cda, "D_N": cda * Q})
    tot_cda = sum(r["CDA_m2"] for r in out)
    return out, {"CDA_m2": tot_cda, "D_N": tot_cda * Q, "P_W": tot_cda * Q * VD}


# ------------------------------------------------- corrected baseline (round poles)

def exposed_beam_area(length_mm, dia_mm=V.BEAM_DIAMETER, shadowed=True):
    """Frontal area of a crossbeam.

    `shadowed=True` charges only the span in clear air between the demihulls;
    the outboard ends sit in the hull's own blockage. That is the physically
    right call but it is an assumption, so both numbers are reported.
    """
    L = V.BASELINE["hull"]["clear_gap"] if shadowed else length_mm
    return L * dia_mm / 1e6


def corrected_baseline(shadowed=True):
    """The note 00 budget with the beams re-charged as round poles."""
    Re_beam = reynolds(V.BEAM_DIAMETER / 1000.0)
    cd_b = float(cd_cylinder(Re_beam))
    a_fwd = exposed_beam_area(V.BASELINE["beam_fwd"]["length"], shadowed=shadowed)
    a_aft = exposed_beam_area(V.BASELINE["beam_aft"]["length"], shadowed=shadowed)
    rows = [
        ("crossbeam fwd (round D104)", a_fwd, cd_b),
        ("crossbeam aft (0.85 wake)",  a_aft, cd_b * 0.85),
        ("exposed pilot + cavity",     0.150, 0.90),
        ("corner brackets x4",         0.072, 1.10),
        # pod frontal re-measured from the STL, note 00 used 0.279
        ("pod shell",                  V.BASELINE["pod"]["frontal_m2"], 0.12),
        ("rails x2 (blunt face)",      0.028, 0.90),
    ]
    return rows, {"Re_beam": Re_beam, "cd_cylinder": cd_b}


# ------------------------------------------------------------- design variables

def beam_fairing(t_over_c, dia_mm=V.BEAM_DIAMETER, span_mm=None, wake=1.0,
                 chord_mm=None):
    """Drag of one faired crossbeam.

    Chord defaults to the SMALLEST one that actually swallows the pole with
    clearance, which is about 12% longer than the naive dia/(t/c). A consequence
    worth noticing: since chord ~ 1.12 D/(t/c), the section thickness comes out at
    ~1.12 D whatever t/c you pick, so the frontal area is fixed and t/c buys you
    nothing but a longer, heavier chord.
    """
    import parametric as PM
    span_mm = span_mm if span_mm is not None else V.BASELINE["hull"]["clear_gap"]
    if chord_mm is None:
        chord_mm = PM.min_chord_for_pole(t_over_c, dia_mm)
    t_mm = t_over_c * chord_mm
    cd = float(cd_streamlined_strut(t_over_c, reynolds(chord_mm / 1000.0))) * wake
    A = span_mm * t_mm / 1e6            # frontal area of the FAIRING, not the pole
    return {"t_over_c": t_over_c, "chord_mm": chord_mm, "thickness_mm": t_mm,
            "C_D": cd, "A_m2": A, "CDA_m2": cd * A, "D_N": cd * A * Q,
            "mass_kg": PM.fairing_mass_kg(t_over_c, chord_mm, span_mm)}


# Sharp-edged 3D base, flow attached up to it. Hoerner's range for this is
# roughly 0.15-0.25 on base area; note 01 s4.4 adds ~30% if the truncation is
# rounded rather than sharp, which is why it insists on a sharp base.
CD_BASE_SHARP = 0.20


def pod_shell_drag(frontal_m2, wetted_m2, closure_deg, length_mm,
                   base_area_m2=None):
    """Pod shell drag: friction + separation penalty + base drag.

    Below the note 01 s4.2 threshold the aft body stays attached and the shell is
    essentially a friction-drag body. Past it, separation adds pressure drag; the
    penalty is a smooth ramp calibrated so the as-built 15.6 deg pod lands on the
    C_D = 0.12 that note 00 charges it.
    """
    Re_L = reynolds(length_mm / 1000.0)
    cd_fric = cf_turbulent(Re_L) * wetted_m2 / frontal_m2
    excess = max(0.0, closure_deg - 12.0)
    cd_sep = SEP_PENALTY * excess ** 2
    # Base drag is referenced to base area, not frontal area, so convert.
    cd_base = (CD_BASE_SHARP * base_area_m2 / frontal_m2) if base_area_m2 else 0.0
    cd = cd_fric + cd_sep + cd_base
    return {"C_D": cd, "C_D_friction": float(cd_fric), "C_D_separation": float(cd_sep),
            "C_D_base": float(cd_base), "base_area_m2": base_area_m2,
            "A_m2": frontal_m2, "CDA_m2": cd * frontal_m2, "D_N": cd * frontal_m2 * Q}


def _calibrate_sep_penalty():
    """Pick SEP_PENALTY so the as-built pod reproduces note 00's C_D = 0.12."""
    b = V.BASELINE["pod"]
    Re_L = reynolds(b["length"] / 1000.0)
    cd_fric = cf_turbulent(Re_L) * b["surface_area_m2"] / b["frontal_m2"]
    excess = 15.59 - 12.0
    return max(0.0, (0.12 - cd_fric)) / excess ** 2


SEP_PENALTY = 0.0            # placeholder, set immediately below
SEP_PENALTY = _calibrate_sep_penalty()


# ------------------------------------------------------------------- reporting

def show(title, rows, note=None):
    tab, tot = budget(rows)
    print(f"\n{title}")
    print(f"  {'item':<30}{'A m2':>8}{'C_D':>8}{'C_D.A':>9}{'D  N':>9}")
    print("  " + "-" * 64)
    for r in tab:
        print(f"  {r['name']:<30}{r['A_m2']:>8.3f}{r['C_D']:>8.2f}"
              f"{r['CDA_m2']:>9.3f}{r['D_N']:>9.1f}")
    print("  " + "-" * 64)
    print(f"  {'TOTAL':<30}{'':>8}{'':>8}{tot['CDA_m2']:>9.3f}{tot['D_N']:>9.1f}"
          f"   -> {tot['P_W'] / 1000:.2f} kW")
    if note:
        print(f"  {note}")
    return tot


def main():
    print(f"Volare drag model   V = {VD} m/s, q = {Q:.1f} Pa, rho = {V.RHO_AIR}")

    t0 = show("1. NOTE 00 BASELINE, reproduced", NOTE00_BASELINE)
    # note 00 totals its already-rounded per-row C_D.A values, which lands on
    # 1.181 / 168.8 N; summing unrounded gives 1.179 / 168.6 N. Same budget.
    ok = abs(t0["CDA_m2"] - 1.181) < 0.005 and abs(t0["D_N"] - 168.8) < 0.8
    print(f"  {'OK  ' if ok else 'FAIL'} matches note 00 (1.181, 168.8 N, 2.58 kW) "
          f"to within its own row rounding")

    rows, info = corrected_baseline(shadowed=True)
    t1 = show(f"2. CORRECTED BASELINE - round poles, Re_beam = {info['Re_beam']:.2e}, "
              f"C_D = {info['cd_cylinder']:.2f}", rows)
    rows_u, _ = corrected_baseline(shadowed=False)
    t1u = show("3. CORRECTED, charging the FULL beam span (no hull shadowing)", rows_u)

    print(f"\nEFFECT OF THE ROUND-POLE CORRECTION")
    print(f"  note 00              C_D.A {t0['CDA_m2']:.3f}   D {t0['D_N']:.1f} N   "
          f"P {t0['P_W'] / 1000:.2f} kW")
    print(f"  round, shadowed span C_D.A {t1['CDA_m2']:.3f}   D {t1['D_N']:.1f} N   "
          f"P {t1['P_W'] / 1000:.2f} kW   ({(t1['D_N'] / t0['D_N'] - 1) * 100:+.0f}%)")
    print(f"  round, full span     C_D.A {t1u['CDA_m2']:.3f}   D {t1u['D_N']:.1f} N   "
          f"P {t1u['P_W'] / 1000:.2f} kW   ({(t1u['D_N'] / t0['D_N'] - 1) * 100:+.0f}%)")

    beam_share_00 = (NOTE00_BASELINE[0][1] * NOTE00_BASELINE[0][2] +
                     NOTE00_BASELINE[1][1] * NOTE00_BASELINE[1][2]) / t0["CDA_m2"]
    beam_share_1 = (rows[0][1] * rows[0][2] + rows[1][1] * rows[1][2]) / t1["CDA_m2"]
    print(f"\n  beams as a share of total drag:  note 00 {beam_share_00 * 100:.0f}%"
          f"   ->  corrected {beam_share_1 * 100:.0f}%")
    print("  The beams are still the number one item, so note 00's priority order")
    print("  survives - but the headline saving is smaller than 88%.")

    # --- fairing sweep, the actual design variable -----------------------------
    print("\n4. BEAM FAIRING SWEEP (both beams, aft charged a 0.85 wake factor)")
    print(f"  {'t/c':>6}{'chord mm':>10}{'thick mm':>10}{'C_D':>8}"
          f"{'D both N':>10}{'saved N':>9}{'mass kg':>9}")
    base_beams = rows[0][1] * rows[0][2] * Q + rows[1][1] * rows[1][2] * Q
    for tc in (0.50, 0.40, 0.333, 0.30, 0.25, 0.20, 0.167):
        f = beam_fairing(tc)
        fa = beam_fairing(tc, wake=0.85)
        d = f["D_N"] + fa["D_N"]
        m = f["mass_kg"] + fa["mass_kg"]
        print(f"  {tc:>6.3f}{f['chord_mm']:>10.0f}{f['thickness_mm']:>10.1f}"
              f"{f['C_D']:>8.4f}{d:>10.1f}{base_beams - d:>9.1f}{m:>9.2f}")
    print(f"  bare round poles: {base_beams:.1f} N")
    print("  note 00 assumed a 4:1 fairing (t/c = 0.25) giving 3.9 N for the pair.")
    print("  Drag alone keeps pushing t/c down; mass pushes back. See optimise.py.")

    # --- pod shell, the low-value item ----------------------------------------
    print("\n5. POD SHELL vs AFT CLOSURE ANGLE")
    b = V.BASELINE["pod"]
    print(f"  {'closure deg':>12}{'C_D':>8}{'D N':>8}{'vs as-built':>13}")
    d0 = pod_shell_drag(b["frontal_m2"], b["surface_area_m2"], 15.59, b["length"])["D_N"]
    for cl in (15.59, 14.0, 12.0, 10.0, 8.0):
        r = pod_shell_drag(b["frontal_m2"], b["surface_area_m2"], cl, b["length"])
        print(f"  {cl:>12.2f}{r['C_D']:>8.4f}{r['D_N']:>8.1f}{d0 - r['D_N']:>12.1f} N")
    print(f"  friction floor C_D = {pod_shell_drag(b['frontal_m2'], b['surface_area_m2'], 0, b['length'])['C_D']:.4f}")
    print("  Fixing the pod aft body completely is worth ~"
          f"{d0 - pod_shell_drag(b['frontal_m2'], b['surface_area_m2'], 12.0, b['length'])['D_N']:.1f} N"
          f" = {(d0 - pod_shell_drag(b['frontal_m2'], b['surface_area_m2'], 12.0, b['length'])['D_N']) * VD:.0f} W.")
    print("  Confirms note 00: do the fairings first, the pod contour last.")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
