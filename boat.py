r"""
volare_thermal.boat
===================

The boat: hull in water, cockpit in air, propeller in between.

Turns a commanded throttle into a real power demand, and a real power into a
real velocity. Without this the thermal model is being driven by an invented
power profile; with it, the power profile is a CONSEQUENCE of how you drive.

WHAT IS MODELLED
----------------
Hull resistance (below the waterline)
  * Frictional      ITTC-1957 line, on the actual wetted surface
  * Residuary       displacement regime, Froude-scaled
  * Planing         Savitsky-style lift/drag once the hull unsticks
  * Spray + appendage allowances
Air resistance (above the waterline)
  * Cockpit and superstructure projected area x Cd, plus the crossbeams
Propulsion
  * Open-water propeller: thrust and torque from KT/KQ vs advance ratio
  * Wake fraction, thrust deduction, relative rotative efficiency
  * Slip, cavitation flag, ventilation flag
Dynamics
  * (m + m_added) dv/dt = T(1-t) - R_hull - R_air
  * Hard 25 kW cap at the motor shaft, enforced everywhere

STL IMPORT
----------
`Hull.from_stl()` reads a binary or ASCII STL, finds the waterline for a given
displacement, and splits triangles into WETTED (below waterline) and DRY
(above, exposed to air). Wetted surface area then comes from the real
geometry rather than a guess, which is the dominant term in frictional
resistance -- typically 60-80 % of total drag at cruise.

UNITS: SI. Speeds in m/s internally; helpers convert to km/h and knots.
"""

from __future__ import annotations

import struct
import numpy as np
from dataclasses import dataclass, field

G = 9.80665
RHO_SW = 1025.0          # seawater, kg/m3
NU_SW = 1.05e-6          # kinematic viscosity, m2/s at ~20 degC
RHO_AIR = 1.20
KMH = 3.6
KNOT = 1.9438445


# ============================================================================
#  1.  HULL GEOMETRY  (STL)
# ============================================================================

def load_stl(path) -> np.ndarray:
    """Read binary or ASCII STL. Returns (n_tri, 3, 3) vertex array in metres.
    Auto-detects millimetre files and converts."""
    with open(path, "rb") as f:
        head = f.read(84)
        f.seek(0)
        raw = f.read()
    tris = []
    is_ascii = raw[:5].lower().startswith(b"solid") and b"facet" in raw[:2048]
    if is_ascii:
        vals = []
        for line in raw.decode("utf-8", "ignore").splitlines():
            p = line.split()
            if p and p[0] == "vertex":
                vals.append([float(p[1]), float(p[2]), float(p[3])])
        tris = np.array(vals).reshape(-1, 3, 3)
    else:
        n = struct.unpack("<I", head[80:84])[0]
        body = raw[84:]
        exp = n * 50
        if len(body) < exp:
            n = len(body) // 50
        arr = np.frombuffer(body[:n * 50], dtype=np.uint8).reshape(n, 50)
        f4 = arr[:, 12:48].copy().view("<f4").reshape(n, 3, 3)
        tris = np.asarray(f4, dtype=float)
    tris = np.asarray(tris, dtype=float)
    span = np.ptp(tris.reshape(-1, 3), axis=0).max()
    if span > 50.0:                       # almost certainly millimetres
        tris = tris / 1000.0
    return tris


def _tri_areas(t):
    return 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0],
                                         t[:, 2] - t[:, 0]), axis=1)


def _clip_below(tris, z_w):
    """Split triangles at the plane z = z_w. Returns (below, above) lists.
    Triangles straddling the plane are cut properly rather than assigned
    whole, which matters for wetted area at shallow draft."""
    below, above = [], []
    for t in tris:
        d = t[:, 2] - z_w
        neg = d < 0
        k = int(neg.sum())
        if k == 3:
            below.append(t); continue
        if k == 0:
            above.append(t); continue
        idx = np.argsort(~neg)            # wet vertices first
        t2, d2 = t[idx], d[idx]
        def cut(a, b, da, db):
            return a + (b - a) * (da / (da - db))
        if k == 1:
            p, q = cut(t2[0], t2[1], d2[0], d2[1]), cut(t2[0], t2[2], d2[0], d2[2])
            below.append(np.array([t2[0], p, q]))
            above.append(np.array([p, t2[1], t2[2]]))
            above.append(np.array([p, t2[2], q]))
        else:
            p, q = cut(t2[0], t2[2], d2[0], d2[2]), cut(t2[1], t2[2], d2[1], d2[2])
            below.append(np.array([t2[0], t2[1], p]))
            below.append(np.array([t2[1], q, p]))
            above.append(np.array([p, q, t2[2]]))
    return (np.array(below) if below else np.zeros((0, 3, 3)),
            np.array(above) if above else np.zeros((0, 3, 3)))


