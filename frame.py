"""Frame layout to ENERGY_REQ_38, and the floor panel that follows from it.

Note 05's sequencing puts this second, before anything else: "Fix the frame
layout... This changes the pod's boundary conditions, so the FE model is not
valid until it is frozen."

ENERGY_REQ_38, quoted in note 09 A2:

    "at least two clamps or jaws per beam, continuously enveloping the entire
     circumference of the beam, over a minimum width of 50 mm per clamp/jaw,
     installed symmetrically either side of the ship's centreline with a minimum
     spacing of 750 mm... rubber gasket... minimum thickness 1 mm."

The STL has them at 400 mm. Moving to 750 mm nearly doubles the floor span, and
sandwich deflection is dominated by the L^4 bending term, so the floor schedule
in note 03 no longer holds. This module sizes the fix and prices it in mass.

    python scripts/frame.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import volare as V

OUT = Path(__file__).resolve().parents[2] / "cad" / "out"

# --- materials, from note 03 / note 05 ---------------------------------------
E_SKIN = 10.0e9          # Pa, E-glass woven roving / polyester laminate
G_CORE = 20.0e6          # Pa, H60 PVC foam
E_CORE = 60.0e6          # Pa
TAU_CORE_ULT = 0.76e6    # Pa, H60 ultimate shear
TAU_CORE_ALLOW = 0.38e6  # Pa, FoS 2 per note 05
RHO_SKIN = 1800.0        # kg/m3, laminate at ~45% fibre by volume
RHO_CORE = 60.0          # kg/m3, H60

CORE_STOCK_MM = (10.0, 15.0, 20.0, 25.0, 30.0, 40.0)   # note 05: discrete stock
PLY_MM = 0.5             # one 600 gsm woven roving ply, wet layup

# --- load case LC-1, note 05 --------------------------------------------------
PILOT_KG = V.PILOT_DESIGN_KG
SLAM_G = V.SLAM_G
SEAT_PATCH_M2 = 0.60 * 0.45      # pilot bearing footprint on the floor
FLOOR_LENGTH_M = 1.20            # structural floor under the pilot, fore-aft

# ENERGY_REQ_38
CLAMP_MIN_SPACING = V.CLAMP_MIN_SPACING   # 750 mm
CLAMP_MIN_WIDTH = V.CLAMP_MIN_WIDTH       # 50 mm
GASKET_MIN_MM = 1.0


def pressure_Pa():
    """LC-1: pilot at 3g spread over the seat bearing patch."""
    return PILOT_KG * SLAM_G * 9.81 / SEAT_PATCH_M2


def panel_deflection(span_mm, core_mm, skin_mm, w_Pa=None, ends="simple"):
    """Sandwich strip of unit width under UDL: bending + core shear.

        d  = core + skin                     (centroid separation)
        D  = E_f * t_f * d^2 / 2             (flexural rigidity, thin faces)
        S  = G_c * d^2 / t_c                 (shear rigidity)

    Both terms matter here: at 400 mm span shear is a third of the total, and
    ignoring it is why a pure L^4 scaling argument overstates the penalty.
    """
    w = pressure_Pa() if w_Pa is None else w_Pa
    L = span_mm / 1000.0
    tf, tc = skin_mm / 1000.0, core_mm / 1000.0
    d = tc + tf
    D = E_SKIN * tf * d ** 2 / 2.0
    S = G_CORE * d ** 2 / tc
    kb, ks = (5.0 / 384.0, 1.0 / 8.0) if ends == "simple" else (1.0 / 384.0, 1.0 / 8.0)
    db = kb * w * L ** 4 / D
    ds = ks * w * L ** 2 / S
    # skin stress and core shear at midspan / support
    M = w * L ** 2 / (8.0 if ends == "simple" else 12.0)
    sigma = M / (tf * d)                       # per unit width
    tau = w * L / 2.0 / d
    # skin wrinkling, note 05 section 3
    sigma_wr = 0.5 * (E_SKIN * E_CORE * G_CORE) ** (1.0 / 3.0)
    return {"span_mm": span_mm, "core_mm": core_mm, "skin_mm": skin_mm,
            "deflection_mm": (db + ds) * 1000.0,
            "bending_mm": db * 1000.0, "shear_mm": ds * 1000.0,
            "shear_share": ds / (db + ds),
            "skin_stress_MPa": sigma / 1e6,
            "core_shear_MPa": tau / 1e6,
            "core_shear_ok": tau <= TAU_CORE_ALLOW,
            "wrinkling_FoS": sigma_wr / max(sigma, 1.0),
            "mass_kg_m2": 2 * skin_mm / 1000.0 * RHO_SKIN + core_mm / 1000.0 * RHO_CORE}


def limit_mm(span_mm, ratio=200.0):
    return span_mm / ratio


def size_floor(span_mm, ratio=200.0):
    """Lightest stock core + integer ply count meeting deflection, shear, wrinkling."""
    best = None
    for core in CORE_STOCK_MM:
        for nply in range(2, 13):
            r = panel_deflection(span_mm, core, nply * PLY_MM)
            if r["deflection_mm"] > limit_mm(span_mm, ratio):
                continue
            if not r["core_shear_ok"] or r["wrinkling_FoS"] < 2.0:
                continue
            r["plies_per_skin"] = nply
            if best is None or r["mass_kg_m2"] < best["mass_kg_m2"]:
                best = r
            break                      # thinner skins already failed at this core
    return best


def main():
    w = pressure_Pa()
    print("=" * 72)
    print("VOLARE FRAME LAYOUT TO ENERGY_REQ_38, AND THE FLOOR THAT FOLLOWS")
    print("=" * 72)

    print("\n1. CLAMP GEOMETRY")
    r = V.BASELINE["rail"]
    print(f"  as built            {r['spacing_cc']:.0f} mm apart  -> NON-COMPLIANT")
    print(f"  required            {CLAMP_MIN_SPACING:.0f} mm minimum, >= {CLAMP_MIN_WIDTH:.0f} mm wide each,")
    print(f"                      enveloping the full circumference, >= {GASKET_MIN_MM:.0f} mm gasket")
    print(f"  move each rail      {(CLAMP_MIN_SPACING - r['spacing_cc']) / 2:.0f} mm outboard, to Y = "
          f"+/-{CLAMP_MIN_SPACING / 2:.0f} mm")
    pod_half = V.BASELINE["pod"]["beam_max"] / 2
    print(f"\n  PACKAGING PROBLEM: the pod is only {V.BASELINE['pod']['beam_max']:.0f} mm wide "
          f"(+/-{pod_half:.0f} mm).")
    print(f"  Clamps at +/-{CLAMP_MIN_SPACING / 2:.0f} mm sit {CLAMP_MIN_SPACING / 2 - pod_half:.0f} mm "
          f"OUTBOARD of the pod's widest point, and")
    print(f"  the pod is narrower than that over most of its length. The clamps")
    print(f"  cannot be tucked under the floor - they need outboard brackets, or")
    print(f"  the floor has to widen locally at the two beam stations.")
    print(f"  Note 09 Q-TC-5 asks whether 750 mm is centre-to-centre or between")
    print(f"  inner faces. Inner-face would need {CLAMP_MIN_SPACING + CLAMP_MIN_WIDTH:.0f} mm centres - "
          f"ask before building.")

    print(f"\n2. FLOOR PANEL, LC-1 (pilot {PILOT_KG:.0f} kg at {SLAM_G:.0f}g)")
    print(f"  bearing patch {SEAT_PATCH_M2:.3f} m2 -> {w / 1000:.1f} kPa on the floor")
    print(f"  limit L/200\n")
    print(f"  {'span':>6}{'core':>6}{'skin':>6}{'defl':>8}{'limit':>7}"
          f"{'shear%':>8}{'sigma':>8}{'wrink':>7}{'kg/m2':>7}")
    print("  " + "-" * 66)
    for span, core, skin in ((400, 20, 1.5), (750, 20, 1.5), (750, 30, 2.5),
                             (750, 30, 3.0), (375, 20, 1.5)):
        d = panel_deflection(span, core, skin)
        flag = "" if d["deflection_mm"] <= limit_mm(span) else "  FAIL"
        print(f"  {span:>6}{core:>6}{skin:>6.1f}{d['deflection_mm']:>8.2f}"
              f"{limit_mm(span):>7.2f}{d['shear_share'] * 100:>8.0f}"
              f"{d['skin_stress_MPa']:>8.1f}{d['wrinkling_FoS']:>7.1f}"
              f"{d['mass_kg_m2']:>7.2f}{flag}")

    d400 = panel_deflection(400, 20, 1.5)
    d750 = panel_deflection(750, 20, 1.5)
    print(f"\n  Note 09 A2 calls this 'a 12.4x penalty' from the L^4 term, and its")
    print(f"  table shows 1.80 -> 9.20 mm, which is 5.1x, not 12.4x. Neither is")
    print(f"  right: core shear carries {d400['shear_share'] * 100:.0f}% of the deflection at 400 mm")
    print(f"  and only {d750['shear_share'] * 100:.0f}% at 750 mm, so the real ratio is "
          f"{d750['deflection_mm'] / d400['deflection_mm']:.1f}x")
    print(f"  ({d400['deflection_mm']:.2f} -> {d750['deflection_mm']:.2f} mm on the same schedule).")
    print(f"  The conclusion stands - the floor is under-built - but by less than")
    print(f"  note 09 says, and the fix is cheaper than its table implies.")

    print("\n3. THE THREE WAYS TO FIX IT")
    area = CLAMP_MIN_SPACING / 1000.0 * FLOOR_LENGTH_M
    area400 = 0.400 * FLOOR_LENGTH_M
    opts = []

    base = size_floor(400)
    if base:
        opts.append(("as-drawn 400 mm span (non-compliant, reference)",
                     base, area400, 0.0))

    a = size_floor(750)
    if a:
        opts.append(("A: 750 mm span, thicken the panel", a, area, 0.0))

    # keel beam halves the span; charge the beam itself
    b = size_floor(375)
    keel_kg = 1.9 * FLOOR_LENGTH_M          # 60x40x3 alu top-hat, ~1.9 kg/m
    if b:
        opts.append(("B: 750 mm span + centreline keel beam (span 375)",
                     b, area, keel_kg))

    # transverse frames at 400 mm pitch: same panel span athwartships, but the
    # fore-aft strip is then supported every 400 mm
    c = size_floor(400)
    frames_kg = 0.9 * (CLAMP_MIN_SPACING / 1000.0) * 3     # 3 frames across
    if c:
        opts.append(("C: 750 mm span + 3 transverse frames (span 400)",
                     c, area, frames_kg))

    print(f"  {'option':<48}{'core':>6}{'ply':>5}{'kg/m2':>7}{'panel':>8}{'+beam':>7}{'total':>8}")
    print("  " + "-" * 89)
    for name, r_, ar, extra in opts:
        panel = r_["mass_kg_m2"] * ar
        print(f"  {name:<48}{r_['core_mm']:>6.0f}{r_['plies_per_skin']:>5}"
              f"{r_['mass_kg_m2']:>7.2f}{panel:>8.2f}{extra:>7.2f}{panel + extra:>8.2f}")

    ref = opts[0][1]["mass_kg_m2"] * area400
    print(f"\n  Against the non-compliant as-drawn floor ({ref:.2f} kg):")
    for name, r_, ar, extra in opts[1:]:
        tot = r_["mass_kg_m2"] * ar + extra
        print(f"    {name.split(':')[0]:<3} {tot - ref:+6.2f} kg")

    ranked = sorted(opts[1:], key=lambda o: o[1]["mass_kg_m2"] * o[2] + o[3])
    best, second = ranked[0], ranked[1]
    gap = (second[1]["mass_kg_m2"] * second[2] + second[3]) - \
          (best[1]["mass_kg_m2"] * best[2] + best[3])
    print(f"\n  All three land within {(ranked[-1][1]['mass_kg_m2'] * ranked[-1][2] + ranked[-1][3]) - (best[1]['mass_kg_m2'] * best[2] + best[3]):.2f} kg of each other, and "
          f"B and C within {gap:.2f} kg -")
    print(f"  which is inside the precision of an areal-density estimate. Do NOT")
    print(f"  pick between B and C on mass. Decide on these instead:")
    print(f"    B (keel beam)      also carries the seat mount, gives one clean")
    print(f"                       centreline load path, and adds a bonding line")
    print(f"                       the moulder has to get straight.")
    print(f"    C (3 frames)       spreads load better into the shell but means")
    print(f"                       three more core-removal/insert details, which")
    print(f"                       is where note 05 s3 says student builds fail.")
    print(f"    A (thicken)        no new parts at all, +{(opts[1][1]['mass_kg_m2'] * opts[1][2]) - (best[1]['mass_kg_m2'] * best[2] + best[3]):.2f} kg over the lightest.")
    print(f"                       40 mm core is also 20 mm more pod depth to find.")
    print(f"\n  Whichever wins, budget about +{(best[1]['mass_kg_m2'] * best[2] + best[3]) - ref:.1f} kg against note 06's")
    print(f"  27 kg cockpit shell line - it does not currently carry this.")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "frame.json").write_text(json.dumps(
        {"pressure_Pa": w, "clamp_spacing_mm": CLAMP_MIN_SPACING,
         "options": [{"name": n, **r_, "area_m2": ar, "extra_kg": e,
                      "total_kg": r_["mass_kg_m2"] * ar + e} for n, r_, ar, e in opts]},
        indent=2, default=float))
    print(f"\nwrote {OUT / 'frame.json'}")


if __name__ == "__main__":
    main()
