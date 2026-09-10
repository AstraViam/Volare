"""
pod_envelope.py -- the pod's real internal section, station by station.

    python scripts/pod_envelope.py

Measures FULLCOCPITV1_3.stl and writes out/pod_envelope.json: for a series of
X stations, the internal half-width and the floor and crown heights.

WHY THIS EXISTS
---------------
volare.BASELINE gives the pod as 2537.7 x 700 x 497.3 mm. Those are extreme
values over the whole shell, and taking them for the space available is how
the first powertrain layout ended up with twelve components poking through
the skin.

The pod is a tapered shell. At the transom it is 514 mm wide and 160 mm tall;
at the cockpit it is 700 wide and 484 tall. A box that fits amidships does not
fit aft, and nothing in a bounding box says so.

    X      half-width   floor   crown   usable height
    -900      257        626     786        160
    -700      272        621     831        210
    -500      286        626     897        271
    -300      303        638     959        321
    -100      320        636    1009        373
     100      336        617    1051        434
     300      350        591    1075        484

WHAT IT IS AND IS NOT
---------------------
It is a per-station bounding rectangle of the shell's cross-section. It is
NOT the true section: a curved shell has corners the rectangle claims and the
hull does not have. So a box that this says fits may still foul a chine, and
the full-assembly clash test against the real triangles remains the authority.

This is for PLACING things; that is for CHECKING them.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import parts as P          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out")

ENVELOPE_PATH = os.path.join(OUT, "pod_envelope.json")

STEP_MM = 50.0          # station spacing
BAND_MM = 40.0          # half-width of the slab sampled at each station


def measure(part_name: str = "pod_shell") -> dict:
    """Slice the pod and record the interior rectangle at each station."""
    plist = P.split_assembly()

    match = [p for p in plist if p["name"] == part_name]

    if not match:
        raise RuntimeError(
            f"No part named '{part_name}' in the assembly. Found: "
            + ", ".join(p["name"] for p in plist))

    V = match[0]["tris"].reshape(-1, 3)

    x0, x1 = float(V[:, 0].min()), float(V[:, 0].max())

    stations = np.arange(np.ceil(x0 / STEP_MM) * STEP_MM,
                         np.floor(x1 / STEP_MM) * STEP_MM + 1e-6, STEP_MM)

    rows = []

    for x in stations:
        m = (V[:, 0] >= x - BAND_MM) & (V[:, 0] <= x + BAND_MM)

        if m.sum() < 12:
            continue

        s = V[m]

        rows.append(dict(
            x=float(x),
            y_min=float(s[:, 1].min()), y_max=float(s[:, 1].max()),
            z_min=float(s[:, 2].min()), z_max=float(s[:, 2].max()),
            half_width=float((s[:, 1].max() - s[:, 1].min()) / 2.0),
            height=float(s[:, 2].max() - s[:, 2].min()),
            n=int(m.sum())))

    return dict(
        source="FULLCOCPITV1_3.stl",
        part=part_name,
        frame="X forward, Y port, Z up; origin centreline x mid-length x keel",
        units="mm",
        step_mm=STEP_MM,
        band_mm=BAND_MM,
        x_min=x0, x_max=x1,
        stations=rows,
        note="Per-station bounding rectangle of the shell section. A box "
             "inside this may still foul a chine -- use the full-assembly "
             "clash test to confirm.")


class Envelope:
    """Query the pod's interior at any station."""

    def __init__(self, data: dict, wall_mm: float = 15.0,
                 min_height_mm: float = 60.0):
        self.data = data
        self.wall = wall_mm
        self.min_height = min_height_mm

        st = data["stations"]

        self.x = np.array([r["x"] for r in st])
        self.hw = np.array([r["half_width"] for r in st])
        self.zlo = np.array([r["z_min"] for r in st])
        self.zhi = np.array([r["z_max"] for r in st])

        self.x_min = float(self.x.min())
        self.x_max = float(self.x.max())

    @classmethod
    def load(cls, wall_mm: float = 15.0,
             min_height_mm: float = 60.0) -> "Envelope":
        if not os.path.isfile(ENVELOPE_PATH):
            data = measure()
            os.makedirs(OUT, exist_ok=True)
            with open(ENVELOPE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
        else:
            with open(ENVELOPE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        return cls(data, wall_mm, min_height_mm)

    def at(self, x: float) -> tuple[float, float, float]:
        """(half_width, floor, crown) at a station, inside the wall allowance.

        Outside the pod this returns a zero-width slot rather than
        extrapolating. A placer that is allowed to hang a box off the end of
        the boat will do exactly that.
        """
        if x < self.x_min or x > self.x_max:
            return 0.0, 0.0, 0.0

        hw = float(np.interp(x, self.x, self.hw)) - self.wall
        lo = float(np.interp(x, self.x, self.zlo)) + self.wall
        hi = float(np.interp(x, self.x, self.zhi)) - self.wall

        # Around X = 450 to 650 the measured floor comes out ABOVE the
        # measured crown. That is the cockpit aperture: the slab there
        # samples the rim of the opening and never reaches a closed
        # section, so min and max Z describe the coaming rather than a
        # cavity.
        #
        # Reported as unusable rather than clamped. It is where the pilot
        # sits, it is forward of the bulkhead, and ENERGY_REQ_26 forbids
        # the energy container from being there anyway -- so a placer that
        # is told there is no room loses nothing and gains not putting a
        # contactor in the footwell.
        if hi - lo < self.min_height:
            return 0.0, 0.0, 0.0

        return max(hw, 0.0), lo, hi

    def slot(self, x0: float, x1: float) -> tuple[float, float, float]:
        """The rectangle available across a whole X range.

        The WORST station governs, not the average. A box spanning a taper
        has to pass through the narrow end.
        """
        xs = np.arange(x0, x1 + 1e-6, min(STEP_MM / 2.0, max(x1 - x0, 1.0)))

        if len(xs) == 0:
            xs = np.array([x0, x1])

        hw, lo, hi = 1e9, -1e9, 1e9

        for x in xs:
            h, l, t = self.at(float(x))
            if h <= 0.0:
                return 0.0, 0.0, 0.0       # unusable anywhere in the span
            hw = min(hw, h)
            lo = max(lo, l)
            hi = min(hi, t)

        return hw, lo, hi

    def fits(self, centre, size, margin: float = 0.0) -> tuple[bool, str]:
        """Is this box inside the pod, with `margin` to spare?"""
        c = np.asarray(centre, float)
        s = np.asarray(size, float)

        x0, x1 = c[0] - s[0] / 2.0, c[0] + s[0] / 2.0

        if x0 < self.x_min or x1 > self.x_max:
            return False, (f"X {x0:.0f}..{x1:.0f} runs outside the pod "
                           f"({self.x_min:.0f}..{self.x_max:.0f})")

        hw, lo, hi = self.slot(x0, x1)

        if hw <= 0.0:
            return False, (f"X {x0:.0f}..{x1:.0f} crosses the cockpit "
                           f"aperture, where there is no closed section")

        need_y = s[1] / 2.0 + margin

        if abs(c[1]) + need_y > hw:
            return False, (f"needs |Y| {abs(c[1]) + need_y:.0f} mm, the pod "
                           f"gives {hw:.0f} mm over this range")

        if c[2] - s[2] / 2.0 - margin < lo:
            return False, (f"bottom at {c[2] - s[2]/2.0:.0f} mm is below the "
                           f"floor at {lo:.0f} mm")

        if c[2] + s[2] / 2.0 + margin > hi:
            return False, (f"top at {c[2] + s[2]/2.0:.0f} mm is above the "
                           f"crown at {hi:.0f} mm")

        return True, "fits"


def main() -> int:
    data = measure()

    os.makedirs(OUT, exist_ok=True)
    with open(ENVELOPE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)

    env = Envelope(data)

    print()
    print("=" * 62)
    print(" POD INTERNAL ENVELOPE")
    print("=" * 62)
    print(f" {data['part']} from {data['source']}")
    print(f" {len(data['stations'])} stations at {STEP_MM:.0f} mm, "
          f"X {data['x_min']:.0f} to {data['x_max']:.0f} mm")
    print(f" wall allowance {env.wall:.0f} mm\n")

    print(f"  {'X':>7}{'half-width':>12}{'floor':>8}{'crown':>8}{'height':>8}")

    for x in range(-850, 1651, 100):
        hw, lo, hi = env.at(float(x))
        if hw <= 0:
            continue
        print(f"  {x:>7}{hw:>12.0f}{lo:>8.0f}{hi:>8.0f}{hi - lo:>8.0f}")

    print(f"\n written {ENVELOPE_PATH}")
    print("=" * 62)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