def projected_area(tris, axis, n=1200):
    """True silhouette area of a mesh projected along `axis` (0=x,1=y,2=z).

    Rasterised rather than summed per-triangle, because summing |n.a| over
    triangles double-counts every surface hidden behind another one. For a
    closed body that overestimates by roughly 2x. This returns the actual
    shadow the body casts, which is what drag depends on.
    """
    keep = [i for i in range(3) if i != axis]
    P = tris[:, :, keep]
    lo, hi = P.reshape(-1, 2).min(axis=0), P.reshape(-1, 2).max(axis=0)
    span = hi - lo
    px = span.max() / n
    W, H = int(np.ceil(span[0] / px)) + 2, int(np.ceil(span[1] / px)) + 2
    grid = np.zeros((H, W), bool)
    q = ((P - lo) / px).astype(int)
    for tri in q:
        x0, y0 = tri.min(axis=0); x1, y1 = tri.max(axis=0)
        xs, ys = np.arange(x0, x1 + 1), np.arange(y0, y1 + 1)
        if len(xs) == 0 or len(ys) == 0:
            continue
        X, Y = np.meshgrid(xs, ys)
        p0, p1, p2 = tri
        d = ((p1[1]-p2[1])*(p0[0]-p2[0]) + (p2[0]-p1[0])*(p0[1]-p2[1]))
        if abs(d) < 1e-9:
            grid[np.clip(Y, 0, H-1), np.clip(X, 0, W-1)] = True
            continue
        a = ((p1[1]-p2[1])*(X-p2[0]) + (p2[0]-p1[0])*(Y-p2[1])) / d
        b = ((p2[1]-p0[1])*(X-p2[0]) + (p0[0]-p2[0])*(Y-p2[1])) / d
        c = 1 - a - b
        m = (a >= -.02) & (b >= -.02) & (c >= -.02)
        grid[np.clip(Y[m], 0, H-1), np.clip(X[m], 0, W-1)] = True
    return float(grid.sum() * px * px)


@dataclass
class Cockpit:
    """The pod above the waterline: it sits in AIR, so it contributes
    aerodynamic drag and convective area, NOT buoyancy or wetted surface.

    Loading a cockpit STL does not give you a waterline -- for that you need
    the demihulls. What it does give you is a real frontal area, which is the
    only geometric quantity aerodynamic drag actually depends on.
    """
    tris: np.ndarray | None = None
    travel_axis: int = 1               # which axis the boat moves along
    Cd: float = 0.55                   # streamlined pod; blunt box ~0.9
    frontal_area_m2: float = 0.275
    side_area_m2: float = 0.778
    plan_area_m2: float = 1.515
    surface_area_m2: float = 4.58
    volume_m3: float = 0.321
    length_m: float = 2.53
    width_m: float = 0.70
    height_m: float = 0.486

    @classmethod
    def from_stl(cls, path, travel_axis=None, Cd=0.55, raster=1200):
        t = load_stl(path)
        v = t.reshape(-1, 3)
        span = v.max(axis=0) - v.min(axis=0)
        if travel_axis is None:
            travel_axis = int(np.argmax(span))   # longest axis = direction of travel
        others = [i for i in range(3) if i != travel_axis]
        vol = abs(np.einsum("ij,ij->i", t[:, 0],
                            np.cross(t[:, 1], t[:, 2])).sum() / 6.0)
        return cls(tris=t, travel_axis=travel_axis, Cd=Cd,
                   frontal_area_m2=projected_area(t, travel_axis, raster),
                   side_area_m2=projected_area(t, others[0], raster),
                   plan_area_m2=projected_area(t, 2 if 2 in others else others[1],
                                               raster),
                   surface_area_m2=float(_tri_areas(t).sum()),
                   volume_m3=float(vol),
                   length_m=float(span[travel_axis]),
                   width_m=float(span[others[0]]),
                   height_m=float(span[others[-1]]))

    def drag_N(self, v_air):
        return 0.5 * RHO_AIR * self.Cd * self.frontal_area_m2 * v_air ** 2

    def summary(self):
        return dict(source="STL" if self.tris is not None else "assumed",
                    length_mm=round(self.length_m*1000, 1),
                    width_mm=round(self.width_m*1000, 1),
                    height_mm=round(self.height_m*1000, 1),
                    frontal_area_m2=round(self.frontal_area_m2, 4),
                    side_area_m2=round(self.side_area_m2, 4),
                    plan_area_m2=round(self.plan_area_m2, 4),
                    surface_area_m2=round(self.surface_area_m2, 3),
                    volume_L=round(self.volume_m3*1000, 1), Cd=self.Cd)


