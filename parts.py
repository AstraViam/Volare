"""Split FULLCOCPITV1_3.stl into named parts and tag them by CFD wall zone.

Kept out of the Blender script deliberately: the classification is pure numpy so
it can be regression-tested from a bare Python install, and Blender just consumes
the result. Names match the wall zones the force reports are split by in
note 01 section 5.
"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import geom
import volare as V

ROOT = Path(__file__).resolve().parents[2]

# Parts the rules forbid us from touching (ENERGY_REQ_3).
SUPPLIED = {"hull_port", "hull_stbd", "beam_fwd", "beam_aft"}


def classify(size, cen):
    """Rule-based part naming from bounding-box size and centroid (boat frame, mm).

    Ordered most-distinctive first. Returns (name, collection, cfd_zone).
    """
    dx, dy, dz = size
    side = "port" if cen[1] > 0 else "stbd"
    # anything sitting on a demihull centreline is hull hardware, not rail hardware
    on_hull = abs(abs(cen[1]) - abs(V.BASELINE["hull"]["y_centres"][0])) < 120.0

    if dx > 4000:                                  # 4992 mm demihull
        return f"hull_{side}", "SUPPLIED", "hull-above-wl"
    if dx > 2000 and dy > 600:                     # 2537 x 700 pod
        return "pod_shell", "COCKPIT", "pod-shell"
    if dy > 2000 and dx < 200:                     # crossbeam, runs athwartships
        which = "fwd" if cen[0] > 0 else "aft"
        return f"beam_{which}", "SUPPLIED", f"beam-{which}"
    if dx > 2000 and dy < 200:                     # 3112 mm rail, runs fore-aft
        return f"rail_{side}", "FRAME", f"rail-{side}"
    if on_hull:                                    # beam-to-hull clamp hardware
        return f"hull_clamp_{side}", "FRAME", "bracket"
    if dx < 40 and 100 < dy < 200:                 # 16.5 x 139 x 50 rail mounting pad
        return f"rail_pad_{side}", "FRAME", "pad"
    if dz < 40:
        return f"clamp_plate_{side}", "FRAME", "bracket"
    return f"bracket_{side}", "FRAME", "bracket"


def split_assembly(path=None, min_area_mm2=1000.0):
    """-> list of dicts, one per part, in the canonical boat frame (mm)."""
    path = path or ROOT / "source_documents" / "FULLCOCPITV1_3.stl"
    raw = geom.read_stl(path)
    T = V.asm_to_boat(raw.reshape(-1, 3)).reshape(-1, 3, 3)

    lab = geom.loose_parts(T)
    out = []
    for i in range(lab.max() + 1):
        Ti = T[lab == i]
        _, a = geom.tri_normals_areas(Ti)
        if a.sum() < min_area_mm2:
            continue
        lo, hi = Ti.reshape(-1, 3).min(0), Ti.reshape(-1, 3).max(0)
        size = hi - lo
        cen = (Ti.mean(1) * a[:, None]).sum(0) / a.sum()
        name, coll, zone = classify(size, cen)
        out.append({
            "name": name, "collection": coll, "cfd_zone": zone,
            "tris": Ti, "triangles": int(len(Ti)),
            "bbox_min": lo, "bbox_size": size, "centroid": cen,
            "area_m2": float(a.sum() / 1e6),
            "volume_L": float(abs(geom.signed_volume(Ti)) / 1e6),
            "supplied": name in SUPPLIED,
        })

    # de-duplicate names that repeat (pads, brackets) with a station index
    seen = {}
    for p in sorted(out, key=lambda p: (p["name"], -p["centroid"][0])):
        n = p["name"]
        seen[n] = seen.get(n, 0) + 1
    counts = dict(seen)
    idx = {}
    for p in sorted(out, key=lambda p: (p["name"], -p["centroid"][0])):
        n = p["name"]
        if counts[n] > 1:
            idx[n] = idx.get(n, 0) + 1
            p["name"] = f"{n}_{idx[n]}"
    return sorted(out, key=lambda p: -p["area_m2"])


def check_pod_registration(parts, tol=1.0):
    """Compare the pod-only STL against the assembly's pod copy.

    Checks volare.pod_to_boat, which was derived by hand, AND quantifies the
    revision drift between the two files - they are not the same mesh.
    """
    pod_asm = next(p for p in parts if p["name"] == "pod_shell")
    P = geom.read_stl(ROOT / "source_documents" / "Cockpit_V1_3.stl")
    pod_std = V.pod_to_boat(P.reshape(-1, 3)).reshape(-1, 3, 3)
    a = pod_asm["tris"].reshape(-1, 3)
    b = pod_std.reshape(-1, 3)
    d_min = np.abs(a.min(0) - b.min(0))
    d_max = np.abs(a.max(0) - b.max(0))
    return {"bbox_min_delta_mm": d_min.round(2).tolist(),
            "bbox_max_delta_mm": d_max.round(2).tolist(),
            # anchored on the nose (Xmax) and the floor (Zmin); Y must also match.
            "anchored": bool(max(d_max[0], d_min[2], d_min[1], d_max[1]) <= tol),
            "revision_drift_mm": {"tail_x": float(d_min[0].round(2)),
                                  "crown_z": float(d_max[2].round(2))}}


def main():
    parts = split_assembly()
    print(f"{len(parts)} parts, canonical boat frame (X fwd, Y port, Z up)\n")
    hdr = f"{'name':<18}{'coll':<10}{'cfd zone':<14}{'tris':>7}" \
          f"{'dX':>8}{'dY':>8}{'dZ':>8}{'cX':>9}{'cY':>9}{'cZ':>8}{'m2':>8}"
    print(hdr)
    print("-" * len(hdr))
    for p in parts:
        s, c = p["bbox_size"], p["centroid"]
        flag = " *" if p["supplied"] else ""
        print(f"{p['name']:<18}{p['collection']:<10}{p['cfd_zone']:<14}{p['triangles']:>7}"
              f"{s[0]:>8.1f}{s[1]:>8.1f}{s[2]:>8.1f}{c[0]:>9.1f}{c[1]:>9.1f}{c[2]:>8.1f}"
              f"{p['area_m2']:>8.4f}{flag}")
    print("\n  * = supplied by the organiser, ENERGY_REQ_3, do not modify")

    reg = check_pod_registration(parts)
    print(f"\npod-only STL vs assembly copy, anchored on nose + floor: "
          f"{'anchor OK' if reg['anchored'] else 'ANCHOR BAD'}")
    print(f"  revision drift: assembly copy is {reg['revision_drift_mm']['tail_x']:.1f} mm "
          f"longer in the tail and {reg['revision_drift_mm']['crown_z']:.1f} mm taller at the crown")
    print("  -> these are DIFFERENT REVISIONS of the pod, not the same mesh."
          " The assembly copy is authoritative; confirm with the modeller.")

    # derived checks that matter for the frame redesign
    rails = [p for p in parts if p["cfd_zone"].startswith("rail-")]
    if len(rails) == 2:
        sp = abs(rails[0]["centroid"][1] - rails[1]["centroid"][1])
        print(f"rail spacing {sp:.1f} mm  -> needs {V.CLAMP_MIN_SPACING:.0f} mm "
              f"(ENERGY_REQ_38): move each rail outboard by "
              f"{(V.CLAMP_MIN_SPACING - sp) / 2:.1f} mm")
    beams = {p["name"]: p for p in parts if p["name"].startswith("beam")}
    if len(beams) == 2:
        print(f"beam span {abs(beams['beam_fwd']['centroid'][0] - beams['beam_aft']['centroid'][0]):.1f} mm "
              f"(fixed by the hull suspension stations)")
        dz = beams["beam_fwd"]["centroid"][2] - beams["beam_aft"]["centroid"][2]
        print(f"beam height step: fwd sits {dz:+.1f} mm relative to aft "
              f"-> the rails are not level, check this against the real poles")
    return reg["anchored"]


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
