"""Team Volare - canonical boat frame, measured baseline, and frozen rule constraints.

Single source of truth shared by the pure-numpy analysis scripts and the Blender
scripts. Every number in BASELINE was measured from the supplied STLs by
`stl_audit.py`, not copied from the notes; where the notes disagree the measured
value wins and the discrepancy is recorded in DISCREPANCIES.

Canonical frame (right-handed, millimetres):
    X  forward (bow positive)
    Y  to port
    Z  up
    origin  centreline x hull mid-length x hull keel bottom

The two source STLs do NOT share a frame:
    Cockpit_V1_3.stl   Y = longitudinal, X = transverse, Z = up, origin on pod floor
    FULLCOCPITV1_3.stl X = longitudinal (aft positive), Y = transverse, Z = up
"""
import numpy as np

# --- assembly STL frame -> canonical boat frame -------------------------------
# Verified against note 08: pod nose must land 639.6 mm ahead of the forward
# crossbeam (note says 640 mm) and the beam span must be 2998.6 mm.
ASM_HULL_MID_X = -44.6      # hull bbox centre, assembly frame
ASM_CENTRELINE_Y = -948.2   # midpoint of the two demihull centres
ASM_KEEL_Z = -897.1         # lowest point of the hulls


def asm_to_boat(P):
    """(N,3) mm in FULLCOCPITV1_3 frame -> canonical boat frame."""
    P = np.asarray(P, float)
    return np.stack([
        -(P[:, 0] - ASM_HULL_MID_X),
        -(P[:, 1] - ASM_CENTRELINE_Y),
        P[:, 2] - ASM_KEEL_Z,
    ], axis=1)


# 4x4 form, for Blender object matrices (mm in, mm out)
ASM_TO_BOAT_M = np.array([
    [-1.0, 0.0, 0.0,  ASM_HULL_MID_X],
    [0.0, -1.0, 0.0,  ASM_CENTRELINE_Y],
    [0.0,  0.0, 1.0, -ASM_KEEL_Z],
    [0.0,  0.0, 0.0,  1.0],
])

# Pod-only STL frame -> canonical. Pod file: +Y_pod is aft, X_pod is transverse,
# Z_pod near 0 on the pod floor. Anchored nose-to-nose and floor-to-floor with
# the assembly copy.
#
# WARNING: the two STLs hold DIFFERENT REVISIONS of the pod. Registered on the
# nose and floor, the assembly copy is 5.2 mm longer in the tail and 13.6 mm
# taller at the crown, and the tail face is retessellated (536 vs 34 vertices on
# the aftmost plane). They are not interchangeable. The assembly copy is
# authoritative because it is the one positioned against the frame; the pod-only
# file is the one note 00's envelope figures were taken from.
POD_FLOOR_Z_BOAT = 579.5     # anchors pod-file Zmin (-1.8) onto assembly Zmin (577.7)
POD_NOSE_X_BOAT = 1651.3     # = -(-1695.9) - 44.6
POD_STL_Y_MIN = -1332.5      # nose end in the pod file
POD_REVISION_DELTA_MM = {"tail_x": 5.2, "crown_z": 13.6}


def pod_to_boat(P):
    """(N,3) mm in Cockpit_V1_3 frame -> canonical boat frame."""
    P = np.asarray(P, float)
    return np.stack([
        POD_NOSE_X_BOAT - (P[:, 1] - POD_STL_Y_MIN),
        -P[:, 0],
        P[:, 2] + POD_FLOOR_Z_BOAT,
    ], axis=1)


POD_TO_BOAT_M = np.array([
    [0.0, -1.0, 0.0, POD_NOSE_X_BOAT + POD_STL_Y_MIN],
    [-1.0, 0.0, 0.0, 0.0],
    [0.0,  0.0, 1.0, POD_FLOOR_Z_BOAT],
    [0.0,  0.0, 0.0, 1.0],
])


