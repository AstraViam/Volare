r"""
volare_thermal.pack_thermal
===========================

Coupled electro-thermal nodal model for a cylindrical-cell battery pack,
with a resolved coolant hydraulic circuit.

WHAT THIS MODEL DOES THAT A LUMPED MODEL CANNOT
-----------------------------------------------
1. Every cell is an individual ELECTRICAL entity.  Cells in a parallel group
   share a terminal voltage, so current splits by impedance -- it is NOT
   I_pack/P.  Hot cells have lower R0 and hog current.
2. Every cell is an individual THERMAL entity at a known (x, y) position,
   coupled to neighbours, busbars, and a coolant path that heats along its
   length.
3. The coolant side is resolved HYDRAULICALLY: flow splits across circuits,
   Reynolds number sets the tube-side heat transfer coefficient, and
   pressure drop is computed.  This captures the central design tension:
       many parallel tubes -> good coverage, low velocity, laminar,
                              poor h, low dP
       few  parallel tubes -> poor coverage, high velocity, turbulent,
                              excellent h, high dP
   The optimum is a few circuits that each SERPENTINE through several gaps.
   A lumped model cannot see this at all.
4. Both domains are solved together, so the destabilising feedback
       hotter -> lower R0 -> more current -> more heat -> hotter
   and its stabilising counterpart
       more current -> faster SOC drop -> lower OCV -> sheds current
   both appear, and their balance sets the real hotspot.

MODEL STRUCTURE
---------------
Electrical (per cell i, within a parallel group):
    V_group = U_ocv,i(z_i) - I_i*R0_i(T_i, z_i) - sum_k V_RC,k,i
    subject to sum_i I_i = I_pack        -> closed form, no iteration

Heat generation (Bernardi 1985), I positive on discharge:
    q_i = I_i*(U_ocv,i - V_group)  -  I_i*T_i*(dU/dT)_i
          |__ irreversible ______|    |__ reversible (entropic) __|

Thermal (implicit Euler on a sparse RC network):
    C dT/dt = -G T + q + s
  Nodes: 2 per cell (core, can) + 1 per busbar + 1 per coolant segment
         + 1 enclosure-air node.  Outside ambient is a fixed boundary.

UNITS: SI throughout, except cell capacity (Ah).  Temperatures are KELVIN
internally; all reported values are degC.

PARAMETER PROVENANCE  --  READ THIS
-----------------------------------
Default cell parameters are LITERATURE / DATASHEET-DERIVED estimates for a
Molicel INR21700-P50B.  They are structurally right and numerically
approximate.  The model's value is its structure; the numbers must come from
your own HPPC campaign.  See README.md -> "Parametrising from your own cells".
Confidence tags: [HIGH] datasheet, [MED] literature-typical, [LOW] estimated.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu
from dataclasses import dataclass, field


# ============================================================================
#  1.  CELL MODEL
# ============================================================================

@dataclass
class CellParams:
    """Electro-thermal parameters for one cell chemistry/format.
    Defaults approximate a Molicel INR21700-P50B (NMC, 5.0 Ah, 3.6 V nom)."""

    # --- Nameplate -----------------------------------------------------
    capacity_Ah: float = 5.0          # [HIGH] datasheet typical
    v_nominal: float = 3.6            # [HIGH]
    v_max: float = 4.20               # [HIGH]
    v_min: float = 2.50               # [HIGH]

    # --- Physical ------------------------------------------------------
    mass_kg: float = 0.070            # [HIGH] datasheet max 71 g
    diameter_m: float = 0.02155       # [HIGH]
    height_m: float = 0.07015         # [HIGH]
    cp_J_kgK: float = 1050.0          # [MED] typical Li-ion 1000-1150

    # --- Intra-cell conduction -----------------------------------------
    # Core->can radial resistance from k_radial ~ 0.6 W/m/K:
    #   dT = q/(4*pi*L*k_r) = q/(4*pi*0.070*0.6)  ->  R = 1.9 K/W
    R_core_can_KW: float = 2.0        # [MED] tune against instrumented module
    core_mass_fraction: float = 0.75  # [LOW] thermal mass split core vs can

    # --- ECM: R0 + 2 RC pairs ------------------------------------------
    # Reconciled to datasheet: 6.5 mOhm AC @1 kHz, ~12.8 mOhm DC @50% SOC.
    # Long-pulse steady total R0+R1+R2 = 16.5 mOhm.
    R0_ref_ohm: float = 0.0075        # [LOW-MED] ohmic at T_ref, mid-SOC
    R1_ref_ohm: float = 0.0040        # [LOW] charge transfer
    tau1_s: float = 10.0              # [LOW]
    R2_ref_ohm: float = 0.0050        # [LOW] diffusion
    tau2_s: float = 120.0             # [LOW]

    T_ref_K: float = 298.15
    Ea_over_R_K: float = 2500.0       # [LOW-MED] R falls ~38% over 25->45 degC

    # --- Safety thresholds ---------------------------------------------
    T_warn_C: float = 45.0
    T_max_C: float = 60.0

    # --- Curves ---------------------------------------------------------
    # OCV vs SOC. [MED] generic high-nickel NMC shape.  REPLACE with a C/20
    # discharge from your own cells: this curve sets SOC accuracy and the OCV
    # feedback that limits current hogging.
    ocv_soc: np.ndarray = field(default_factory=lambda: np.array(
        [0.00, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50,
         0.60, 0.70, 0.80, 0.90, 0.95, 1.00]))
    ocv_v: np.ndarray = field(default_factory=lambda: np.array(
        [2.80, 3.15, 3.30, 3.45, 3.55, 3.63, 3.72,
         3.81, 3.89, 3.98, 4.08, 4.14, 4.20]))

    # Entropic coefficient dU/dT [V/K]. [LOW] literature NMC.
    # Negative -> exothermic on discharge.
    dudt_soc: np.ndarray = field(default_factory=lambda: np.array(
        [0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0]))
    dudt_v_per_K: np.ndarray = field(default_factory=lambda: np.array(
        [-3.0e-4, -2.2e-4, -1.6e-4, -1.0e-4, -0.6e-4, 0.0, 0.5e-4]))

    # R0 multiplier vs SOC. [LOW]
    rsoc_soc: np.ndarray = field(default_factory=lambda: np.array(
        [0.0, 0.05, 0.15, 0.30, 0.70, 0.90, 1.00]))
    rsoc_mult: np.ndarray = field(default_factory=lambda: np.array(
        [2.20, 1.60, 1.20, 1.02, 1.00, 1.05, 1.15]))

    # ------------------------------------------------------------------
    @property
    def thermal_capacity_JK(self) -> float:
        return self.mass_kg * self.cp_J_kgK

    @property
    def lateral_area_m2(self) -> float:
        return np.pi * self.diameter_m * self.height_m

    @property
    def end_area_m2(self) -> float:
        return np.pi * (self.diameter_m / 2.0) ** 2

    def ocv(self, z):
        return np.interp(np.clip(z, 0.0, 1.0), self.ocv_soc, self.ocv_v)

    def dudt(self, z):
        return np.interp(np.clip(z, 0.0, 1.0), self.dudt_soc, self.dudt_v_per_K)

    def _arrhenius(self, T_K):
        return np.exp(self.Ea_over_R_K * (1.0 / T_K - 1.0 / self.T_ref_K))

    # -- measured R0(SOC, T) map (set by celldata.CellDataset) ------------
    def attach_R0_map(self, soc, T_C, R_ohm):
        """Use a measured 2D map instead of the analytic Arrhenius form.
        soc (n_s,), T_C (n_t,), R_ohm (n_t, n_s). Bilinear, clamped at edges."""
        self._map_soc = np.asarray(soc, float)
        self._map_T = np.asarray(T_C, float) + 273.15
        self._map_R = np.asarray(R_ohm, float)
        o = np.argsort(self._map_T)
        self._map_T, self._map_R = self._map_T[o], self._map_R[o]
        return self

    @property
    def has_R0_map(self):
        return getattr(self, "_map_R", None) is not None

    def _R0_from_map(self, T_K, z):
        Ts, Rs, ss = self._map_T, self._map_R, self._map_soc
        T = np.clip(T_K, Ts[0], Ts[-1])
        if len(Ts) == 1:
            return np.interp(z, ss, Rs[0])
        i = np.clip(np.searchsorted(Ts, T) - 1, 0, len(Ts) - 2)
        w = (T - Ts[i]) / (Ts[i + 1] - Ts[i])
        lo = np.array([np.interp(z, ss, Rs[k]) for k in range(len(Ts))])
        zi = np.clip(np.arange(len(np.atleast_1d(z))), 0, None)
        a = np.take_along_axis(lo, np.atleast_1d(i)[None, :]
                               if lo.ndim > 1 else np.atleast_1d(i), axis=0)
        b = np.take_along_axis(lo, np.atleast_1d(i + 1)[None, :]
                               if lo.ndim > 1 else np.atleast_1d(i + 1), axis=0)
        return (a[0] * (1 - w) + b[0] * w) if lo.ndim > 1 else \
               (lo[i] * (1 - w) + lo[i + 1] * w)

    def R0(self, T_K, z, scale=1.0):
        if self.has_R0_map:
            return self._R0_from_map(T_K, np.clip(z, 0.0, 1.0)) * scale
        m = np.interp(np.clip(z, 0.0, 1.0), self.rsoc_soc, self.rsoc_mult)
        return self.R0_ref_ohm * scale * self._arrhenius(T_K) * m

    # -- capacity vs temperature (from measured temperature-sweep curves) ---
    cap_temp_C: np.ndarray | None = None
    cap_temp_mult: np.ndarray | None = None

    def capacity_factor(self, T_K):
        """Usable capacity multiplier at temperature.

        A cell does not hold the same charge at 0 degC as at 25. Ignoring this
        makes SOC drift optimistic exactly when the pack is cold -- at the
        start of a race, which is when you are planning the whole strategy.
        """
        if self.cap_temp_C is None:
            return np.ones_like(np.asarray(T_K, float))
        return np.interp(np.asarray(T_K, float) - 273.15,
                         self.cap_temp_C, self.cap_temp_mult)

    def R_rc(self, T_K, scale=1.0, z=0.5):
        """RC-branch resistances [ohm].

        When a measured R0(SOC,T) map is attached, the RC branches are scaled
        FROM THE MAP rather than from the analytic Arrhenius form. Otherwise
        R0 would follow the measurement while R1 and R2 followed a fitted
        exponential, and the three would disagree badly at temperature
        extremes -- exactly where the map is most valuable.
        """
        if self.has_R0_map:
            R0 = self._R0_from_map(T_K, np.clip(z, 0.0, 1.0)) * scale
            f1 = self.R1_ref_ohm / max(self.R0_ref_ohm, 1e-12)
            f2 = self.R2_ref_ohm / max(self.R0_ref_ohm, 1e-12)
            return R0 * f1, R0 * f2
        a = self._arrhenius(T_K)
        return self.R1_ref_ohm * scale * a, self.R2_ref_ohm * scale * a


# ============================================================================
#  2.  COOLANT FLUID + TUBE CORRELATIONS
# ============================================================================

@dataclass
class Coolant:
    """Closed-loop coolant. Defaults: 50/50 water-ethylene glycol at ~30 degC.

    NOTE the viscosity: glycol is ~3x water.  That is what pushes small
    parallel tubes into the laminar regime and destroys their heat transfer.
    Deionised water + corrosion inhibitor performs far better thermally; the
    freeze protection glycol buys you is not needed in Monaco in July.
    Set mu=0.0008, k=0.62, cp=4180, rho=997 and re-run: it is worth kelvins.
    """
    flow_L_per_min: float = 8.0       # [DESIGN VARIABLE]
    inlet_T_C: float = 28.0           # after the seawater heat exchanger
    rho_kg_m3: float = 1050.0         # [MED]
    cp_J_kgK: float = 3500.0          # [MED]
    mu_Pa_s: float = 0.0025           # [MED] 50/50 glycol @30C; water = 0.0008
    k_W_mK: float = 0.38              # [MED] 50/50 glycol; water = 0.62

    @property
    def mdot_kg_s(self) -> float:
        return self.flow_L_per_min / 60000.0 * self.rho_kg_m3

    @property
    def Pr(self) -> float:
        return self.mu_Pa_s * self.cp_J_kgK / self.k_W_mK


def tube_side_htc(coolant: Coolant, tube_id_m: float, mdot_per_circuit: float):
    """Internal convection coefficient in a round tube.
    Laminar (Re<2300): Nu = 3.66.  Turbulent (Re>4000): Dittus-Boelter.
    Transitional: linear blend -- crude, but this band is somewhere to avoid
    designing into, not somewhere to model precisely.
    Returns (h [W/m2K], Re, regime, velocity [m/s])."""
    A = np.pi * (tube_id_m / 2.0) ** 2
    v = mdot_per_circuit / (coolant.rho_kg_m3 * A)
    Re = coolant.rho_kg_m3 * v * tube_id_m / coolant.mu_Pa_s
    Nu_lam = 3.66
    Nu_turb = 0.023 * max(Re, 1.0) ** 0.8 * coolant.Pr ** 0.4
    if Re < 2300:
        Nu, regime = Nu_lam, "laminar"
    elif Re > 4000:
        Nu, regime = Nu_turb, "turbulent"
    else:
        f = (Re - 2300) / 1700.0
        Nu, regime = (1 - f) * Nu_lam + f * Nu_turb, "transitional"
    return Nu * coolant.k_W_mK / tube_id_m, Re, regime, v


def tube_pressure_drop(coolant: Coolant, tube_id_m: float,
                       mdot_per_circuit: float, length_m: float,
                       n_bends: int = 0, K_bend: float = 1.5):
    """Darcy-Weisbach pressure drop for one circuit [Pa]."""
    A = np.pi * (tube_id_m / 2.0) ** 2
    v = mdot_per_circuit / (coolant.rho_kg_m3 * A)
    Re = coolant.rho_kg_m3 * v * tube_id_m / coolant.mu_Pa_s
    f = 64.0 / max(Re, 1.0) if Re < 2300 else 0.316 * max(Re, 1.0) ** -0.25
    return (f * length_m / tube_id_m + n_bends * K_bend) * \
           0.5 * coolant.rho_kg_m3 * v ** 2


# ============================================================================
#  3.  PACK LAYOUT  (spatial + wiring + hydraulics)
# ============================================================================

@dataclass
class PackLayout:
    """Spatial arrangement, electrical wiring, and coolant routing.

    Cells sit on a rectangular or hex-staggered grid.  Each ROW is one
    parallel group; rows stack in series.

    COOLANT ROUTING
    ---------------
    Tubes lie in inter-row gaps.  Gap g is between row g and row g+1.
    A tube exists in gap g if g % tube_every == 0.
    Tubes are grouped into `n_circuits` PARALLEL hydraulic circuits; within a
    circuit the tubes run in SERIES (serpentine), alternate tubes flowing in
    opposite directions like a real snaking tube.

        n_circuits = n_tubes  ->  all parallel   (laminar, poor h, low dP)
        n_circuits = 1        ->  one long snake (turbulent, huge dP)
        n_circuits = 3..6     ->  usually the optimum

    A cell couples to EVERY tube it touches, so with tube_every=1 an interior
    cell has coolant on both sides.
    """

    n_series: int = 26                # rows
    n_parallel: int = 21              # columns
    pitch_x_m: float = 0.0235         # column pitch (21.55 dia + 1.95 gap)
    pitch_y_m: float = 0.0235         # row pitch
    stagger: bool = False
    tube_every: int = 2               # tube in every Nth inter-row gap
    n_circuits: int = 3               # [DESIGN VARIABLE]
    interleave_circuits: bool = True  # spread each circuit across the pack

    # --- thermal coupling ----------------------------------------------
    # Cell can <-> neighbour can, through gap filler / holder / air:
    #   air only        gap_filler_k ~ 0.03 -> G ~ 0.012 W/K
    #   thermal potting gap_filler_k ~ 1.5  -> G ~ 0.58  W/K
    gap_filler_k_WmK: float = 1.5     # [MED] potting compound
    gap_contact_frac: float = 0.16    # [LOW] effective conduction area fraction

    # Cell can <-> TUBE WALL: contact + potting + wall only.
    # Tube-side convection is computed separately and added in series.
    R_can_tubewall_KW: float = 2.5    # [DESIGN VARIABLE] bonded 2-3, lazy 8+

    tube_id_m: float = 0.006          # [DESIGN VARIABLE]

    # Cell can <-> busbar through the weld tab.  Ni 0.15x8 mm, 15 mm long:
    #   G = 90 * 1.2e-6 / 0.015 = 0.0072 W/K per tab, x2 = 0.015.
    # Deliberately poor -- this is why busbars run hot independently.
    G_can_busbar_WK: float = 0.015    # [MED]

    # Enclosure
    h_internal_WmK: float = 6.0
    enclosure_air_volume_m3: float = 0.05
    enclosure_UA_WK: float = 3.0

    # Busbars (one per series interconnect)
    busbar_mass_kg: float = 0.45
    busbar_cp_J_kgK: float = 385.0
    busbar_R_ohm: float = 7.0e-5      # [LOW] effective, distributed feed
    busbar_cooled: bool = False
    R_busbar_coolant_KW: float = 2.0

    # ------------------------------------------------------------------
    def __post_init__(self):
        self.n_cells = self.n_series * self.n_parallel
        self._build_positions()
        self._build_wiring()
        self._build_adjacency()
        self._build_coolant()

    def _build_positions(self):
        xs, ys = [], []
        for r in range(self.n_series):
            off = 0.5 * self.pitch_x_m if (self.stagger and r % 2) else 0.0
            for c in range(self.n_parallel):
                xs.append(c * self.pitch_x_m + off)
                ys.append(r * self.pitch_y_m)
        self.x, self.y = np.array(xs), np.array(ys)
        self.row = np.repeat(np.arange(self.n_series), self.n_parallel)
        self.col = np.tile(np.arange(self.n_parallel), self.n_series)

    def _build_wiring(self):
        self.series_index = self.row.copy()
        self.parallel_index = self.col.copy()

    def _build_adjacency(self):
        cutoff = 1.15 * max(self.pitch_x_m, self.pitch_y_m)
        pts = np.column_stack([self.x, self.y])
        d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
        iu, ju = np.triu_indices(self.n_cells, k=1)
        mask = d[iu, ju] < cutoff
        self.neighbour_pairs = np.column_stack([iu[mask], ju[mask]])
        counts = np.zeros(self.n_cells)
        np.add.at(counts, self.neighbour_pairs[:, 0], 1)
        np.add.at(counts, self.neighbour_pairs[:, 1], 1)
        self.n_neighbours = counts
        self.exposed_frac = np.clip(1.0 - counts / 6.0, 0.05, 1.0)

    def _build_coolant(self):
        self.tube_gaps = [g for g in range(self.n_series - 1)
                          if g % self.tube_every == 0]
        self.n_tubes = len(self.tube_gaps)
        self.n_circuits_eff = int(np.clip(self.n_circuits, 1,
                                          max(1, self.n_tubes)))
        self.n_seg_per_tube = max(2, self.n_parallel // 4)

        if self.interleave_circuits:
            tube_circuit = np.arange(self.n_tubes) % self.n_circuits_eff
        else:
            tube_circuit = (np.arange(self.n_tubes) *
                            self.n_circuits_eff // max(1, self.n_tubes))
        self.tube_circuit = tube_circuit

        seg_of = {}
        self.coolant_seg_tube, self.coolant_seg_circuit = [], []
        sid = 0
        for t in range(self.n_tubes):
            for s in range(self.n_seg_per_tube):
                seg_of[(t, s)] = sid
                self.coolant_seg_tube.append(t)
                self.coolant_seg_circuit.append(int(tube_circuit[t]))
                sid += 1
        self.n_coolant_segs = sid
        self.coolant_seg_tube = np.array(self.coolant_seg_tube)
        self.coolant_seg_circuit = np.array(self.coolant_seg_circuit)

        self.upstream = -np.ones(self.n_coolant_segs, dtype=int)
        self.circuit_paths = []
        for c in range(self.n_circuits_eff):
            tubes_c = [t for t in range(self.n_tubes) if tube_circuit[t] == c]
            path = []
            for k, t in enumerate(tubes_c):
                order = list(range(self.n_seg_per_tube))
                if k % 2:
                    order = order[::-1]        # serpentine
                path.extend(seg_of[(t, s)] for s in order)
            self.circuit_paths.append(path)
            for a, b in zip(path[:-1], path[1:]):
                self.upstream[b] = a

        pairs = []
        for i in range(self.n_cells):
            r, c = self.row[i], self.col[i]
            s = min(self.n_seg_per_tube - 1,
                    int(c * self.n_seg_per_tube / self.n_parallel))
            for t, g in enumerate(self.tube_gaps):
                if r == g or r == g + 1:
                    pairs.append((i, seg_of[(t, s)]))
        self.cell_coolant_pairs = (np.array(pairs, dtype=int) if pairs
                                   else np.zeros((0, 2), dtype=int))

        touched = np.zeros(self.n_cells, dtype=int)
        for i, _ in self.cell_coolant_pairs:
            touched[i] += 1
        self.n_tubes_touching = touched
        self.frac_cells_tube_cooled = float(np.mean(touched > 0))

    # -- derived quantities ----------------------------------------------
    def G_cell_cell(self, cell: CellParams) -> float:
        gap = max(1e-4, self.pitch_x_m - cell.diameter_m)
        return self.gap_filler_k_WmK * (self.gap_contact_frac *
                                        cell.lateral_area_m2) / gap

    def G_cell_air(self, cell: CellParams) -> np.ndarray:
        A = cell.lateral_area_m2 * self.exposed_frac + 2 * cell.end_area_m2 * 0.3
        return self.h_internal_WmK * A

    def tube_length_per_circuit(self) -> float:
        return (self.n_tubes / self.n_circuits_eff) * \
               self.n_parallel * self.pitch_x_m

    def hydraulics(self, coolant: Coolant) -> dict:
        """Flow regime, htc, and pressure drop for the chosen routing."""
        mdot_c = coolant.mdot_kg_s / self.n_circuits_eff
        h, Re, regime, v = tube_side_htc(coolant, self.tube_id_m, mdot_c)
        L = self.tube_length_per_circuit()
        n_bends = max(0, int(self.n_tubes / self.n_circuits_eff) - 1)
        dp = tube_pressure_drop(coolant, self.tube_id_m, mdot_c, L, n_bends)
        A_w = np.pi * self.tube_id_m * self.pitch_x_m   # per cell, one tube
        R_conv = 1.0 / max(1e-9, h * A_w)
        return dict(n_circuits=self.n_circuits_eff, n_tubes=self.n_tubes,
                    velocity_m_s=v, Re=Re, regime=regime, h_W_m2K=h,
                    R_conv_per_cell_KW=R_conv,
                    R_total_per_tube_KW=self.R_can_tubewall_KW + R_conv,
                    circuit_length_m=L, dP_Pa=dp, dP_bar=dp / 1e5,
                    flow_per_circuit_L_min=coolant.flow_L_per_min /
                    self.n_circuits_eff)


# ============================================================================
#  4.  CELL POPULATION  (the "different cells" part)
# ============================================================================

def make_population(n_cells: int,
                    sigma_capacity: float = 0.015,
                    sigma_resistance: float = 0.060,
                    correlation: float = -0.4,
                    rng: np.random.Generator | None = None):
    """Per-cell capacity and resistance multipliers.

    sigma_* are RELATIVE standard deviations.
      Ungraded reputable batch : sigma_Q ~ 0.015, sigma_R ~ 0.060
      Graded to +/-1% / +/-5%  : sigma_Q ~ 0.004, sigma_R ~ 0.017
    correlation < 0: high-resistance cells tend to have lower capacity.
    """
    rng = rng or np.random.default_rng(0)
    L = np.linalg.cholesky(np.array([[1.0, correlation], [correlation, 1.0]]))
    v = L @ rng.standard_normal((2, n_cells))
    return (np.clip(1.0 + sigma_capacity * v[0], 0.8, 1.2),
            np.clip(1.0 + sigma_resistance * v[1], 0.5, 2.0))


def place_cells(layout: PackLayout, cap_mult, res_mult, strategy="random",
                rng: np.random.Generator | None = None,
                coolness: np.ndarray | None = None):
    """Assign graded cells to physical positions.

      'random'   -- shuffle (what you get if you do not think about it)
      'balanced' -- equalise total capacity across parallel groups
      'thermal'  -- highest-resistance cells go to the coolest positions.
                    `coolness` = per-position score, higher = cooler
                    (e.g. -T_final from a uniform baseline run).
    """
    rng = rng or np.random.default_rng(0)
    n = layout.n_cells
    idx = rng.permutation(n)
    cap, res = cap_mult[idx], res_mult[idx]

    if strategy == "random":
        return cap, res

    if strategy == "balanced":
        order = np.argsort(cap)[::-1]
        out_cap, out_res = np.empty(n), np.empty(n)
        S, P = layout.n_series, layout.n_parallel
        slot, totals = np.zeros(S, dtype=int), np.zeros(S)
        for k in order:
            g = int(np.argmin(np.where(slot < P, totals, np.inf)))
            pos = g * P + slot[g]
            out_cap[pos], out_res[pos] = cap[k], res[k]
            totals[g] += cap[k]
            slot[g] += 1
        return out_cap, out_res

    if strategy == "thermal":
        if coolness is None:
            raise ValueError("strategy='thermal' needs `coolness`")
        pos_order = np.argsort(coolness)[::-1]     # coolest positions first
        cell_order = np.argsort(res)[::-1]         # hottest-running cells first
        out_cap, out_res = np.empty(n), np.empty(n)
        out_cap[pos_order] = cap[cell_order]
        out_res[pos_order] = res[cell_order]
        return out_cap, out_res

    raise ValueError(f"unknown strategy {strategy!r}")


# ============================================================================
#  5.  THERMAL NETWORK
# ============================================================================

class ThermalNetwork:
    """Sparse RC network over a PackLayout (2D) or PackGeometry (3D).

    Node ordering:
        [0        : N)      cell cores
        [N        : 2N)     cell cans
        [2N       : 2N+B)   busbars
        [2N+B     : 2N+B+M) coolant segments
        [2N+B+M]            enclosure air

    Assembly is fully vectorised: the optimiser builds thousands of these,
    and a Python loop over 546 cells x 1500 pairs made that the bottleneck.
    """

    def __init__(self, layout, cell: CellParams, coolant: Coolant,
                 T_ambient_C: float = 30.0, adiabatic: bool = False):
        self.layout, self.cell, self.coolant = layout, cell, coolant
        self.T_amb = T_ambient_C + 273.15
        self.adiabatic = adiabatic

        N = layout.n_cells
        B = layout.n_series - 1
        M = getattr(layout, "n_coolant_segs", 0)
        self.N, self.B, self.M = N, B, M
        self.i_core = np.arange(0, N)
        self.i_can = np.arange(N, 2 * N)
        self.i_bus = np.arange(2 * N, 2 * N + B)
        self.i_cool = np.arange(2 * N + B, 2 * N + B + M)
        self.i_air = 2 * N + B + M
        self.n_nodes = self.i_air + 1
        self._assemble()

    # -- vectorised symmetric-conductance accumulator --------------------
    @staticmethod
    def _sym(i, j, g):
        i = np.asarray(i); j = np.asarray(j); g = np.asarray(g, dtype=float)
        return (np.r_[i, j, i, j], np.r_[i, j, j, i], np.r_[g, g, -g, -g])

    def _assemble(self):
        L, C_, cool = self.layout, self.cell, self.coolant
        N, B, M = self.N, self.B, self.M
        n = self.n_nodes
        R, Cc, V = [], [], []

        def add(i, j, g):
            r, c, v = self._sym(i, j, g)
            R.append(r); Cc.append(c); V.append(v)

        # core <-> can
        add(self.i_core, self.i_can, np.full(N, 1.0 / C_.R_core_can_KW))

        # can <-> can  (per-pair conductance: 3D is anisotropic)
        pairs = L.neighbour_pairs
        if len(pairs) and not self.adiabatic:
            g_pair = getattr(L, "neighbour_G", None)
            if g_pair is None:
                g_pair = np.full(len(pairs), L.G_cell_cell(C_))
            self.G_cell_cell_value = float(np.mean(g_pair))
            add(self.i_can[pairs[:, 0]], self.i_can[pairs[:, 1]], g_pair)
        else:
            self.G_cell_cell_value = 0.0

        hyd = self.hydraulics()
        self.hydraulics_info = hyd
        self.R_cell_to_coolant_KW = hyd["R_total_per_tube_KW"]

        if not self.adiabatic:
            # can <-> busbar
            si = L.series_index
            m = si < B
            add(self.i_can[m], self.i_bus[si[m]],
                np.full(m.sum(), L.G_can_busbar_WK))
            m = si - 1 >= 0
            add(self.i_can[m], self.i_bus[si[m] - 1],
                np.full(m.sum(), L.G_can_busbar_WK))

            # can <-> coolant, weighted by contact quality
            cp = getattr(L, "cell_coolant_pairs", np.zeros((0, 2), dtype=int))
            if len(cp):
                w = getattr(L, "cell_coolant_weight", np.ones(len(cp)))
                add(self.i_can[cp[:, 0]], self.i_cool[cp[:, 1]],
                    w / self.R_cell_to_coolant_KW)

            if getattr(L, "busbar_cooled", False) and M > 0:
                b = np.arange(B)
                seg = np.clip(b * M // max(1, B), 0, M - 1)
                add(self.i_bus[b], self.i_cool[seg],
                    np.full(B, 1.0 / L.R_busbar_coolant_KW))

            # can <-> enclosure air
            add(self.i_can, np.full(N, self.i_air), self.G_cell_air())
            add(self.i_bus, np.full(B, self.i_air), np.full(B, 0.5))

        rows = np.concatenate(R); cols = np.concatenate(Cc)
        vals = np.concatenate(V)
        G = sparse.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()

        # coolant advection (upwind, non-symmetric)
        mcp = cool.mdot_kg_s / max(1, self._n_circuits()) * cool.cp_J_kgK
        self.mdot_cp_per_circuit = mcp
        self.inlet_segments = []
        if M and not self.adiabatic:
            up = L.upstream
            seg = np.arange(M)
            ar = [self.i_cool[seg]]; ac = [self.i_cool[seg]]
            av = [np.full(M, mcp)]
            has = up >= 0
            ar.append(self.i_cool[seg[has]])
            ac.append(self.i_cool[up[has]])
            av.append(np.full(has.sum(), -mcp))
            self.inlet_segments = list(seg[~has])
            G = G + sparse.coo_matrix(
                (np.concatenate(av),
                 (np.concatenate(ar), np.concatenate(ac))),
                shape=(n, n)).tocsr()

        G = G.tolil()
        if not self.adiabatic:
            G[self.i_air, self.i_air] += L.enclosure_UA_WK
        self.G = G.tocsc()

        # capacitances
        Cv = np.zeros(n)
        Cv[self.i_core] = C_.thermal_capacity_JK * C_.core_mass_fraction
        Cv[self.i_can] = C_.thermal_capacity_JK * (1 - C_.core_mass_fraction)
        Cv[self.i_bus] = L.busbar_mass_kg * L.busbar_cp_J_kgK
        if M:
            seglen = getattr(L, "seg_lengths", None)
            if seglen is None:
                seglen = np.full(M, (L.n_parallel * L.pitch_x_m) /
                                 L.n_seg_per_tube)
            v_seg = np.pi * (L.tube_id_m / 2) ** 2 * seglen
            Cv[self.i_cool] = np.maximum(1e-3, v_seg * cool.rho_kg_m3 *
                                         cool.cp_J_kgK)
        Cv[self.i_air] = L.enclosure_air_volume_m3 * 1.2 * 1005.0
        self.C = Cv

        s = np.zeros(n)
        if not self.adiabatic:
            s[self.i_air] += L.enclosure_UA_WK * self.T_amb
            for seg in self.inlet_segments:
                s[self.i_cool[seg]] += mcp * (cool.inlet_T_C + 273.15)
        self.s = s

    # -- geometry-agnostic helpers ---------------------------------------
    def _n_circuits(self):
        return getattr(self.layout, "n_circuits_eff", 1)

    def G_cell_air(self):
        L, C_ = self.layout, self.cell
        if hasattr(L, "end_exposed_frac"):
            A = (C_.lateral_area_m2 * L.exposed_frac +
                 2 * C_.end_area_m2 * L.end_exposed_frac)
            return L.h_internal_WmK * A
        return L.G_cell_air(C_)

    def hydraulics(self):
        L, cool = self.layout, self.coolant
        if hasattr(L, "hydraulics") and not hasattr(L, "seg_lengths"):
            return L.hydraulics(cool)
        # PackGeometry path: derive per-circuit length from the tube list
        nc = max(1, L.n_circuits_eff)
        mdot_c = cool.mdot_kg_s / nc
        h, Re, regime, v = tube_side_htc(cool, L.tube_id_m, mdot_c)
        lengths = {}
        bends = {}
        for t in L.tubes:
            lengths[t.circuit] = lengths.get(t.circuit, 0.0) + t.length
            bends[t.circuit] = bends.get(t.circuit, 0) + t.n_bends
        Lc = max(lengths.values()) if lengths else 1.0
        nb = max(bends.values()) if bends else 0
        dp = tube_pressure_drop(cool, L.tube_id_m, mdot_c, Lc, nb)
        A_w = np.pi * L.tube_id_m * L.cell_diameter_m
        R_conv = 1.0 / max(1e-9, h * A_w)
        return dict(n_circuits=nc, n_tubes=len(L.tubes), velocity_m_s=v,
                    Re=Re, regime=regime, h_W_m2K=h,
                    R_conv_per_cell_KW=R_conv,
                    R_total_per_tube_KW=L.R_can_tubewall_KW + R_conv,
                    circuit_length_m=Lc, dP_Pa=dp, dP_bar=dp / 1e5,
                    flow_per_circuit_L_min=cool.flow_L_per_min / nc,
                    pump_hydraulic_W=dp * cool.mdot_kg_s / cool.rho_kg_m3 * nc)

    def factorise(self, dt: float):
        M = sparse.diags(self.C / dt).tocsc() + self.G
        return splu(M.tocsc())

    # -- fast steady-state solve (for optimisation) -----------------------
    def steady_state(self, q_cell, q_bus_each=0.0, n_iter=4, cell=None,
                     z=0.5, res_mult=None):
        """Solve G T = q + s directly, iterating on the temperature
        dependence of the heat source.  ~200x faster than a transient run
        and adequate for ranking designs inside an optimiser.

        q_cell may be a scalar (uniform) or a per-cell array.  If `cell` is
        given, q is recomputed each iteration at the current temperature
        using a fixed per-cell current implied by the initial q.
        """
        lu = splu(self.G.tocsc())
        q = np.full(self.N, q_cell) if np.isscalar(q_cell) else np.asarray(q_cell)
        I_eq = None
        if cell is not None:
            R0 = cell.R0(np.full(self.N, 298.15), z,
                         1.0 if res_mult is None else res_mult)
            I_eq = np.sqrt(np.maximum(q, 0) / np.maximum(R0, 1e-9))
        T = None
        for _ in range(max(1, n_iter)):
            src = self.s.copy()
            src[self.i_core] += q
            src[self.i_bus] += q_bus_each
            T = lu.solve(src)
            if cell is not None and I_eq is not None:
                R0 = cell.R0(T[self.i_core], z,
                             1.0 if res_mult is None else res_mult)
                q = I_eq ** 2 * R0
        return T


# ============================================================================
#  6.  DRIVE CYCLES
# ============================================================================

def mebc_endurance_lap():
    """(duration_s, motor shaft power W) for one representative lap.
    Launch onto plane, two straights, two slow corners.  Mean ~12.9 kW.
    REPLACE with logged sea-trial data as soon as you have it."""
    return [(8, 25_000), (40, 12_000), (6, 4_000),
            (6, 20_000), (35, 13_000), (6, 4_000)]


def build_power_profile(segments, total_s, dt):
    t = np.arange(0.0, total_s, dt)
    lap = sum(d for d, _ in segments)
    p = np.zeros_like(t)
    acc, tm = 0.0, np.mod(t, lap)
    for d, w in segments:
        p[(tm >= acc) & (tm < acc + d)] = w
        acc += d
    return t, p


def constant_power_profile(power_W, total_s, dt):
    t = np.arange(0.0, total_s, dt)
    return t, np.full_like(t, float(power_W))


# ============================================================================
#  7.  COUPLED SOLVER
# ============================================================================

@dataclass
class SimResult:
    t: np.ndarray
    T_core_C: np.ndarray
    T_can_C: np.ndarray
    T_bus_C: np.ndarray
    T_cool_C: np.ndarray
    T_air_C: np.ndarray
    I_cell: np.ndarray
    soc: np.ndarray
    q_cell: np.ndarray
    I_pack: np.ndarray
    V_pack: np.ndarray
    q_total: np.ndarray
    q_busbar: np.ndarray
    energy_out_Wh: np.ndarray
    hydraulics: dict = field(default_factory=dict)
    stopped_reason: str = ""


def simulate(layout: PackLayout,
             cell: CellParams,
             coolant: Coolant,
             power_W: np.ndarray,
             dt: float = 0.5,
             T_init_C: float = 28.0,
             T_ambient_C: float = 30.0,
             soc_init: float = 1.0,
             cap_mult: np.ndarray | None = None,
             res_mult: np.ndarray | None = None,
             inverter_eff: float = 0.96,
             group_v_cutoff: float = 2.80,
             adiabatic: bool = False,
             store_every: int = 2) -> SimResult:
    """Coupled electro-thermal simulation.

    power_W is MOTOR SHAFT-INPUT power; bus power = power_W / inverter_eff.
    adiabatic=True removes all heat rejection (validation / worst case).
    """
    N = layout.n_cells
    S, P = layout.n_series, layout.n_parallel
    cap_mult = np.ones(N) if cap_mult is None else cap_mult
    res_mult = np.ones(N) if res_mult is None else res_mult

    net = ThermalNetwork(layout, cell, coolant, T_ambient_C, adiabatic)
    lu = net.factorise(dt)

    T = np.full(net.n_nodes, T_init_C + 273.15)
    if not adiabatic:
        T[net.i_cool] = coolant.inlet_T_C + 273.15
        T[net.i_air] = T_ambient_C + 273.15

    z = np.full(N, float(soc_init))
    v1, v2 = np.zeros(N), np.zeros(N)
    cap_Ah = cell.capacity_Ah * cap_mult
    e1, e2 = np.exp(-dt / cell.tau1_s), np.exp(-dt / cell.tau2_s)
    R_bus_total = layout.busbar_R_ohm * max(0, layout.n_series - 1)

    nt = len(power_W)
    keep = set(range(0, nt, store_every))
    rec = {k: [] for k in ("t", "Tcore", "Tcan", "Tbus", "Tcool", "Tair",
                           "I", "z", "q", "Ip", "Vp", "qtot", "qbus", "E")}
    energy_Wh, reason = 0.0, "completed"

    for k in range(nt):
        T_cell = T[net.i_core]
        R0 = cell.R0(T_cell, z, res_mult)
        R1, R2 = cell.R_rc(T_cell, res_mult, z)
        U = cell.ocv(z)

        # --- electrical: exact closed-form group solve ------------------
        a = (U - v1 - v2) / R0
        b = 1.0 / R0
        A = a.reshape(S, P).sum(axis=1)
        Bs = b.reshape(S, P).sum(axis=1)
        V_oc_eff = float((A / Bs).sum())
        R_cells = float((1.0 / Bs).sum())
        # Series interconnects carry the FULL pack current and their IR drop is
        # part of the source impedance. Leaving it out means the pack delivers
        # V_cells*I to the inverter *and* dissipates I^2*R_bus on top -- energy
        # from nowhere. At 1.75 mOhm over 25 interconnects that is 8.6 % of the
        # pack's own resistance, so it is not a rounding error.
        R_eff = R_cells + R_bus_total

        P_bus = power_W[k] / inverter_eff
        disc = V_oc_eff ** 2 - 4.0 * R_eff * P_bus
        I_pack = (V_oc_eff / (2.0 * R_eff) if disc <= 0.0
                  else (V_oc_eff - np.sqrt(disc)) / (2.0 * R_eff))

        V_g = (A - I_pack) / Bs
        V_cells = float(V_g.sum())
        V_pack = V_cells - I_pack * R_bus_total      # terminal voltage
        Vg_full = np.repeat(V_g, P)
        I = a - Vg_full * b

        # --- heat generation (Bernardi) --------------------------------
        q_cell = I * (U - Vg_full) - I * T_cell * cell.dudt(z)
        q_bus_each = I_pack ** 2 * layout.busbar_R_ohm
        q_bus_total = q_bus_each * net.B

        # --- implicit thermal step -------------------------------------
        src = net.s.copy()
        src[net.i_core] += q_cell
        src[net.i_bus] += q_bus_each
        T = lu.solve(net.C / dt * T + src)

        # --- electrical state advance ----------------------------------
        v1 = v1 * e1 + I * R1 * (1 - e1)
        v2 = v2 * e2 + I * R2 * (1 - e2)
        z = z - I * dt / (3600.0 * cap_Ah * cell.capacity_factor(T_cell))
        energy_Wh += V_pack * I_pack * dt / 3600.0

        if k in keep:
            rec["t"].append(k * dt)
            rec["Tcore"].append(T[net.i_core] - 273.15)
            rec["Tcan"].append(T[net.i_can] - 273.15)
            rec["Tbus"].append(T[net.i_bus] - 273.15)
            rec["Tcool"].append(T[net.i_cool] - 273.15 if net.M
                                else np.zeros(1))
            rec["Tair"].append(T[net.i_air] - 273.15)
            rec["I"].append(I.copy()); rec["z"].append(z.copy())
            rec["q"].append(q_cell.copy())
            rec["Ip"].append(I_pack); rec["Vp"].append(V_pack)
            rec["qtot"].append(float(q_cell.sum()) + q_bus_total)
            rec["qbus"].append(q_bus_total); rec["E"].append(energy_Wh)

        if float(np.min(V_g)) < group_v_cutoff:
            reason = f"group voltage cutoff at t={k*dt:.0f}s"; break
        if float(np.min(z)) <= 0.02:
            reason = f"SOC exhausted at t={k*dt:.0f}s"; break

    return SimResult(
        t=np.array(rec["t"]), T_core_C=np.array(rec["Tcore"]),
        T_can_C=np.array(rec["Tcan"]), T_bus_C=np.array(rec["Tbus"]),
        T_cool_C=np.array(rec["Tcool"]), T_air_C=np.array(rec["Tair"]),
        I_cell=np.array(rec["I"]), soc=np.array(rec["z"]),
        q_cell=np.array(rec["q"]), I_pack=np.array(rec["Ip"]),
        V_pack=np.array(rec["Vp"]), q_total=np.array(rec["qtot"]),
        q_busbar=np.array(rec["qbus"]), energy_out_Wh=np.array(rec["E"]),
        hydraulics=net.hydraulics_info, stopped_reason=reason)


# ============================================================================
#  8.  POST-PROCESSING
# ============================================================================

def summarise(res: SimResult, layout: PackLayout, label: str = "") -> dict:
    Tend = res.T_core_C[-1]
    return dict(
        label=label,
        t_end_s=float(res.t[-1]),
        T_max_C=float(res.T_core_C.max()),
        T_max_final_C=float(Tend.max()),
        T_min_final_C=float(Tend.min()),
        T_spread_K=float(Tend.max() - Tend.min()),
        T_mean_final_C=float(Tend.mean()),
        T_busbar_max_C=float(res.T_bus_C.max()),
        coolant_out_C=float(res.T_cool_C[-1].max()),
        core_can_gradient_K=float((res.T_core_C[-1] - res.T_can_C[-1]).max()),
        q_mean_W=float(res.q_total.mean()),
        q_peak_W=float(res.q_total.max()),
        q_busbar_frac=float(res.q_busbar.mean() / max(1e-9, res.q_total.mean())),
        I_hog_ratio=hog_ratio(res, layout),
        soc_spread_final_pct=float(100 * (res.soc[-1].max() -
                                          res.soc[-1].min())),
        energy_Wh=float(res.energy_out_Wh[-1]),
        reason=res.stopped_reason)


def hog_ratio(res: SimResult, layout: PackLayout) -> float:
    """max/mean cell current within a parallel group, time-averaged.
    1.00 = perfect sharing.  1.15 = worst cell carries 15% more current and
    therefore ~32% more ohmic heat than its group average."""
    S, P = layout.n_series, layout.n_parallel
    I = res.I_cell.reshape(len(res.t), S, P)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.abs(I).max(axis=2) / np.maximum(1e-9, np.abs(I).mean(axis=2))
    return float(np.nanmean(r[len(r) // 4:]))


def temperature_grid(res: SimResult, layout: PackLayout, t_index: int = -1):
    return res.T_core_C[t_index].reshape(layout.n_series, layout.n_parallel)


def greedy_sensor_placement(res: SimResult, layout: PackLayout, n_sensors: int,
                            candidate_stride: int = 1):
    """Choose thermistor positions that best predict the pack maximum.

    ENERGY_REQ_67/_68 require showing a temperature to the pilot and warning
    at 90% of maximum.  With N sensors on 552 cells you are ESTIMATING that
    maximum, and where you put them decides how wrong you are.

    Greedy forward selection minimising RMS error of a least-squares linear
    estimator of max(T_core) built from the chosen CAN temperatures.
    Returns (cell_indices, [(row, col), ...], rms_error_after_each_pick)."""
    X, y = res.T_can_C, res.T_core_C.max(axis=1)
    n_t, n_c = X.shape
    cands = list(range(0, n_c, candidate_stride))
    chosen, errors = [], []
    for _ in range(n_sensors):
        best_j, best_err = None, np.inf
        for j in cands:
            if j in chosen:
                continue
            A = np.column_stack([X[:, chosen + [j]], np.ones(n_t)])
            coef, *_ = np.linalg.lstsq(A, y, rcond=None)
            err = float(np.sqrt(np.mean((A @ coef - y) ** 2)))
            if err < best_err:
                best_err, best_j = err, j
        chosen.append(best_j); errors.append(best_err)
    return chosen, [(int(layout.row[c]), int(layout.col[c]))
                    for c in chosen], errors
