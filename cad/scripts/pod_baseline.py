"""Characterise the V1.3 pod in the canonical boat frame.

Extracts the shape signature the parametric model has to reproduce - area
distribution, top/bottom centreline, coaming peak, cockpit opening, aft closure
angle - and re-tests the specific geometry defects called out in note 00.

Writes cad/out/pod_baseline.json and cad/out/pod_baseline.csv.
"""
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import geom
import volare as V

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cad" / "out"


def load_pod():
    P = geom.read_stl(ROOT / "source_documents" / "Cockpit_V1_3.stl")
    return V.pod_to_boat(P.reshape(-1, 3)).reshape(-1, 3, 3)


def cockpit_opening(T, z_probe=None):
    """The pod file is closed, so the opening shows up as an inward-folded rim.

    Find it as the region where the Y=0 top line drops below the local crown:
    slice horizontally just under the crown and look for the inner loop.
    """
    zmax = T[:, :, 2].max()
    z = z_probe if z_probe is not None else zmax - 30.0
    S, _ = geom.plane_segments(T, 2, z)          # in-plane coords (X, Y)
    if len(S) == 0:
        return None
    P = S.reshape(-1, 2)
    return {"probe_z_mm": round(float(z), 1),
            "x_extent_mm": round(float(P[:, 0].max() - P[:, 0].min()), 1),
            "y_extent_mm": round(float(P[:, 1].max() - P[:, 1].min()), 1),
            "segments": int(len(S))}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    T = load_pod()
    st = geom.shape_stats(T)

    # area distribution along X (forward positive)
    xs, A, W, H = geom.section_profile(T, 0, n=300)
    i_max = int(np.argmax(A))

    # centreline top / bottom
    cx, ctop, cbot = geom.centreline_profile(T, y=0.0, n=400)
    good = np.isfinite(ctop)
    x_peak = float(cx[good][np.argmax(ctop[good])])
    z_peak = float(np.nanmax(ctop))
    x_tail = float(cx[good].min())
    x_nose = float(cx[good].max())

    mean_cl, max_cl = geom.closure_angle(cx, ctop, x_peak, x_tail)

    # slope profile aft of the peak, for the <=12 deg target in note 01 s4.2
    m = good & (cx <= x_peak)
    slope = np.degrees(np.arctan(np.gradient(ctop[m], cx[m])))
    x_aft = cx[m]
    over12 = float(np.sum(np.abs(slope) > 12.0) / max(len(slope), 1) * 100.0)

    # tail base: cross-section area at the aftmost station -> base drag patch
    base_area_mm2 = geom.section_area(T, 0, x_tail + 2.0)

    rep = {
        "frame": "canonical boat frame: X forward, Y port, Z up, origin = centreline x hull mid-length x keel",
        "shape": {k: v for k, v in st.items() if k != "mesh"},
        "mesh": st["mesh"],
        "stations": {
            "x_nose_mm": round(x_nose, 1),
            "x_tail_mm": round(x_tail, 1),
            "x_max_section_mm": round(float(xs[i_max]), 1),
            "max_section_area_m2": round(float(A[i_max]) / 1e6, 4),
            "max_section_at_pct_from_nose": round(float((x_nose - xs[i_max]) / (x_nose - x_tail) * 100), 1),
            "x_coaming_peak_mm": round(x_peak, 1),
            "z_coaming_peak_mm": round(z_peak, 1),
            "z_floor_mm": round(float(T[:, :, 2].min()), 1),
        },
        "aft_body": {
            "peak_to_tail_mm": round(x_peak - x_tail, 1),
            "drop_mm": round(z_peak - float(ctop[good][0]), 1),
            "mean_closure_deg": round(float(mean_cl), 2),
            "max_local_slope_deg": round(float(max_cl), 2),
            "pct_of_aft_body_over_12deg": round(over12, 1),
            "base_area_at_tail_m2": round(float(base_area_mm2) / 1e6, 4),
        },
        "opening_probe": cockpit_opening(T),
        "defects": {},
    }

    # --- the three geometry defects from note 00 section 1, re-tested ---------
    d = rep["defects"]
    d["rail_pod_interference_mm"] = round(V.RAIL_POD_INTERFERENCE, 1)
    d["rail_spacing_mm"] = V.BASELINE["rail"]["spacing_cc"]
    d["rail_spacing_required_mm"] = V.CLAMP_MIN_SPACING
    d["rail_spacing_compliant"] = V.BASELINE["rail"]["spacing_cc"] >= V.CLAMP_MIN_SPACING
    d["aft_closure_target_deg"] = 12.0
    d["aft_closure_compliant"] = bool(mean_cl <= 12.0)
    d["truncated_tail"] = bool(base_area_mm2 / 1e6 > 0.005)

    (OUT / "pod_baseline.json").write_text(json.dumps(rep, indent=2))

    # station table for the parametric fit
    ct = np.interp(xs, cx[good][::-1], ctop[good][::-1])
    cb = np.interp(xs, cx[good][::-1], cbot[good][::-1])
    lines = ["x_mm,area_mm2,width_mm,height_mm,z_top_mm,z_bot_mm"]
    lines += [f"{x:.2f},{a:.1f},{w:.2f},{h:.2f},{t:.2f},{b:.2f}"
              for x, a, w, h, t, b in zip(xs, A, W, H, ct, cb)]
    (OUT / "pod_baseline.csv").write_text("\n".join(lines))

    # --- console summary ------------------------------------------------------
    s, stn, ab = rep["shape"], rep["stations"], rep["aft_body"]
    print("V1.3 POD BASELINE  (canonical boat frame, mm / m2)\n")
    print(f"  envelope           {s['length_mm']:.1f} L x {s['beam_mm']:.1f} B x {s['height_mm']:.1f} H")
    print(f"  laminate area      {s['surface_area_m2']:.4f} m2")
    print(f"  enclosed volume    {s['volume_L']:.1f} L")
    print(f"  frontal / planform {s['frontal_m2']:.4f} / {s['planform_m2']:.4f} m2")
    print(f"  fineness L/Deq     {s['fineness_L_over_Deq']:.2f}   (min-drag band 4-6)")
    print(f"  watertight         {st['mesh']['watertight']}")
    print(f"\n  nose X {stn['x_nose_mm']:+.0f} -> tail X {stn['x_tail_mm']:+.0f}")
    print(f"  max section        {stn['max_section_area_m2']:.4f} m2 at X {stn['x_max_section_mm']:+.0f} "
          f"({stn['max_section_at_pct_from_nose']:.0f}% aft of nose)")
    print(f"  coaming peak       X {stn['x_coaming_peak_mm']:+.0f}, Z {stn['z_coaming_peak_mm']:.0f}")
    print("\nAFT BODY (note 01 s4.2 target: mean <= 12 deg)")
    print(f"  peak -> tail       {ab['peak_to_tail_mm']:.0f} mm run, {ab['drop_mm']:.0f} mm drop")
    print(f"  mean closure       {ab['mean_closure_deg']:.2f} deg   "
          f"{'PASS' if ab['mean_closure_deg'] <= 12 else 'FAIL - separation risk'}")
    print(f"  max local slope    {ab['max_local_slope_deg']:.2f} deg")
    print(f"  aft body over 12deg {ab['pct_of_aft_body_over_12deg']:.0f}% of stations")
    print(f"  base patch at tail {ab['base_area_at_tail_m2']:.4f} m2  "
          f"{'-> keep sharp-edged (note 01 s4.4)' if d['truncated_tail'] else ''}")
    print("\nDEFECTS")
    print(f"  rail/pod interference   {d['rail_pod_interference_mm']:.1f} mm  (note 00 said 83)")
    print(f"  rail spacing            {d['rail_spacing_mm']:.0f} mm vs {d['rail_spacing_required_mm']:.0f} required"
          f"  -> {'OK' if d['rail_spacing_compliant'] else 'NON-COMPLIANT, ENERGY_REQ_38'}")
    print(f"\nwrote {OUT / 'pod_baseline.json'}")
    print(f"wrote {OUT / 'pod_baseline.csv'}  ({len(xs)} stations)")


if __name__ == "__main__":
    main()
