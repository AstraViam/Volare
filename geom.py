"""Pure-numpy triangle-mesh metrics for the Volare cockpit.

No Blender, no CAD kernel, so every number here is reproducible from a bare
Python install and can be regression-tested. The Blender scripts pull vertex
arrays out of `bpy` and hand them straight to these functions, so the metric
definitions cannot drift between the two environments.
"""
import struct
from pathlib import Path
import numpy as np

# ---------------------------------------------------------------- mesh basics


def read_stl(path):
    """Binary or ASCII STL -> (F,3,3) float64 triangle-vertex array."""
    raw = Path(path).read_bytes()
    if raw[:5] == b"solid" and b"facet" in raw[:512]:
        verts = [[float(x) for x in ln.split()[1:4]]
                 for ln in raw.decode("utf-8", "replace").splitlines()
                 if ln.strip().startswith("vertex")]
        return np.asarray(verts, float).reshape(-1, 3, 3)
    n = struct.unpack("<I", raw[80:84])[0]
    dt = np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")])
    rec = np.frombuffer(raw, dtype=dt, count=n, offset=84)
    return rec["v"].astype(np.float64).reshape(-1, 3, 3)


def write_stl(path, T, header=b"volare"):
    T = np.asarray(T, np.float32).reshape(-1, 3, 3)
    n, _ = tri_normals_areas(T.astype(np.float64))
    dt = np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")])
    rec = np.zeros(len(T), dt)
    rec["n"] = n.astype(np.float32)
    rec["v"] = T.reshape(len(T), 9)
    with open(path, "wb") as f:
        f.write(header[:80].ljust(80, b"\0"))
        f.write(struct.pack("<I", len(T)))
        f.write(rec.tobytes())


def tri_normals_areas(T):
    cr = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    a2 = np.linalg.norm(cr, axis=1)
    nrm = np.zeros_like(cr)
    good = a2 > 1e-20
    nrm[good] = cr[good] / a2[good, None]
    return nrm, 0.5 * a2


def signed_volume(T):
    """Divergence theorem. Positive for outward-wound closed meshes."""
    return np.einsum("ij,ij->i", T[:, 0], np.cross(T[:, 1], T[:, 2])).sum() / 6.0


