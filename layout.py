"""
layout.py -- fit boxes inside the pod, automatically.

The powertrain positions in params/volare_params.json are PREFERENCES. This
turns them into placements that actually fit the measured shell, so changing
the battery pack -- a different cell, a different grid, a different series
count -- re-solves the layout instead of silently pushing a box through the
skin.

WHY A SOLVER AND NOT HAND-PLACED NUMBERS
----------------------------------------
The first layout was hand-placed against volare.BASELINE's bounding box and
twelve components fouled the hull. Fixing them by hand took three passes and
each pass invalidated the last, because the pod tapers in two axes at once
and moving a box aft makes it both narrower and shorter.

More to the point, the pack is not settled. Cell choice, series count and the
group grid are all still open, and every one of them changes the container's
size. A layout that has to be re-derived by hand each time is a layout that
will stop being re-derived.

HOW IT PLACES
-------------
Greedy, in a fixed order, largest and most-constrained first: the energy
container, then what must sit on it, then what must sit aft of it. Each part
is searched over a grid of candidate positions around its preference and
scored on distance from that preference; the first feasible position wins.

Greedy is enough here because the ordering is not arbitrary -- the container
dominates the space and everything else fits around it. A proper packing
solver would buy nothing on nineteen boxes and would be much harder to read.

WHAT IT GUARANTEES
------------------
Every placed part is inside the pod envelope, clear of the parts placed
before it, and on the correct side of the bulkhead for its zone. What it does
NOT guarantee is a global optimum, or that a part fouls no chine -- the
envelope is a per-station rectangle, and build_full_assembly.py checks against
the real triangles.

Anything it cannot place is reported with the reason, not quietly dropped.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pod_envelope import Envelope     # noqa: E402


class Placement:
    """One solved position, with how it was reached."""

    def __init__(self, name, centre, size, ok, reason, moved_mm):
        self.name = name
        self.centre = np.asarray(centre, float)
        self.size = np.asarray(size, float)
        self.ok = ok
        self.reason = reason
        self.moved_mm = moved_mm

    @property
    def lo(self):
        return self.centre - self.size / 2.0

    @property
    def hi(self):
        return self.centre + self.size / 2.0


def overlaps(lo_a, hi_a, lo_b, hi_b, gap=0.0):
    return bool(np.all(lo_a < hi_b + gap) and np.all(lo_b < hi_a + gap))


class Layout:
    """Place boxes inside the pod, keeping them clear of each other."""

    def __init__(self, env: Envelope, gap_mm: float = 6.0):
        self.env = env
        self.gap = gap_mm
        self.placed: list[Placement] = []

    # -- constraints ------------------------------------------------------

    def _clear_of_placed(self, lo, hi, ignore=()):
        for p in self.placed:
            if p.name in ignore or not p.ok:
                continue
            if overlaps(lo, hi, p.lo, p.hi, self.gap):
                return False, p.name
        return True, ""

    # -- the search -------------------------------------------------------

    def place(self, name, size, prefer, *, sit="floor", x_range=400.0,
              y_options=None, z_range=180.0, ignore=(), fixed=False,
              x_min=None, x_max=None):
        """Find a position for `size` near `prefer`.

        sit     "floor"  rest on the pod floor at that station
                "lid"    rest on whatever is already below it
                "free"   search in Z as well
        fixed   accept `prefer` unchanged, and only report whether it fits
        x_min   the box's aft face may not go below this station
        x_max   the box's forward face may not go above this station -- how
                ENERGY_REQ_50 is enforced, by refusing to place HV forward
                of the bulkhead rather than by checking afterwards
        """
        size = np.asarray(size, float)
        prefer = np.asarray(prefer, float)

        if fixed:
            ok, why = self.env.fits(prefer, size)
            if ok:
                clear, who = self._clear_of_placed(
                    prefer - size / 2.0, prefer + size / 2.0, ignore)
                if not clear:
                    ok, why = False, f"overlaps {who}"
            p = Placement(name, prefer, size, ok, why, 0.0)
            self.placed.append(p)
            return p

        if y_options is None:
            y_options = [prefer[1], -prefer[1], 0.0]

        best = None

        # Coarse then fine, so a part that fits near its preference is found
        # quickly and one that does not still gets a thorough search.
        for step in (40.0, 10.0):
            xs = np.arange(prefer[0] - x_range, prefer[0] + x_range + 1e-6,
                           step)

            for x in xs:
                x0, x1 = x - size[0] / 2.0, x + size[0] / 2.0

                if x_min is not None and x0 < x_min:
                    continue
                if x_max is not None and x1 > x_max:
                    continue

                hw, floor, crown = self.env.slot(x0, x1)

                if hw <= 0.0 or (crown - floor) < size[2]:
                    continue

                for y in y_options:
                    if abs(y) + size[1] / 2.0 > hw:
                        continue

                    if sit == "floor":
                        z_candidates = [floor + size[2] / 2.0]
                    elif sit == "lid":
                        # rest on the tallest thing already placed under it
                        base = floor
                        for p in self.placed:
                            if not p.ok:
                                continue
                            if (p.lo[0] < x1 and x0 < p.hi[0] and
                                    p.lo[1] < y + size[1] / 2.0 and
                                    y - size[1] / 2.0 < p.hi[1]):
                                base = max(base, p.hi[2] + self.gap)
                        z_candidates = [base + size[2] / 2.0]
                    else:
                        z_candidates = list(np.arange(
                            floor + size[2] / 2.0,
                            crown - size[2] / 2.0 + 1e-6,
                            max(z_range / 6.0, 20.0)))

                    for z in z_candidates:
                        c = np.array([x, y, z])

                        ok, why = self.env.fits(c, size)
                        if not ok:
                            continue

                        clear, _ = self._clear_of_placed(
                            c - size / 2.0, c + size / 2.0, ignore)
                        if not clear:
                            continue

                        d = float(np.linalg.norm(c - prefer))
                        if best is None or d < best[0]:
                            best = (d, c)

            if best is not None:
                break

        if best is None and sit != "free":
            # Fall back to a free search over the whole usable pod.
            #
            # A preference expresses where a part WANTS to be -- the
            # terminal box on the container lid, the pump beside it. When
            # the pod has no room there, refusing to place the part at all
            # is less useful than putting it somewhere legal and saying how
            # far it had to move. The distance is reported, so a part that
            # ends up 800 mm from its preference is visible as a layout
            # that needs a human rather than a solver.
            for x in np.arange(self.env.x_min + size[0] / 2.0,
                               self.env.x_max - size[0] / 2.0, 20.0):
                x0, x1 = x - size[0] / 2.0, x + size[0] / 2.0

                if x_min is not None and x0 < x_min:
                    continue
                if x_max is not None and x1 > x_max:
                    continue

                hw, floor, crown = self.env.slot(x0, x1)

                if hw <= 0.0 or (crown - floor) < size[2]:
                    continue

                y_span = hw - size[1] / 2.0

                for y in np.linspace(-y_span, y_span, 9):
                    for z in np.arange(floor + size[2] / 2.0,
                                       crown - size[2] / 2.0 + 1e-6, 25.0):
                        c = np.array([x, y, z])

                        ok, _ = self.env.fits(c, size)
                        if not ok:
                            continue

                        clear, _ = self._clear_of_placed(
                            c - size / 2.0, c + size / 2.0, ignore)
                        if not clear:
                            continue

                        d = float(np.linalg.norm(c - prefer))
                        if best is None or d < best[0]:
                            best = (d, c)

        if best is None:
            # Report the reason at the preferred position: it is the one the
            # designer chose, so it is the one worth explaining.
            _, why = self.env.fits(prefer, size)
            p = Placement(name, prefer, size, False,
                          f"nowhere in the pod ({why} at the preference)",
                          0.0)
        else:
            d, c = best
            p = Placement(name, c, size, True, "placed", d)

        self.placed.append(p)
        return p

    # -- reporting --------------------------------------------------------

    def report(self) -> str:
        lines = []
        lines.append(f"  {'part':<22}{'centre mm':>24}{'moved':>8}  status")

        for p in self.placed:
            c = f"{p.centre[0]:.0f},{p.centre[1]:.0f},{p.centre[2]:.0f}"
            if p.ok:
                mv = f"{p.moved_mm:.0f}" if p.moved_mm > 0.5 else "-"
                lines.append(f"  {p.name:<22}{c:>24}{mv:>8}  ok")
            else:
                lines.append(f"  {p.name:<22}{c:>24}{'-':>8}  "
                             f"CANNOT PLACE: {p.reason}")

        return "\n".join(lines)

    @property
    def failures(self):
        return [p for p in self.placed if not p.ok]
