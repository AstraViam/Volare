"""Parametric fairing geometry - shared by the optimiser and by Blender.

The optimiser needs the section to answer two questions the drag correlation
alone cannot: does this fairing physically wrap the 104 mm pole, and how much
laminate does it cost? Blender needs the same section to build the surface. So
the section lives here once, and both consume it.
"""
import sys
from functools import lru_cache
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import geom
import params
import volare as V

# Fairing shell: 2 x 300 gsm E-glass wet layup + gelcoat, plus internal ribs and
# the bonding flange. Estimate - weigh a test panel before trusting it.
FAIRING_AREAL_KG_M2 = 2.2
SCREEN_AREAL_KG_M2 = params.get("cockpit.screen_areal_density_kg_m2")
POLE_CLEARANCE_MM = params.get("cockpit.fairing_pole_clearance_mm")


def naca_thickness(xc, t_over_c):
    """NACA 4-digit symmetric half-thickness y/c at chord fraction xc."""
    xc = np.asarray(xc, float)
    return 5.0 * t_over_c * (0.2969 * np.sqrt(np.clip(xc, 0, None))
                             - 0.1260 * xc
                             - 0.3516 * xc ** 2
                             + 0.2843 * xc ** 3
                             - 0.1015 * xc ** 4)


def section(t_over_c, chord_mm, n=120):
    """Closed section outline, (2n,2) in mm, origin at the leading edge."""
    # cosine spacing so the leading edge is resolved
    beta = np.linspace(0.0, np.pi, n)
    xc = 0.5 * (1.0 - np.cos(beta))
    yt = naca_thickness(xc, t_over_c) * chord_mm
    x = xc * chord_mm
    upper = np.stack([x, yt], 1)
    lower = np.stack([x[::-1], -yt[::-1]], 1)
    return np.concatenate([upper, lower[1:-1]])


