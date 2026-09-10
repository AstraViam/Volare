"""Float the Volare demihulls in seawater and report the static condition.

MASS BASIS (confirmed by the team, 2026-09-04):
    entire cockpit INCLUDING the pilot   <= 250 kg   (ENERGY_REQ_48)
    supplied hulls + beams                  65 kg
    -------------------------------------------------
    theoretical maximum displacement       315 kg

That settles the question note 06 flagged as blocking the whole project: the cap
DOES include the pilot. Note 06's revised budget of 282 kg for the boat alone,
before the pilot, is therefore 102 kg over - see the console output.

This is the AT-REST condition. At the 55 km/h design speed the boat planes
(note 01: Froude 2.18, volumetric Froude 6.65), so the running wetted area is a
small aft patch, nothing like the figures here. Static hydrostatics is what you
need for freeboard and reserve buoyancy, stability, the float-off at handover,
and the slow end of the endurance event.

    python scripts/hydrostatics.py
    python scripts/hydrostatics.py --sweep
    python scripts/hydrostatics.py --mass 315

Seawater defaults to 1028 kg/m3 (Mediterranean, ~38 PSU at 20 C), not the 1025
usually quoted for open ocean. Monaco harbour is Med water.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).parent))
import geom
import parts as P
import volare as V

OUT = Path(__file__).resolve().parents[2] / "cad" / "out"
RHO_SW = 1028.0
RHO_FW = 1000.0
G = 9.81

COCKPIT_CAP_KG = V.MASS_CAP_KG          # 250, cockpit incl. pilot, excl. hulls
HULLS_BEAMS_KG = V.HULLS_BEAMS_KG       # 65, supplied
DESIGN_MAX_KG = V.MAX_DISPLACEMENT_KG   # 315 kg all-up at the cap

MASS_CASES = {
    "THEORETICAL MAX (250 cockpit incl. pilot + 65 supplied)": DESIGN_MAX_KG,
    "note 06 design as it stands (202 cockpit + 70 pilot + 65)":
        V.DESIGN_DISPLACEMENT_KG,
    "empty, no pilot (250 - 70 + 65)": COCKPIT_CAP_KG - V.PILOT_DESIGN_KG + HULLS_BEAMS_KG,
}


# ------------------------------------------------------------ vectorised clip

def clip_below(T, zw):
    """Triangles of T below z = zw, cut exactly at the plane. Fully vectorised."""
    d = T[:, :, 2] - zw
    below = d <= 0
    n = below.sum(1)

    whole = T[n == 3]
    out = [whole] if len(whole) else []

    # one vertex below -> one triangle [v0, P(v0->v1), P(v2->v0)]
    m = n == 1
    if m.any():
        Tm, dm = T[m], d[m]
        lone = np.argmax(below[m], axis=1)
        idx = (lone[:, None] + np.arange(3)[None, :]) % 3
        r = np.take_along_axis(Tm, idx[:, :, None].repeat(3, 2), axis=1)
        rd = np.take_along_axis(dm, idx, axis=1)
        a = r[:, 0] + (rd[:, 0] / (rd[:, 0] - rd[:, 1]))[:, None] * (r[:, 1] - r[:, 0])
        b = r[:, 0] + (rd[:, 0] / (rd[:, 0] - rd[:, 2]))[:, None] * (r[:, 2] - r[:, 0])
        out.append(np.stack([r[:, 0], a, b], axis=1))

    # two vertices below -> a quad, split into two triangles
    m = n == 2
    if m.any():
        Tm, dm = T[m], d[m]
        lone = np.argmax(~below[m], axis=1)              # the vertex ABOVE
        idx = (lone[:, None] + np.arange(3)[None, :]) % 3
        r = np.take_along_axis(Tm, idx[:, :, None].repeat(3, 2), axis=1)
        rd = np.take_along_axis(dm, idx, axis=1)
        a = r[:, 0] + (rd[:, 0] / (rd[:, 0] - rd[:, 1]))[:, None] * (r[:, 1] - r[:, 0])
        b = r[:, 0] + (rd[:, 0] / (rd[:, 0] - rd[:, 2]))[:, None] * (r[:, 2] - r[:, 0])
        out.append(np.stack([a, r[:, 1], r[:, 2]], axis=1))
        out.append(np.stack([a, r[:, 2], b], axis=1))

    if not out:
        return np.zeros((0, 3, 3))
    R = np.concatenate(out)
    return R[np.isfinite(R).all(axis=(1, 2))]


# --------------------------------------------------------------- waterplane

def waterplane(T, zw):
    """Area, centroid and second moments of the waterplane.

    Green's theorem over the consistently-oriented cut segments, so the two
    demihulls are handled as separate loops without joining them up - which is
    exactly what gives a catamaran its enormous transverse BM.
    """
    S, _ = geom.plane_segments(T, 2, zw)          # in-plane coords are (X, Y)
    if len(S) == 0:
        return None
    p, q = S[:, 0], S[:, 1]
    cr = p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]
    A2 = 0.5 * cr.sum()
    if abs(A2) < 1e-9:
        return None
    cx = ((p[:, 0] + q[:, 0]) * cr).sum() / (6.0 * A2)
    cy = ((p[:, 1] + q[:, 1]) * cr).sum() / (6.0 * A2)
    Ixx = ((p[:, 1] ** 2 + p[:, 1] * q[:, 1] + q[:, 1] ** 2) * cr).sum() / 12.0
    Iyy = ((p[:, 0] ** 2 + p[:, 0] * q[:, 0] + q[:, 0] ** 2) * cr).sum() / 12.0
    A = abs(A2)
    Pn = S.reshape(-1, 2)
    return {"area_mm2": A, "lcf_x": cx, "tcf_y": cy,
            "Ixx_mm4": abs(Ixx) - A * cy ** 2,      # about the fore-aft axis
            "Iyy_mm4": abs(Iyy) - A * cx ** 2,      # about the athwart axis
            "lwl_mm": float(Pn[:, 0].max() - Pn[:, 0].min()),
            "bwl_mm": float(Pn[:, 1].max() - Pn[:, 1].min()),
            "half_beam_wl_mm": float(np.abs(Pn[:, 1]).max())}


def _tri_quad_moment(T, k):
    """Per-triangle integral of coord k squared over the facet: A*(sum sq + sum prod)/6."""
    c = T[:, :, k]
    return (c[:, 0] ** 2 + c[:, 1] ** 2 + c[:, 2] ** 2
            + c[:, 0] * c[:, 1] + c[:, 0] * c[:, 2] + c[:, 1] * c[:, 2]) / 6.0


def submerged(T, zw, wp=None):
    """Volume, LCB, KB and wetted area below z = zw.

    Volume by the divergence theorem on the clipped surface plus the waterplane
    cap:  V = sum(n_z * A * z_bar) + zw * A_wp.  No section-area integration, so
    it is one vectorised pass instead of a few hundred slices.
    """
    sub = clip_below(T, zw)
    if len(sub) == 0:
        return {"volume_mm3": 0.0, "wetted_mm2": 0.0, "lcb_x": 0.0,
                "kb_z": 0.0, "tris": sub}
    nrm, a = geom.tri_normals_areas(sub)
    wp = wp if wp is not None else waterplane(T, zw)
    A_wp = wp["area_mm2"] if wp else 0.0

    zbar = sub[:, :, 2].mean(1)
    vol = float((nrm[:, 2] * a * zbar).sum() + zw * A_wp)

    # int z dV = closed integral of (z^2/2) n_z dA
    int_z = float((nrm[:, 2] * a * _tri_quad_moment(sub, 2)).sum() / 2.0
                  + zw ** 2 / 2.0 * A_wp)
    # int x dV = closed integral of (x^2/2) n_x dA; the cap has n_x = 0
    int_x = float((nrm[:, 0] * a * _tri_quad_moment(sub, 0)).sum() / 2.0)

    return {"volume_mm3": vol, "wetted_mm2": float(a.sum()),
            "lcb_x": int_x / vol if vol else 0.0,
            "kb_z": int_z / vol if vol else 0.0, "tris": sub}


def sink_to(T, mass_kg, rho=RHO_SW):
    zmin, zmax = float(T[:, :, 2].min()), float(T[:, :, 2].max())
    target = mass_kg / rho * 1e9

    def resid(zw):
        return submerged(T, zw)["volume_mm3"] - target

    if resid(zmax) < 0:
        return None
    return brentq(resid, zmin + 1e-6, zmax, xtol=1e-4)


# ------------------------------------------------------------------- reporting

def condition(T, total_area_m2, mass_kg, rho=RHO_SW, deck_z=None):
    zw = sink_to(T, mass_kg, rho)
    if zw is None:
        return None
    wp = waterplane(T, zw)
    s = submerged(T, zw, wp)
    keel = float(T[:, :, 2].min())
    deck = deck_z if deck_z is not None else float(T[:, :, 2].max())
    vol_m3 = s["volume_mm3"] / 1e9
    wetted = s["wetted_mm2"] / 1e6
    draft = zw - keel

    d = {"mass_kg": mass_kg, "rho": rho,
         "waterline_z_mm": zw, "draft_mm": draft, "freeboard_mm": deck - zw,
         "displaced_volume_L": vol_m3 * 1000.0,
         "check_kg": vol_m3 * rho,
         "wetted_area_m2": wetted,
         "wetted_fraction": wetted / total_area_m2,
         "total_hull_area_m2": total_area_m2,
         "lcb_x_mm": s["lcb_x"], "KB_mm": s["kb_z"] - keel}
    if wp:
        A = wp["area_mm2"] / 1e6
        lwl, bwl = wp["lwl_mm"], wp["bwl_mm"]
        # per-demihull beam, the meaningful one for hull-form coefficients
        b_demi = 2.0 * (wp["half_beam_wl_mm"] - V.BASELINE["hull"]["y_centres"][0]) \
            if wp["half_beam_wl_mm"] > V.BASELINE["hull"]["y_centres"][0] else bwl
        am = s["volume_mm3"] / max(lwl, 1.0)          # mean section area
        d.update({
            "waterplane_area_m2": A,
            "LWL_mm": lwl, "BWL_overall_mm": bwl, "BWL_demihull_mm": b_demi,
            "LCF_x_mm": wp["lcf_x"],
            "Cb": s["volume_mm3"] / max(lwl * b_demi * 2.0 * draft, 1.0),
            "Cwp": wp["area_mm2"] / max(lwl * b_demi * 2.0, 1.0),
            "L_over_B_demihull": lwl / max(b_demi, 1.0),
            "BMt_mm": wp["Ixx_mm4"] / max(s["volume_mm3"], 1.0),
            "BMl_mm": wp["Iyy_mm4"] / max(s["volume_mm3"], 1.0),
            "TPC_kg_per_cm": A * 0.01 * rho,
            "slenderness_L_over_vol13": lwl / 1000.0 / max(vol_m3, 1e-9) ** (1 / 3),
        })
        d["KMt_mm"] = d["KB_mm"] + d["BMt_mm"]
        d["KMl_mm"] = d["KB_mm"] + d["BMl_mm"]
    return d


def show(tag, d, pod_floor_z=None, keel=0.0):
    if d is None:
        print(f"\n{tag}\n  NO SOLUTION - the hulls submerge completely.")
        return
    print(f"\n{tag}")
    print(f"  displacement           {d['mass_kg']:9.1f} kg   in {d['rho']:.0f} kg/m3")
    print(f"  {'-' * 62}")
    print(f"  WATER LEVEL (Z, keel=0){d['waterline_z_mm']:9.1f} mm")
    print(f"  draft                  {d['draft_mm']:9.1f} mm")
    print(f"  freeboard to deck      {d['freeboard_mm']:9.1f} mm")
    if pod_floor_z is not None:
        print(f"  pod floor above water  {pod_floor_z - keel - d['waterline_z_mm']:9.1f} mm")
    print(f"  displaced volume       {d['displaced_volume_L']:9.1f} L    "
          f"(checks to {d['check_kg']:.1f} kg)")
    print(f"  {'-' * 62}")
    print(f"  WETTED AREA            {d['wetted_area_m2']:9.3f} m2   of "
          f"{d['total_hull_area_m2']:.3f} m2 moulded")
    print(f"  WETTED FRACTION        {d['wetted_fraction'] * 100:9.1f} %")
    if "waterplane_area_m2" in d:
        print(f"  waterplane area        {d['waterplane_area_m2']:9.3f} m2")
        print(f"  {'-' * 62}")
        print(f"  LWL                    {d['LWL_mm']:9.0f} mm")
        print(f"  BWL, one demihull      {d['BWL_demihull_mm']:9.0f} mm")
        print(f"  BWL, overall           {d['BWL_overall_mm']:9.0f} mm")
        print(f"  L/B demihull           {d['L_over_B_demihull']:9.2f}")
        print(f"  slenderness L/vol^1/3  {d['slenderness_L_over_vol13']:9.2f}")
        print(f"  Cb / Cwp               {d['Cb']:9.3f} / {d['Cwp']:.3f}")
        print(f"  {'-' * 62}")
        print(f"  LCB (X, fwd +)         {d['lcb_x_mm']:9.1f} mm")
        print(f"  LCF (X, fwd +)         {d['LCF_x_mm']:9.1f} mm")
        print(f"  KB                     {d['KB_mm']:9.1f} mm")
        print(f"  BMt / KMt              {d['BMt_mm']:9.0f} / {d['KMt_mm']:.0f} mm")
        print(f"  BMl / KMl              {d['BMl_mm']:9.0f} / {d['KMl_mm']:.0f} mm")
        print(f"  immersion              {d['TPC_kg_per_cm']:9.1f} kg per cm")


def main():
    argv = sys.argv[1:]
    plist = P.split_assembly()
    hulls = [p for p in plist if p["name"].startswith("hull_")]
    T = np.concatenate([p["tris"] for p in hulls])
    total_area = sum(p["area_m2"] for p in hulls)

    keel = float(T[:, :, 2].min())
    T = T.copy()
    T[:, :, 2] -= keel                                # Z measured from the keel
    deck = float(T[:, :, 2].max())
    pod_floor = V.BASELINE["pod"]["z_floor"]

    mesh = geom.manifold_report(*geom.weld(T))
    print("=" * 66)
    print("VOLARE STATIC HYDROSTATICS - both demihulls, Z measured from the keel")
    print("=" * 66)
    print(f"  hull mesh            {len(T)} tris, watertight={mesh['watertight']}")
    print(f"  moulded surface      {total_area:.4f} m2 (both hulls)")
    print(f"  moulded volume       {abs(geom.signed_volume(T)) / 1e6:.1f} L (both hulls)")
    print(f"  hull depth (keel-deck) {deck:.1f} mm")
    print(f"  seawater             {RHO_SW:.0f} kg/m3 (Mediterranean)")
    if not mesh["watertight"]:
        print("  WARNING: hull mesh is not closed; volumes are approximate")

    print("\nMASS BASIS")
    print(f"  cockpit incl. pilot  {COCKPIT_CAP_KG:6.1f} kg  (cap, ENERGY_REQ_48)")
    print(f"  hulls + beams        {HULLS_BEAMS_KG:6.1f} kg  (supplied, ENERGY_REQ_3)")
    print(f"  THEORETICAL MAX      {DESIGN_MAX_KG:6.1f} kg")

    if "--mass" in argv:
        m = float(argv[argv.index("--mass") + 1])
        show(f"DISPLACEMENT {m:.0f} kg", condition(T, total_area, m, deck_z=deck),
             pod_floor, keel)
    else:
        for tag, m in MASS_CASES.items():
            show(tag, condition(T, total_area, m, deck_z=deck), pod_floor, keel)

        d = condition(T, total_area, DESIGN_MAX_KG, deck_z=deck)
        dfw = condition(T, total_area, DESIGN_MAX_KG, rho=RHO_FW, deck_z=deck)
        if d and dfw:
            print(f"\nFRESH vs SALT at {DESIGN_MAX_KG:.0f} kg")
            print(f"  salt {RHO_SW:.0f}: draft {d['draft_mm']:.1f} mm, "
                  f"wetted {d['wetted_area_m2']:.3f} m2")
            print(f"  fresh {RHO_FW:.0f}: draft {dfw['draft_mm']:.1f} mm, "
                  f"wetted {dfw['wetted_area_m2']:.3f} m2  "
                  f"({dfw['draft_mm'] - d['draft_mm']:+.1f} mm deeper)")

        if d:
            print("\nWHAT THIS CONSTRAINS")
            print(f"  For level trim the whole-boat LCG must sit at X = "
                  f"{d['lcb_x_mm']:+.1f} mm.")
            print(f"  Every 10 kg of overload sinks the boat "
                  f"{10.0 / d['TPC_kg_per_cm'] * 10:.1f} mm and adds roughly "
                  f"{(condition(T, total_area, DESIGN_MAX_KG + 10, deck_z=deck)['wetted_area_m2'] - d['wetted_area_m2']) * 1e4 / 100:.0f} "
                  f"dm2 of wetted area.")
            print(f"  Reserve buoyancy to the deck: "
                  f"{abs(geom.signed_volume(T)) / 1e6 * RHO_SW / 1000 - d['mass_kg']:.0f} kg "
                  f"before the hulls are fully immersed.")
            print(f"  BMt is {d['BMt_mm'] / 1000:.1f} m - transverse stability is a "
                  f"non-issue at this hull spacing; BMl {d['BMl_mm'] / 1000:.1f} m "
                  f"means trim is set by LCG, not by hull form.")

    if "--sweep" in argv:
        print("\nDISPLACEMENT SWEEP")
        print(f"  {'mass kg':>9}{'WL Z mm':>10}{'draft':>9}{'wetted m2':>11}"
              f"{'wetted %':>10}{'freeboard':>11}{'LCB mm':>10}")
        rows = []
        for m in (150, 200, 250, 280, 315, 350, 400, 450, 500, 600):
            dd = condition(T, total_area, m, deck_z=deck)
            if dd is None:
                print(f"  {m:>9.0f}   submerges")
                continue
            rows.append(dd)
            print(f"  {m:>9.0f}{dd['waterline_z_mm']:>10.1f}{dd['draft_mm']:>9.1f}"
                  f"{dd['wetted_area_m2']:>11.3f}{dd['wetted_fraction'] * 100:>10.1f}"
                  f"{dd['freeboard_mm']:>11.1f}{dd['lcb_x_mm']:>10.1f}")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "hydrostatics.json").write_text(json.dumps(rows, indent=2, default=float))
        print(f"\nwrote {OUT / 'hydrostatics.json'}")

    print("\nNOTE: this is the AT-REST condition. At 55 km/h the boat planes")
    print("(volumetric Froude 6.65) and the running wetted area is a small aft")
    print("patch - a fraction of the figures above.")


if __name__ == "__main__":
    main()
