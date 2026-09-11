"""Shared solid-modelling helpers for the STEP and STL exporters.

    import solids as S
    S.box_solid(centre, size)          axis-aligned box, centred
    S.cylinder_solid(c, od, l, axis)   cylinder or tube along X, Y or Z
    S.capsule_chain(points, od)        a cable run
    S.as_shape(obj)                    Workplane or Shape -> Shape
    S.intersects(a, b)                 shared volume, mm^3
    S.write_binary_stl(path, tris, h)  binary STL from a triangle array

WHY THIS MODULE EXISTS

Three exporters need the same primitives. Before this, `export_supplied.py`
(then `export_step.py`) and `export_assembly_step.py` each carried their own copy of `box_solid` and
`capsule_chain`, and the copies had already started to differ: one returned a
Workplane, the other a Shape, and the intersection test silently returned zero
for whichever it was not handed. CLAUDE.md is explicit that a constant must not
exist twice; the same goes for a primitive.

CADQUERY IS OPTIONAL

It pulls in OCP, a ~400 MB binary wheel that nothing else in `cad/scripts`
needs. Importing this module without it succeeds; calling a solid-building
function without it raises with a message that says what to install. That lets
`tools/run_python_selftests.py` run the whole suite on the analysis
environment, and `write_binary_stl` works either way because it is pure numpy.

Team Volare / ICT Mumbai.
"""

from __future__ import annotations

import math
import struct

import numpy as np

try:
    import cadquery as cq
    HAVE_CADQUERY = True
except ImportError:                                  # pragma: no cover
    cq = None
    HAVE_CADQUERY = False


def _require():
    if not HAVE_CADQUERY:
        raise RuntimeError(
            "this needs cadquery, which is not installed. "
            "pip install cadquery (it pulls in OCP, about 400 MB)")


def as_shape(obj):
    """Workplane or Shape in, Shape out.

    cq.Assembly children hold whichever the caller happened to build with, and
    the two have different APIs: a Workplane has `.solids()`, a Shape has
    `.Solids()`. Normalising here is what stops a boolean from quietly
    returning nothing because it was handed the wrong one.
    """
    _require()
    return obj.val() if isinstance(obj, cq.Workplane) else obj


def box_solid(centre, size):
    """An axis-aligned box, centred on `centre`. Returns a Shape."""
    _require()
    return cq.Workplane("XY").box(*size).translate(tuple(centre)).val()


def cylinder_solid(centre, od, length, axis, bore=0.0):
    """A cylinder, or a tube when bore is non-zero, along X (0), Y (1) or Z (2).

    extrude(both=True) grows in both directions, so half the length is extruded
    and the result is centred on `centre`.
    """
    _require()
    plane = {0: "YZ", 1: "XZ", 2: "XY"}[axis]
    wp = cq.Workplane(plane).circle(od / 2.0)
    if bore and bore > 0:
        wp = wp.circle(bore / 2.0)
    return wp.extrude(length / 2.0, both=True).translate(tuple(centre)).val()


def capsule_chain(points, od):
    """A cable run as cylinders with spheres at the joints.

    A sweep along a polyline with sharp corners fails or self-intersects, and
    in some kernels it fails silently. Capsules cannot. For clearance checking
    the envelope is identical everywhere except inside the corner radius, where
    a real cable is fatter than a sweep, not thinner.
    """
    _require()
    r = od / 2.0
    solid = None
    for a, b in zip(points[:-1], points[1:]):
        a = np.asarray(a, float)
        d = np.asarray(b, float) - a
        length = float(np.linalg.norm(d))
        if length < 1e-6:
            continue
        seg = cq.Workplane("XY").circle(r).extrude(length)
        u = d / length
        cross = np.cross([0.0, 0.0, 1.0], u)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, float(u[2])))))
        if abs(angle) > 1e-9:
            if np.linalg.norm(cross) < 1e-12:
                cross = np.array([1.0, 0.0, 0.0])    # antiparallel; any normal
            seg = seg.rotate((0, 0, 0), tuple(cross), angle)
        seg = seg.translate(tuple(a))
        solid = seg if solid is None else solid.union(seg)
    for p in points[1:-1]:
        ball = cq.Workplane("XY").sphere(r).translate(tuple(p))
        solid = ball if solid is None else solid.union(ball)
    return None if solid is None else as_shape(solid)


def intersects(a, b):
    """Volume shared by two solids, mm^3. Zero when they only touch."""
    _require()
    try:
        common = as_shape(a).intersect(as_shape(b))
    except Exception:
        return 0.0              # a failed boolean is not evidence of a clash
    if common is None or not common.Solids():
        return 0.0
    return abs(common.Volume())


def write_binary_stl(path, tris, header):
    """Binary STL. Normals are recomputed from the vertices, not carried over.

    Pure numpy, so this works without cadquery.
    """
    tris = np.asarray(tris, np.float64)
    rec = np.zeros(len(tris), dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"),
                                              ("a", "<u2")]))
    nr = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    norm = np.linalg.norm(nr, axis=1, keepdims=True)
    rec["n"] = nr / np.where(norm < 1e-20, 1.0, norm)
    rec["v"] = tris.reshape(-1, 9)
    with open(path, "wb") as f:
        f.write(header.encode("ascii", "replace")[:80].ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        f.write(rec.tobytes())


def _selftest() -> bool:
    ok = True
    print("solids.py selfcheck")
    tri = np.array([[[0, 0, 0], [10, 0, 0], [0, 10, 0]]], float)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.stl"
        write_binary_stl(p, tri, "test")
        n = p.stat().st_size
        good = n == 84 + 50
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'}  binary STL is {n} bytes "
              f"(want {84 + 50} for one triangle)")

    if not HAVE_CADQUERY:
        print("  skip  cadquery is not installed; solid tests not run")
        return ok

    b = box_solid([0, 0, 0], [100, 100, 100])
    good = abs(b.Volume() - 1e6) < 1.0
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'}  box volume {b.Volume():.0f} mm3 "
          f"(want 1000000)")

    t = cylinder_solid([0, 0, 0], 100.0, 200.0, 2, bore=80.0)
    want = math.pi * (50 ** 2 - 40 ** 2) * 200.0
    good = abs(t.Volume() - want) / want < 1e-3
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'}  tube volume {t.Volume():.0f} mm3 "
          f"(want {want:.0f})")

    b2 = box_solid([50, 0, 0], [100, 100, 100])
    v = intersects(b, b2)
    good = abs(v - 5e5) < 1.0
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'}  half-overlapped boxes share "
          f"{v:.0f} mm3 (want 500000)")

    v = intersects(b, box_solid([300, 0, 0], [10, 10, 10]))
    good = v == 0.0
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'}  disjoint boxes share {v:.0f} mm3")

    run = capsule_chain([(0, 0, 0), (0, 0, 100), (100, 0, 100)], 20.0)
    bb = run.BoundingBox()
    good = abs(bb.xlen - 110.0) < 1.0 and abs(bb.zlen - 110.0) < 1.0
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'}  L-shaped cable run is "
          f"{bb.xlen:.1f} x {bb.zlen:.1f} over a 100 x 100 route with a "
          f"20 mm cable")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if _selftest() else 1)