@dataclass
class Hull:
    """Hull geometry with a waterline. Supply an STL or parametric dimensions."""
    tris: np.ndarray | None = None
    # parametric fallback (used when no STL supplied)
    Lwl_m: float = 4.99
    Bwl_m: float = 0.45
    draft_m: float = 0.14
    n_hulls: int = 2                    # catamaran
    block_coefficient: float = 0.55
    prismatic_coefficient: float = 0.62

    waterline_z: float = 0.0
    displacement_kg: float = 250.0

    # air-exposed structure
    cockpit: 'Cockpit | None' = None    # set from an STL for real frontal area
    cockpit_frontal_area_m2: float = 0.42
    cockpit_Cd: float = 0.55
    beam_diameter_m: float = 0.104      # organiser round crossbeams
    beam_span_m: float = 2.035
    n_beams: int = 2
    beam_Cd: float = 1.2                # round, NOT 2.05 (square)
    beams_faired: bool = False

    def __post_init__(self):
        if self.cockpit is not None:
            self.cockpit_frontal_area_m2 = self.cockpit.frontal_area_m2
            self.cockpit_Cd = self.cockpit.Cd
        self.from_geometry = self.tris is not None
        if self.from_geometry:
            self.tris = np.asarray(self.tris, float)
            self._measure()
        else:
            self._parametric()

    # -- STL path --------------------------------------------------------
    @classmethod
    def from_stl(cls, path, displacement_kg=250.0, **kw):
        h = cls(tris=load_stl(path), displacement_kg=displacement_kg, **kw)
        h.solve_waterline(displacement_kg)
        return h

    def _mesh_volume_below(self, z_w):
        below, _ = _clip_below(self.tris, z_w)
        if len(below) == 0:
            return 0.0, 0.0
        # signed volume via divergence theorem, closed by the waterplane
        v = np.abs(np.einsum("ij,ij->i",
                             below[:, 0],
                             np.cross(below[:, 1], below[:, 2])).sum() / 6.0)
        return v, float(_tri_areas(below).sum())

    def solve_waterline(self, displacement_kg=None, tol=1e-4, iters=60):
        """Bisect the waterline height so displaced mass matches the boat."""
        if not self.from_geometry:
            return self.waterline_z
        m = displacement_kg or self.displacement_kg
        target = m / RHO_SW
        zlo, zhi = self.tris[:, :, 2].min(), self.tris[:, :, 2].max()
        for _ in range(iters):
            zm = 0.5 * (zlo + zhi)
            v, _ = self._mesh_volume_below(zm)
            if v < target:
                zlo = zm
            else:
                zhi = zm
            if abs(v - target) / max(target, 1e-9) < tol:
                break
        self.waterline_z = 0.5 * (zlo + zhi)
        self.displacement_kg = m
        self._measure()
        return self.waterline_z

    def _measure(self):
        below, above = _clip_below(self.tris, self.waterline_z)
        self.wetted_area_m2 = float(_tri_areas(below).sum())
        self.dry_area_m2 = float(_tri_areas(above).sum())
        self.volume_m3, _ = self._mesh_volume_below(self.waterline_z)
        if len(below):
            xs = below[:, :, 0]
            self.Lwl_m = float(xs.max() - xs.min())
            ys = below[:, :, 1]
            self.Bwl_m = float(ys.max() - ys.min())
            self.draft_m = float(self.waterline_z - below[:, :, 2].min())
        # frontal area above water, for air drag
        if len(above):
            self.dry_frontal_area_m2 = float(
                (above[:, :, 1].max() - above[:, :, 1].min()) *
                (above[:, :, 2].max() - self.waterline_z)) * 0.55
        else:
            self.dry_frontal_area_m2 = self.cockpit_frontal_area_m2

    # -- parametric path --------------------------------------------------
    def _parametric(self):
        self.volume_m3 = (self.displacement_kg / RHO_SW)
        # Holtrop-style wetted surface approximation, per hull
        Lw, B, T = self.Lwl_m, self.Bwl_m, self.draft_m
        Cb = self.block_coefficient
        S = Lw * (2 * T + B) * np.sqrt(Cb) * \
            (0.453 + 0.4425 * Cb - 0.2862 * Cb ** 2)
        self.wetted_area_m2 = float(S * self.n_hulls)
        self.dry_area_m2 = float(
            self.cockpit.surface_area_m2 if self.cockpit is not None
            else 0.6 * self.wetted_area_m2)
        self.dry_frontal_area_m2 = self.cockpit_frontal_area_m2
        self.waterline_z = 0.0

    # -- reporting --------------------------------------------------------
    def summary(self) -> dict:
        return dict(source="STL" if self.from_geometry else "parametric",
                    Lwl_m=round(self.Lwl_m, 3), Bwl_m=round(self.Bwl_m, 3),
                    draft_m=round(self.draft_m, 3),
                    waterline_z=round(self.waterline_z, 4),
                    displacement_kg=round(self.displacement_kg, 1),
                    volume_m3=round(self.volume_m3, 4),
                    wetted_area_m2=round(self.wetted_area_m2, 3),
                    dry_area_m2=round(self.dry_area_m2, 3),
                    dry_frontal_area_m2=round(self.dry_frontal_area_m2, 3))


# ============================================================================
#  2.  RESISTANCE
# ============================================================================

