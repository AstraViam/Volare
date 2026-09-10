r"""
volare_thermal.geometry
=======================

3D pack geometry: arbitrary cell placement, arbitrary tube routing.

THE CENTRAL ABSTRACTION
-----------------------
A tube is no longer "a thing that lives in a row gap".  It is a **polyline in
3D** -- a list of waypoints -- discretised into segments.  A cell couples to
a tube segment if it is within reach of it, with a conductance that falls off
with distance.  Everything else follows:

  * serpentine, spiral, cross-layer, U-bend, manifold-and-rail -- all just
    different waypoint lists
  * cells can sit anywhere, in any number of layers, in any outline
  * you can import a hull-constrained outline and pack cells into it

WHAT 3D ADDS THAT 2D CANNOT SEE
-------------------------------
1. **Interior layers are trapped.**  In a stack, only the top and bottom
   layers see enclosure air.  A middle layer can only reject heat sideways or
   into a tube in its own plane.  If you put tubes in every second LAYER the
   way you might put them in every second row, the middle layer cooks.
2. **Vertical coupling is weak and anisotropic.**  Stacked cells meet
   end-to-end through busbar + insulator, typically 0.02-0.10 W/K -- an order
   of magnitude worse than a potted side-to-side contact (~0.6 W/K).  Heat
   does not travel between layers.  Treat each layer as thermally almost
   independent and cool it on its own merits.
3. **Height is free real estate for tubes.**  A tube in the inter-LAYER gap
   touches cells above and below it, so it works two layers at once.

COORDINATE CONVENTION
---------------------
x, y  = in-plane (cell axes are parallel to z)
z     = stack direction, layer 0 at z = 0
All lengths in metres.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field


# ============================================================================
#  TUBE PATHS
# ============================================================================

@dataclass
class TubePath:
    """A coolant tube as a polyline in 3D.

    waypoints : (n, 3) array of metres.  The tube runs through them in order.
    circuit   : which parallel hydraulic circuit this tube belongs to.
    seg_len   : target discretisation length; smaller resolves the coolant
                temperature rise along the tube more finely.
    """
    waypoints: np.ndarray
    circuit: int = 0
    seg_len: float = 0.025

    def __post_init__(self):
        self.waypoints = np.asarray(self.waypoints, dtype=float)
        if self.waypoints.ndim != 2 or self.waypoints.shape[1] != 3:
            raise ValueError("waypoints must be (n, 3)")
        self._discretise()

    def _discretise(self):
        pts, lens = [], []
        for a, b in zip(self.waypoints[:-1], self.waypoints[1:]):
            d = np.linalg.norm(b - a)
            n = max(1, int(round(d / self.seg_len)))
            for k in range(n):
                t0, t1 = k / n, (k + 1) / n
                pts.append((a + (b - a) * (t0 + t1) / 2))
                lens.append(d / n)
        self.seg_centres = np.array(pts) if pts else np.zeros((0, 3))
        self.seg_lengths = np.array(lens) if lens else np.zeros(0)
        self.length = float(self.seg_lengths.sum())
        self.n_segments = len(self.seg_lengths)

    @property
    def n_bends(self) -> int:
        return max(0, len(self.waypoints) - 2)


# --- builders for common routings -------------------------------------------

def serpentine_in_plane(x0, x1, ys, z, circuit=0, seg_len=0.025):
    """Boustrophedon: run along x at each y in `ys`, reversing each pass."""
    wp = []
    for i, y in enumerate(ys):
        a, b = (x0, x1) if i % 2 == 0 else (x1, x0)
        wp.append([a, y, z])
        wp.append([b, y, z])
    return TubePath(np.array(wp), circuit, seg_len)


def straight_run(x0, x1, y, z, circuit=0, seg_len=0.025):
    return TubePath(np.array([[x0, y, z], [x1, y, z]]), circuit, seg_len)


def build_layer_tubes(x0, x1, y_positions, z, n_circuits,
                      interleave=True, counterflow=True, seg_len=0.025):
    """Group `y_positions` into `n_circuits` serpentine circuits.

    interleave  : circuit c takes every n_circuits-th y (spreads each circuit
                  across the pack instead of giving it one contiguous block)
    counterflow : reverse the pass order of odd circuits, so neighbouring
                  circuits run in opposite directions and the inlet-to-outlet
                  gradient of one is cancelled by the other
    """
    n_circuits = int(np.clip(n_circuits, 1, max(1, len(y_positions))))
    tubes = []
    for c in range(n_circuits):
        ys = ([y for i, y in enumerate(y_positions) if i % n_circuits == c]
              if interleave else
              [y for i, y in enumerate(y_positions)
               if i * n_circuits // max(1, len(y_positions)) == c])
        if not ys:
            continue
        if counterflow and c % 2:
            ys = ys[::-1]
        tubes.append(serpentine_in_plane(x0, x1, ys, z, c, seg_len))
    return tubes


# ============================================================================
#  CELL ARRAYS
# ============================================================================

def grid_layer(n_x, n_y, pitch_x, pitch_y, z=0.0, stagger=False,
               mask=None, origin=(0.0, 0.0)):
    """Rectangular or hex-staggered grid of cell centres in one layer."""
    pts = []
    for j in range(n_y):
        off = 0.5 * pitch_x if (stagger and j % 2) else 0.0
        for i in range(n_x):
            if mask is not None and not mask(i, j):
                continue
            pts.append([origin[0] + i * pitch_x + off,
                        origin[1] + j * pitch_y, z])
    return np.array(pts)


def pack_into_outline(outline_xy, pitch_x, pitch_y, z=0.0, stagger=True,
                      margin=0.0):
    """Fill an arbitrary closed 2D outline with cells on a lattice.

    outline_xy : (n, 2) polygon vertices, metres.
    Use this to pack cells into a hull-constrained footprint rather than
    assuming a rectangle.
    """
    poly = np.asarray(outline_xy, dtype=float)
    xmin, ymin = poly.min(axis=0) + margin
    xmax, ymax = poly.max(axis=0) - margin
    n_x = max(1, int((xmax - xmin) / pitch_x) + 1)
    n_y = max(1, int((ymax - ymin) / pitch_y) + 1)
    cand = grid_layer(n_x, n_y, pitch_x, pitch_y, z, stagger,
                      origin=(xmin, ymin))
    keep = np.array([_point_in_poly(p[0], p[1], poly) for p in cand])
    return cand[keep]


def _point_in_poly(x, y, poly):
    n, inside = len(poly), False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


# ============================================================================
#  PACK GEOMETRY
# ============================================================================

@dataclass
class PackGeometry:
    """Full 3D pack: cell positions, electrical wiring, tube routing.

    This is what ThermalNetwork consumes.  Build it directly for arbitrary
    geometry, or use `PackLayout` in pack_thermal.py for the common
    stacked-grid case.
    """
    positions: np.ndarray                  # (N, 3) cell centres
    series_index: np.ndarray               # (N,) which series group
    tubes: list = field(default_factory=list)

    # --- cell geometry (must match CellParams) -------------------------
    cell_diameter_m: float = 0.02155
    cell_height_m: float = 0.07015

    # --- conduction parameters ------------------------------------------
    gap_filler_k_WmK: float = 1.5          # potting between cells, in-plane
    gap_contact_frac: float = 0.16         # effective in-plane contact area
    G_layer_WK: float = 0.05               # VERTICAL cell-to-cell (weak!)
    R_can_tubewall_KW: float = 2.5         # bond + wall, excl. convection
    tube_id_m: float = 0.006
    tube_contact_reach: float = 1.35       # multiples of (r_cell + r_tube)

    G_can_busbar_WK: float = 0.015
    busbar_mass_kg: float = 0.45
    busbar_cp_J_kgK: float = 385.0
    busbar_R_ohm: float = 7.0e-5
    busbar_cooled: bool = False
    R_busbar_coolant_KW: float = 2.0

    h_internal_WmK: float = 6.0
    enclosure_air_volume_m3: float = 0.05
    enclosure_UA_WK: float = 3.0

    def __post_init__(self):
        self.positions = np.asarray(self.positions, dtype=float)
        self.series_index = np.asarray(self.series_index, dtype=int)
        self.n_cells = len(self.positions)
        if len(self.series_index) != self.n_cells:
            raise ValueError("series_index length must match positions")
        self.n_series = int(self.series_index.max()) + 1
        counts = np.bincount(self.series_index, minlength=self.n_series)
        if counts.min() != counts.max():
            raise ValueError(
                f"parallel groups must be equal size; got {counts.min()}"
                f"..{counts.max()}. Every series group carries the same pack "
                "current, so unequal groups are an electrical error.")
        self.n_parallel = int(counts[0])

        # parallel index within each group, in position order
        self.parallel_index = np.zeros(self.n_cells, dtype=int)
        seen = np.zeros(self.n_series, dtype=int)
        for i, s in enumerate(self.series_index):
            self.parallel_index[i] = seen[s]
            seen[s] += 1
        # solver expects cells ordered group-major
        self.order = np.lexsort((self.parallel_index, self.series_index))
        self.inv_order = np.argsort(self.order)

        self.x, self.y, self.z = self.positions.T
        self.layer_id = self._infer_layers()
        self.n_layers = int(self.layer_id.max()) + 1
        self._build_adjacency()
        self._build_coolant()

    # -- layers -----------------------------------------------------------
    def _infer_layers(self):
        zs = np.unique(np.round(self.z, 6))
        return np.searchsorted(zs, np.round(self.z, 6))

    # -- adjacency --------------------------------------------------------
    def _build_adjacency(self):
        """In-plane and vertical neighbour pairs, with separate conductances.

        In-plane: side-to-side through potting, good (~0.6 W/K).
        Vertical: end-to-end through busbar + insulator, poor (~0.05 W/K).
        Treating these as the same number is the single biggest error you can
        make in a stacked pack.
        """
        P = self.positions
        d_xy = np.linalg.norm(P[:, None, :2] - P[None, :, :2], axis=-1)
        d_z = np.abs(P[:, None, 2] - P[None, :, 2])
        iu, ju = np.triu_indices(self.n_cells, k=1)
        dxy, dz = d_xy[iu, ju], d_z[iu, ju]

        inplane_cut = 1.30 * self.cell_diameter_m
        same_layer = dz < 1e-6
        m_in = same_layer & (dxy < inplane_cut)

        vert_cut = 1.6 * self.cell_height_m
        m_vt = (~same_layer) & (dz < vert_cut) & \
               (dxy < 0.6 * self.cell_diameter_m)

        pairs = np.column_stack([np.r_[iu[m_in], iu[m_vt]],
                                 np.r_[ju[m_in], ju[m_vt]]])
        gap = np.maximum(1e-4, dxy[m_in] - self.cell_diameter_m)
        A_eff = self.gap_contact_frac * np.pi * self.cell_diameter_m * \
            self.cell_height_m
        g_in = self.gap_filler_k_WmK * A_eff / gap
        g_vt = np.full(m_vt.sum(), self.G_layer_WK)

        self.neighbour_pairs = pairs
        self.neighbour_G = np.r_[g_in, g_vt]
        self.n_inplane_pairs = int(m_in.sum())
        self.n_vertical_pairs = int(m_vt.sum())

        # exposure to enclosure air: a cell buried in the stack sees none
        cnt_in = np.zeros(self.n_cells)
        np.add.at(cnt_in, pairs[:self.n_inplane_pairs, 0], 1)
        np.add.at(cnt_in, pairs[:self.n_inplane_pairs, 1], 1)
        self.n_neighbours = cnt_in
        lateral = np.clip(1.0 - cnt_in / 6.0, 0.02, 1.0)
        # end faces: only outer layers can see air through their ends
        cnt_vt = np.zeros(self.n_cells)
        np.add.at(cnt_vt, pairs[self.n_inplane_pairs:, 0], 1)
        np.add.at(cnt_vt, pairs[self.n_inplane_pairs:, 1], 1)
        ends_free = np.clip(1.0 - cnt_vt / 2.0, 0.0, 1.0)
        self.exposed_frac = lateral
        self.end_exposed_frac = ends_free

    # -- coolant ----------------------------------------------------------
    def _build_coolant(self):
        """Chain tube segments into circuits and couple cells by distance."""
        centres, lengths, circ, upstream = [], [], [], []
        sid = 0
        self.circuit_paths = {}
        for tube in self.tubes:
            prev = self.circuit_paths.get(tube.circuit, [None])[-1] \
                if tube.circuit in self.circuit_paths else None
            path = self.circuit_paths.setdefault(tube.circuit, [])
            for k in range(tube.n_segments):
                centres.append(tube.seg_centres[k])
                lengths.append(tube.seg_lengths[k])
                circ.append(tube.circuit)
                upstream.append(prev if prev is not None else -1)
                prev = sid
                path.append(sid)
                sid += 1
        self.n_coolant_segs = sid
        self.seg_centres = np.array(centres) if sid else np.zeros((0, 3))
        self.seg_lengths = np.array(lengths) if sid else np.zeros(0)
        self.coolant_seg_circuit = np.array(circ, dtype=int) if sid else \
            np.zeros(0, dtype=int)
        self.upstream = np.array(upstream, dtype=int) if sid else \
            np.zeros(0, dtype=int)
        self.n_circuits_eff = (len(set(circ)) if sid else 1)

        # cell <-> segment coupling by proximity
        reach = self.tube_contact_reach * \
            (self.cell_diameter_m / 2 + self.tube_id_m / 2)
        pairs, weights = [], []
        if sid:
            d = np.linalg.norm(self.positions[:, None, :] -
                               self.seg_centres[None, :, :], axis=-1)
            ii, ss = np.where(d < reach)
            for i, s in zip(ii, ss):
                # linear falloff: full contact at touching, zero at reach
                touch = self.cell_diameter_m / 2 + self.tube_id_m / 2
                w = np.clip((reach - d[i, s]) / max(1e-9, reach - touch),
                            0.0, 1.0)
                if w > 0.02:
                    pairs.append((i, s))
                    weights.append(w)
        self.cell_coolant_pairs = (np.array(pairs, dtype=int) if pairs
                                   else np.zeros((0, 2), dtype=int))
        self.cell_coolant_weight = (np.array(weights) if weights
                                    else np.zeros(0))
        touched = np.zeros(self.n_cells)
        for (i, _), w in zip(self.cell_coolant_pairs, self.cell_coolant_weight):
            touched[i] += w
        self.tube_contact_score = touched
        self.frac_cells_tube_cooled = float(np.mean(touched > 0.05))

    # -- reporting helpers -------------------------------------------------
    @property
    def row(self):
        return self.series_index

    @property
    def col(self):
        return self.parallel_index

    def uncooled_cells(self, threshold=0.05):
        return np.where(self.tube_contact_score <= threshold)[0]

    def layer_grid(self, values, layer=0, n_x=None, n_y=None):
        """Reshape a per-cell array into a 2D image for one layer."""
        m = self.layer_id == layer
        xs, ys = self.x[m], self.y[m]
        ux, uy = np.unique(np.round(xs, 6)), np.unique(np.round(ys, 6))
        g = np.full((len(uy), len(ux)), np.nan)
        for v, xx, yy in zip(values[m], xs, ys):
            i = np.searchsorted(uy, round(yy, 6))
            j = np.searchsorted(ux, round(xx, 6))
            g[i, j] = v
        return g

    def total_tube_length(self):
        return float(sum(t.length for t in self.tubes))

    def cooling_mass_kg(self, coolant_rho=1050.0, tube_wall_kg_per_m=0.055):
        """Tube wall + contained coolant + a manifold allowance per circuit."""
        L = self.total_tube_length()
        a = np.pi * (self.tube_id_m / 2) ** 2
        return (L * tube_wall_kg_per_m + L * a * coolant_rho
                + 0.18 * self.n_circuits_eff)

    def summary(self) -> dict:
        return dict(
            n_cells=self.n_cells, n_series=self.n_series,
            n_parallel=self.n_parallel, n_layers=self.n_layers,
            n_tubes=len(self.tubes), n_circuits=self.n_circuits_eff,
            n_coolant_segments=self.n_coolant_segs,
            tube_length_m=round(self.total_tube_length(), 3),
            cooling_mass_kg=round(self.cooling_mass_kg(), 3),
            inplane_pairs=self.n_inplane_pairs,
            vertical_pairs=self.n_vertical_pairs,
            frac_tube_cooled=round(self.frac_cells_tube_cooled, 3),
            n_uncooled=len(self.uncooled_cells()),
            envelope_mm=[round(1000 * (self.x.max() - self.x.min() +
                                       self.cell_diameter_m), 1),
                         round(1000 * (self.y.max() - self.y.min() +
                                       self.cell_diameter_m), 1),
                         round(1000 * (self.z.max() - self.z.min() +
                                       self.cell_height_m), 1)])


# ============================================================================
#  STACKED-GRID BUILDER  (the common case, in 3D)
# ============================================================================

def stacked_grid_pack(n_series=26, n_parallel=21, n_layers=1,
                      pitch_x=0.0235, pitch_y=0.0235, layer_gap=0.010,
                      stagger=False, tube_every=2, n_circuits=3,
                      interleave=True, counterflow=True,
                      interlayer_tubes=False, seg_len=0.025,
                      wiring="row", **geom_kw) -> PackGeometry:
    """Build a stacked grid pack with in-plane serpentine cooling.

    n_layers splits the SERIES groups across layers, e.g. 26S over 2 layers
    = 13 rows per layer.  Each row remains one parallel group.

    wiring : 'row'      -- each row of each layer is one parallel group
             'column'   -- each column is one parallel group (transposed)

    interlayer_tubes : also run tubes in the gaps BETWEEN layers, where they
                       touch cells above and below and so cool two layers at
                       once.  Only meaningful for n_layers > 1.
    """
    if n_series % n_layers:
        raise ValueError(f"n_layers={n_layers} must divide n_series={n_series}")
    rows_per_layer = n_series // n_layers
    cell_h = geom_kw.get("cell_height_m", 0.07015)

    pos, ser = [], []
    for L in range(n_layers):
        z = L * (cell_h + layer_gap)
        for r in range(rows_per_layer):
            s = L * rows_per_layer + r
            off = 0.5 * pitch_x if (stagger and r % 2) else 0.0
            for c in range(n_parallel):
                pos.append([c * pitch_x + off, r * pitch_y, z])
                ser.append(s)
    pos = np.array(pos)
    ser = np.array(ser)

    if wiring == "column":
        ser = np.array([(p[2] > 0) * 0 for p in pos])  # placeholder
        raise NotImplementedError("column wiring not yet implemented")

    x0, x1 = pos[:, 0].min(), pos[:, 0].max()
    tubes, c0 = [], 0
    for L in range(n_layers):
        z = L * (cell_h + layer_gap)
        ys = [g * pitch_y + pitch_y / 2
              for g in range(rows_per_layer - 1) if g % tube_every == 0]
        # never orphan the last row: if it is not reached, add a final tube
        if ys and (rows_per_layer - 1) * pitch_y - ys[-1] > 0.75 * pitch_y:
            ys.append((rows_per_layer - 1) * pitch_y - pitch_y / 2)
        if not ys:
            ys = [(rows_per_layer - 1) * pitch_y / 2]
        lt = build_layer_tubes(x0, x1, ys, z, n_circuits, interleave,
                               counterflow, seg_len)
        for t in lt:
            t.circuit += c0
        tubes.extend(lt)
        c0 += max(1, len(set(t.circuit for t in lt)))

    if interlayer_tubes and n_layers > 1:
        for L in range(n_layers - 1):
            z = L * (cell_h + layer_gap) + cell_h + layer_gap / 2
            ys = [g * pitch_y for g in range(0, rows_per_layer, 2)]
            lt = build_layer_tubes(x0, x1, ys, z, n_circuits, interleave,
                                   counterflow, seg_len)
            for t in lt:
                t.circuit += c0
            tubes.extend(lt)
            c0 += max(1, len(set(t.circuit for t in lt)))

    return PackGeometry(positions=pos, series_index=ser, tubes=tubes,
                        **geom_kw)


# ============================================================================
#  MODULES  --  move blocks of cells around as rigid units
# ============================================================================

@dataclass
class Module:
    """A rigid block of cells you can place and rotate as a unit.

    This is the abstraction you want when the pack has to fit around a
    stringer, a bulkhead, or the pilot's feet: design one module, then place
    several of them at arbitrary positions and yaw angles.

        rows x cols cells at the given pitch, origin at the module's own
        (0,0,0), placed at `origin` and rotated `yaw_deg` about z.

    series_offset : which series group the module's first row maps to.
                    Modules can share series groups (a group split across two
                    modules) or own them exclusively -- both are legal, but a
                    split group needs a busbar bridging the two modules, and
                    that busbar carries the FULL pack current. Prefer whole
                    groups per module unless you have a reason not to.
    """
    rows: int
    cols: int
    origin: tuple = (0.0, 0.0, 0.0)
    yaw_deg: float = 0.0
    pitch_x: float = 0.0235
    pitch_y: float = 0.0235
    stagger: bool = False
    series_offset: int = 0
    name: str = "module"

    def cell_positions(self):
        pts = []
        for r in range(self.rows):
            off = 0.5 * self.pitch_x if (self.stagger and r % 2) else 0.0
            for c in range(self.cols):
                pts.append([c * self.pitch_x + off, r * self.pitch_y, 0.0])
        p = np.array(pts)
        a = np.radians(self.yaw_deg)
        Rz = np.array([[np.cos(a), -np.sin(a), 0],
                       [np.sin(a), np.cos(a), 0], [0, 0, 1.0]])
        return p @ Rz.T + np.asarray(self.origin, float)

    def series_index(self):
        return np.repeat(np.arange(self.rows) + self.series_offset, self.cols)

    def footprint(self, cell_d=0.02155):
        p = self.cell_positions()
        return dict(name=self.name, cells=self.rows * self.cols,
                    x_mm=[round(1000 * (p[:, 0].min() - cell_d / 2), 1),
                          round(1000 * (p[:, 0].max() + cell_d / 2), 1)],
                    y_mm=[round(1000 * (p[:, 1].min() - cell_d / 2), 1),
                          round(1000 * (p[:, 1].max() + cell_d / 2), 1)],
                    z_mm=round(1000 * p[0, 2], 1))


def modules_to_geometry(modules, tubes=None, auto_tube=True, tube_every=2,
                        n_circuits=3, counterflow=True, seg_len=0.025,
                        **geom_kw) -> PackGeometry:
    """Assemble Modules into one PackGeometry.

    With auto_tube=True, a serpentine circuit is generated per module in its
    own local frame and then rotated with it, so rotated modules keep sensible
    cooling. Pass `tubes` explicitly to override.
    """
    pos = np.vstack([m.cell_positions() for m in modules])
    ser = np.concatenate([m.series_index() for m in modules])

    if tubes is None and auto_tube:
        tubes, c0 = [], 0
        for m in modules:
            a = np.radians(m.yaw_deg)
            Rz = np.array([[np.cos(a), -np.sin(a), 0],
                           [np.sin(a), np.cos(a), 0], [0, 0, 1.0]])
            x0, x1 = -0.5 * m.pitch_x, (m.cols - 0.5) * m.pitch_x
            ys = [g * m.pitch_y + m.pitch_y / 2
                  for g in range(m.rows - 1) if g % tube_every == 0]
            if ys and (m.rows - 1) * m.pitch_y - ys[-1] > 0.75 * m.pitch_y:
                ys.append((m.rows - 1) * m.pitch_y - m.pitch_y / 2)
            if not ys:
                ys = [(m.rows - 1) * m.pitch_y / 2]
            local = build_layer_tubes(x0, x1, ys, 0.0, n_circuits, True,
                                      counterflow, seg_len)
            for t in local:
                t.waypoints = t.waypoints @ Rz.T + np.asarray(m.origin, float)
                t._discretise()
                t.circuit += c0
                tubes.append(t)
            c0 += max(1, len(set(t.circuit for t in local)))

    return PackGeometry(positions=pos, series_index=ser,
                        tubes=tubes or [], **geom_kw)


def check_module_clearance(modules, cell_d=0.02155, min_gap_mm=3.0):
    """Warn about modules whose cells physically overlap or nearly touch."""
    issues = []
    for a in range(len(modules)):
        for b in range(a + 1, len(modules)):
            pa, pb = modules[a].cell_positions(), modules[b].cell_positions()
            if abs(pa[0, 2] - pb[0, 2]) > 1e-6:
                continue
            d = np.linalg.norm(pa[:, None, :2] - pb[None, :, :2], axis=-1)
            gap = (d.min() - cell_d) * 1000
            if gap < min_gap_mm:
                issues.append(dict(a=modules[a].name, b=modules[b].name,
                                   gap_mm=round(float(gap), 2),
                                   overlapping=gap < 0))
    return issues



# ============================================================================
#  MANIFOLD FLOW DISTRIBUTION
# ============================================================================

def manifold_split(n_circuits, circuit_lengths_m, tube_id_m, coolant,
                   total_flow_L_min, header_id_m=0.016,
                   takeoff_spacing_m=0.045, takeoff_loss_K=1.8,
                   config="U", iters=400, damping=0.35):
    r"""Solve how the flow ACTUALLY divides between parallel circuits.

    THE FAILURE MODE THIS EXPOSES
    -----------------------------
    Everything else in this project assumes flow splits equally between
    circuits. Real manifolds do not: the supply header loses static pressure
    along its length as fluid is drawn off, so the far circuits see less
    driving pressure and run starved. A starved circuit is a hot region that
    appears NOWHERE in the temperature output, because the solver was told it
    had design flow.

    METHOD
    ------
    Every branch connects the supply header to the return header at its own
    take-off, so it sees a local pressure difference

        dP_i = P_supply(i) - P_return(i)

    and its own resistance sets the flow that difference produces. Iterate:
    guess the branch flows, build both header pressure profiles from them,
    re-solve each branch against its local dP, renormalise to conserve mass,
    repeat under damping until it stops moving.

    config : "U" supply and return at the SAME end (worst distribution)
             "Z" return at the far end, which self-compensates and is almost
                 always the better plumbing choice.
    """
    rho, mu = coolant.rho_kg_m3, coolant.mu_Pa_s
    A_t = np.pi * (tube_id_m / 2) ** 2
    A_h = np.pi * (header_id_m / 2) ** 2
    m_tot = total_flow_L_min / 60000.0 * rho
    L = np.asarray(circuit_lengths_m, float)
    n = len(L)
    if n <= 1:
        return dict(flows_L_min=[total_flow_L_min], ratio=1.0, starved=0,
                    mean_L_min=total_flow_L_min, worst_deficit_pct=0.0,
                    dP_bar=0.0, config=config, note="single circuit")

    def darcy(m, d, A, length):
        v = np.abs(np.asarray(m, float)) / (rho * A)
        Re = np.maximum(rho * v * d / mu, 1e-6)
        f = np.where(Re < 2300, 64.0 / Re, 0.316 * Re ** -0.25)
        return f * length / d * 0.5 * rho * v * v

    def branch_R(m):
        """dP across a branch for flow m."""
        v = np.abs(np.asarray(m, float)) / (rho * A_t)
        Re = np.maximum(rho * v * tube_id_m / mu, 1e-6)
        f = np.where(Re < 2300, 64.0 / Re, 0.316 * Re ** -0.25)
        return (f * L / tube_id_m + takeoff_loss_K) * 0.5 * rho * v * v

    m = np.full(n, m_tot / n)
    for _ in range(iters):
        # --- supply header: carries the flow not yet drawn off ---
        carried_s = m_tot - np.concatenate([[0.0], np.cumsum(m)[:-1]])
        dp_s = np.cumsum(darcy(carried_s, header_id_m, A_h, takeoff_spacing_m))
        # velocity head recovered as the header slows
        v_s = carried_s / (rho * A_h)
        recov = 0.5 * rho * (v_s[0] ** 2 - v_s ** 2)
        P_s = -dp_s + recov
        # --- return header ---
        if config == "Z":
            carried_r = np.cumsum(m)               # grows toward the far end
        else:
            carried_r = np.cumsum(m[::-1])[::-1]   # grows back toward the inlet
        dp_r = np.cumsum(darcy(carried_r, header_id_m, A_h, takeoff_spacing_m))
        P_r = dp_r
        avail = P_s - P_r
        avail = avail - avail.min() + branch_R(m).mean()   # anchor the datum

        # --- re-solve each branch against its own available pressure ---
        base = branch_R(m)
        # dP ~ m^2 in turbulent, m in laminar; sqrt is a safe compromise and
        # the damping below handles the difference
        m_new = m * np.sqrt(np.maximum(avail, 1e-9) / np.maximum(base, 1e-9))
        m_new = np.maximum(m_new, 1e-9)
        m_new *= m_tot / m_new.sum()
        step = m_new - m
        m = m + damping * step
        if np.max(np.abs(step)) / max(m_tot / n, 1e-12) < 1e-7:
            break

    flows = m / rho * 60000.0
    return dict(flows_L_min=[float(v) for v in flows],
                ratio=float(flows.max() / max(flows.min(), 1e-9)),
                starved=int(np.argmin(flows)),
                mean_L_min=float(flows.mean()),
                worst_deficit_pct=float((1 - flows.min() / flows.mean()) * 100),
                dP_bar=float(branch_R(m).max() / 1e5),
                config=config)
