r"""
volare_thermal.track
====================

Race course geometry for the Monaco Energy Boat Challenge, built from the
official MEBC 2026 Energy Course Description.

THE FOUR EVENTS
---------------
  Qualifying    Stadium, fastest single lap, running start, 2 h window.
  Endurance     Stadium, lap = 1 NAUTICAL MILE (1852 m), maximum distance in
                3 h, fleet start, NO recharging during the race.
  Slalom        YCM Marina, buoy course, +10 s per buoy missed, >3 missed =
                run discarded.
  Championship  YCM Marina, head-to-head, inner or outer loop, standing start.
                Fastest qualifier takes the OUTER loop.

WHY THE COURSE HAS TO BE REAL GEOMETRY
--------------------------------------
A lap length alone tells you nothing about how the energy is spent. Corner
radius sets the speed you can carry; the length of each straight sets how
long you spend at full power; and the ratio between them decides whether the
race is energy-limited or time-limited. This module represents the course as
an ordered list of STRAIGHT and ARC segments, so at any distance `s` along
the lap you get exact position, heading, curvature and therefore a physical
cornering speed limit.

Sector boundaries follow F1 convention (three sectors), which is what makes
lap-time deltas diagnosable rather than just a single number at the line.

CALIBRATION NOTE
----------------
The published course maps are marked "Sample course - For illustration only",
so the segment lengths and radii below are a faithful reconstruction of the
published SHAPE scaled to the official 1 NM lap length -- not a survey. The
lap length, the 3 h limit, the no-recharge rule and the penalty structure are
exact. Replace the geometry with GPS traces from practice as soon as you have
them; `Track.from_gps()` takes a lat/lon polyline directly.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field

G = 9.80665
NM = 1852.0


# ============================================================================
#  TRACK
# ============================================================================

@dataclass
class Track:
    """Course as an ordered list of segments.

    Each segment is a dict:
        {"type": "straight", "length": L, "name": ...}
        {"type": "arc", "radius": R, "angle_deg": A, "dir": +1|-1, "name": ...}

    +1 = left turn (counter-clockwise), -1 = right.
    """
    name: str = "Monaco Stadium — Endurance"
    segments: list = field(default_factory=list)
    lateral_g_limit: float = 0.55
    n_sectors: int = 3
    marks: list = field(default_factory=list)     # [{"name","s"}...]
    event: str = "endurance"
    time_limit_s: float = 3 * 3600.0
    resolution_m: float = 2.0

    def __post_init__(self):
        self._build()

    # -- geometry ---------------------------------------------------------
    def _build(self):
        s, x, y, th = 0.0, 0.0, 0.0, 0.0
        S, X, Y, TH, K, SEG = [], [], [], [], [], []
        for i, g in enumerate(self.segments):
            if g["type"] == "straight":
                n = max(2, int(g["length"] / self.resolution_m))
                for k in range(n):
                    ds = g["length"] / n
                    S.append(s); X.append(x); Y.append(y); TH.append(th)
                    K.append(0.0); SEG.append(i)
                    x += np.cos(th) * ds; y += np.sin(th) * ds; s += ds
            else:
                R = g["radius"]; A = np.radians(g["angle_deg"]) * g.get("dir", 1)
                L = abs(A) * R
                n = max(3, int(L / self.resolution_m))
                for k in range(n):
                    ds = L / n
                    S.append(s); X.append(x); Y.append(y); TH.append(th)
                    K.append(np.sign(A) / R); SEG.append(i)
                    dth = A / n
                    x += np.cos(th + dth / 2) * ds
                    y += np.sin(th + dth / 2) * ds
                    th += dth; s += ds
        self.s = np.array(S); self.x = np.array(X); self.y = np.array(Y)
        self.heading = np.array(TH); self.curvature = np.array(K)
        self.seg_index = np.array(SEG)
        self.length = float(s)
        self.closure_error_m = float(np.hypot(x, y))
        # cornering speed limit from curvature
        with np.errstate(divide="ignore"):
            self.v_limit = np.where(
                np.abs(self.curvature) < 1e-9, 1e6,
                np.sqrt(self.lateral_g_limit * G /
                        np.maximum(np.abs(self.curvature), 1e-9)))
        self.sector_bounds = [self.length * k / self.n_sectors
                              for k in range(self.n_sectors + 1)]

    # -- queries ----------------------------------------------------------
    def at(self, s_along):
        i = int(np.searchsorted(self.s, s_along % self.length)) % len(self.s)
        return dict(x=float(self.x[i]), y=float(self.y[i]),
                    heading=float(self.heading[i]),
                    curvature=float(self.curvature[i]),
                    v_limit=float(self.v_limit[i]),
                    segment=self.segments[self.seg_index[i]].get("name", ""),
                    sector=self.sector_of(s_along))

    def speed_limit(self, s_along):
        return float(np.interp(s_along % self.length, self.s, self.v_limit))

    def sector_of(self, s_along):
        x = s_along % self.length
        for k in range(self.n_sectors):
            if x < self.sector_bounds[k + 1]:
                return k
        return self.n_sectors - 1

    def scale_to(self, target_length_m):
        """Scale every straight so the lap hits an exact target length.

        Corner radii are left ALONE deliberately: they are set by the buoy
        positions and the boat's turning ability, not by how long you want the
        lap to be. Scaling them would silently change every corner speed.
        """
        arc = sum(abs(np.radians(g["angle_deg"])) * g["radius"]
                  for g in self.segments if g["type"] == "arc")
        st = sum(g["length"] for g in self.segments
                 if g["type"] == "straight")
        if st <= 0:
            raise ValueError("no straights to scale")
        f = (target_length_m - arc) / st
        if f <= 0:
            raise ValueError(f"corners alone are {arc:.0f} m, longer than the "
                             f"{target_length_m:.0f} m target")
        for g in self.segments:
            if g["type"] == "straight":
                g["length"] *= f
        self._build()
        return self

    @classmethod
    def from_gps(cls, lat, lon, name="GPS trace", **kw):
        """Build a track from a GPS polyline. Local tangent-plane projection
        about the centroid -- accurate to millimetres over a 2 km course."""
        lat = np.asarray(lat, float); lon = np.asarray(lon, float)
        lat0, lon0 = lat.mean(), lon.mean()
        R = 6378137.0
        x = np.radians(lon - lon0) * R * np.cos(np.radians(lat0))
        y = np.radians(lat - lat0) * R
        t = cls(name=name, segments=[{"type": "straight", "length": 1.0}], **kw)
        ds = np.hypot(np.diff(x), np.diff(y))
        s = np.concatenate([[0], np.cumsum(ds)])
        th = np.unwrap(np.arctan2(np.diff(y), np.diff(x)))
        th = np.concatenate([th, th[-1:]])
        k = np.gradient(th, s, edge_order=1)
        t.s, t.x, t.y, t.heading, t.curvature = s, x, y, th, k
        t.seg_index = np.zeros(len(s), int)
        t.length = float(s[-1])
        t.closure_error_m = float(np.hypot(x[-1] - x[0], y[-1] - y[0]))
        t.v_limit = np.where(np.abs(k) < 1e-9, 1e6,
                             np.sqrt(t.lateral_g_limit * G /
                                     np.maximum(np.abs(k), 1e-9)))
        t.sector_bounds = [t.length * i / t.n_sectors
                           for i in range(t.n_sectors + 1)]
        return t

    def summary(self):
        straights = [g for g in self.segments if g["type"] == "straight"]
        arcs = [g for g in self.segments if g["type"] == "arc"]
        return dict(name=self.name, event=self.event,
                    length_m=round(self.length, 1),
                    length_NM=round(self.length / NM, 4),
                    n_straights=len(straights), n_corners=len(arcs),
                    longest_straight_m=round(max((g["length"] for g in straights),
                                                 default=0), 1),
                    tightest_radius_m=round(min((g["radius"] for g in arcs),
                                                default=0), 1),
                    min_corner_speed_kmh=round(float(self.v_limit.min()*3.6), 1),
                    closure_error_m=round(self.closure_error_m, 2),
                    time_limit_min=round(self.time_limit_s / 60, 1))


# ============================================================================
#  THE OFFICIAL COURSES
# ============================================================================

def stadium(length_m, radius_m, name="Stadium", **kw) -> Track:
    """A closed stadium loop: two equal straights, two 180 deg end arcs.

    WHY EQUAL RADII. A four-segment loop only closes if the geometry is
    consistent. Solving the closure condition for two straights and two arcs
    whose angles sum to 360 gives

        L2 = -(r1 - r2)(1 - cos a1) / sin a1

    so unequal end radii FIX the straight length -- you can no longer scale
    the lap to a target distance without breaking closure, and a track that
    does not close accumulates position error every lap. Equal radii make
    L1 = L2 free, which is what lets the lap be scaled to exactly 1 NM.

    The published map does show one end wider than the other, but it is
    marked "for illustration only", so reproducing that asymmetry would be
    inventing precision. Use Track.from_gps() on a practice trace instead.
    """
    straight = (length_m - 2 * np.pi * radius_m) / 2.0
    if straight <= 0:
        raise ValueError(f"radius {radius_m} m needs more than {length_m} m of lap")
    return Track(name=name, lateral_g_limit=kw.pop("lateral_g_limit", 0.55),
                 segments=[
                     {"type": "straight", "length": straight, "name": "NE leg"},
                     {"type": "arc", "radius": radius_m, "angle_deg": 180.0,
                      "dir": 1, "name": "Far mark"},
                     {"type": "straight", "length": straight,
                      "name": "SW return leg"},
                     {"type": "arc", "radius": radius_m, "angle_deg": 180.0,
                      "dir": 1, "name": "Marina turn"}],
                 marks=[{"name": "Start / Finish", "s": 0.0},
                        {"name": "Far mark", "s": straight + np.pi*radius_m/2},
                        {"name": "Marina mark",
                         "s": 2*straight + np.pi*radius_m*1.5}], **kw)


def monaco_endurance(radius_m=60.0) -> Track:
    """Energy Endurance — Stadium, 1 NM lap, 3 h, maximum distance.

    Lap length (1 NM), the 3 h limit and the no-recharge rule are EXACT from
    the course description. The 60 m turn radius is a working assumption
    consistent with the published loop proportions -- it sets your corner
    speed, so replace it with a GPS trace from practice.
    """
    return stadium(NM, radius_m, name="Monaco Stadium — Endurance (1 NM)",
                   event="endurance", time_limit_s=3 * 3600.0)


def monaco_qualifying() -> Track:
    """Energy Qualifying — Stadium, fastest lap, 2 h window.
    Same stadium, shorter lap (the published map shows the same loop; the
    stated 'maximum distance' figure in the PDF is garbled, so this uses half
    the endurance lap as a working assumption -- CONFIRM WITH THE ORGANISER)."""
    t = stadium(NM / 2, 45.0, name="Monaco Stadium — Qualifying",
                event="qualifying", time_limit_s=2 * 3600.0)
    return t


def monaco_championship(loop="outer") -> Track:
    """Energy Championship — YCM Marina, head-to-head, standing start.
    Fastest qualifier takes the OUTER loop."""
    r_out, r_in = 55.0, 42.0
    L = 210.0 if loop == "outer" else 175.0
    r = r_out if loop == "outer" else r_in
    return Track(
        name=f"YCM Marina — Championship ({loop})",
        event="championship", time_limit_s=900.0, lateral_g_limit=0.55,
        segments=[
            {"type": "straight", "length": L, "name": "Start straight"},
            {"type": "arc", "radius": r, "angle_deg": 180.0, "dir": 1,
             "name": "Far loop"},
            {"type": "straight", "length": L, "name": "Return"},
            {"type": "arc", "radius": r, "angle_deg": 180.0, "dir": 1,
             "name": "Start loop"},
        ],
        marks=[{"name": "Start / Finish", "s": 0.0}])


def monaco_slalom(n_gates=8, gate_spacing=38.0, offset=26.0) -> Track:
    """Energy Slalom — YCM Marina buoy course, fastest time.
    +10 s per buoy missed; more than 3 missed and the run is discarded."""
    segs = [{"type": "straight", "length": 30.0, "name": "Approach"}]
    R = 16.0
    for k in range(n_gates):
        d = 1 if k % 2 == 0 else -1
        segs.append({"type": "arc", "radius": R, "angle_deg": 78.0, "dir": d,
                     "name": f"Buoy {k+1}"})
        segs.append({"type": "arc", "radius": R, "angle_deg": 78.0, "dir": -d,
                     "name": f"Exit {k+1}"})
        segs.append({"type": "straight", "length": gate_spacing * 0.35,
                     "name": f"Gate {k+1}-{k+2}"})
    segs.append({"type": "straight", "length": 30.0, "name": "Finish"})
    # a slalom is a point-to-point run, not a closed loop: closure error is
    # meaningless here and is reported as such.
    t = Track(name="YCM Marina — Slalom", event="slalom", segments=segs,
              lateral_g_limit=0.55, time_limit_s=300.0, n_sectors=3,
              marks=[{"name": f"Buoy {k+1}",
                      "s": 30.0 + k * (2 * np.radians(78) * R + gate_spacing*0.35)}
                     for k in range(n_gates)])
    return t


COURSES = {"endurance": monaco_endurance, "qualifying": monaco_qualifying,
           "championship_outer": lambda: monaco_championship("outer"),
           "championship_inner": lambda: monaco_championship("inner"),
           "slalom": monaco_slalom}


# ============================================================================
#  ENDURANCE STRATEGY
# ============================================================================

def endurance_strategy(dyn, track, energy_kWh=9.828, reserve_frac=0.03,
                       inverter_eff=0.96, powers_W=None):
    """Find the pace that maximises distance inside BOTH limits.

    Endurance is won on distance, and distance is bounded twice:
        by energy   distance = E_usable / (Wh per km)
        by time     distance = v * T_limit
    Below a certain speed you run out of clock; above it you run out of
    energy. The optimum sits exactly where the two bind together -- and if
    the energy limit binds everywhere (which it does here), the answer is
    simply the most efficient speed you can sustain, not the fastest.
    """
    if powers_W is None:
        powers_W = np.linspace(1500, dyn.P_shaft_max_W, 40)
    E = energy_kWh * 1000.0 * (1 - reserve_frac)
    rows = []
    for P in powers_W:
        v = dyn.steady_speed(float(P))
        if v <= 0.3:
            continue
        # bus power includes inverter loss; pack sees more than the shaft
        P_bus = float(P) / inverter_eff
        wh_per_km = P_bus / (v * 3.6)
        d_energy = E / wh_per_km                       # km
        d_time = v * track.time_limit_s / 1000.0       # km
        d = min(d_energy, d_time)
        rows.append(dict(P_shaft_W=float(P), v_kmh=v * 3.6,
                         wh_per_km=wh_per_km,
                         dist_energy_km=d_energy, dist_time_km=d_time,
                         distance_km=d, laps=d * 1000.0 / track.length,
                         limited_by="energy" if d_energy < d_time else "time",
                         duration_h=d / max(v * 3.6, 1e-6)))
    best = max(rows, key=lambda r: r["distance_km"])
    return best, rows