@dataclass
class ResistanceModel:
    """Total resistance vs speed. Displacement below hump, planing above."""
    hull: Hull
    correlation_allowance: float = 4.0e-4     # ITTC Ca, roughness
    appendage_factor: float = 1.08            # shaft, strut, rudder
    form_factor_k: float = 0.18               # (1+k)
    planing_transition_Fn: float = 1.20       # volumetric Froude at unstick
    planing_LD: float = 5.6                   # lift/drag once planing
    spray_factor: float = 1.06
    aero_enabled: bool = True
    # Wetted area retained once fully planing, as a fraction of static.
    # A planing hull lifts most of itself clear: 0.25-0.35 is typical, and
    # this is THE most sensitive parameter in the whole drag model. Getting
    # it wrong by 2x moves your top speed by ~8 km/h. Measure it from video
    # of a sea trial (spray root position) as soon as you can.
    planing_wetted_frac: float = 0.30

    def froude_volumetric(self, v):
        return v / np.sqrt(G * max(self.hull.volume_m3, 1e-6) ** (1 / 3))

    def frictional(self, v):
        """ITTC-1957 on the real wetted surface."""
        v = np.maximum(np.abs(v), 1e-3)
        Re = v * self.hull.Lwl_m / NU_SW
        Cf = 0.075 / (np.log10(np.maximum(Re, 1e3)) - 2.0) ** 2
        Ct = (Cf * (1 + self.form_factor_k) + self.correlation_allowance)
        return 0.5 * RHO_SW * Ct * self.hull.wetted_area_m2 * v ** 2 * \
            self.appendage_factor

    def residuary(self, v):
        """Wave-making. Peaks at the hump, falls away once planing."""
        Fn = self.froude_volumetric(v)
        # smooth hump centred near Fn_vol ~ 1.0, decaying after transition
        hump = 0.55 * np.exp(-((Fn - 1.05) / 0.42) ** 2)
        tail = 0.10 / (1.0 + np.exp((Fn - self.planing_transition_Fn) * 4.0))
        Cr = hump + tail
        return 0.5 * RHO_SW * Cr * (self.hull.volume_m3 ** (2 / 3)) * v ** 2 \
            * 0.35

    def planing(self, v):
        """Once planing, drag is dominated by lift/drag of the wetted plane."""
        Fn = self.froude_volumetric(v)
        blend = 1.0 / (1.0 + np.exp(-(Fn - self.planing_transition_Fn) * 5.0))
        W = self.hull.displacement_kg * G
        return blend * (W / self.planing_LD) * self.spray_factor

    def aerodynamic(self, v, v_wind=0.0):
        if not self.aero_enabled:
            return 0.0 * v
        h = self.hull
        va = v + v_wind
        A_beam = 0.0 if h.beams_faired else \
            h.n_beams * h.beam_diameter_m * h.beam_span_m
        Cd_beam = 0.35 if h.beams_faired else h.beam_Cd
        return 0.5 * RHO_AIR * va ** 2 * (
            h.cockpit_Cd * h.dry_frontal_area_m2 + Cd_beam * A_beam)

    def total(self, v, v_wind=0.0):
        v = np.asarray(v, float)
        Fn = self.froude_volumetric(v)
        blend = 1.0 / (1.0 + np.exp(-(Fn - self.planing_transition_Fn) * 5.0))
        hydro = (1 - blend) * (self.frictional(v) + self.residuary(v)) \
            + self.planing(v) \
            + blend * self.frictional(v) * self.planing_wetted_frac
        return hydro + self.aerodynamic(v, v_wind)

    def effective_power(self, v, v_wind=0.0):
        return self.total(v, v_wind) * v

    def curve(self, v_max_kmh=70.0, n=140):
        v = np.linspace(0.2, v_max_kmh / KMH, n)
        return dict(v_ms=v, v_kmh=v * KMH,
                    R_total_N=self.total(v),
                    R_friction_N=self.frictional(v),
                    R_residuary_N=self.residuary(v),
                    R_planing_N=self.planing(v),
                    R_air_N=self.aerodynamic(v),
                    P_effective_W=self.effective_power(v))


@dataclass
class SuppliedResistance:
    """Hull resistance from the MEBC-supplied curve, not from a correlation.

    WHY THIS EXISTS
    ---------------
    ``ResistanceModel`` above is parametric: Holtrop wetted surface, an
    ITTC friction line, a wave-making hump and a Savitsky planing term. It
    was the only thing available when it was written, and it is badly wrong
    for this hull:

              speed      supplied      parametric
               5 kn          89 N          ~470 N
              10 kn         212 N          ~640 N
              15 kn         381 N          ~720 N
              20 kn         624 N          ~815 N

    The error is the planing term. Each demihull is roughly 5 m by 0.45 m,
    an L/B near 11 -- a slender semi-displacement form that does not plane
    at all. The Savitsky term was contributing a flat 585 N above 20 km/h
    that simply is not there, and it dominated everything below the top
    speed, which is where an endurance race is actually run.

    The hydrodynamics team supplied five measured points. This class
    interpolates them, adds the drive-leg and air terms, and is the default
    everywhere. The parametric model is kept for comparison and for the
    region above the data.

    WHAT IT DOES NOT COVER
    ----------------------
    The curve stops at 20 knots and was measured at 250 kg. The boat floats
    at about 313 kg once the hulls, the pilot and everything else are on it.
    Neither gap is corrected for, because correcting them needs assumptions
    this class has no basis for -- the hydrodynamics team's own report says
    the heavier case cannot be considered validated. Above the last point
    the larger of a fitted power law and the parametric model is used, which
    errs towards more drag; erring the other way would overstate range.

    The interface matches ``ResistanceModel`` so the two are interchangeable
    wherever a resistance object is taken.
    """

    hull: Hull
    speed_kn: np.ndarray = None
    resistance_N: np.ndarray = None
    max_valid_kn: float = 20.0
    drive_leg_N_at_max: float = 81.56
    curve_displacement_kg: float = 250.0
    aero_enabled: bool = True
    wind_ms: float = 0.0
    parametric: 'ResistanceModel | None' = None

    def __post_init__(self):
        self.speed_kn = np.asarray(self.speed_kn, float)
        self.resistance_N = np.asarray(self.resistance_N, float)

        if self.speed_kn.size < 2:
            raise ValueError(
                "SuppliedResistance needs at least two points; got "
                f"{self.speed_kn.size}. Check hydro.resistance_speed_kn.")

        self.speed_ms = self.speed_kn / KNOT
        self.v_max_valid = self.max_valid_kn / KNOT

        # Shape-preserving interpolation. A cubic spline through five points
        # that all curve the same way overshoots between them, and a
        # resistance curve that dips below its neighbours is not physical.
        try:
            from scipy.interpolate import PchipInterpolator
            self._interp = PchipInterpolator(self.speed_ms, self.resistance_N)
        except ImportError:                       # pragma: no cover
            self._interp = lambda v: np.interp(v, self.speed_ms,
                                               self.resistance_N)

        # Power-law tail fitted to the top two points.
        self._tail_exp = float(
            np.log(self.resistance_N[-1] / self.resistance_N[-2]) /
            np.log(self.speed_ms[-1] / self.speed_ms[-2]))

        self._tail_coeff = float(
            self.resistance_N[-1] / self.speed_ms[-1] ** self._tail_exp)

        self._leg_coeff = self.drive_leg_N_at_max / self.v_max_valid ** 2

        if self.parametric is None:
            self.parametric = ResistanceModel(hull=self.hull)

    # -- components -------------------------------------------------------
    def hydrodynamic(self, v):
        v = np.abs(np.asarray(v, float))
        out = np.zeros_like(v, dtype=float)

        inside = v <= self.v_max_valid

        if np.any(inside):
            out[inside] = self._interp(v[inside])

        if np.any(~inside):
            tail = self._tail_coeff * v[~inside] ** self._tail_exp
            out[~inside] = np.maximum(tail, self.parametric.total(v[~inside]))

        return out + self._leg_coeff * v ** 2

    def aerodynamic(self, v, v_wind=None):
        if not self.aero_enabled:
            return np.zeros_like(np.asarray(v, float))
        if v_wind is None:
            v_wind = self.wind_ms
        h = self.hull
        va = np.asarray(v, float) + v_wind
        A_beam = 0.0 if h.beams_faired else \
            h.n_beams * h.beam_diameter_m * h.beam_span_m
        Cd_beam = 0.35 if h.beams_faired else h.beam_Cd
        return 0.5 * RHO_AIR * va ** 2 * (
            h.cockpit_Cd * h.dry_frontal_area_m2 + Cd_beam * A_beam)

    def total(self, v, v_wind=None):
        v = np.asarray(v, float)
        return self.hydrodynamic(v) + self.aerodynamic(v, v_wind)

    def effective_power(self, v, v_wind=None):
        return self.total(v, v_wind) * np.asarray(v, float)

    def extrapolating(self, v):
        return bool(np.any(np.abs(np.asarray(v, float)) > self.v_max_valid))

    def curve(self, v_max_kmh=70.0, n=140):
        v = np.linspace(0.2, v_max_kmh / KMH, n)
        return dict(v_ms=v, v_kmh=v * KMH,
                    R_total_N=self.total(v),
                    R_hydro_N=self.hydrodynamic(v),
                    R_air_N=self.aerodynamic(v),
                    R_parametric_N=self.parametric.total(v),
                    P_effective_W=self.effective_power(v))

    @classmethod
    def from_params(cls, P, hull):
        """Build straight from the shared parameter file."""
        return cls(
            hull=hull,
            speed_kn=P.hydro.resistance_speed_kn,
            resistance_N=P.hydro.resistance_bare_hull_N,
            max_valid_kn=P.hydro.resistance_max_valid_kn,
            drive_leg_N_at_max=P.hydro.drive_leg_drag_N_at_20kn,
            curve_displacement_kg=P.hydro.resistance_displacement_kg,
            aero_enabled=bool(P.boat.aero_enabled),
            wind_ms=P.boat.wind_speed_ms,
            parametric=ResistanceModel(
                hull=hull,
                correlation_allowance=P.boat.correlation_allowance,
                appendage_factor=P.boat.appendage_factor,
                form_factor_k=P.boat.form_factor_k,
                spray_factor=P.boat.spray_factor,
                aero_enabled=False,
                planing_wetted_frac=P.boat.planing_wetted_frac,
                planing_transition_Fn=P.boat.planing_transition_Fn,
                planing_LD=P.boat.planing_LD))