def weld(T, tol=1e-4):
    P = T.reshape(-1, 3)
    key = np.round(P / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return P[first], inv.reshape(-1, 3)


def manifold_report(V, F):
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    _, c = np.unique(e, axis=0, return_counts=True)
    return {"edges": int(c.size), "boundary_edges": int((c == 1).sum()),
            "manifold_edges": int((c == 2).sum()),
            "non_manifold_edges": int((c >= 3).sum()), "watertight": bool((c == 2).all())}


def loose_parts(T, tol=1e-4):
    """Label triangles by connected component, i.e. separate by loose parts."""
    V, F = weld(T, tol)
    parent = np.arange(len(V))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in F:
        for u, v in ((a, b), (b, c)):
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[rv] = ru
    roots = np.array([find(i) for i in range(len(V))])
    _, inv = np.unique(roots[F[:, 0]], return_inverse=True)
    return inv


# --------------------------------------------------------- projections & cuts


def projected_area(T, axis, pitch=2.0):
    """True silhouette area [m^2] looking down `axis`, by rasterising at `pitch` mm.

    Summing n.d*A over forward-facing triangles only gives the silhouette for a
    convex body. The pod is not convex, so rasterise.
    """
    keep = [i for i in range(3) if i != axis]
    P = T[:, :, keep]
    lo, hi = P.reshape(-1, 2).min(0), P.reshape(-1, 2).max(0)
    nx, ny = np.ceil((hi - lo) / pitch).astype(int) + 1
    grid = np.zeros((nx, ny), bool)
    for t in (P - lo) / pitch:
        c0 = np.maximum(np.floor(t.min(0)).astype(int), 0)
        c1 = np.minimum(np.ceil(t.max(0)).astype(int) + 1, (nx, ny))
        if np.any(c1 <= c0):
            continue
        px, py = np.meshgrid(np.arange(c0[0], c1[0]) + .5,
                             np.arange(c0[1], c1[1]) + .5, indexing="ij")
        v0, v1, v2 = t
        d = (v1[1] - v2[1]) * (v0[0] - v2[0]) + (v2[0] - v1[0]) * (v0[1] - v2[1])
        if abs(d) < 1e-12:
            continue
        w0 = ((v1[1] - v2[1]) * (px - v2[0]) + (v2[0] - v1[0]) * (py - v2[1])) / d
        w1 = ((v2[1] - v0[1]) * (px - v2[0]) + (v0[0] - v2[0]) * (py - v2[1])) / d
        m = (w0 >= -1e-9) & (w1 >= -1e-9) & (w0 + w1 <= 1 + 1e-9)
        if m.any():
            grid[c0[0]:c1[0], c0[1]:c1[1]] |= m
    return grid.sum() * pitch * pitch / 1e6


def plane_segments(T, axis, c):
    """Intersect the mesh with the plane axis=c.

    Returns (S, keep): S is (M,2,2), segments in the two in-plane coords, each
    oriented along n x e_axis (n = outward facet normal). That makes every
    segment run with the interior on a consistent side, so the loops are signed
    consistently without having to be ordered into loops first. Taking the
    orientation from the winding order of the crossed edges does NOT work - it
    flips with the vertex sign pattern.
    """
    d = T[:, :, axis] - c
    hit = ((d > 0).sum(1) > 0) & ((d < 0).sum(1) > 0)
    keep = [i for i in range(3) if i != axis]
    if not hit.any():
        return np.zeros((0, 2, 2)), keep
    Th, dh = T[hit], d[hit]

    # A mixed-sign triangle always has exactly one vertex alone on its side.
    # Roll that vertex to index 0, then the two crossings are on edges 0-1 and
    # 0-2 - which makes the whole thing vectorisable.
    above = dh > 0
    lone = np.where(above.sum(1) == 1, np.argmax(above, axis=1),
                    np.argmax(~above, axis=1))
    idx = (lone[:, None] + np.arange(3)[None, :]) % 3
    r = np.take_along_axis(Th, idx[:, :, None].repeat(3, axis=2), axis=1)
    rd = np.take_along_axis(dh, idx, axis=1)

    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = rd[:, 0] / (rd[:, 0] - rd[:, 1])
        t2 = rd[:, 0] / (rd[:, 0] - rd[:, 2])
    p1 = r[:, 0] + t1[:, None] * (r[:, 1] - r[:, 0])
    p2 = r[:, 0] + t2[:, None] * (r[:, 2] - r[:, 0])

    e = np.zeros(3)
    e[axis] = 1.0
    nrm, _ = tri_normals_areas(Th)
    dirs = np.cross(nrm, e)[:, keep]
    a, b = p1[:, keep], p2[:, keep]
    flip = np.einsum("ij,ij->i", b - a, dirs) < 0
    S = np.stack([np.where(flip[:, None], b, a),
                  np.where(flip[:, None], a, b)], axis=1)
    good = np.isfinite(S).all(axis=(1, 2))
    return S[good], keep


def section_area(T, axis, c):
    """Enclosed cross-section area [mm^2] of a closed mesh at plane axis=c.

    Shoelace over consistently-oriented segments: no loop ordering required, and
    correct for sections that split into several loops.
    """
    S, _ = plane_segments(T, axis, c)
    if len(S) == 0:
        return 0.0
    p, q = S[:, 0], S[:, 1]
    return abs(0.5 * (p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]).sum())


def section_profile(T, axis=0, n=120, pad=1e-3):
    """Area-distribution curve along `axis`: stations, area mm^2, width, height."""
    lo, hi = T[:, :, axis].min(), T[:, :, axis].max()
    span = hi - lo
    xs = np.linspace(lo + pad * span, hi - pad * span, n)
    A = np.empty(n)
    W = np.zeros(n)
    H = np.zeros(n)
    for i, c in enumerate(xs):
        S, _ = plane_segments(T, axis, c)
        A[i] = section_area(T, axis, c)
        if len(S):
            P = S.reshape(-1, 2)
            W[i] = P[:, 0].max() - P[:, 0].min()
            H[i] = P[:, 1].max() - P[:, 1].min()
    return xs, A, W, H


