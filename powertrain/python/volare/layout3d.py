r"""
volare.layout3d
===============

Two-layer pack geometry with END-PLATE (axial) cooling.

This replaces the flat 26x21 ``PackLayout`` for the pack the team is actually
building, while presenting the *same interface* to the solver in
``pack_thermal.py`` -- same attribute names, same array shapes, same
conductance methods. The validated electro-thermal solver consumes it
unchanged, so the physics is not re-implemented and cannot drift.

THE GEOMETRY
------------
26 series groups of 21 cells, arranged as::

    2 layers  x  13 groups per layer
    each group: 3 rows (y) x 7 columns (x)
    groups placed in a 4 x 4 slot grid, 13 filled, 3 left for BMS/contactor

Group numbering follows a serpentine so that G(n) and G(n+1) are always
physically adjacent, and layer 2 is traversed so its first group sits directly
above the last group of layer 1. This mirrors the MATLAB ``P50B_GroupLayout``
exactly -- both models must describe the same pack.

WHY END COOLING, NOT SIDE COOLING
---------------------------------
The flat model put coolant tubes in the inter-row gaps. That cannot be done
here, and the reason is worth stating precisely because it is a geometric
fact, not a preference:

* Inside a group the cell-to-cell edge gap is **2.0 mm**. A 6 mm tube does
  not fit.
* Only the **12 mm inter-group gaps** could take a tube, and a tube there
  reaches just the outer row of each 3-row group.
* That would leave the **centre row of all 26 groups** with no adjacent tube
  -- 182 of 546 cells.

That is the orphaned-row failure mode from the flat study, except affecting a
third of the pack rather than a single row. The flat study measured an orphan
edge row at 3.9 K; a third of the pack orphaned would be far worse.

The two-layer geometry offers something better instead. A cylindrical cell
conducts roughly 30x better along its winding axis (25 W/m.K) than across it
(0.85 W/m.K), and the stack already has three natural plate planes: below
layer 1, between the layers, above layer 2. Cooling the cell **ends** uses the
good conduction path and reaches every cell equally. No cell can be orphaned,
because every cell has two end faces and every end face touches a plate.

The interlayer plate serves both layers, so it carries roughly twice the duty
of the outer plates -- that asymmetry is modelled, not averaged away.

WHAT IS CARRIED OVER FROM THE FLAT MODEL
----------------------------------------
Everything that was not specific to tubes-in-row-gaps:

* serpentine tubes grouped into parallel hydraulic circuits
* Reynolds number and flow-regime detection
* ``Nu = 3.66`` laminar / Dittus-Boelter turbulent, blended in between
* Darcy-Weisbach pressure drop including bend losses
* coolant advection along the flow path, so the fluid warms as it travels
* counter-flow routing on alternate circuits
* the orphan check -- retained and generalised, even though this architecture
  cannot produce an orphan, because a future geometry change might

See also ``volare.pack_thermal`` for the solver and ``volare.params`` for the
parameter source.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .params import Params, load


# ---------------------------------------------------------------------------
#  Geometry helper
# ---------------------------------------------------------------------------

def _serpentine_slots(grid_rows: int, grid_cols: int,
                      groups_per_layer: int, n_layers: int
                      ) -> List[Tuple[int, int, int]]:
    """Group slot order, mirroring MATLAB ``P50B_GroupLayout``.

    Returns ``[(layer, grid_row, grid_col), ...]`` in series order.

    Layer 1 runs top row to bottom row; layer 2 runs bottom to top, with its
    column direction chosen so the first group of layer 2 lands directly above
    the last group of layer 1. Without that the inter-layer link would have to
    run diagonally across the pack instead of straight up.
    """
    out: List[Tuple[int, int, int]] = []
    last_col = 0

    for layer in range(n_layers):

        start_ascending = True if layer == 0 else (last_col == 0)

        for local_r in range(grid_rows):

            r = local_r if layer == 0 else (grid_rows - 1 - local_r)

            ascend = ((local_r % 2) == 0) == start_ascending
            cols = range(grid_cols) if ascend else range(grid_cols - 1, -1, -1)

            for c in cols:
                if len(out) >= (layer + 1) * groups_per_layer:
                    break
                out.append((layer, r, c))
                last_col = c

    return out


# ---------------------------------------------------------------------------
#  Tube
# ---------------------------------------------------------------------------

@dataclass
class Tube:
    """One serpentine pass inside a cold plate.

    ``seg_centres`` is an (n_seg, 3) array of segment centre points in pack
    coordinates. Mission Control draws these directly, so the plumbing you
    see on screen is the plumbing the solver used -- not a separate drawing
    that can drift out of step with it.
    """

    index: int
    circuit: int
    plate: int
    seg_centres: np.ndarray
    length: float
    n_bends: int


# ---------------------------------------------------------------------------
#  Layout
# ---------------------------------------------------------------------------

@dataclass
class TwoLayerLayout:
    """Two-layer 26S21P pack with end-plate cooling.

    Interface-compatible with ``pack_thermal.PackLayout``.
    """

    # --- topology --------------------------------------------------------
    n_series: int = 26
    n_parallel: int = 21
    n_layers: int = 2
    group_rows: int = 3
    group_cols: int = 7
    grid_rows: int = 4
    grid_cols: int = 4

    # --- geometry --------------------------------------------------------
    cell_diameter_m: float = 0.02155
    cell_height_m: float = 0.07015
    cell_clearance_m: float = 0.0020
    group_clearance_x_m: float = 0.0120
    group_clearance_y_m: float = 0.0120
    layer_gap_m: float = 0.0100

    # --- cooling ---------------------------------------------------------
    tubes_per_plate: int = 8
    n_circuits: int = 3
    interleave_circuits: bool = True
    counter_flow: bool = True
    tube_id_m: float = 0.0060
    n_bends_per_tube: int = 2

    plate_thickness_m: float = 0.0050

    #: Cell end face to plate, through the thermal interface pad.
    R_can_plate_KW: float = 1.20
    #: Plate body to embedded tube wall.
    R_plate_tubewall_KW: float = 0.35
    #: Every cell in this stack-up touches a plate at both ends.
    cell_ends_cooled: int = 2

    # --- cell-to-cell conduction ----------------------------------------
    gap_filler_k_WmK: float = 1.5
    gap_contact_frac: float = 0.16

    # --- enclosure and busbar (interface parity with PackLayout) --------
    G_can_busbar_WK: float = 0.015
    h_internal_WmK: float = 6.0
    enclosure_air_volume_m3: float = 0.05
    enclosure_UA_WK: float = 3.0
    busbar_mass_kg: float = 0.45
    busbar_cp_J_kgK: float = 385.0
    busbar_R_ohm: float = 7.0e-5
    busbar_cooled: bool = False
    R_busbar_coolant_KW: float = 2.0

    # ------------------------------------------------------------------
    def __post_init__(self):
        self.n_cells = self.n_series * self.n_parallel
        self.groups_per_layer = self.n_series // self.n_layers

        if self.group_rows * self.group_cols != self.n_parallel:
            raise ValueError(
                f"group_rows x group_cols = "
                f"{self.group_rows * self.group_cols} but n_parallel is "
                f"{self.n_parallel}.")

        if self.grid_rows * self.grid_cols < self.groups_per_layer:
            raise ValueError(
                f"A {self.grid_rows}x{self.grid_cols} grid cannot hold "
                f"{self.groups_per_layer} groups.")

        # pitch is the same in both axes: square packing
        self.pitch_x_m = self.cell_diameter_m + self.cell_clearance_m
        self.pitch_y_m = self.pitch_x_m

        self.group_width_m = (self.cell_diameter_m +
                              (self.group_cols - 1) * self.pitch_x_m)
        self.group_depth_m = (self.cell_diameter_m +
                              (self.group_rows - 1) * self.pitch_y_m)

        self.group_pitch_x_m = self.group_width_m + self.group_clearance_x_m
        self.group_pitch_y_m = self.group_depth_m + self.group_clearance_y_m

        self.pack_width_m = (self.grid_cols * self.group_width_m +
                             (self.grid_cols - 1) * self.group_clearance_x_m)
        self.pack_depth_m = (self.grid_rows * self.group_depth_m +
                             (self.grid_rows - 1) * self.group_clearance_y_m)
        self.layer_pitch_z_m = self.cell_height_m + self.layer_gap_m

        self._build_positions()
        self._build_wiring()
        self._build_adjacency()
        self._build_coolant()
        self._build_tube_geometry()
        self._build_export_aliases()

    # ------------------------------------------------------------------
    #  Positions
    # ------------------------------------------------------------------

    def _build_positions(self):
        slots = _serpentine_slots(self.grid_rows, self.grid_cols,
                                  self.groups_per_layer, self.n_layers)

        if len(slots) != self.n_series:
            raise RuntimeError(
                f"Placed {len(slots)} groups, expected {self.n_series}.")

        self.group_slot = np.array(slots, dtype=int)     # (26, 3)

        xs, ys, zs = [], [], []
        layer_of_cell, row_in_group, col_in_group = [], [], []

        # centre the array of cells inside its group
        x0 = -0.5 * (self.group_cols - 1) * self.pitch_x_m
        y0 = -0.5 * (self.group_rows - 1) * self.pitch_y_m

        # centre the pack about the origin in x and y
        cx = 0.5 * (self.pack_width_m - self.group_width_m)
        cy = 0.5 * (self.pack_depth_m - self.group_depth_m)

        gx_all, gy_all, gz_all = [], [], []

        for g in range(self.n_series):
            layer, gr, gc = slots[g]

            gx = gc * self.group_pitch_x_m - cx
            gy = gr * self.group_pitch_y_m - cy
            gz = layer * self.layer_pitch_z_m

            gx_all.append(gx)
            gy_all.append(gy)
            gz_all.append(gz)

            for r in range(self.group_rows):
                for c in range(self.group_cols):
                    xs.append(gx + x0 + c * self.pitch_x_m)
                    ys.append(gy + y0 + r * self.pitch_y_m)
                    zs.append(gz)
                    layer_of_cell.append(layer)
                    row_in_group.append(r)
                    col_in_group.append(c)

        self.x = np.array(xs)
        self.y = np.array(ys)
        self.z = np.array(zs)                 # base of the cell body

        self.group_x = np.array(gx_all)
        self.group_y = np.array(gy_all)
        self.group_z = np.array(gz_all)

        self.layer = np.array(layer_of_cell, dtype=int)
        self.cell_row = np.array(row_in_group, dtype=int)
        self.cell_col = np.array(col_in_group, dtype=int)

        # ``row``/``col`` keep the flat-model meaning: series index and
        # position within the parallel group, so solver code that reshapes
        # by (n_series, n_parallel) still works.
        self.row = np.repeat(np.arange(self.n_series), self.n_parallel)
        self.col = np.tile(np.arange(self.n_parallel), self.n_series)

    def _build_wiring(self):
        self.series_index = self.row.copy()
        self.parallel_index = self.col.copy()

    # ------------------------------------------------------------------
    #  Lateral conduction
    # ------------------------------------------------------------------

    def _build_adjacency(self):
        """Cell-to-cell conduction pairs.

        Two regimes, and they differ by more than an order of magnitude:

        * **Within a group** the edge gap is 2 mm of potting, a real
          conduction path.
        * **Between groups** it is 12 mm containing a busbar and air. Weak,
          but not zero, and omitting it would make each group thermally
          independent, which is wrong.

        Layers do not conduct to each other directly: the interlayer plate
        sits between them, so that path goes cell -> plate -> cell and is
        handled by the coolant network.
        """
        pairs: List[Tuple[int, int]] = []
        weights: List[float] = []

        intra_cut = 1.15 * self.pitch_x_m
        inter_cut = 1.15 * max(self.group_pitch_x_m - self.group_width_m
                               + self.pitch_x_m,
                               self.group_pitch_y_m - self.group_depth_m
                               + self.pitch_y_m)

        for layer in range(self.n_layers):
            idx = np.where(self.layer == layer)[0]
            p = np.column_stack([self.x[idx], self.y[idx]])

            d = np.hypot(p[:, 0][:, None] - p[:, 0][None, :],
                         p[:, 1][:, None] - p[:, 1][None, :])

            iu, ju = np.triu_indices(len(idx), k=1)
            dd = d[iu, ju]

            same_group = (self.row[idx][iu] == self.row[idx][ju])

            near = dd <= max(intra_cut, inter_cut)

            for a, b, dist, sg in zip(iu[near], ju[near], dd[near],
                                      same_group[near]):
                gap = max(1e-4, dist - self.cell_diameter_m)
                if sg and dist <= intra_cut:
                    w = 1.0
                elif not sg:
                    # weaker: longer path, and no potting across the
                    # busbar channel
                    w = 0.25 * (self.cell_clearance_m / gap)
                else:
                    continue
                pairs.append((idx[a], idx[b]))
                weights.append(w)

        self.neighbour_pairs = (np.array(pairs, dtype=int) if pairs
                                else np.zeros((0, 2), dtype=int))
        self.neighbour_weight = (np.array(weights, float) if weights
                                 else np.zeros(0))

        counts = np.zeros(self.n_cells)
        if len(self.neighbour_pairs):
            np.add.at(counts, self.neighbour_pairs[:, 0], 1)
            np.add.at(counts, self.neighbour_pairs[:, 1], 1)

        self.n_neighbours = counts

        # Fraction of the can free to exchange with enclosure air. A cell
        # with six neighbours is almost fully shrouded.
        self.exposed_frac = np.clip(1.0 - counts / 6.0, 0.05, 1.0)

    # ------------------------------------------------------------------
    #  Coolant network
    # ------------------------------------------------------------------

    def _build_coolant(self):
        """Serpentine tubes inside three cold plates.

        Plate p lies at the boundary between layer p-1 and layer p:

            plate 0  below layer 0          (base)
            plate 1  between layers 0 and 1 (interlayer, double duty)
            plate 2  above layer 1          (lid)

        Every cell couples to the plate below it and the plate above it, so
        every cell is cooled at both ends. That is the property the flat
        layout could not guarantee.
        """
        self.n_plates = self.n_layers + 1

        self.n_tubes = self.n_plates * self.tubes_per_plate

        self.n_circuits_eff = int(np.clip(self.n_circuits, 1, self.n_tubes))

        # segments along each serpentine pass
        self.n_seg_per_tube = max(2, self.grid_cols * 2)

        # --- assign tubes to circuits ------------------------------------
        if self.interleave_circuits:
            tube_circuit = np.arange(self.n_tubes) % self.n_circuits_eff
        else:
            tube_circuit = (np.arange(self.n_tubes) *
                            self.n_circuits_eff // max(1, self.n_tubes))

        self.tube_circuit = tube_circuit
        self.tube_plate = np.repeat(np.arange(self.n_plates),
                                    self.tubes_per_plate)

        # --- coolant segments --------------------------------------------
        self.coolant_seg_tube: List[int] = []
        self.coolant_seg_circuit: List[int] = []
        seg_id = np.zeros((self.n_tubes, self.n_seg_per_tube), dtype=int)

        sid = 0
        for t in range(self.n_tubes):
            for s in range(self.n_seg_per_tube):
                seg_id[t, s] = sid
                self.coolant_seg_tube.append(t)
                self.coolant_seg_circuit.append(int(tube_circuit[t]))
                sid += 1

        self.n_coolant_segs = sid
        self.coolant_seg_tube = np.array(self.coolant_seg_tube)
        self.coolant_seg_circuit = np.array(self.coolant_seg_circuit)
        self.seg_id = seg_id

        # --- chain segments along each circuit ---------------------------
        self.upstream = -np.ones(self.n_coolant_segs, dtype=int)
        self.circuit_paths: List[List[int]] = []

        for c in range(self.n_circuits_eff):
            tubes_c = [t for t in range(self.n_tubes) if tube_circuit[t] == c]
            path: List[int] = []

            for k, t in enumerate(tubes_c):
                order = list(range(self.n_seg_per_tube))

                # serpentine: alternate passes reverse
                if k % 2 == 1:
                    order = order[::-1]

                # counter-flow: reverse whole alternate circuits
                if self.counter_flow and (c % 2 == 1):
                    order = order[::-1]

                for s in order:
                    path.append(int(seg_id[t, s]))

            for a, b in zip(path[:-1], path[1:]):
                self.upstream[b] = a

            self.circuit_paths.append(path)

        # --- map cells to segments ---------------------------------------
        # A cell couples to the plate beneath it and the plate above it. On
        # each plate it meets the serpentine segment nearest its x position.
        pairs: List[Tuple[int, int]] = []

        # normalised x across the pack, for segment selection
        xspan = max(1e-9, self.x.max() - self.x.min())

        for i in range(self.n_cells):
            frac = (self.x[i] - self.x.min()) / xspan
            s = min(self.n_seg_per_tube - 1,
                    int(frac * self.n_seg_per_tube))

            layer = self.layer[i]

            for plate in (layer, layer + 1):        # below, above
                # pick the tube in this plate whose y band contains the cell
                yfrac = ((self.y[i] - self.y.min()) /
                         max(1e-9, self.y.max() - self.y.min()))
                local_t = min(self.tubes_per_plate - 1,
                              int(yfrac * self.tubes_per_plate))
                t = plate * self.tubes_per_plate + local_t
                pairs.append((i, int(seg_id[t, s])))

        self.cell_coolant_pairs = (np.array(pairs, dtype=int) if pairs
                                   else np.zeros((0, 2), dtype=int))

        touched = np.zeros(self.n_cells)
        if len(self.cell_coolant_pairs):
            np.add.at(touched, self.cell_coolant_pairs[:, 0], 1)

        self.n_tubes_touching = touched
        self.frac_cells_tube_cooled = float(np.mean(touched > 0))

        # --- orphan check ------------------------------------------------
        # Retained from the flat model. This architecture cannot orphan a
        # cell, but a future geometry change might, and a silent orphan is
        # worth several kelvin.
        self.orphaned_cells = np.where(touched == 0)[0]
        self.has_orphans = len(self.orphaned_cells) > 0

    # ------------------------------------------------------------------
    #  Tube geometry
    # ------------------------------------------------------------------

    def _build_tube_geometry(self):
        """Physical path of every serpentine pass, for drawing and for length.

        Plate ``p`` sits at the boundary below layer ``p``, i.e. between
        layer p-1 and layer p, with the outermost two forming the base and
        the lid. Each plate carries ``tubes_per_plate`` passes spread across
        the pack depth; each pass runs the full pack width in x.

        Mission Control draws these points directly, so the plumbing on
        screen is the plumbing the solver used.
        """
        self.tubes: List[Tube] = []

        x0 = self.x.min() - 0.5 * self.cell_diameter_m
        x1 = self.x.max() + 0.5 * self.cell_diameter_m
        y0 = self.y.min() - 0.5 * self.cell_diameter_m
        y1 = self.y.max() + 0.5 * self.cell_diameter_m

        pass_length = x1 - x0

        for t in range(self.n_tubes):

            plate = int(self.tube_plate[t])
            local_t = t - plate * self.tubes_per_plate

            # plate plane: just outside the cells it serves
            z = plate * self.layer_pitch_z_m - 0.5 * self.layer_gap_m

            # y band this pass occupies
            frac = (local_t + 0.5) / self.tubes_per_plate
            y = y0 + frac * (y1 - y0)

            # segment centres along x; alternate passes reverse so the
            # drawn path is a real serpentine rather than a set of
            # disconnected strokes
            xs = np.linspace(x0, x1, self.n_seg_per_tube)
            if local_t % 2 == 1:
                xs = xs[::-1]

            pts = np.column_stack([xs,
                                   np.full(self.n_seg_per_tube, y),
                                   np.full(self.n_seg_per_tube, z)])

            self.tubes.append(Tube(
                index=t,
                circuit=int(self.tube_circuit[t]),
                plate=plate,
                seg_centres=pts,
                length=float(pass_length),
                n_bends=self.n_bends_per_tube,
            ))

        self.plate_z = [p * self.layer_pitch_z_m - 0.5 * self.layer_gap_m
                        for p in range(self.n_plates)]

    # ------------------------------------------------------------------
    #  Aliases the browser exporter expects
    # ------------------------------------------------------------------

    def _build_export_aliases(self):
        """Names ``webexport.export_model`` looks for.

        Kept in one place and clearly labelled, so it is obvious which
        attributes exist only to satisfy the exporter rather than the
        physics.
        """
        # solver order: cells are already generated group-major
        self.order = np.arange(self.n_cells)

        # the exporter calls the layer index ``layer_id``
        self.layer_id = self.layer

        # per-pair conductance, so the weaker inter-group coupling is
        # exported rather than averaged away
        base = self.gap_filler_k_WmK * self.gap_contact_frac
        gap = max(1e-4, self.pitch_x_m - self.cell_diameter_m)
        lateral_area = np.pi * self.cell_diameter_m * self.cell_height_m
        g0 = base * lateral_area / gap

        self.neighbour_G = (self.neighbour_weight * g0
                            if len(self.neighbour_weight)
                            else np.zeros(0))

        # every cell-to-coolant link carries equal weight: both ends of a
        # cell are nominally identical
        self.cell_coolant_weight = np.full(len(self.cell_coolant_pairs),
                                           1.0 / max(1, self.cell_ends_cooled))

        # how well each cell is reached by coolant, for the display shading
        self.tube_contact_score = self.n_tubes_touching.astype(float)

    # ------------------------------------------------------------------
    #  Conductances -- interface parity with PackLayout
    # ------------------------------------------------------------------

    def G_cell_cell(self, cell) -> float:
        """Mean can-to-can conductance through the gap filler."""
        gap = max(1e-4, self.pitch_x_m - cell.diameter_m)
        base = (self.gap_filler_k_WmK *
                self.gap_contact_frac * cell.lateral_area_m2) / gap

        if len(self.neighbour_weight):
            return float(base * np.mean(self.neighbour_weight))
        return float(base)

    def G_cell_air(self, cell) -> np.ndarray:
        return (self.h_internal_WmK * cell.lateral_area_m2 *
                self.exposed_frac)

    def R_cell_to_coolant_KW(self) -> float:
        """Cell core path to the coolant, per end, then both ends in parallel.

        Two ends conducting in parallel is the whole reason this architecture
        works: it halves the path resistance relative to cooling one face.
        """
        per_end = self.R_can_plate_KW + self.R_plate_tubewall_KW
        return per_end / max(1, self.cell_ends_cooled)

    # Name kept for drop-in compatibility with the flat model's solver.
    @property
    def R_can_tubewall_KW(self) -> float:
        return self.R_cell_to_coolant_KW()

    def tube_length_per_circuit(self) -> float:
        """Wetted length one circuit sees.

        Each serpentine pass crosses the pack width; a circuit strings
        several passes in series.
        """
        per_tube = self.pack_width_m
        return (self.n_tubes / self.n_circuits_eff) * per_tube

    def wetted_area_per_cell_m2(self) -> float:
        """Tube wall area attributable to one cell, both ends."""
        return (self.cell_ends_cooled * np.pi * self.tube_id_m *
                self.pitch_x_m)

    def hydraulics(self, coolant) -> dict:
        """Flow regime, heat-transfer coefficient and pressure drop.

        Identical treatment to the flat model, applied to the plate tubes.
        """
        from .pack_thermal import tube_side_htc, tube_pressure_drop

        mdot_total = coolant.flow_L_per_min / 60000.0 * coolant.rho_kg_m3
        mdot_c = mdot_total / self.n_circuits_eff

        h, Re, regime, v = tube_side_htc(coolant, self.tube_id_m, mdot_c)

        L = self.tube_length_per_circuit()
        n_bends = max(0, int(self.n_tubes / self.n_circuits_eff) - 1) \
            + self.n_bends_per_tube
        dp = tube_pressure_drop(coolant, self.tube_id_m, mdot_c, L, n_bends)

        A_w = self.wetted_area_per_cell_m2()

        R_conv = 1.0 / max(1e-9, h * A_w)

        R_solid = self.R_cell_to_coolant_KW()

        # Key names match the flat PackLayout exactly. ThermalNetwork reads
        # R_total_per_tube_KW, and a mismatch here would surface as a
        # KeyError rather than a wrong number -- which is the right failure
        # mode, but only if the contract is kept deliberately.
        return dict(
            n_circuits=self.n_circuits_eff,
            n_tubes=self.n_tubes,
            n_plates=self.n_plates,
            velocity_m_s=v,
            Re=Re,
            regime=regime,
            h_W_m2K=h,
            R_conv_per_cell_KW=R_conv,
            R_total_per_tube_KW=R_solid + R_conv,
            circuit_length_m=L,
            dP_Pa=dp,
            dP_bar=dp / 1e5,
            flow_per_circuit_L_min=(coolant.flow_L_per_min /
                                    self.n_circuits_eff),

            # extras specific to the plate architecture
            R_conv_KW=R_conv,
            R_solid_KW=R_solid,
            tube_length_per_circuit_m=L,
            wetted_area_per_cell_m2=A_w,
        )

    # ------------------------------------------------------------------
    #  Reporting
    # ------------------------------------------------------------------

    def summary(self) -> str:
        lines = []
        a = lines.append
        a("Two-layer pack layout")
        a(f"  {self.n_series}S{self.n_parallel}P, {self.n_cells} cells")
        a(f"  {self.n_layers} layers x {self.groups_per_layer} groups")
        a(f"  group {self.group_rows} x {self.group_cols} cells")
        a(f"  grid {self.grid_rows} x {self.grid_cols} "
          f"({self.grid_rows*self.grid_cols - self.groups_per_layer} slots free)")
        a("")
        a(f"  cell envelope  {self.pack_width_m*1e3:.0f} x "
          f"{self.pack_depth_m*1e3:.0f} x "
          f"{(self.n_layers*self.cell_height_m + (self.n_layers-1)*self.layer_gap_m)*1e3:.0f} mm")
        a("")
        a("Cooling: end plates (axial)")
        a(f"  {self.n_plates} plates, {self.tubes_per_plate} passes each "
          f"= {self.n_tubes} tubes")
        a(f"  {self.n_circuits_eff} hydraulic circuits, "
          f"counter-flow {'on' if self.counter_flow else 'off'}")
        a(f"  every cell cooled at {self.cell_ends_cooled} ends")
        a(f"  R cell->coolant (solid) {self.R_cell_to_coolant_KW():.2f} K/W")
        a(f"  cells reached by coolant: "
          f"{self.frac_cells_tube_cooled*100:.1f}%")
        if self.has_orphans:
            a(f"  ORPHANS: {len(self.orphaned_cells)} cells have no "
              f"coolant path")
        else:
            a("  no orphaned cells -- every cell has two cooled ends")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Construction from the shared parameter file
# ---------------------------------------------------------------------------

def from_params(P: Optional[Params] = None) -> TwoLayerLayout:
    """Build the layout from ``params/volare_params.json``.

    This is the only construction path used by the rest of the project, so
    the Python and MATLAB models cannot describe different packs.
    """
    if P is None:
        P = load()

    return TwoLayerLayout(
        n_series=int(P.pack.n_series),
        n_parallel=int(P.pack.n_parallel),
        n_layers=int(P.pack.n_layers),
        group_rows=int(P.pack.group_rows),
        group_cols=int(P.pack.group_cols),
        grid_rows=int(P.pack.grid_rows),
        grid_cols=int(P.pack.grid_cols),

        cell_diameter_m=P.cell.diameter_m,
        cell_height_m=P.cell.height_m,
        cell_clearance_m=P.pack.cell_clearance_m,
        group_clearance_x_m=P.pack.group_clearance_x_m,
        group_clearance_y_m=P.pack.group_clearance_y_m,
        layer_gap_m=P.pack.layer_gap_m,

        tubes_per_plate=int(P.cooling.tubes_per_plate),
        n_circuits=int(P.cooling.n_circuits),
        interleave_circuits=bool(P.cooling.interleave_circuits),
        counter_flow=bool(P.cooling.counter_flow),
        tube_id_m=P.cooling.tube_id_m,
        n_bends_per_tube=int(P.cooling.n_bends_per_tube),
        plate_thickness_m=P.cooling.plate_thickness_m,

        R_can_plate_KW=P.cooling.R_can_plate_KW,
        R_plate_tubewall_KW=P.cooling.R_plate_tubewall_KW,
        cell_ends_cooled=int(P.cooling.cell_ends_cooled),

        gap_filler_k_WmK=P.cooling.gap_filler_k_W_mK,
        gap_contact_frac=P.cooling.gap_contact_frac,

        G_can_busbar_WK=P.busbar.G_can_busbar_WK,
        h_internal_WmK=P.pack.h_internal_W_m2K,
        enclosure_air_volume_m3=P.pack.enclosure_air_volume_m3,
        enclosure_UA_WK=P.pack.enclosure_UA_WK,
        busbar_cooled=bool(P.busbar.busbar_cooled),
        R_busbar_coolant_KW=P.busbar.R_busbar_coolant_KW,
    )


if __name__ == "__main__":                                  # pragma: no cover
    lay = from_params()
    print(lay.summary())