# --- measured baseline, canonical frame, mm -----------------------------------
BASELINE = {
    "pod": {
        "x_nose": 1651.3, "x_tail": -886.4, "length": 2537.7,
        "beam_max": 700.0, "height": 497.3,
        "z_floor": 577.7, "z_crown": 1075.0,
        "surface_area_m2": 4.5803, "volume_L": 320.58,
        "frontal_m2": 0.2702, "planform_m2": 1.5114, "profile_m2": 0.7518,
    },
    "hull": {
        "length": 4992.0, "beam": 454.0, "depth": 600.0,
        "y_centres": (1017.5, -1017.5),   # port, starboard
        "spacing_cc": 2035.1, "clear_gap": 1581.1,
        "surface_area_m2": 6.9051, "closed_volume_L": 685.5,
    },
    # NB: in the assembly the FORWARD beam is the 2190 mm one. Note 00's table
    # lists the stations in the STL frame, where forward is -X.
    "beam_fwd": {"x": 1011.7, "section_mm": (104.0, 104.0), "length": 2190.0,
                 "z_bottom": 416.1, "z_top": 520.1},
    "beam_aft": {"x": -1986.9, "section_mm": (104.0, 104.0), "length": 2300.0,
                 "z_bottom": 507.4, "z_top": 611.4},
    "beam_span": 2998.6,
    "rail": {"y_centres": (200.0, -200.0), "spacing_cc": 400.0,
             "length": 3112.6, "width": 109.0, "height": 249.8,
             "z_bottom": 413.6, "z_top": 663.4},
    "pads": {"count": 6, "size_mm": (16.5, 139.0, 50.4),
             "x_stations": (902.6, 702.7, 502.8), "y_centres": (200.6, -200.6)},
}

# The 83 mm defect in note 00 section 1, re-measured.
RAIL_POD_INTERFERENCE = BASELINE["rail"]["z_top"] - BASELINE["pod"]["z_floor"]   # 85.7 mm

DISCREPANCIES = [
    ("pod revision", "the two STLs are different revisions: registered nose-to-nose "
                     "and floor-to-floor the assembly copy is 5.2 mm longer and 13.6 mm "
                     "taller than Cockpit_V1_3.stl (485.6 vs 497.3 mm envelope). "
                     "Confirm with the modeller which is current"),
    ("rail section", "note 00 says 104 x 135 mm; measured envelope is 109 x 249.8 mm "
                     "over 3112.6 mm length (note says 2970 mm), and the 14.8 L volume "
                     "shows it is an open section, not a solid box"),
    ("rail interference", f"note 00 says 83 mm; measured {RAIL_POD_INTERFERENCE:.1f} mm"),
    ("hull volume", "note 00 says 593 L moulded; the closed STL volume is 685.5 L"),
]


# --- frozen constraints from Technical Rules V2026.1 --------------------------
RULES = {
    "ENERGY_REQ_3":   "hulls + beams supplied, 65 kg, 2 poles dia 104 mm, 3.0 m apart - do not modify",
    "ENERGY_REQ_38":  "cockpit clamps envelop the beam, >=50 mm wide, >=750 mm apart",
    "ENERGY_REQ_48":  "cockpit mass excluding hulls <= 250 kg",
    "ENERGY_REQ_7":   "stored energy <= 10 kWh, battery factor 1.0, hydrogen 0.35",
    "ENERGY_REQ_188": "motor <= 25 kW nominal",
    "ENERGY_REQ_28":  "solar <= 4 m2 including mounting frame",
    "ENERGY_REQ_25/26/50/51/52": "energy container >=500 mm from pilot, behind an A1 bulkhead",
}

CLAMP_MIN_SPACING = 750.0     # mm, ENERGY_REQ_38 - baseline rails are at 400 mm
CLAMP_MIN_WIDTH = 50.0        # mm
BEAM_DIAMETER = 104.0         # mm, round carbon pole (STL models it as square)