# ============================================================================
#  3.  PROPULSION
# ============================================================================

@dataclass
class Propeller:
    """Open-water propeller with a Wageningen-like KT/KQ shape."""
    diameter_m: float = 0.240
    pitch_ratio: float = 1.05           # P/D
    blade_area_ratio: float = 0.62
    n_blades: int = 3
    wake_fraction: float = 0.06         # v_advance = v (1 - w)
    thrust_deduction: float = 0.08      # R = T (1 - t)
    rel_rotative_eff: float = 1.0
    gear_ratio: float = 1.0             # motor rev per prop rev

    def _J(self, v, n_rps):
        va = v * (1 - self.wake_fraction)
        return va / max(n_rps * self.diameter_m, 1e-6)

    def KT(self, J):
        PD = self.pitch_ratio
        return np.maximum(0.0, 0.36 * PD - 0.32 * J - 0.06 * J ** 2)

    def KQ(self, J):
        PD = self.pitch_ratio
        return np.maximum(1e-4, 0.055 * PD - 0.036 * J - 0.008 * J ** 2)

    def thrust(self, v, n_rps):
        J = self._J(v, n_rps)
        return self.KT(J) * RHO_SW * n_rps ** 2 * self.diameter_m ** 4

    def torque(self, v, n_rps):
        J = self._J(v, n_rps)
        return self.KQ(J) * RHO_SW * n_rps ** 2 * self.diameter_m ** 5

    def open_water_eff(self, v, n_rps):
        J = self._J(v, n_rps)
        kq = self.KQ(J)
        return float(np.clip(J * self.KT(J) / (2 * np.pi * kq), 0.0, 0.85))

    def slip(self, v, n_rps):
        theo = n_rps * self.pitch_ratio * self.diameter_m
        return float(np.clip(1 - v * (1 - self.wake_fraction) /
                             max(theo, 1e-6), -0.5, 1.0))

    def shaft_power(self, v, n_rps):
        return 2 * np.pi * n_rps * self.torque(v, n_rps) / self.rel_rotative_eff

    def rps_for_power(self, v, P_shaft, lo=0.5, hi=180.0, iters=40):
        """Invert shaft power to shaft speed (monotone in n)."""
        if P_shaft <= 0:
            return 0.0
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            if self.shaft_power(v, mid) < P_shaft:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def match_to(self, v_target_ms, P_shaft_W, D_bounds=(0.18, 0.34),
                 PD_bounds=(0.75, 1.65), n_max_rps=110.0, grid=26,
                 sigma_min=0.06):
        """Pick diameter and pitch ratio that maximise open-water efficiency
        at a target operating point, subject to a shaft-speed limit.

        Prop matching is worth far more than most people expect: a badly
        matched prop costs 20-25 points of efficiency, which is 5-10 kW at
        race power -- more than any cooling or aero change on the boat.
        """
        best = None
        for D in np.linspace(*D_bounds, grid):
            for PD in np.linspace(*PD_bounds, grid):
                p = Propeller(diameter_m=D, pitch_ratio=PD,
                              blade_area_ratio=self.blade_area_ratio,
                              n_blades=self.n_blades,
                              wake_fraction=self.wake_fraction,
                              thrust_deduction=self.thrust_deduction,
                              gear_ratio=self.gear_ratio)
                n = p.rps_for_power(v_target_ms, P_shaft_W)
                if n > n_max_rps:
                    continue
                if p.cavitation_number(v_target_ms, n) < sigma_min:
                    continue   # soft screen: sigma at 0.7R, see docstring
                e = p.open_water_eff(v_target_ms, n)
                if best is None or e > best[0]:
                    best = (e, D, PD, n)
        if best is None:
            return self, dict(matched=False,
                              reason="no candidate met the rpm and cavitation "
                                     "screens; relax n_max_rps or sigma_min")
        e, D, PD, n = best
        out = Propeller(diameter_m=D, pitch_ratio=PD,
                        blade_area_ratio=self.blade_area_ratio,
                        n_blades=self.n_blades,
                        wake_fraction=self.wake_fraction,
                        thrust_deduction=self.thrust_deduction,
                        gear_ratio=self.gear_ratio)
        return out, dict(matched=True, eff=e, diameter_m=D, pitch_ratio=PD,
                         n_rps=n, n_rpm=n * 60 * self.gear_ratio,
                         J=out._J(v_target_ms, n),
                         cav_number=out.cavitation_number(v_target_ms, n))

    def cavitation_number(self, v, n_rps, depth_m=0.25):
        p = 101325.0 + RHO_SW * G * depth_m - 2340.0
        vr = np.sqrt(max(v, 0.1) ** 2 + (0.7 * np.pi * n_rps *
                                         self.diameter_m) ** 2)
        return float(p / (0.5 * RHO_SW * vr ** 2))


