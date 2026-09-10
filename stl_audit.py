"""Baseline geometry audit of the Volare cockpit STLs.

Pure numpy - no Blender, no CAD kernel. Establishes the numbers the parametric
Blender model has to reproduce, and re-checks the figures quoted in
notes/00 - Master Brief.md section 1.
"""
import sys, struct, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "source_documents"
OUT = ROOT / "cad" / "out"


def read_stl(path):
    """Binary or ASCII STL -> (F,3,3) float64 array of triangle vertices."""
    raw = path.read_bytes()
    if raw[:5] == b"solid" and b"facet" in raw[:512]:
        verts = []
        for line in raw.decode("utf-8", "replace").splitlines():
            s = line.strip()
            if s.startswith("vertex"):
                verts.append([float(x) for x in s.split()[1:4]])
        return np.asarray(verts, float).reshape(-1, 3, 3)
    n = struct.unpack("<I", raw[80:84])[0]
    rec = np.frombuffer(raw, dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]),
                        count=n, offset=84)
    return rec["v"].astype(np.float64).reshape(-1, 3, 3)


def tri_normals_areas(T):
    e1 = T[:, 1] - T[:, 0]
    e2 = T[:, 2] - T[:, 0]
    cr = np.cross(e1, e2)
    a2 = np.linalg.norm(cr, axis=1)
    a = 0.5 * a2
    nrm = np.zeros_like(cr)
    good = a2 > 1e-20
    nrm[good] = cr[good] / a2[good, None]
    return nrm, a


def signed_volume(T):
    """Divergence-theorem volume. Sign tells you the winding direction."""
    return np.einsum("ij,ij->i", T[:, 0], np.cross(T[:, 1], T[:, 2])).sum() / 6.0


def weld(T, tol=1e-4):
    """Merge coincident vertices -> (V, F) index mesh."""
    P = T.reshape(-1, 3)
    key = np.round(P / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return P[first], inv.reshape(-1, 3)


def manifold_report(V, F):
    """Edge-use histogram. A closed 2-manifold has every edge used exactly twice."""
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.sort(e, axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return {"edges": int(counts.size),
            "boundary_edges_used_1x": int((counts == 1).sum()),
            "manifold_edges_used_2x": int((counts == 2).sum()),
            "non_manifold_used_3x_plus": int((counts >= 3).sum()),
            "watertight": bool((counts == 2).all())}


def components(V, F):
    """Union-find over triangles sharing a welded vertex."""
    parent = np.arange(len(V))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in F:
        for u, v in ((a, b), (b, c)):
            ra, rb = find(u), find(v)
            if ra != rb:
                parent[rb] = ra
    roots = np.array([find(i) for i in range(len(V))])
    tri_root = roots[F[:, 0]]
    labels, inv = np.unique(tri_root, return_inverse=True)
    return inv, len(labels)


def projected_area(T, axis, pitch=2.0):
    """True silhouette area by rasterising the projection onto a `pitch`-mm grid.

    Summing n.d*A over forward-facing triangles only equals the silhouette for a
    convex body; the pod is not convex, so rasterise instead.
    """
    keep = [i for i in range(3) if i != axis]
    P = T[:, :, keep]                                   # (F,3,2)
    lo = P.reshape(-1, 2).min(0)
    hi = P.reshape(-1, 2).max(0)
    nx, ny = np.ceil((hi - lo) / pitch).astype(int) + 1
    grid = np.zeros((nx, ny), bool)
    G = (P - lo) / pitch                                # triangle coords in cells
    for t in G:
        c0 = np.floor(t.min(0)).astype(int)
        c1 = np.ceil(t.max(0)).astype(int) + 1
        c0 = np.maximum(c0, 0)
        c1 = np.minimum(c1, (nx, ny))
        if np.any(c1 <= c0):
            continue
        xs = np.arange(c0[0], c1[0]) + 0.5
        ys = np.arange(c0[1], c1[1]) + 0.5
        px, py = np.meshgrid(xs, ys, indexing="ij")
        v0, v1, v2 = t
        d = (v1[1] - v2[1]) * (v0[0] - v2[0]) + (v2[0] - v1[0]) * (v0[1] - v2[1])
        if abs(d) < 1e-12:
            continue
        w0 = ((v1[1] - v2[1]) * (px - v2[0]) + (v2[0] - v1[0]) * (py - v2[1])) / d
        w1 = ((v2[1] - v0[1]) * (px - v2[0]) + (v0[0] - v2[0]) * (py - v2[1])) / d
        w2 = 1.0 - w0 - w1
        m = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if m.any():
            grid[c0[0]:c1[0], c0[1]:c1[1]] |= m
    return grid.sum() * pitch * pitch / 1e6             # m^2


def summarise(name, T, do_proj=True):
    nrm, a = tri_normals_areas(T)
    V, F = weld(T)
    lo, hi = T.reshape(-1, 3).min(0), T.reshape(-1, 3).max(0)
    vol = signed_volume(T)
    # area-weighted surface centroid
    cen = (T.mean(1) * a[:, None]).sum(0) / a.sum()
    d = {
        "name": name,
        "triangles": int(len(T)),
        "welded_vertices": int(len(V)),
        "degenerate_triangles": int((a <= 1e-9).sum()),
        "bbox_min_mm": lo.round(1).tolist(),
        "bbox_max_mm": hi.round(1).tolist(),
        "bbox_size_mm": (hi - lo).round(1).tolist(),
        "surface_area_m2": round(a.sum() / 1e6, 4),
        "signed_volume_L": round(vol / 1e6, 2),
        "surface_centroid_mm": cen.round(1).tolist(),
        "mesh": manifold_report(V, F),
    }
    if do_proj:
        d["projected_area_m2"] = {
            "frontal_X": round(projected_area(T, 0), 4),
            "profile_Y": round(projected_area(T, 1), 4),
            "planform_Z": round(projected_area(T, 2), 4),
        }
    return d


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}

    pod = read_stl(SRC / "Cockpit_V1_3.stl")
    report["pod"] = summarise("Cockpit_V1_3 (pod shell)", pod)

    full = read_stl(SRC / "FULLCOCPITV1_3.stl")
    report["full_assembly"] = summarise("FULLCOCPITV1_3 (full assembly)", full, do_proj=True)

    # split the assembly into physical parts
    V, F = weld(full)
    lab, ncomp = components(V, F)
    parts = []
    for i in range(ncomp):
        Ti = full[lab == i]
        nrm, a = tri_normals_areas(Ti)
        if a.sum() < 1000:          # < 0.001 m^2, stray shard
            continue
        lo, hi = Ti.reshape(-1, 3).min(0), Ti.reshape(-1, 3).max(0)
        parts.append({
            "triangles": int(len(Ti)),
            "bbox_min_mm": lo.round(1).tolist(),
            "bbox_size_mm": (hi - lo).round(1).tolist(),
            "centroid_mm": ((Ti.mean(1) * a[:, None]).sum(0) / a.sum()).round(1).tolist(),
            "surface_area_m2": round(a.sum() / 1e6, 4),
            "volume_L": round(abs(signed_volume(Ti)) / 1e6, 2),
        })
    parts.sort(key=lambda p: -p["surface_area_m2"])
    report["assembly_components"] = {"count": len(parts), "parts": parts}

    (OUT / "stl_audit.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