def centreline_profile(T, y=0.0, n=240):
    """Top and bottom Z along the plane Y=y, as functions of X.

    Feeds the aft-body closure-angle check in note 01 section 4.2.
    """
    S, _ = plane_segments(T, 1, y)          # in-plane coords are (X, Z)
    if len(S) == 0:
        return np.zeros(0), np.zeros(0), np.zeros(0)
    P = S.reshape(-1, 2)
    xs = np.linspace(P[:, 0].min(), P[:, 0].max(), n)
    top = np.full(n, np.nan)
    bot = np.full(n, np.nan)
    a, b = S[:, 0], S[:, 1]
    span = a[:, 0] != b[:, 0]
    for i, x in enumerate(xs):
        m = (((a[:, 0] - x) * (b[:, 0] - x)) <= 0) & span
        if not m.any():
            continue
        t = (x - a[m, 0]) / (b[m, 0] - a[m, 0])
        z = a[m, 1] + t * (b[m, 1] - a[m, 1])
        top[i], bot[i] = z.max(), z.min()
    return xs, top, bot


def closure_angle(xs, top, x_peak, x_tail):
    """Mean and max downward slope [deg] of the top line between two stations.

    X is forward-positive, so the aft body runs from the coaming peak (larger X)
    down to the tail (smaller X).
    """
    m = np.isfinite(top) & (xs >= min(x_peak, x_tail)) & (xs <= max(x_peak, x_tail))
    if m.sum() < 3:
        return float("nan"), float("nan")
    x, z = xs[m], top[m]
    mean = np.degrees(np.arctan2(z[-1] - z[0], abs(x[-1] - x[0])))
    local = np.degrees(np.arctan(np.gradient(z, x)))
    return abs(mean), float(np.nanmax(np.abs(local)))


# ----------------------------------------------------------------- shape stats


def shape_stats(T, pitch=2.0, centreline=False):
    """The metric block every design point reports. Lengths mm, areas m^2."""
    _, a = tri_normals_areas(T)
    V, F = weld(T)
    lo, hi = T.reshape(-1, 3).min(0), T.reshape(-1, 3).max(0)
    size = hi - lo
    frontal = projected_area(T, 0, pitch)
    d_eq = 2.0 * np.sqrt(frontal * 1e6 / np.pi)     # equivalent circular diameter
    out = {
        "triangles": int(len(T)),
        "bbox_min_mm": lo.round(2).tolist(),
        "bbox_size_mm": size.round(2).tolist(),
        "length_mm": float(size[0]), "beam_mm": float(size[1]), "height_mm": float(size[2]),
        "surface_area_m2": float(a.sum() / 1e6),
        "volume_L": float(abs(signed_volume(T)) / 1e6),
        "frontal_m2": float(frontal),
        "planform_m2": float(projected_area(T, 2, pitch)),
        "profile_m2": float(projected_area(T, 1, pitch)),
        "fineness_L_over_Deq": float(size[0] / d_eq) if d_eq > 0 else float("nan"),
        "mesh": manifold_report(V, F),
    }
    if centreline:
        out["_centreline"] = centreline_profile(T)
    return out


# ------------------------------------------------------------------ self-test


def _box(lo, hi):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    f = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    return v[f]


def _selftest():
    print("geom.py selftest")
    box = _box(np.array([0., 0., 0.]), np.array([100., 200., 300.]))
    assert abs(signed_volume(box) / 1e3 - 6000) < 1e-6
    assert abs(section_area(box, 0, 50.0) - 200 * 300) < 1e-6
    assert abs(projected_area(box, 0, 1.0) - 0.06) < 2e-4
    print("  OK   analytic box: volume, section area, projected area")

    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from volare import pod_to_boat
    P = read_stl(Path(__file__).resolve().parents[2] / "source_documents" / "Cockpit_V1_3.stl")
    T = pod_to_boat(P.reshape(-1, 3)).reshape(-1, 3, 3)

    xs, A, W, H = section_profile(T, 0, n=400)
    v_int = np.trapezoid(A, xs) / 1e6
    v_div = abs(signed_volume(T)) / 1e6
    err = abs(v_int - v_div) / v_div
    print(f"  {'OK  ' if err < 0.01 else 'FAIL'} pod volume: divergence {v_div:.2f} L vs "
          f"area-integral {v_int:.2f} L ({err * 100:.2f}%)")

    st = shape_stats(T)
    good = True
    for k, exp in (("surface_area_m2", 4.5803), ("volume_L", 320.58),
                   ("frontal_m2", 0.2702), ("planform_m2", 1.5114),
                   ("profile_m2", 0.7518)):
        ok = abs(st[k] - exp) < max(0.005 * exp, 1e-3)
        good &= ok
        print(f"  {'OK  ' if ok else 'FAIL'} pod {k:<16} = {st[k]:.4f}  (audit {exp})")
    return good and err < 0.01


if __name__ == "__main__":
    raise SystemExit(0 if _selftest() else 1)