# ============================================================================
#  4.  LONGITUDINAL DYNAMICS
# ============================================================================

def match_propeller_to_boat(hull, resistance, prop, mass_kg=250.0,
                            P_shaft_W=25000.0, iters=6, **match_kw):
    """Iteratively match the propeller to the boat at its OWN top speed.

    Matching at a target speed the boat cannot reach optimises a point that
    does not exist. Instead: guess a speed, match, recompute the achievable
    speed with that prop, repeat. Converges in a few passes.
    """
    p = prop
    d = BoatDynamics(hull, resistance, p, mass_kg=mass_kg,
                     P_shaft_max_W=P_shaft_W)
    v = d.steady_speed(P_shaft_W)
    hist = [v]
    info = dict(matched=False)
    for _ in range(iters):
        p_new, inf = p.match_to(v, P_shaft_W, **match_kw)
        if not inf.get("matched"):
            break
        p, info = p_new, inf
        d = BoatDynamics(hull, resistance, p, mass_kg=mass_kg,
                         P_shaft_max_W=P_shaft_W)
        v_new = d.steady_speed(P_shaft_W)
        hist.append(v_new)
        if abs(v_new - v) < 0.02:
            v = v_new
            break
        v = v_new
    info["top_speed_ms"] = v
    info["top_speed_kmh"] = v * KMH
    info["iterations_kmh"] = [round(h * KMH, 2) for h in hist]
    return p, info


@dataclass
class BoatDynamics:
    """(m + m_added) dv/dt = T(1-t) - R.  Hard cap at the shaft."""
    hull: Hull
    resistance: ResistanceModel
    propeller: Propeller
    mass_kg: float = 250.0
    added_mass_frac: float = 0.10
    P_shaft_max_W: float = 25_000.0       # ENERGY_REQ_188 — never exceeded
    driveline_eff: float = 0.97
    v: float = 0.0
    n_rps: float = 0.0

    def __post_init__(self):
        self.m_eff = self.mass_kg * (1 + self.added_mass_frac)

    def step(self, dt, P_shaft_cmd_W, v_wind=0.0):
        """Advance one timestep under a commanded shaft power.

        Returns a dict of the operating point.  The cap is applied here and
        nowhere else, so no code path can exceed it.
        """
        P = float(np.clip(P_shaft_cmd_W, 0.0, self.P_shaft_max_W))
        P_prop = P * self.driveline_eff
        n = self.propeller.rps_for_power(self.v, P_prop)
        T = self.propeller.thrust(self.v, n)
        T_eff = T * (1 - self.propeller.thrust_deduction)
        R = float(self.resistance.total(self.v, v_wind))
        a = (T_eff - R) / self.m_eff
        self.v = max(0.0, self.v + a * dt)
        self.n_rps = n
        return dict(v_ms=self.v, v_kmh=self.v * KMH, v_kn=self.v * KNOT,
                    a_ms2=a, thrust_N=T, resistance_N=R,
                    P_shaft_W=P, P_effective_W=R * self.v,
                    n_rps=n, n_rpm=n * 60 * self.propeller.gear_ratio,
                    prop_eff=self.propeller.open_water_eff(self.v, n),
                    slip=self.propeller.slip(self.v, n),
                    cav_number=self.propeller.cavitation_number(self.v, n),
                    capped=P_shaft_cmd_W > self.P_shaft_max_W + 1e-6)

    def steady_speed(self, P_shaft_W, v_wind=0.0, dt=0.25, t_max=180.0):
        """Terminal speed at a held power."""
        v0, self.v = self.v, self.v
        for _ in range(int(t_max / dt)):
            prev = self.v
            self.step(dt, P_shaft_W, v_wind)
            if abs(self.v - prev) < 1e-5:
                break
        out = self.v
        self.v = v0
        return out

    def power_speed_curve(self, powers_W=None, v_wind=0.0):
        if powers_W is None:
            powers_W = np.linspace(1000, self.P_shaft_max_W, 25)
        rows = []
        for P in powers_W:
            v = self.steady_speed(float(P), v_wind)
            n = self.propeller.rps_for_power(v, P * self.driveline_eff)
            rows.append(dict(P_shaft_W=float(P), v_ms=v, v_kmh=v * KMH,
                             v_kn=v * KNOT,
                             prop_eff=self.propeller.open_water_eff(v, n),
                             n_rpm=n * 60 * self.propeller.gear_ratio,
                             Wh_per_km=(P / max(v * KMH, 1e-6)) / 1.0))
        return rows


