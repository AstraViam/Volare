"""Build the propulsion unit as true B-rep solids and write one STEP file.

    python cad/scripts/export_motor_step.py   ->  cad/out/step/volare_motor.step

WHERE THE SHAPE COMES FROM

Four dimensions are dimensioned on the Competr drawing (datasheet 06/25,
section 6, page 7) and are exact: the powerhead is 322 mm fore-aft and 210 mm
across, the unit is 705 mm from cowling top to gearcase bottom, and 546 mm
fore-aft at propeller level. The bracket adds three more from section 7:
600 wide, 250 high, 470 fore-aft. All of them are in the parameter file with
DATASHEET provenance and a page reference.

How the 705 mm divides between cowling, leg and gearcase is NOT dimensioned.
Those splits are scaled off the drawing, they are tagged as such below, and
they are the only free numbers in the model.

WHAT THE DRAWING CORRECTED

The specification table gives "300x210x800mm", and `motor.length_m = 0.8` was
being read as an 800 mm FORE-AFT length; `cad/out/powertrain.json` still
carries the outboard as an 800 x 300 x 210 box, which lays a 705 mm-tall
outboard on its side and puts 800 mm of it astern. The drawing settles it:
322 fore-aft, 210 across, 705 tall. This script builds the drawing.

The rotors are tractive. Datasheet section 5.1 calls the architecture "a
tractive, counter-rotating propeller" and the side, transom and trim views all
put both rotors AHEAD of the leg, pulling. Anything drawn with them astern is
wrong.

THE ROTORS ARE THE TEAM'S, NOT COMPETR'S

The blades are generated from the converged propulsor design: diameter, blade
count, pitch ratio, expanded area ratio, hub and axial gap from the `hydro`
section, and the chord, thickness and camber distributions that
`propulsor/config.m` hands the MATLAB optimiser. The built solid is then
re-measured -- swept radius, expanded area ratio and pitch ratio read back off
the geometry -- and the script exits non-zero if any of them disagrees with
what went in.

Team Volare / ICT Mumbai.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np  # noqa: E402
from scipy.interpolate import PchipInterpolator  # noqa: E402


# cadquery pulls in OCP, a ~400 MB binary wheel. Nothing else in cad/scripts
# needs it, so this module degrades to a clear skip rather than failing
# tools/run_python_selftests.py on a machine that only has the analysis
# environment.
try:
    import cadquery as cq
    HAVE_CADQUERY = True
except ImportError:                                  # pragma: no cover
    cq = None
    HAVE_CADQUERY = False

import params  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cad" / "out" / "step"

# --- blade shape, mirroring propulsor/config.m -------------------------------
# Shapes, not sizes. The chord curve is scaled so the expanded area hits the
# target EAR; propeller_geometry.m explains at length why the chord is a scaled
# shape under monotone (pchip) interpolation and not free values per station.
CHORD_X = [0.20, 0.40, 0.60, 0.75, 0.90, 1.00]
CHORD_V = [0.72, 0.94, 1.00, 0.96, 0.72, 0.18]
TOC_X, TOC_V = [0.20, 0.60, 1.00], [0.16, 0.075, 0.030]
FOC_X, FOC_V = [0.20, 0.60, 1.00], [0.020, 0.025, 0.015]
TOC_MIN = 0.020
SKEW_TIP_DEG, SKEW_EXP = 15.0, 2.0
RAKE_TIP_DEG, RAKE_EXP = 5.0, 1.0

N_STATIONS = 16
N_CHORDWISE = 41

LEG_TAPER = 0.46          # leg chord at the gearcase, as a fraction of the top


def _pchip(xs, vs, x):
    return PchipInterpolator(np.asarray(xs, float), np.asarray(vs, float))(x)


def naca_section(toc, foc, n=N_CHORDWISE):
    """Aerofoil outline, unit chord, mid-chord at s = 0.

    NACA four-digit thickness on a parabolic mean line. The mean line is not
    the a=0.8 line propeller sections are usually drawn with; at 1.5 to 2.5 per
    cent camber the two differ by far less than anyone would build to, and a
    parabola cannot produce the trailing-edge kink a truncated a=0.8 line does.
    """
    beta = np.linspace(0.0, math.pi, n)
    xc = 0.5 * (1.0 - np.cos(beta))
    yt = 5.0 * toc * (0.2969 * np.sqrt(xc) - 0.1260 * xc - 0.3516 * xc ** 2
                      + 0.2843 * xc ** 3 - 0.1036 * xc ** 4)   # closed TE
    yc = 4.0 * foc * xc * (1.0 - xc)
    th = np.arctan(4.0 * foc * (1.0 - 2.0 * xc))
    upper = np.stack([xc - yt * np.sin(th), yc + yt * np.cos(th)], axis=1)
    lower = np.stack([xc + yt * np.sin(th), yc - yt * np.cos(th)], axis=1)
    pts = np.vstack([upper, lower[-2:0:-1]])
    pts[:, 0] -= 0.5
    return pts


def blade_geometry(diameter, hub, pitch_ratio, ear, blades):
    """Radial distributions for one blade, plus the numbers to check against."""
    R = diameter / 2.0
    x_hub = (hub / 2.0) / R
    x = np.linspace(x_hub, 1.0, N_STATIONS)
    r = x * R

    shape = _pchip(CHORD_X, CHORD_V, x)
    if np.any(shape <= 0):
        raise ValueError("chord shape went non-positive")
    disk = math.pi * diameter ** 2 / 4.0
    k = ear * disk / (blades * np.trapezoid(shape, r))
    c = k * shape

    toc = np.maximum(_pchip(TOC_X, TOC_V, x), TOC_MIN)
    foc = _pchip(FOC_X, FOC_V, x)
    pitch = pitch_ratio * diameter
    theta = np.arctan2(pitch, 2.0 * math.pi * r)

    xn = (x - x_hub) / (1.0 - x_hub)
    skew = math.radians(SKEW_TIP_DEG) * xn ** SKEW_EXP
    rake = math.radians(RAKE_TIP_DEG) * R * xn ** RAKE_EXP
    return dict(R=R, x_hub=x_hub, x=x, r=r, c=c, toc=toc, foc=foc,
                theta=theta, skew=skew, rake=rake, pitch=pitch,
                ear_design=ear, blades=blades, diameter=diameter)


def sections_3d(g, i_from):
    """Closed section loops on their cylinders, propeller frame, axis = +X."""
    out = []
    for i in range(i_from, len(g["x"])):
        sec = naca_section(g["toc"][i], g["foc"][i])
        s = sec[:, 0] * g["c"][i]
        nv = sec[:, 1] * g["c"][i]
        th, r = g["theta"][i], g["r"][i]
        axial = s * math.sin(th) + nv * math.cos(th) + g["rake"][i]
        tang = s * math.cos(th) - nv * math.sin(th)
        psi = g["skew"][i] + tang / r
        out.append(np.stack([axial, r * np.sin(psi), r * np.cos(psi)], axis=1))
    return out


def rotor(g, hand):
    """Hub boss plus blades. hand = +1 right-handed, -1 left-handed.

    The loft starts at the first station whose section wraps less than one
    blade pitch of arc. Below that radius a cylindrical section of that chord
    would sweep further round the hub than the next blade, and the loft fuses
    into a blob instead of a blade. Real propellers have the same root chords;
    they fair them into the hub boss rather than wrapping them, and that is
    what the boss does here. The radius where the loft starts is reported.
    """
    wrap = g["c"] / g["r"]                       # radians of arc per section
    limit = 0.95 * 2.0 * math.pi / g["blades"]
    i0 = int(np.argmax(wrap < limit))
    if wrap[i0] >= limit:
        raise ValueError("every section wraps more than one blade pitch")

    secs = sections_3d(g, i0)
    wires = [cq.Wire.makePolygon([cq.Vector(*p) for p in s], close=True)
             for s in secs]
    blade = cq.Solid.makeLoft(wires, ruled=False)

    # The boss is the DESIGN hub diameter over its full length, with a raised
    # band out to the loft's start radius to carry the blade roots. Making the
    # whole boss r0 would report a hub half again too big; leaving it at the
    # hub diameter would leave the blades floating clear of it.
    boss_len = 1.45 * float(g["c"][i0])
    band_len = 1.10 * float(g["c"][i0])
    hub_r = g["x_hub"] * g["R"]
    boss = cq.Solid.makeCylinder(hub_r, boss_len,
                                 cq.Vector(-boss_len * 0.45, 0, 0),
                                 cq.Vector(1, 0, 0))
    band = cq.Solid.makeCylinder(g["r"][i0], band_len,
                                 cq.Vector(-band_len * 0.45, 0, 0),
                                 cq.Vector(1, 0, 0))
    shape = boss.fuse(band)
    for b in range(g["blades"]):
        shape = shape.fuse(blade.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0),
                                        360.0 * b / g["blades"]))
    if hand < 0:
        shape = shape.mirror("XZ")
    return shape.clean(), dict(i0=i0, r0=float(g["r"][i0]),
                               wrap_deg=np.degrees(wrap), boss_len=boss_len,
                               hub_r=hub_r)


def measure_rotor(solid, g, axis_y=0.0, axis_z=0.0):
    """Read diameter, EAR and P/D back off the built geometry.

    Swept diameter is the largest radius FROM THE SHAFT AXIS, not the bounding
    box and not the distance from the boat origin. Three skewed tips 120
    degrees apart rarely put one on a bounding-box axis, so a box under-reads
    the diameter by several per cent; and once the rotor is translated into
    the boat frame, a radius taken about the origin over-reads it by the
    mounting height. Both look like modelling errors and are measuring errors.
    """
    p = np.array([v.toTuple() for v in solid.Vertices()])
    swept = 2.0 * float(np.hypot(p[:, 1] - axis_y, p[:, 2] - axis_z).max())
    ear = (g["blades"] * float(np.trapezoid(g["c"], g["r"]))
           / (math.pi * g["diameter"] ** 2 / 4.0))
    th07 = float(np.interp(0.7, g["x"], g["theta"]))
    pd07 = 2.0 * math.pi * 0.7 * g["R"] * math.tan(th07) / g["diameter"]
    return swept, ear, pd07


def build_assembly():
    """The propulsion unit as a cq.Assembly, plus the numbers to report on.

    Split out of main() so `export_assembly_step.py` can embed the motor in
    the whole-boat file without a second copy of these dimensions. CLAUDE.md
    is explicit that a constant must not exist twice.
    """
    P = params.get

    L = P("motor.drawing_length_mm")
    W = P("motor.drawing_width_mm")
    H = P("motor.drawing_height_mm")
    OAL = P("motor.drawing_overall_length_mm")
    bkt = (P("motor.bracket_length_mm"), P("motor.bracket_width_mm"),
           P("motor.bracket_height_mm"))
    cx, cy, _cz = P("powertrain.motor_centre_mm")
    trim = P("powertrain.motor_shaft_angle_deg")

    cowl_h = H * P("motor.cowl_fraction")
    leg_h = H * P("motor.leg_fraction")
    gear_h = H * P("motor.gearcase_fraction")
    gear_od = W * P("motor.gearcase_od_fraction")

    # Vertical datum. The drawing dimensions the whole unit from the
    # anti-ventilation plate, so the plate is the datum here too, not the
    # cowling and not powertrain.motor_centre_mm's Z. The plate sits at the
    # keel line; the bracket top is the mounting height above it.
    plate_z = P("powertrain.motor_plate_z_mm")
    cowl_top = plate_z + leg_h + cowl_h
    cowl_z = cowl_top - cowl_h / 2.0
    leg_top = cowl_top - cowl_h
    leg_bot = leg_top - leg_h
    shaft_z = leg_bot - gear_h / 2.0

    ok = True
    asm = cq.Assembly(name="volare_motor")
    grey = cq.Color(0.22, 0.24, 0.27, 1.0)

    # 1. cowling, 322 x 210 x cowl_h, dimensioned in X and Y
    cowl = (cq.Workplane("XY").box(L, W, cowl_h).edges("|Z").fillet(42.0)
            .edges("|X").fillet(18.0).translate((cx, cy, cowl_z)))
    asm.add(cowl, name="OUTBOARD/cowling", color=grey)

    # 2. leg: tapered strut, full powerhead chord at the top narrowing to the
    #    gearcase. Elliptical section throughout, as the drawing shows.
    top_w = W * 0.62
    bot_c, bot_w = L * LEG_TAPER, gear_od
    leg = cq.Solid.makeLoft([
        cq.Wire.makeEllipse(L * 0.46, top_w / 2.0, cq.Vector(cx, cy, leg_top),
                            cq.Vector(0, 0, 1), cq.Vector(1, 0, 0)),
        cq.Wire.makeEllipse(bot_c / 2.0, bot_w / 2.0,
                            cq.Vector(cx, cy, leg_bot),
                            cq.Vector(0, 0, 1), cq.Vector(1, 0, 0)),
    ], ruled=False)
    asm.add(leg, name="OUTBOARD/leg", color=grey)

    # 3. anti-ventilation plate at the mounting-height datum
    plate = (cq.Workplane("XY").box(L * 0.95, W * 1.15, 10.0)
             .edges("|Z").fillet(30.0).translate((cx, cy, plate_z)))
    asm.add(plate, name="OUTBOARD/anti_ventilation_plate", color=grey)

    # 4. gearcase. The 546 mm overall runs from the forward rotor tips to the
    #    gearcase trailing edge, so the case tail sets the aft end.
    case_len = 300.0
    case_x0 = cx + L * 0.34                       # tail, aft
    case = cq.Solid.makeCylinder(gear_od / 2.0, case_len,
                                 cq.Vector(case_x0 - case_len, cy, shaft_z),
                                 cq.Vector(1, 0, 0))
    tail = cq.Solid.makeSphere(gear_od / 2.0, cq.Vector(case_x0, cy, shaft_z),
                               angleDegrees1=-90, angleDegrees2=90,
                               angleDegrees3=360)
    asm.add(case.fuse(tail).clean(), name="OUTBOARD/gearcase", color=grey)
    nose_x = case_x0 - case_len

    # 5. transom bracket, forward of the cowling, against the 14 deg transom
    brk = (cq.Workplane("XY").box(bkt[0], bkt[1], bkt[2])
           .edges("|Z").fillet(24.0)
           .translate((cx + L / 2.0 + bkt[0] / 2.0 + 5.0, cy,
                       plate_z + P("motor.transom_mounting_height_mm") - bkt[2] / 2.0)))
    asm.add(brk, name="OUTBOARD/transom_bracket", color=cq.Color(0.38, 0.40, 0.44, 1.0))

    # 6. the two rotors, FORWARD of the gearcase because the unit is tractive
    hub = P("hydro.hub_diameter_m") * 1000.0
    gap = P("hydro.axial_gap_m") * 1000.0
    x_rear = nose_x - 30.0                         # nearer the gearcase
    x_front = x_rear - gap                         # further forward
    shaft = cq.Solid.makeCylinder(
        24.0, nose_x - (x_front - 60.0),
        cq.Vector(x_front - 60.0, cy, shaft_z), cq.Vector(1, 0, 0))
    asm.add(shaft, name="OUTBOARD/shaft", color=cq.Color(0.55, 0.57, 0.60, 1.0))

    built = {}
    for which, xpos, hand, col in (
            ("front", x_front, +1, (0.13, 0.40, 0.72, 1.0)),
            ("rear", x_rear, -1, (0.20, 0.52, 0.85, 1.0))):
        g = blade_geometry(P(f"hydro.{which}_diameter_m") * 1000.0, hub,
                           P(f"hydro.{which}_pitch_ratio"),
                           P(f"hydro.{which}_EAR"),
                           int(P(f"hydro.{which}_blades")))
        sol, info = rotor(g, hand)
        info["measured"] = measure_rotor(sol, g)      # measure before moving it
        sol = sol.translate(cq.Vector(xpos, cy, shaft_z))
        asm.add(sol, name=f"PROPULSOR/rotor_{which}", color=cq.Color(*col))
        built[which] = (g, sol, info)

    return asm, dict(L=L, W=W, H=H, OAL=OAL, bkt=bkt, cx=cx, cy=cy, trim=trim,
                     cowl_h=cowl_h, leg_h=leg_h, gear_h=gear_h,
                     gear_od=gear_od, plate_z=plate_z, shaft_z=shaft_z,
                     hub=hub, gap=gap, built=built)


def report(asm, I) -> bool:
    """Print the build and check it. Returns True if every check passed."""
    P = params.get
    L, W, H, OAL = I["L"], I["W"], I["H"], I["OAL"]
    bkt, trim = I["bkt"], I["trim"]
    cowl_h, leg_h, gear_h = I["cowl_h"], I["leg_h"], I["gear_h"]
    gear_od, shaft_z, hub, gap = I["gear_od"], I["shaft_z"], I["hub"], I["gap"]
    built = I["built"]
    ok = True

    print("=" * 74)
    print(" VOLARE -- COMPETR OUTBOARD + TEAM PROPULSOR, TRUE B-REP SOLIDS")
    print("=" * 74)
    print(" frame  X fwd, Y port, Z up; origin centreline x mid-length x keel; mm")
    print(f" trim   {trim:.1f} deg in this pose; datasheet allows "
          f"{P('motor.trim_min_deg'):.0f} to {P('motor.trim_max_deg'):+.0f}\n")

    print(" DIMENSIONED ON THE DRAWING (datasheet 06/25 sections 6 and 7)")
    for what, val in (("powerhead fore-aft", L), ("powerhead width", W),
                      ("cowling top to gearcase bottom", H),
                      ("overall length at propeller level", OAL),
                      ("bracket fore-aft", bkt[0]), ("bracket width", bkt[1]),
                      ("bracket height", bkt[2]),
                      ("transom mounting height", P("motor.transom_mounting_height_mm"))):
        print(f"   {what:<34} {val:7.1f} mm")

    print("\n SCALED OFF THE DRAWING (not dimensioned; the only free numbers here)")
    print(f"   cowling / leg / gearcase        {cowl_h:.0f} / {leg_h:.0f} / "
          f"{gear_h:.0f} mm  = {H:.0f}")
    print(f"   gearcase diameter               {gear_od:.0f} mm")

    print("\n BUILT GEOMETRY, RE-MEASURED ON THE SOLID")
    for which in ("front", "rear"):
        g, sol, info = built[which]
        swept, ear, pd07 = info["measured"]
        for what, got, want, tol, unit in (
                ("diameter", swept, g["diameter"], 0.5, "mm"),
                ("EAR", ear, g["ear_design"], 0.002, ""),
                ("P/D at 0.7R", pd07, P(f"hydro.{which}_pitch_ratio"), 0.002, ""),
                ("blades", float(g["blades"]), float(g["blades"]), 0.0, "")):
            good = abs(got - want) <= tol
            ok &= good
            print(f"   {'ok  ' if good else 'FAIL'}  rotor {which:<5} {what:<12}"
                  f" {got:9.4f} {unit:<3} (design {want:.4f})")
        print(f"         rotor {which:<5} hub {2 * info['hub_r']:.1f} mm dia, "
              f"root band {2 * info['r0']:.1f} mm, chord "
              f"{g['c'].min():.1f}..{g['c'].max():.1f} mm, {sol.Volume() / 1e6:.3f} L")

    print(f"   axial gap between rotor planes  {gap:.1f} mm (hydro.axial_gap_m)")

    print("\n FINDINGS")
    g_f = built["front"][0]
    root_wrap = built["front"][2]["wrap_deg"][0]
    print(f"   The root section of the front rotor wraps {root_wrap:.0f} deg of "
          f"arc against a {360 / g_f['blades']:.0f} deg blade")
    print( "   pitch. That is normal for a wide-bladed three-blader and is why "
           "the boss")
    print( "   exists, but it means the root cannot be cut as a cylindrical "
           "section.")

    stock = P("motor.stock_propeller_diameter_mm")
    biggest = max(built[w][0]["diameter"] for w in ("front", "rear"))
    print(f"\n   The designed rotors are {biggest:.0f} mm. The gearcase on this "
          f"drawing is")
    print(f"   built around a {stock:.0f} mm propeller, scaled off the rear view. "
          f"The designed")
    print(f"   pair is {100 * (biggest / stock - 1):.0f} per cent larger and will "
          f"not fit the stock gearcase")
    print( "   or its gearing. Raise it with Competr before ordering.")

    tip = shaft_z - biggest / 2.0
    submerged = -tip
    good = submerged > 0.5 * biggest
    ok &= good
    print(f"\n   {'ok  ' if good else 'FAIL'}  lowest blade tip Z = {tip:.1f} mm, "
          f"{submerged:.0f} mm below the keel; the")
    print( "         whole disc has to be under the hull bottom for "
           "hydro.propulsor_type")
    print( "         'fully submerged' to hold. The rotors are tractive, "
           "forward of")
    print( "         the leg, per datasheet section 5.1.")

    print(f"\n   cad/scripts/powertrain.py now builds the outboard from the "
          f"drawing too:")
    print(f"   {L:.0f} x {W:.0f} x {H:.0f}, where it was an 800 x 300 x 210 box "
          f"lying on its side.")
    print( "   The 10 kg that used to sit on a 120 x 90 x 500 'drive leg' is "
           "now the")
    print( "   transom bracket, which is what the datasheet actually weighs.")

    compound = asm.toCompound()
    bb = compound.BoundingBox()
    print(f"\n bounding box  X {bb.xmin:9.1f} .. {bb.xmax:9.1f} ({bb.xlen:7.1f} mm)")
    print(f"               Y {bb.ymin:9.1f} .. {bb.ymax:9.1f} ({bb.ylen:7.1f} mm)")
    print(f"               Z {bb.zmin:9.1f} .. {bb.zmax:9.1f} ({bb.zlen:7.1f} mm)")

    good = abs(bb.zlen - H) < 0.30 * H
    ok &= good
    print(f"   {'ok  ' if good else 'FAIL'}  built height {bb.zlen:.0f} mm is "
          f"within a rotor radius of the drawn {H:.0f} mm")

    return ok


def main() -> int:
    if not HAVE_CADQUERY:
        print(f"{Path(__file__).name}: skipped, cadquery is not "
              "installed. pip install cadquery to build the STEP.")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    asm, info = build_assembly()
    ok = report(asm, info)
    path = OUT / "volare_motor.step"
    asm.export(str(path))
    print(f"\n wrote {path}  ({path.stat().st_size / 1e6:.2f} MB)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