def section_perimeter_mm(t_over_c, chord_mm, n=400):
    p = section(t_over_c, chord_mm, n)
    d = np.diff(np.vstack([p, p[:1]]), axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


def pole_fits(t_over_c, chord_mm, dia_mm=V.BEAM_DIAMETER,
              clearance_mm=POLE_CLEARANCE_MM, n=200):
    """Can this section envelope the round pole, with clearance?

    Places the pole centre at the section's max-thickness station (x/c = 0.30 for
    a NACA 4-digit) and checks the fairing half-thickness against the circle at
    every chordwise station the pole occupies.

    Returns (fits, worst_margin_mm). Negative margin = interference.
    """
    r = dia_mm / 2.0
    x_pole = 0.30 * chord_mm
    xs = np.linspace(x_pole - r, x_pole + r, n)
    inside = (xs >= 0.0) & (xs <= chord_mm)
    if not inside.all():
        return False, -abs(float(np.min([xs.min(), chord_mm - xs.max()])))
    y_fair = naca_thickness(xs / chord_mm, t_over_c) * chord_mm
    y_pole = np.sqrt(np.maximum(r ** 2 - (xs - x_pole) ** 2, 0.0))
    margin = float(np.min(y_fair - y_pole - clearance_mm))
    return bool(margin >= 0.0), margin


@lru_cache(maxsize=8192)
def _min_chord_cached(t_over_c, dia_mm, clearance_mm):
    return _min_chord(t_over_c, dia_mm, clearance_mm)


def min_chord_for_pole(t_over_c, dia_mm=V.BEAM_DIAMETER,
                       clearance_mm=POLE_CLEARANCE_MM):
    """Smallest chord at this t/c that still swallows the pole.

    Rounded to 1e-5 in t/c before caching - the optimiser calls this thousands of
    times with near-identical arguments and the bisection is the hot loop.
    """
    return _min_chord_cached(round(float(t_over_c), 5), float(dia_mm),
                             float(clearance_mm))


def _min_chord(t_over_c, dia_mm, clearance_mm):
    lo, hi = dia_mm, 40.0 * dia_mm
    if not pole_fits(t_over_c, hi, dia_mm, clearance_mm)[0]:
        return hi        # finite, and far past any packaging limit -> infeasible
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if pole_fits(t_over_c, mid, dia_mm, clearance_mm)[0]:
            hi = mid
        else:
            lo = mid
    return hi


def fairing_mass_kg(t_over_c, chord_mm, span_mm, areal=FAIRING_AREAL_KG_M2):
    """Shell mass of one fairing: outline perimeter x span x areal density."""
    per = section_perimeter_mm(t_over_c, chord_mm)
    return per * span_mm / 1e6 * areal


def fairing_mesh(t_over_c, chord_mm, span_mm, centre_mm, axis=1, n=80,
                 x_pole_frac=0.30):
    """Triangulated fairing shell, (F,3,3) mm in the boat frame.

    Swept along `axis` (1 = athwartships for a crossbeam), positioned so the pole
    centre lands on `centre_mm`. Open at both ends - it is a shell, not a solid.
    """
    p = section(t_over_c, chord_mm, n)                  # (M,2), LE at x=0
    p[:, 0] -= x_pole_frac * chord_mm                   # origin onto the pole axis
    m = len(p)
    a, b = [i for i in range(3) if i != axis]
    verts = []
    for s in (-span_mm / 2.0, +span_mm / 2.0):
        for q in p:
            v = [0.0, 0.0, 0.0]
            v[axis] = centre_mm[axis] + s
            v[a] = centre_mm[a] + q[0]
            v[b] = centre_mm[b] + q[1]
            verts.append(v)
    Vt = np.asarray(verts, float)
    tris = []
    for i in range(m):
        j = (i + 1) % m
        tris.append([Vt[i], Vt[j], Vt[m + j]])
        tris.append([Vt[i], Vt[m + j], Vt[m + i]])
    return np.asarray(tris, float)


# --------------------------------------------------- pod aft-body recontour

def recontour_pod(T, max_slope_deg, ease=0.15):
    """Redistribute the pod's aft body to hold a bounded surface slope.

    Note 01 section 4.2 asks for local slope <= 12 deg with continuous curvature.
    A straight taper gives the lowest possible max slope for a given drop but
    breaks slope continuity at the crown; a pure ease gives continuity but peaks
    ~1.6x the mean. This integrates a trapezoidal SLOPE profile instead: the
    slope ramps in over `ease` of the run, holds flat, and eases out at the base.
    That bounds the maximum by construction and keeps dz/dx continuous.

    Returns (deformed triangles, info).
    """
    xs, top, bot = geom.centreline_profile(T, 0.0, 400)
    ok = np.isfinite(top)
    xs, top = xs[ok], top[ok]
    i_pk = int(np.argmax(top))
    x_pk, z_pk = xs[i_pk], top[i_pk]
    x_tl = xs.min()
    L = x_pk - x_tl

    # trapezoidal slope shape g(t), t = 0 at the crown -> 1 at the tail
    t = np.linspace(0.0, 1.0, 400)
    g = np.ones_like(t)
    r = t < ease
    g[r] = 0.5 * (1 - np.cos(np.pi * t[r] / ease))          # smooth ramp in
    r = t > (1 - ease * 0.6)
    tt = (t[r] - (1 - ease * 0.6)) / (ease * 0.6)
    g[r] = 1.0 - 0.55 * (0.5 * (1 - np.cos(np.pi * tt)))     # ease out, sharp base
    gbar = float(np.trapezoid(g, t))

    slope = np.tan(np.radians(max_slope_deg))
    drop = slope * L * gbar                                  # max slope == target
    z_end = z_pk - drop

    # target crown height as a function of x
    zt = z_pk - drop * np.cumsum(g) / g.sum()
    x_of_t = x_pk - t * L
    order = np.argsort(x_of_t)
    tgt_x, tgt_z = x_of_t[order], zt[order]

    floor = float(T[:, :, 2].min())
    cur = np.interp(tgt_x, xs, top)

    P = T.reshape(-1, 3).copy()
    aft = P[:, 0] <= x_pk
    if aft.any():
        c = np.interp(P[aft, 0], tgt_x, cur)
        g2 = np.interp(P[aft, 0], tgt_x, tgt_z)
        scale = np.where(c > floor + 1.0, (g2 - floor) / np.maximum(c - floor, 1.0), 1.0)
        P[aft, 2] = floor + (P[aft, 2] - floor) * scale
    Td = P.reshape(-1, 3, 3)

    xs2, top2, _ = geom.centreline_profile(Td, 0.0, 400)
    ok2 = np.isfinite(top2)
    mean2, max2 = geom.closure_angle(xs2[ok2], top2[ok2], x_pk, x_tl + 40.0)
    return Td, {
        "x_peak": float(x_pk), "run_mm": float(L),
        "drop_before_mm": float(z_pk - np.interp(x_tl, xs, top)),
        "drop_after_mm": float(drop),
        "tail_raised_mm": float(z_end - np.interp(x_tl, xs, top)),
        "mean_slope_deg": float(mean2), "max_slope_deg": float(max2),
        "target_deg": float(max_slope_deg),
        "base_area_before_m2": float(geom.section_area(T, 0, x_tl + 3) / 1e6),
        "base_area_after_m2": float(geom.section_area(Td, 0, x_tl + 3) / 1e6),
    }



# ------------------------------------------------------------- windscreen

def windscreen_mesh(pod_T, x_base, half_w, height, rake_deg, sweep_deg,
                    shoulder_len=420.0):
    """Raked screen plus shoulder fairings, seated ON the pod crown.

    Note 01 section 4.1: 35-40 deg rake, top edge radiused, side edges swept back
    25 deg so the shed vortex passes outboard of the shoulders, and the shoulder
    fairings close the open cavity by blending the coaming into the headrest.

    The base and the shoulder run are read off the pod's own crown line rather
    than guessed, so the screen sits on the surface at whatever the recontour
    left behind instead of floating above it.
    """
    xs, top, _ = geom.centreline_profile(pod_T, 0.0, 400)
    ok = np.isfinite(top)
    xs, top = xs[ok], top[ok]

    def crown(x):
        return float(np.interp(x, xs, top))

    rk, sw = np.radians(rake_deg), np.radians(sweep_deg)
    z0 = crown(x_base)
    dx = -height * np.sin(rk)              # rakes aft (-X) as it rises
    dz = height * np.cos(rk)
    tw = half_w * 0.72                     # narrows toward the top
    x_top, z_top = x_base + dx, z0 + dz

    bl, br = [x_base, +half_w, z0], [x_base, -half_w, z0]
    tl, tr = [x_top, +tw, z_top], [x_top, -tw, z_top]
    tris = [[bl, br, tr], [bl, tr, tl]]

    # side edges swept back: a triangle each side from the screen base to the
    # top edge, leaning aft by `sweep_deg`
    x_sw = x_base - half_w * np.tan(sw)
    for sgn, ytop in ((+1, tw), (-1, -tw)):
        tris.append([[x_base, sgn * half_w, z0], [x_top, ytop, z_top],
                     [x_sw, sgn * half_w, z0]])

    # shoulder fairings: from the screen top edge aft along the crown, closing
    # the cavity. Each is a ruled strip following the crown line.
    n = 8
    for sgn, ytop in ((+1, tw), (-1, -tw)):
        for i in range(n):
            xa = x_top - shoulder_len * i / n
            xb = x_top - shoulder_len * (i + 1) / n
            fa, fb = i / n, (i + 1) / n
            ya, yb = ytop + (sgn * half_w - ytop) * fa, ytop + (sgn * half_w - ytop) * fb
            za = z_top + (crown(xa) - z_top) * fa
            zb = z_top + (crown(xb) - z_top) * fb
            tris.append([[xa, ya, za], [xb, yb, zb], [xb, sgn * half_w, crown(xb)]])
            tris.append([[xa, ya, za], [xb, sgn * half_w, crown(xb)],
                         [xa, sgn * half_w, crown(xa)]])
    return np.asarray(tris, float)


# Measured on the V1.3 pod by base_area_vs_closure() over 8-15.59 deg: holding a
# shallower aft slope means raising the tail, and the base grows almost exactly
# linearly with the angle you buy. Max residual against the measurements is
# 0.16 cm2, so a straight line is the honest model.
BASE_AREA_FIT = (-0.0095924, 0.2404476)     # m2 per deg, m2 intercept
BASE_AREA_RANGE_DEG = (8.0, 15.59)


def base_area_for_closure(closure_deg):
    """Base (transom) area implied by holding this aft-body slope. m2."""
    m, c = BASE_AREA_FIT
    return float(m * closure_deg + c)


def base_area_vs_closure(T, angles):
    """Measured base area for each achievable closure angle.

    The optimiser prices the closure angle but assumes base area is fixed.
    It is not - holding a shallower slope means raising the tail, and the base
    grows. This gives the real exchange rate.
    """
    out = []
    for a in angles:
        Td, info = recontour_pod(T, float(a))
        out.append({"closure_deg": float(a),
                    "base_area_m2": info["base_area_after_m2"],
                    "max_slope_deg": info["max_slope_deg"],
                    "tail_raised_mm": info["tail_raised_mm"]})
    return out


def _selftest():
    print("parametric.py selftest")
    ok = True

    # thickness peaks at the right place and the right value
    xc = np.linspace(0, 1, 2001)
    for tc in (0.12, 0.25, 0.40):
        yt = naca_thickness(xc, tc)
        t_max = 2 * yt.max()
        x_at = xc[int(np.argmax(yt))]
        good = abs(t_max - tc) < 0.01 * tc + 0.003 and abs(x_at - 0.30) < 0.02
        ok &= good
        print(f"  {'OK  ' if good else 'FAIL'} t/c {tc:.2f}: max thickness "
              f"{t_max:.4f} at x/c {x_at:.3f}")

    # a chord set by dia/tc, as aero.py assumes, does NOT actually fit the pole
    print("\n  does chord = D/(t/c) swallow the pole?")
    for tc in (0.20, 0.25, 0.333, 0.40, 0.50):
        c_naive = V.BEAM_DIAMETER / tc
        fits, margin = pole_fits(tc, c_naive)
        c_min = min_chord_for_pole(tc)
        print(f"    t/c {tc:.3f}  naive chord {c_naive:6.0f} mm -> "
              f"{'fits' if fits else 'INTERFERES'} by {margin:+6.1f} mm   "
              f"minimum chord {c_min:6.0f} mm  ({c_min / c_naive:.2f}x)")

    # perimeter sanity: thin section approaches 2 x chord
    per = section_perimeter_mm(0.08, 1000.0)
    good = 2000 < per < 2100
    ok &= good
    print(f"\n  {'OK  ' if good else 'FAIL'} thin section perimeter "
          f"{per:.0f} mm for a 1000 mm chord (expect just over 2000)")

    # mesh closes on itself and has sane area
    T = fairing_mesh(0.30, 400.0, 1500.0, (1011.7, 0.0, 468.0))
    import geom
    _, area = geom.tri_normals_areas(T)
    per30 = section_perimeter_mm(0.30, 400.0)
    expect = per30 * 1500.0 / 1e6
    good = abs(area.sum() / 1e6 - expect) < 0.01 * expect
    ok &= good
    print(f"  {'OK  ' if good else 'FAIL'} swept mesh area {area.sum() / 1e6:.4f} m2 "
          f"vs perimeter x span {expect:.4f} m2  ({len(T)} tris)")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if _selftest() else 1)