# ============================================================================
#  5.  PILOT / THROTTLE
# ============================================================================

@dataclass
class RaceCourse:
    """A closed lap defined by legs. Each leg has a length and a speed target;
    corners impose a speed cap through their radius."""
    legs: list = field(default_factory=lambda: [
        dict(name="start straight", length_m=420.0, radius_m=None),
        dict(name="turn 1", length_m=70.0, radius_m=28.0),
        dict(name="back straight", length_m=380.0, radius_m=None),
        dict(name="turn 2", length_m=70.0, radius_m=25.0),
    ])
    lateral_g_limit: float = 0.55

    @property
    def lap_length_m(self):
        return sum(l["length_m"] for l in self.legs)

    def speed_cap(self, s_along_lap):
        s = s_along_lap % self.lap_length_m
        acc = 0.0
        for l in self.legs:
            if s < acc + l["length_m"]:
                if l["radius_m"]:
                    return float(np.sqrt(self.lateral_g_limit * G *
                                         l["radius_m"]))
                return 1e6
            acc += l["length_m"]
        return 1e6

    def leg_name(self, s_along_lap):
        s = s_along_lap % self.lap_length_m
        acc = 0.0
        for l in self.legs:
            if s < acc + l["length_m"]:
                return l["name"]
            acc += l["length_m"]
        return self.legs[-1]["name"]


@dataclass
class Pilot:
    """Speed-following throttle with a proportional term and a power cap.
    This is what turns a course into a power trace."""
    course: RaceCourse
    target_speed_kmh: float = 55.0
    kp_W_per_ms: float = 9000.0
    P_max_W: float = 25_000.0
    P_min_W: float = 0.0

    def command(self, v_ms, s_along_lap):
        v_target = min(self.target_speed_kmh / KMH,
                       self.course.speed_cap(s_along_lap))
        err = v_target - v_ms
        return float(np.clip(self.kp_W_per_ms * err, self.P_min_W, self.P_max_W))


# ============================================================================
#  6.  DRIVETRAIN THERMAL
# ============================================================================