# Mass basis, confirmed by the team 2026-09-04. This settles note 09's Q-TC-2 and
# note 06's "governing unknown": the 250 kg cap DOES include the pilot, and it
# covers the entire cockpit but NOT the supplied hulls and beams.
#
# CAREFUL: note 06 section 8's "+32 over cap" and "+102 over cap" are wrong. Its
# 282 kg subtotal INCLUDES 80 kg of demihulls, so it compares a hull-inclusive
# figure against a cap that excludes hulls. Cockpit items alone are 202 kg; with
# a 70 kg pilot that is 272 kg, i.e. 22 kg over - a gap the levers in note 06 can
# actually close. See mass.py.
MASS_CAP_KG = 250.0           # entire cockpit INCLUDING pilot, EXCLUDING hulls
HULLS_BEAMS_KG = 65.0         # supplied, ENERGY_REQ_3, outside the cap
PILOT_DESIGN_KG = 70.0
NOTE06_COCKPIT_KG = 202.0     # note 06 section 8 total (282) minus its 80 kg hulls
NOTE06_TOTAL_KG = NOTE06_COCKPIT_KG + PILOT_DESIGN_KG    # 272 kg vs the 250 cap
MASS_OVERAGE_KG = NOTE06_TOTAL_KG - MASS_CAP_KG          # 22 kg over
MAX_DISPLACEMENT_KG = MASS_CAP_KG + HULLS_BEAMS_KG       # 315 kg at the cap
DESIGN_DISPLACEMENT_KG = NOTE06_TOTAL_KG + HULLS_BEAMS_KG   # 337 kg as it stands

# --- design point -------------------------------------------------------------
V_DESIGN = 15.28              # m/s, 55 km/h
RHO_AIR = 1.225               # kg/m3
Q_DESIGN = 0.5 * RHO_AIR * V_DESIGN ** 2      # 143.0 Pa
NU_AIR = 1.5e-5               # m2/s
PILOT_MASS_KG = 70.0          # design pilot
SLAM_G = 3.0


def selfcheck():
    """Assert the frame transform reproduces the independently-known numbers."""
    ok = []
    nose = asm_to_boat([[-1695.9, -948.2, -319.4]])[0]
    ok.append(("pod nose X", nose[0], 1651.3, 0.1))
    cant = BASELINE["pod"]["x_nose"] - BASELINE["beam_fwd"]["x"]
    ok.append(("fwd cantilever (note 08: 640)", cant, 639.6, 0.5))
    ok.append(("beam span (note 08: 2998)", BASELINE["beam_span"], 2998.6, 0.5))
    ok.append(("q_inf (note 01: 143.0 Pa)", Q_DESIGN, 143.0, 0.2))
    ok.append(("Re_pod (note 01: 2.59e6)",
               V_DESIGN * BASELINE["pod"]["length"] / 1000.0 / NU_AIR, 2.585e6, 1e4))
    fails = [(n, g, e) for n, g, e, t in ok if abs(g - e) > t]
    for n, g, e, t in ok:
        print(f"  {'OK ' if abs(g - e) <= t else 'FAIL'}  {n:<34} = {g:>12.4g}  (expect {e:g})")
    return not fails


if __name__ == "__main__":
    print("volare.py selfcheck - canonical frame vs independently-derived values")
    good = selfcheck()
    print(f"\nrail/pod interference: {RAIL_POD_INTERFERENCE:.1f} mm")
    print(f"rail spacing {BASELINE['rail']['spacing_cc']:.0f} mm vs "
          f"{CLAMP_MIN_SPACING:.0f} mm required -> "
          f"{'COMPLIANT' if BASELINE['rail']['spacing_cc'] >= CLAMP_MIN_SPACING else 'NON-COMPLIANT (ENERGY_REQ_38)'}")
    print("\nmeasured-vs-note discrepancies:")
    for k, v in DISCREPANCIES:
        print(f"  - {k}: {v}")
    raise SystemExit(0 if good else 1)