@dataclass
class Drivetrain:
    r"""Motor and inverter losses and their temperatures.

    WHY THIS MATTERS FOR REQ_188
    ----------------------------
    "25 kW nominal" is a THERMAL statement, not an electrical one. A motor is
    rated continuous at the power it can shed heat at, indefinitely, at some
    assumed ambient. Your Competr spec quotes 26.9 kW nominal against a 25 kW
    cap, and the torque and speed ceilings do not reconcile -- which is
    exactly the kind of inconsistency a loss-and-temperature model exposes.
    Until the manufacturer sends a real torque-speed and efficiency map, every
    number below is ESTIMATED and the model says so.

    LOSS MODEL
    ----------
      copper      3 * I_ph^2 * R_ph(T_winding)     rises as it heats
      iron        k_fe * (omega/omega_ref)^2       speed dependent
      conduction  3 * I_ph * V_ce                  inverter
      switching   k_sw * f_sw * I_ph               inverter

    Copper loss rising with winding temperature is the feedback that matters:
    hotter windings mean more resistance means more loss means hotter still.
    Unlike the pack, there is no stabilising SOC term here.

    THERMAL PATHS
    -------------
    The motor is an OUTBOARD -- its case sits in the sea, which is an
    excellent heat sink and the reason it can take this power at all. The
    inverter is inboard and has to reject into the coolant loop, competing
    with the pack for the same circuit.
    """
    # --- electrical [ESTIMATED — replace from the manufacturer] ---------
    Kt_Nm_per_A: float = 0.30
    R_phase_ohm: float = 0.012          # per phase at 25 degC
    cu_tempco: float = 0.00393          # copper, per K
    iron_loss_ref_W: float = 300.0      # at reference speed
    omega_ref_rad_s: float = 490.0
    Vce_sat: float = 1.20               # inverter conduction drop
    k_switching_W_per_A: float = 1.25   # lumped switching loss

    # --- thermal [ESTIMATED] --------------------------------------------
    C_winding_J_K: float = 3200.0
    C_case_J_K: float = 6000.0
    R_wind_case_KW: float = 0.020
    R_case_sea_KW: float = 0.0055       # submerged outboard: very good
    C_junction_J_K: float = 90.0
    C_heatsink_J_K: float = 2400.0
    R_junc_hs_KW: float = 0.030
    R_hs_coolant_KW: float = 0.020

    # --- limits ----------------------------------------------------------
    T_winding_warn_C: float = 130.0
    T_winding_max_C: float = 155.0      # class F insulation
    T_junction_warn_C: float = 100.0
    T_junction_max_C: float = 125.0

    # --- state -----------------------------------------------------------
    T_winding_C: float = 25.0
    T_case_C: float = 25.0
    T_junction_C: float = 25.0
    T_heatsink_C: float = 25.0

    def reset(self, T=25.0):
        self.T_winding_C = self.T_case_C = T
        self.T_junction_C = self.T_heatsink_C = T
        return self

    def phase_current(self, P_shaft_W, omega_rad_s):
        if omega_rad_s < 1e-3:
            return 0.0
        return (P_shaft_W / omega_rad_s) / max(self.Kt_Nm_per_A, 1e-6)

    def losses(self, P_shaft_W, omega_rad_s):
        """Returns (motor_loss_W, inverter_loss_W, I_phase_A)."""
        I = self.phase_current(P_shaft_W, omega_rad_s)
        R = self.R_phase_ohm * (1 + self.cu_tempco * (self.T_winding_C - 25.0))
        cu = 3.0 * I * I * R
        fe = self.iron_loss_ref_W * (omega_rad_s / self.omega_ref_rad_s) ** 2
        cond = 3.0 * I * self.Vce_sat
        sw = self.k_switching_W_per_A * I
        return cu + fe, cond + sw, I

    def step(self, dt, P_shaft_W, omega_rad_s, T_sea_C, T_coolant_C):
        """Exponential-Euler update, same scheme as the pack."""
        q_m, q_i, I = self.losses(P_shaft_W, omega_rad_s)
        g_wc = 1.0 / self.R_wind_case_KW
        g_cs = 1.0 / self.R_case_sea_KW
        g_jh = 1.0 / self.R_junc_hs_KW
        g_hc = 1.0 / self.R_hs_coolant_KW

        ss = (q_m + g_wc * self.T_case_C) / g_wc
        self.T_winding_C = ss + (self.T_winding_C - ss) * \
            np.exp(-(g_wc / self.C_winding_J_K) * dt)
        gc = g_wc + g_cs
        ss = (g_wc * self.T_winding_C + g_cs * T_sea_C) / gc
        self.T_case_C = ss + (self.T_case_C - ss) * \
            np.exp(-(gc / self.C_case_J_K) * dt)

        ss = (q_i + g_jh * self.T_heatsink_C) / g_jh
        self.T_junction_C = ss + (self.T_junction_C - ss) * \
            np.exp(-(g_jh / self.C_junction_J_K) * dt)
        gh = g_jh + g_hc
        ss = (g_jh * self.T_junction_C + g_hc * T_coolant_C) / gh
        self.T_heatsink_C = ss + (self.T_heatsink_C - ss) * \
            np.exp(-(gh / self.C_heatsink_J_K) * dt)

        eff_m = P_shaft_W / max(P_shaft_W + q_m, 1e-6)
        eff_i = (P_shaft_W + q_m) / max(P_shaft_W + q_m + q_i, 1e-6)
        return dict(motor_loss_W=q_m, inverter_loss_W=q_i, I_phase_A=I,
                    eff_motor=eff_m, eff_inverter=eff_i,
                    T_winding_C=self.T_winding_C, T_case_C=self.T_case_C,
                    T_junction_C=self.T_junction_C,
                    T_heatsink_C=self.T_heatsink_C)

    def derate(self):
        """Linear thermal derate factor, worst of motor and inverter."""
        a = np.clip((self.T_winding_max_C - self.T_winding_C) /
                    max(1e-6, self.T_winding_max_C - self.T_winding_warn_C), 0, 1)
        b = np.clip((self.T_junction_max_C - self.T_junction_C) /
                    max(1e-6, self.T_junction_max_C - self.T_junction_warn_C), 0, 1)
        return float(min(a, b))

    def continuous_rating_W(self, omega_rad_s, T_sea_C=29.0, T_coolant_C=32.0,
                            lo=1000.0, hi=45000.0, iters=44):
        """The power this drivetrain can hold INDEFINITELY at this speed.

        This is what "nominal" actually means, and it is the number to compare
        against the 25 kW cap. Bisects for the shaft power whose steady-state
        winding and junction temperatures both land exactly on their limits.
        """
        def steady(P):
            d = Drivetrain(**{k: getattr(self, k) for k in
                              ("Kt_Nm_per_A", "R_phase_ohm", "cu_tempco",
                               "iron_loss_ref_W", "omega_ref_rad_s", "Vce_sat",
                               "k_switching_W_per_A", "C_winding_J_K",
                               "C_case_J_K", "R_wind_case_KW", "R_case_sea_KW",
                               "C_junction_J_K", "C_heatsink_J_K",
                               "R_junc_hs_KW", "R_hs_coolant_KW")})
            d.reset(T_sea_C)
            for _ in range(900):
                d.step(5.0, P, omega_rad_s, T_sea_C, T_coolant_C)
            return d.T_winding_C, d.T_junction_C
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            tw, tj = steady(mid)
            if tw > self.T_winding_max_C or tj > self.T_junction_max_C:
                hi = mid
            else:
                lo = mid
        tw, tj = steady(lo)
        return dict(P_continuous_W=lo, T_winding_C=tw, T_junction_C=tj,
                    rpm=omega_rad_s * 60 / (2 * np.pi))
