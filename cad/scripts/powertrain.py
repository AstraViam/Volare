"""
powertrain.py -- every powertrain component, placed in the canonical frame.

Pure numpy. Blender and FreeCAD are consumers of this, not the place it lives,
which is the same rule the rest of cad/ follows and for the same reason: the
clearance and compliance maths has to be testable without a GUI app.

WHERE THE NUMBERS COME FROM
---------------------------
params/volare_params.json in the P50B_26S21P project, section `powertrain`,
plus the pack envelope which that project's P50B_Geometry CALCULATES from cell
dimensions and clearances.

Nothing here restates a dimension. If a value is not in the parameter file this
module raises rather than inventing one, because a CAD model built on a number
nobody chose is worse than no CAD model -- it looks authoritative.

That matters more than usual here. The P50B project has found eight separate
cases of two parts of the design quietly describing different boats, every one
of them a duplicated literal that agreed until it did not. A fourth
implementation of the design, in Blender, carrying its own copy of the pack
size, would be the ninth.

WHAT IS MODELLED
----------------
Envelopes, positions, masses and cable routes. A contactor is a box of the
right size in the right place with the right mass; it is not a magnetic
circuit. The questions this has to answer are: does it fit, does it clear, is
it legal, where is the centre of gravity, and can the cable actually be bent
that way.

WHAT IT CHECKS
--------------
ENERGY_REQ_25   energy container at least 500 mm from the pilot
ENERGY_REQ_26   container not in the pilot's seating area
ENERGY_REQ_50   everything hazardous aft of the bulkhead
ENERGY_REQ_58   fuse immediately after the energy storage
ENERGY_REQ_85   E-stop within a metre of the starboard side
ENERGY_REQ_185  organiser bay volume, clear of power cables by 100 mm
ENERGY_REQ_48   mass and centre of gravity
plus: nothing intersects anything else, and every HV cable route is bendable.

USAGE
    python scripts/powertrain.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import volare  # noqa: E402
from pod_envelope import Envelope  # noqa: E402
from layout import Layout  # noqa: E402


# ---------------------------------------------------------------------------
#  The shared parameter file
# ---------------------------------------------------------------------------

# The MATLAB pack project lives inside this repository at <repo>/powertrain,
# so the default resolves relative to this file and the repo is self-contained
# on any machine. Set P50B_ROOT to override, for example when pointing at a
# working copy of the MATLAB project held outside the repo.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

P50B_ROOT = os.environ.get("P50B_ROOT", os.path.join(_REPO_ROOT, "powertrain"))

PARAMS_PATH = os.path.join(P50B_ROOT, "params", "volare_params.json")


def load_params() -> dict:
    """Read the shared parameter file, unwrapping the {v,u,s,n} leaves.

    Deliberately does not import the P50B Python package: cad/ must run from a
    bare install with numpy, and reaching into another project's package to
    read a JSON file would make that false.
    """
    if not os.path.isfile(PARAMS_PATH):
        raise FileNotFoundError(
            f"Shared parameter file not found:\n  {PARAMS_PATH}\n"
            "Set P50B_ROOT to the P50B_26S21P project directory. This module "
            "will not substitute defaults -- a CAD model built on invented "
            "dimensions looks authoritative and is not.")

    with open(PARAMS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    def unwrap(node):
        if isinstance(node, dict):
            if "v" in node and "s" in node:
                return node["v"]
            return {k: unwrap(v) for k, v in node.items()
                    if not k.startswith("_")}
        return node

    return unwrap(raw)


GEOMETRY_PATH = os.path.join(P50B_ROOT, "output", "P50B_Geometry.json")
COMPLIANCE_PATH = os.path.join(P50B_ROOT, "output", "P50B_Compliance.json")


def load_geometry() -> dict:
    """Read the pack geometry MATLAB derived.

    NOT recomputed here. The first version of this module reproduced
    P50B_Geometry's envelope arithmetic and got 717.4 x 340.6 x 173.3 mm
    against the model's 709.4 x 332.6 x 180.3 -- 8 mm wrong on two axes and
    7 mm the other way on the third. The arithmetic looked right; the
    enclosure clearance is applied once to the height and twice to the
    width, and the layer gap sits inside the cell stack rather than outside
    it. Both are obvious once you have the two numbers side by side and
    invisible until then.

    That would have been a box in Blender that did not match the box every
    other model in the project describes -- the ninth instance of the same
    failure mode in this design. So the derivation happens once, in the
    model that owns it, and this consumes the answer.
    """
    if not os.path.isfile(GEOMETRY_PATH):
        raise FileNotFoundError(
            f"Pack geometry export not found:\n  {GEOMETRY_PATH}\n"
            "Run:  matlab -batch P50B_ExportGeometry\n"
            "This module will not recompute the envelope. Deriving it in "
            "two places is exactly the mistake this project keeps finding.")

    with open(GEOMETRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# Every value the MATLAB geometry export is derived from, mapped to the field
# it lands in. Keyed by the export path; each entry is the source parameter,
# the scale from parameter units to export units, and a tolerance.
#
# Adding a parameter that P50B_ExportGeometry consumes? Add it here too, or the
# freshness check will not notice when it changes.
_GEOMETRY_INPUTS = [
    # (export path,            parameter path,           scale, tol)
    ("pack.nSeries",           "pack.n_series",            1.0, 0),
    ("pack.nParallel",         "pack.n_parallel",          1.0, 0),
    ("pack.nLayers",           "pack.n_layers",            1.0, 0),
    ("pack.groupsPerLayer",    "pack.groups_per_layer",    1.0, 0),
    ("grid.rows",              "pack.grid_rows",           1.0, 0),
    ("grid.cols",              "pack.grid_cols",           1.0, 0),
    ("group.rows",             "pack.group_rows",          1.0, 0),
    ("group.cols",             "pack.group_cols",          1.0, 0),
    ("cell.diameter_mm",       "cell.diameter_m",        1000.0, 1e-6),
    ("cell.height_mm",         "cell.height_m",          1000.0, 1e-6),
    ("cell.mass_kg",           "cell.mass_kg",             1.0, 1e-9),
    ("cell.clearance_mm",      "pack.cell_clearance_m",  1000.0, 1e-6),
]


def _dig(obj, dotted):
    """Fetch a dotted path, unwrapping the {v,u,s,n} parameter leaves."""
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    if isinstance(cur, dict) and "v" in cur:
        return cur["v"]
    return cur


def check_export_freshness() -> str | None:
    """Report whether the geometry export still matches the parameters.

    Compares the VALUES the export was built from against the parameter file,
    not the two files' modification times.

    Modification time is the wrong test and produced a false alarm: editing a
    comment in volare_params.json, which changes nothing the export depends
    on, made the file newer and the check reported the export stale. Worse, it
    is silent in the opposite direction -- touching the export file would make
    a genuinely stale export look current.

    Comparing values also says WHICH parameter moved, which is what you need in
    order to decide whether rerunning P50B_ExportGeometry is necessary.
    """
    if not (os.path.isfile(GEOMETRY_PATH) and os.path.isfile(PARAMS_PATH)):
        return None

    try:
        with open(GEOMETRY_PATH, "r", encoding="utf-8") as f:
            geom = json.load(f)
        with open(PARAMS_PATH, "r", encoding="utf-8") as f:
            prm = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return f"could not compare export against parameters: {exc}"

    drifted = []
    unchecked = []
    for export_path, param_path, scale, tol in _GEOMETRY_INPUTS:
        have = _dig(geom, export_path)
        want = _dig(prm, param_path)
        if have is None or want is None:
            unchecked.append(export_path)
            continue
        want = want * scale
        if abs(float(have) - float(want)) > tol:
            drifted.append(f"{param_path} is {want:g} but the export has {have:g}")

    if drifted:
        return ("geometry export no longer matches the parameters -- rerun "
                "P50B_ExportGeometry. " + "; ".join(drifted))
    if unchecked:
        return ("could not verify " + ", ".join(unchecked) +
                " against the parameter file; the export format may have changed")
    return None          # fresh; the caller treats None as a pass


# ---------------------------------------------------------------------------
#  Parts
# ---------------------------------------------------------------------------

@dataclass
class Part:
    """One powertrain component: a box, somewhere, with a mass."""

    name: str
    size: np.ndarray            # mm, (length X, width Y, height Z)
    centre: np.ndarray          # mm, canonical boat frame
    mass_kg: float
    zone: str                   # "HV", "LV", "COOLING", "STRUCTURE", "ORGANISER"
    note: str = ""
    parent: str | None = None   # enclosed by another part

    @property
    def lo(self) -> np.ndarray:
        return self.centre - self.size / 2.0

    @property
    def hi(self) -> np.ndarray:
        return self.centre + self.size / 2.0

    @property
    def volume_L(self) -> float:
        return float(np.prod(self.size)) / 1e6

    def clearance_to(self, other: "Part") -> float:
        """Gap between two boxes, negative if they overlap."""
        gap = np.maximum(self.lo - other.hi, other.lo - self.hi)
        if np.all(gap < 0):
            return float(np.max(gap))          # deepest overlap, negative
        pos = gap[gap > 0]
        return float(np.sqrt(np.sum(pos ** 2)))

    def distance_to_plane_x(self, x: float) -> float:
        """Signed gap from the nearest face to a station. + means clear of it."""
        if self.lo[0] > x:
            return float(self.lo[0] - x)
        if self.hi[0] < x:
            return float(x - self.hi[0])
        return 0.0


@dataclass
class CableRun:
    """An HV or three-phase cable, as a polyline with a bend-radius limit."""

    name: str
    points: np.ndarray          # (n,3) mm
    od_mm: float
    min_bend_mm: float
    zone: str = "HV"
    note: str = ""

    @property
    def length_mm(self) -> float:
        d = np.diff(self.points, axis=0)
        return float(np.sum(np.linalg.norm(d, axis=1)))

    def corner_radii(self) -> list[float]:
        """Radius of the inscribed arc at each interior vertex.

        A polyline has infinitely sharp corners; a cable cannot. The radius
        that fits inside the corner is what decides whether the route is
        buildable, and it depends on the angle AND on how much straight length
        there is either side to swallow the arc.
        """
        out = []
        for i in range(1, len(self.points) - 1):
            a = self.points[i - 1] - self.points[i]
            b = self.points[i + 1] - self.points[i]
            la, lb = np.linalg.norm(a), np.linalg.norm(b)
            if la < 1e-6 or lb < 1e-6:
                continue
            cos = float(np.clip(np.dot(a, b) / (la * lb), -1.0, 1.0))
            theta = np.arccos(cos)              # interior angle
            if theta > np.pi - 1e-6:
                out.append(np.inf)              # straight through
                continue
            # largest arc that fits in the shorter leg
            out.append(float(min(la, lb) * np.tan(theta / 2.0)))
        return out

    @property
    def tightest_bend_mm(self) -> float:
        r = self.corner_radii()
        return float(min(r)) if r else float("inf")

    def min_distance_to_point(self, q: np.ndarray) -> float:
        """Closest approach of the route to a point, segment by segment."""
        best = np.inf
        for i in range(len(self.points) - 1):
            a, b = self.points[i], self.points[i + 1]
            ab = b - a
            t = np.dot(q - a, ab) / max(np.dot(ab, ab), 1e-9)
            t = float(np.clip(t, 0.0, 1.0))
            best = min(best, float(np.linalg.norm(q - (a + t * ab))))
        return best


# ---------------------------------------------------------------------------
#  Build
# ---------------------------------------------------------------------------

def build(P: dict | None = None, solve: bool = True) -> dict:
    """Assemble the powertrain, fitting it to the pod's measured section.

    solve=True places every component with layout.Layout, using the
    positions in the parameter file as PREFERENCES. solve=False takes
    those positions literally, which is only useful for reproducing an
    earlier layout.
    """
    if P is None:
        P = load_params()

    pt = P["powertrain"]
    ck = P["cockpit"]
    mo = P["motor"]
    ms = P["mass"]

    def v3(key):
        return np.array(pt[key], float)

    parts: list[Part] = []
    cables: list[CableRun] = []

    GEO = load_geometry()

    env = Envelope.load()
    lay = Layout(env)

    bulkhead_x = pt["bulkhead_x_mm"]
    seat_x = pt["pilot_seat_x_mm"]

    # ENERGY_REQ_25 measures from the seat to the nearest face of the
    # container, so the container's forward face may not come further
    # forward than this. Enforced during placement rather than checked
    # afterwards -- a solver told the real limit finds a legal answer,
    # and one told a preference finds an illegal one and reports it.
    container_x_max = min(bulkhead_x,
                          seat_x - P["rules"]["container_min_from_pilot_mm"])

    def put(name, size, prefer_key, **kw):
        pl = lay.place(name, size, v3(prefer_key), **kw)
        return pl

    # --- fixed structure claims its space first ---------------------------
    #
    # The bulkhead spans the pod and cannot move. Registering it as a
    # fixed placement before anything else is searched means the solver
    # routes around it; without that, the heat exchanger was placed 136 mm
    # inside it and the clash only surfaced two checks later.
    bulkhead_size = np.array([pt["bulkhead_thickness_mm"],
                              pt["bulkhead_width_mm"],
                              pt["bulkhead_height_mm"]])

    lay.place("bulkhead", bulkhead_size,
              np.array([bulkhead_x, 0.0, pt["bulkhead_z_mm"]]), fixed=True)

    # --- energy container -------------------------------------------------
    pack_env = np.array(GEO["packEnvelope_mm"], float)

    wall = pt["pack_container_wall_mm"]
    container_env = pack_env + 2 * wall + np.array([40.0, 40.0, 30.0])

    pl_container = put("energy_container", container_env, "pack_centre_mm",
                       sit="floor", x_range=700.0, y_options=[0.0],
                       x_max=container_x_max)

    parts.append(Part(
        "energy_container", container_env, pl_container.centre, 6.0, "HV",
        "ENERGY_REQ_155 overpressure valve aft, 56 fire port to port, "
        "189 external charge interface, 171-173 labels, 182 sensor "
        "pass-through to the pack core"))

    parts.append(Part(
        "battery_pack", pack_env, pl_container.centre, GEO["mass"]["pack_kg"],
        "HV",
        f"{GEO['pack']['nSeries']}S{GEO['pack']['nParallel']}P, "
        f"{GEO['pack']['nCells']} cells, "
        f"{GEO['pack']['storedEnergy_Wh']:.0f} Wh",
        parent="energy_container"))

    # ORDER MATTERS.
    #
    # The aft bay is 415 mm long and the PDU and inverter are the only
    # parts that must live there -- close to the motor, aft of the
    # container. Everything else has alternatives.
    #
    # Placed after the terminal box, the box's lid position failed by a
    # few millimetres, it fell back into the aft bay, and the PDU then
    # had 196 mm of length for a 300 mm box. Greedy placement gives the
    # scarce space to whoever asks first, so the constrained parts ask
    # first.
    # --- PDU and inverter, aft of the container ---------------------------
    pdu_size = v3("pdu_size_mm")

    aft_x = pl_container.lo[0] - pdu_size[0] / 2.0 - 30.0

    pl_pdu = lay.place("pdu", pdu_size,
                       np.array([aft_x, -140.0, 700.0]),
                       sit="floor", x_range=350.0,
                       y_options=[-140.0, -110.0, -80.0, 0.0],
                       x_max=container_x_max)

    parts.append(Part("pdu", pdu_size, pl_pdu.centre, 3.2, "HV",
                      "fuse feed, main and precharge contactors, HV "
                      "interlock. ENERGY_REQ_60 and 63 satisfied by one lid"))

    for nm, size, m, frac, note in [
        ("main_contactor", v3("contactor_size_mm"), 0.8, 0.28,
         "ENERGY_REQ_79: opened by the E-stop through a relay, not software"),
        ("precharge_contactor", v3("precharge_contactor_size_mm"), 0.2, -0.28,
         "without it the main contactor welds onto the DC-link capacitance"),
    ]:
        parts.append(Part(nm, size,
                          pl_pdu.centre + np.array([frac * pdu_size[0], 0, 0]),
                          m, "HV", note, parent="pdu"))

    inv_size = v3("inverter_size_mm")

    pl_inv = lay.place("inverter", inv_size,
                       np.array([pl_pdu.centre[0], 140.0, 700.0]),
                       sit="floor", x_range=350.0,
                       y_options=[140.0, 110.0, 80.0],
                       x_max=container_x_max)

    parts.append(Part(
        "inverter", inv_size, pl_inv.centre, ms["inverter_kg"], "HV",
        "NOT SELECTED -- Competr lists it on request. Envelope reservation"))

    # --- terminal box, on the container lid -------------------------------
    #
    # P50B_GroupLayout puts BOTH pack terminals on the TOP face, so the
    # fuse belongs directly above them. With the fuse downstream in the
    # PDU there were 1014 mm of unprotected HV cable, which the
    # ENERGY_REQ_58 check rejected.
    tb_size = v3("terminal_box_size_mm")

    pl_tb = lay.place("terminal_box", tb_size,
                      np.array([pl_container.centre[0] + 80.0, 0.0,
                                pl_container.hi[2] + 70.0]),
                      sit="lid", x_range=400.0, y_options=[0.0],
                      x_max=container_x_max)

    parts.append(Part(
        "terminal_box", tb_size, pl_tb.centre, 1.4, "HV",
        "HV terminal box on the container lid, over the pack terminals. "
        "Holds the main fuse and the shunt so ENERGY_REQ_58 is satisfied "
        "by geometry rather than by argument"))

    parts.append(Part(
        "main_fuse", v3("fuse_size_mm"),
        pl_tb.centre + np.array([tb_size[0] * 0.22, 0.0, 0.0]), 0.3, "HV",
        f"{P['harness']['fuse_rating_A']:.0f} A. ENERGY_REQ_58 immediately "
        f"after the storage; 59 below every conductor it protects",
        parent="terminal_box"))

    parts.append(Part(
        "current_shunt", v3("shunt_size_mm"),
        pl_tb.centre + np.array([-tb_size[0] * 0.25, 0.0, 0.0]), 0.2, "HV",
        "feeds the BMS and the Annex III telemetry current channel",
        parent="terminal_box"))

    # --- DC-DC, on the lid ------------------------------------------------
    pl_dcdc = lay.place("dcdc", v3("dcdc_size_mm"),
                        np.array([pl_container.centre[0] - 60.0, -170.0,
                                  pl_container.hi[2] + 45.0]),
                        sit="lid", x_range=400.0,
                        y_options=[-170.0, 170.0, 0.0],
                        x_max=container_x_max)

    parts.append(Part(
        "dcdc", v3("dcdc_size_mm"), pl_dcdc.centre, 2.1, "LV",
        "HV to 12 V. Also supplies the ENERGY_REQ_184 organiser interface"))

    # --- cooling ----------------------------------------------------------
    pl_pump = lay.place("coolant_pump", v3("coolant_pump_size_mm"),
                        np.array([pl_container.centre[0], 210.0, 700.0]),
                        sit="floor", x_range=400.0,
                        y_options=[210.0, -210.0, 230.0])

    parts.append(Part(
        "coolant_pump", v3("coolant_pump_size_mm"), pl_pump.centre, 0.9,
        "COOLING",
        f"{P['cooling']['flow_L_per_min']:.0f} L/min against the loop drop"))

    pl_hx = lay.place("heat_exchanger", v3("heat_exchanger_size_mm"),
                      np.array([pl_container.centre[0], -210.0, 700.0]),
                      sit="floor", x_range=400.0,
                      y_options=[-210.0, 210.0, -230.0])

    parts.append(Part(
        "heat_exchanger", v3("heat_exchanger_size_mm"), pl_hx.centre, 2.4,
        "COOLING",
        "seawater plate exchanger -- the sea is the ultimate heat sink"))

    # --- LV, forward of the bulkhead --------------------------------------
    pl_lvb = lay.place("lv_battery", v3("lv_battery_size_mm"),
                       v3("lv_battery_centre_mm"),
                       sit="floor", x_range=400.0, x_min=bulkhead_x)

    parts.append(Part(
        "lv_battery", v3("lv_battery_size_mm"), pl_lvb.centre, 1.1, "LV",
        "ENERGY_REQ_7 note 3 exempts it from the energy sum; 58 still "
        "requires it fused and 67 still requires its temperature monitored"))

    pl_vcu = lay.place("vcu", v3("vcu_size_mm"), v3("vcu_centre_mm"),
                       sit="floor", x_range=400.0, x_min=bulkhead_x)

    parts.append(Part(
        "vcu", v3("vcu_size_mm"), pl_vcu.centre, 1.4, "LV",
        "Competr control unit, IP67, datasheet section 2"))

    estop_d = ck["estop_yellow_circle_mm"]

    pl_estop = lay.place("estop", np.array([60.0, estop_d, estop_d]),
                         v3("estop_centre_mm"), sit="free", x_range=350.0,
                         y_options=[-230.0, -200.0, -260.0], x_min=bulkhead_x)

    parts.append(Part(
        "estop", np.array([60.0, estop_d, estop_d]), pl_estop.centre, 0.3,
        "LV",
        "ENERGY_REQ_76 red on a 90 mm yellow circle, 77 >=30 mm button, "
        "81 starboard and forward of the pilot, 85 within 1 m of starboard, "
        "86 facing outboard"))

    # --- fixed geometry ---------------------------------------------------
    #
    # The bulkhead spans the pod at its station and the outboard hangs off
    # the transom. Neither is free to move, so neither is solved.
    parts.append(Part(
        "bulkhead", bulkhead_size,
        np.array([bulkhead_x, 0.0, pt["bulkhead_z_mm"]]),
        5.5, "STRUCTURE",
        f"ENERGY_REQ_50/51/52. A1 fire rated. One "
        f"{ck['bulkhead_hole_diameter_mm']:.0f} mm grommeted pass-through "
        f"(174: >=30, 175: <=50)"))

    parts.append(Part(
        "monitor_bay",
        np.array([ck["monitor_bay_L_mm"], ck["monitor_bay_W_mm"],
                  ck["monitor_bay_H_mm"]]),
        v3("monitor_bay_centre_mm"), ms["organiser_equipment_kg"],
        "ORGANISER",
        "ENERGY_REQ_185 free volume, ON the crown so it is open to the sky "
        "and outside every closed compartment"))

    # The outboard envelope comes from the DIMENSIONED DRAWING, not from the
    # specification table. The table reads "300x210x800mm", and length_m = 0.8
    # was being used as an 800 mm fore-aft dimension, which laid a 705 mm-tall
    # outboard on its side and put 800 mm of it astern. The drawing (datasheet
    # section 6, page 7) gives 322 fore-aft, 210 across, 705 cowling top to
    # gearcase bottom. mo["length_m"] and friends are left in the parameter
    # file because the MATLAB side still quotes the table.
    motor_size = np.array([mo["drawing_length_mm"], mo["drawing_width_mm"],
                           mo["drawing_height_mm"]])
    motor_c = v3("motor_centre_mm")

    # Height is set by the anti-ventilation plate, which is what the drawing
    # dimensions everything from, not by motor_centre_mm's Z.
    plate_z = pt["motor_plate_z_mm"]
    gear_h = mo["drawing_height_mm"] * mo["gearcase_fraction"]
    motor_c = np.array([motor_c[0], motor_c[1],
                        plate_z - gear_h + motor_size[2] / 2.0])

    parts.append(Part(
        "outboard", motor_size, motor_c, mo["mass_kg"], "HV",
        f"{mo['power_nominal_W']/1000:.1f} kW nominal, capped to "
        f"{mo['configured_power_limit_W']/1000:.0f} kW by ENERGY_REQ_188"))

    # What used to be modelled as a 120 x 90 x 500 drive leg is inside the
    # 705 mm envelope above. The separate part carrying trim_mass_kg is the
    # transom bracket and trim assembly, dimensioned in datasheet section 7.
    parts.append(Part(
        "drive_leg", np.array([mo["bracket_length_mm"], mo["bracket_width_mm"],
                               mo["bracket_height_mm"]]),
        np.array([motor_c[0] + mo["drawing_length_mm"] / 2.0
                  + mo["bracket_length_mm"] / 2.0 + 5.0, motor_c[1],
                  plate_z + mo["transom_mounting_height_mm"]
                  - mo["bracket_height_mm"] / 2.0]),
        mo["trim_mass_kg"], "HV",
        "transom bracket and hydraulic trim assembly, datasheet section 7"))

    # --- cables, routed from the SOLVED positions -------------------------
    hv_od = pt["hv_cable_od_mm"]
    hv_bend = pt["hv_cable_bend_radius_mm"]
    ph_od = pt["three_phase_cable_od_mm"]

    pack = by_name(parts, "battery_pack")
    tb = by_name(parts, "terminal_box")
    pdu = by_name(parts, "pdu")
    inv = by_name(parts, "inverter")
    motor = by_name(parts, "outboard")

    for nm, dy in (("hv_pack_pos", 60.0), ("hv_pack_neg", -60.0)):
        cables.append(CableRun(
            nm, np.array([
                [tb.centre[0] + dy * 0.5, dy, pack.hi[2]],
                [tb.centre[0] + dy * 0.5, dy, tb.lo[2]],
            ]), hv_od, hv_bend, "HV",
            "pack terminal straight up into the fused terminal box"))

    # Terminal box down to the PDU. Routed round the side of the container
    # with legs long enough to bend, which the check enforces.
    # Every leg is at least the bend radius long, because a corner needs
    # that much straight either side to be formed. Routed outboard of the
    # PDU and back in, which is longer than a direct line and is the
    # difference between a cable that can be fitted and one that cannot.
    leg = hv_bend + 30.0

    side_y = np.sign(pdu.centre[1]) * (abs(pdu.centre[1]) + leg)

    cables.append(CableRun(
        "hv_fused_to_pdu", np.array([
            [tb.centre[0], np.sign(pdu.centre[1]) * tb.size[1] / 2.0,
             tb.centre[2]],
            [tb.centre[0], side_y, tb.centre[2]],
            [pdu.centre[0], side_y, tb.centre[2]],
            [pdu.centre[0], side_y, pdu.centre[2]],
            [pdu.centre[0], pdu.hi[1], pdu.centre[2]],
        ]), hv_od, hv_bend, "HV",
        "downstream of the fuse, so this is the first protected run"))

    cables.append(CableRun(
        "hv_pdu_to_inverter", np.array([
            [pdu.centre[0], pdu.lo[1], pdu.centre[2]],
            [pdu.lo[0] - hv_bend - 30.0, pdu.lo[1], pdu.centre[2]],
            [pdu.lo[0] - hv_bend - 30.0, inv.centre[1], inv.centre[2]],
            [inv.lo[0], inv.centre[1], inv.centre[2]],
        ]), hv_od, hv_bend, "HV",
        "PDU to the inverter DC input"))

    # Three-phase, inverter to outboard.
    #
    # Two rules govern this route and the old one broke both.
    #
    # First, a corner needs at least one bend radius of STRAIGHT cable either
    # side of it to be formed. The old route stepped outboard to a station
    # only 37 mm short of the outboard centre and turned twice inside that
    # 37 mm, asking for a 37 mm radius in a cable rated for 132. That is not
    # a tight fit, it is an impossible one.
    #
    # Second, and less obvious: DO NOT climb over the outboard. The inverter
    # sits only about 90 mm above the outboard top, so routing up to an apex
    # and back down puts a hairpin in the cable. Lengthening the legs then
    # makes the bend radius WORSE, not better, because raising the apex makes
    # the reversal sharper faster than the legs grow. Measured: 105 mm at a
    # 152 mm leg, falling to 82 mm at a 232 mm leg.
    #
    # So the route descends monotonically. One straight leg off the inverter
    # face, then a single diagonal carrying the outboard offset, the lateral
    # shift and the 91 mm of descent together. One corner, opened out to about
    # 115 degrees, which a 132 mm radius fits inside comfortably.
    #
    # These cables stay deliberately short: they are the loudest EMC source on
    # the boat and length is the cheapest fix for that.
    ph_bend = 6 * ph_od
    ph_leg = ph_bend + 20.0          # straight off the inverter face

    for i, dy in enumerate((-40.0, 0.0, 40.0)):
        cables.append(CableRun(
            f"phase_{'UVW'[i]}", np.array([
                [inv.lo[0], inv.centre[1] + dy, inv.centre[2]],
                [inv.lo[0] - ph_leg, inv.centre[1] + dy, inv.centre[2]],
                [motor.centre[0], dy, motor.hi[2]],
            ]), ph_od, ph_bend, "HV",
            "screened three-phase. Descends monotonically: no climb over the "
            "outboard, because a hairpin there cannot meet the bend radius"))


    return dict(parts=parts, cables=cables, params=P,
                pack_envelope_mm=pack_env, geometry=GEO,
                layout=lay, envelope=env)


def by_name(parts: list[Part], name: str) -> Part:
    for p in parts:
        if p.name == name:
            return p
    raise KeyError(f"No part named '{name}'. Have: "
                   f"{', '.join(p.name for p in parts)}")


# ---------------------------------------------------------------------------
#  Checks
# ---------------------------------------------------------------------------

def check(asm: dict) -> list[tuple[str, bool, str]]:
    """Every geometric and rule check. Returns (name, ok, detail)."""
    parts: list[Part] = asm["parts"]
    cables: list[CableRun] = asm["cables"]
    P = asm["params"]
    pt = P["powertrain"]
    ck = P["cockpit"]

    out = []

    def add(name, ok, detail):
        out.append((name, bool(ok), detail))

    # --- everything is inside the pod ------------------------------------
    lay = asm.get("layout")
    if lay is not None:
        bad = lay.failures
        add("every component fits the pod section", not bad,
            "all placed" if not bad else
            "; ".join(f"{p.name}: {p.reason}" for p in bad))

    # --- pack envelope comes from the MATLAB export ----------------------
    env = asm["pack_envelope_mm"]
    pack = by_name(parts, "battery_pack")
    err = float(np.max(np.abs(pack.size - env)))
    add("pack envelope is the MATLAB export", err < 1e-9,
        f"{env[0]:.1f} x {env[1]:.1f} x {env[2]:.1f} mm, from "
        f"output/P50B_Geometry.json")

    stale = check_export_freshness()
    add("geometry export is current", stale is None,
        stale or f"all {len(_GEOMETRY_INPUTS)} geometry inputs match "
                 "params/volare_params.json")

    # --- nothing intersects ----------------------------------------------
    worst, worst_pair = np.inf, ("", "")
    for i, a in enumerate(parts):
        for b in parts[i + 1:]:
            if a.parent == b.name or b.parent == a.name:
                continue            # a part inside its own enclosure
            if a.parent and a.parent == b.parent:
                continue            # siblings inside one box
            g = a.clearance_to(b)
            if g < worst:
                worst, worst_pair = g, (a.name, b.name)
    add("no part intersects another", worst >= 0,
        f"tightest {worst:.1f} mm between {worst_pair[0]} and {worst_pair[1]}")

    # --- contents fit inside their enclosures ----------------------------
    bad = []
    for p in parts:
        if not p.parent:
            continue
        host = by_name(parts, p.parent)
        if np.any(p.lo < host.lo - 1e-6) or np.any(p.hi > host.hi + 1e-6):
            bad.append(p.name)
    add("enclosed parts fit their enclosure", not bad,
        "all inside" if not bad else "outside: " + ", ".join(bad))

    # --- ENERGY_REQ_25 ----------------------------------------------------
    seat_x = pt["pilot_seat_x_mm"]
    container = by_name(parts, "energy_container")
    d25 = container.distance_to_plane_x(seat_x)
    need25 = P["rules"]["container_min_from_pilot_mm"]
    add("ENERGY_REQ_25 container 500 mm from the pilot", d25 >= need25,
        f"{d25:.0f} mm from the seat at X={seat_x:.0f}, needs {need25:.0f}")

    # --- ENERGY_REQ_26 / 50 -----------------------------------------------
    bx = pt["bulkhead_x_mm"]
    fwd_of_bulkhead = [p.name for p in parts
                       if p.zone == "HV" and p.hi[0] > bx and not p.parent]
    add("ENERGY_REQ_26/50 HV is aft of the bulkhead", not fwd_of_bulkhead,
        "all aft" if not fwd_of_bulkhead
        else "forward: " + ", ".join(fwd_of_bulkhead))

    # --- ENERGY_REQ_58 ----------------------------------------------------
    #
    # Measured as the length of UNPROTECTED cable, which is what the rule
    # is actually about: everything between the pack terminal and the fuse
    # is live, unfused, and a chafe away from a short across 9.8 kWh.
    #
    # 300 mm is the threshold rather than the 1500 mm first used. The
    # earlier number let a metre of unprotected cable pass, which is how
    # the original layout put the fuse in the PDU and looked compliant.
    fuse = by_name(parts, "main_fuse")
    pack = by_name(parts, "battery_pack")

    unprotected = max(c.length_mm for c in cables
                      if c.name in ("hv_pack_pos", "hv_pack_neg"))

    add("ENERGY_REQ_58 fuse just after the storage", unprotected <= 300.0,
        f"{unprotected:.0f} mm of unprotected cable from the pack terminal "
        f"to the fuse, limit 300")

    # --- ENERGY_REQ_85 ----------------------------------------------------
    estop = by_name(parts, "estop")
    hull_y = volare.BASELINE["hull"]["y_centres"][1]        # starboard
    d85 = abs(estop.centre[1] - hull_y)
    max85 = P["rules"]["estop_max_from_starboard_m"] * 1000.0
    add("ENERGY_REQ_85 E-stop within 1 m of starboard", d85 <= max85,
        f"{d85:.0f} mm from the starboard hull centreline, max {max85:.0f}")

    # --- ENERGY_REQ_185 ---------------------------------------------------
    bay = by_name(parts, "monitor_bay")
    need = np.array(P["rules"]["monitor_volume_mm"], float)
    add("ENERGY_REQ_185 organiser bay volume",
        bool(np.all(bay.size >= need - 1e-9)),
        f"{bay.size[0]:.0f} x {bay.size[1]:.0f} x {bay.size[2]:.0f} mm "
        f"against {need[0]:.0f} x {need[1]:.0f} x {need[2]:.0f}")

    # The bay must also stand clear of every power cable by 100 mm.
    # Distance from the BAY's box to each cable's surface, sampled along
    # every run. The first version measured from the bay's centre and
    # subtracted half its smallest dimension, which understates the gap
    # whenever the nearest cable is off the short axis.
    clear_need = P["rules"]["monitor_min_cable_clear_mm"]
    worst_clear, worst_cable = np.inf, ""

    bay_lo, bay_hi = bay.lo, bay.hi

    for c in cables:
        for i in range(len(c.points) - 1):
            a, b = c.points[i], c.points[i + 1]
            for t in np.linspace(0.0, 1.0, 25):
                q = a + t * (b - a)
                gap = np.maximum(np.maximum(bay_lo - q, q - bay_hi), 0.0)
                d = float(np.linalg.norm(gap)) - c.od_mm / 2.0
                if d < worst_clear:
                    worst_clear, worst_cable = d, c.name

    add("ENERGY_REQ_185 bay 100 mm clear of power cables",
        worst_clear >= clear_need,
        f"nearest is {worst_cable} at {worst_clear:.0f} mm, "
        f"needs {clear_need:.0f}")

    # --- cable routes are bendable ----------------------------------------
    tight, tight_name = np.inf, ""
    for c in cables:
        r = c.tightest_bend_mm
        if r < tight:
            tight, tight_name = r, c.name
    ok_bend = all(c.tightest_bend_mm >= c.min_bend_mm for c in cables)
    add("every cable route is bendable", ok_bend,
        f"tightest {tight:.0f} mm on {tight_name}")

    # --- mass and centre of gravity ---------------------------------------
    #
    # EVERY part, enclosed or not. A `parent` says a part sits inside
    # another's volume; it does not say its mass is already counted. The
    # energy container's 6.0 kg is the shell alone and the 51.6 kg pack
    # inside it is additional.
    #
    # This was wrong in both directions before it was right. First the
    # sum excluded enclosed parts, which dropped 53 kg -- most of it the
    # battery -- and put the CG 175 mm too far aft. Then the FreeCAD
    # script was "fixed" to match, which made the two agree on a number
    # neither should have produced. The disagreement was the useful
    # signal; matching it was the mistake.
    m = np.array([p.mass_kg for p in parts])
    c = np.array([p.centre for p in parts])
    total = float(np.sum(m))
    cg = (c * m[:, None]).sum(axis=0) / total

    add("powertrain mass is a sensible fraction of the budget",
        total < P["rules"]["mass_limit_excl_hulls_kg"],
        f"{total:.1f} kg, CG at X={cg[0]:.0f} Y={cg[1]:.0f} Z={cg[2]:.0f} mm")

    # CG athwartships: a boat with its mass off the centreline sits heeled,
    # which costs waterline symmetry and looks like a rigging fault at
    # scrutineering.
    add("CG is close to the centreline", abs(cg[1]) < 40.0,
        f"Y offset {cg[1]:+.0f} mm")

    asm["mass_kg"] = total
    asm["cg_mm"] = cg

    # --- cross-language constants must not drift -------------------------
    #
    # CLAUDE.md: never duplicate a constant across the two languages, read it
    # from the shared parameter file. volare.py is pure constants with no file
    # I/O by design, so it cannot read the file; the next best thing is to
    # fail loudly when the two disagree. They did: volare.py had a 70 kg pilot
    # and the parameter file had 80 kg, a 10 kg error sitting directly against
    # a 250 kg cap with negative margin.
    pilot_param = float(P["boat"]["pilot_mass_kg"])
    add("pilot mass agrees between volare.py and the parameter file",
        abs(volare.PILOT_DESIGN_KG - pilot_param) < 1e-9,
        f"volare.py has {volare.PILOT_DESIGN_KG:.1f} kg, "
        f"boat.pilot_mass_kg has {pilot_param:.1f} kg"
        + ("" if abs(volare.PILOT_DESIGN_KG - pilot_param) < 1e-9
           else " -- the boat is weighed with the pilot, so this lands "
                "straight on the ENERGY_REQ_48 margin"))

    # --- the motor power limit that makes the outboard legal -------------
    #
    # ENERGY_REQ_188 v1.1 caps INSTANTANEOUS power summed over all motors at
    # 25 kW and permits no peak. The outboard hardware is rated above that, so
    # compliance rests entirely on the controller limit being set and being
    # demonstrable. This asserts the limit exists and is at or below the cap.
    limit_w = float(P["motor"].get("power_limit_W", float("inf")))
    rule_w = 25000.0
    add("the motor controller limit meets ENERGY_REQ_188",
        limit_w <= rule_w + 1e-6,
        f"enforced limit {limit_w/1000:.1f} kW against a {rule_w/1000:.0f} kW "
        f"cap; hardware peak is {float(P['motor']['power_max_W'])/1000:.1f} kW and is "
        "not a permitted operating point")

    # --- against the MATLAB weight budget ---------------------------------
    #
    # The budget in P50B_MassBudget books these items as allowances -- a
    # number somebody wrote down. The CAD builds them as boxes with
    # positions. Where the two disagree, the CAD is the better estimate,
    # because an allowance does not know it forgot the container shell.
    #
    # This matters more than a 3% discrepancy usually would: the budget
    # closes with 2.4 kg of margin against a 250 kg limit, so a few
    # kilograms is the whole reserve.
    if os.path.isfile(COMPLIANCE_PATH):

        with open(COMPLIANCE_PATH, "r", encoding="utf-8") as f:
            C = json.load(f)

        if "mass" in C:
            # EXPLICIT mapping, CAD part -> MATLAB budget line.
            #
            # This used to be a set of budget-item names summed with a
            # membership test, and it was silently wrong. It looked for a line
            # called "HV harness and switchgear"; the budget has two lines,
            # "HV switchgear" and "HV harness (cable)". Nothing matched, so
            # 9.6 kg simply vanished from the budget side and the CAD appeared
            # 7 kg heavy when it is in fact slightly light.
            #
            # A membership test cannot fail loudly. A mapping can: anything
            # unmapped on either side is reported below, so the next rename
            # produces a complaint instead of a wrong number.
            CAD_TO_BUDGET = {
                "battery_pack":        "Battery pack",
                "outboard":            "Outboard",
                "drive_leg":           "Trim assembly",
                "inverter":            "Inverter / ESC",
                "energy_container":    "Energy container",
                # switchgear is one budget line and six CAD parts
                "pdu":                 "HV switchgear",
                "main_contactor":      "HV switchgear",
                "precharge_contactor": "HV switchgear",
                "terminal_box":        "HV switchgear",
                "main_fuse":           "HV switchgear",
                "current_shunt":       "HV switchgear",
                "heat_exchanger":      "Cooling system",
                "coolant_pump":        "Cooling system",
                "dcdc":                "LV system",
                "vcu":                 "LV system",
                "lv_battery":          "LV system",
            }

            # Parts the CAD draws that the budget books elsewhere, outside the
            # powertrain. Excluded from BOTH sides so the comparison is like
            # for like.
            CAD_ELSEWHERE = {
                "bulkhead":    "Cockpit structure",
                "estop":       "Safety equipment",
                "monitor_bay": "Organiser equipment",
            }

            # Budget lines with no CAD counterpart, and why.
            BUDGET_UNMODELLED = {
                "HV harness (cable)": "the CAD routes cables but gives them no mass",
                "Cockpit structure": "outside the powertrain",
                "Steering and controls": "outside the powertrain",
                "Seat": "outside the powertrain",
                "Safety equipment": "outside the powertrain",
                "Beam clamps and fasteners": "outside the powertrain",
                "Pilot, ready to sail": "not hardware",
                "Contingency": "an allowance, not a part",
                "Ballast": "an allowance, not a part",
                "Organiser equipment": "drawn as monitor_bay, excluded both sides",
            }

            budget_by_item = {i["item"]: i["kg"] for i in C["mass"]["items"]}

            # --- integrity: nothing may be silently dropped ----------------
            problems = []
            for cad_name, item in CAD_TO_BUDGET.items():
                if item not in budget_by_item:
                    problems.append(f"CAD part '{cad_name}' maps to budget line "
                                    f"'{item}', which does not exist")
            cad_names = {p.name for p in parts}
            for cad_name in list(CAD_TO_BUDGET) + list(CAD_ELSEWHERE):
                if cad_name not in cad_names:
                    problems.append(f"mapping names CAD part '{cad_name}', "
                                    "which the CAD does not build")
            for p_ in parts:
                if p_.mass_kg > 0 and p_.name not in CAD_TO_BUDGET \
                        and p_.name not in CAD_ELSEWHERE:
                    problems.append(f"CAD part '{p_.name}' ({p_.mass_kg:.2f} kg) "
                                    "is in no mapping")
            for item in budget_by_item:
                if item not in CAD_TO_BUDGET.values() \
                        and item not in BUDGET_UNMODELLED:
                    problems.append(f"budget line '{item}' is in no mapping")

            add("the CAD-to-budget mass mapping is complete",
                not problems,
                "; ".join(problems) if problems
                else f"{len(CAD_TO_BUDGET)} CAD parts mapped onto "
                     f"{len(set(CAD_TO_BUDGET.values()))} budget lines, "
                     f"{len(BUDGET_UNMODELLED)} lines deliberately unmodelled")

            # --- like-for-like comparison ----------------------------------
            comparable = sum(p_.mass_kg for p_ in parts
                             if p_.name in CAD_TO_BUDGET)
            budget = sum(budget_by_item[i]
                         for i in set(CAD_TO_BUDGET.values())
                         if i in budget_by_item)
            delta = comparable - budget

            # Per-line audit, so a disagreement says WHERE.
            asm["mass_audit"] = []
            for item in sorted(set(CAD_TO_BUDGET.values())):
                cad_kg = sum(p_.mass_kg for p_ in parts
                             if CAD_TO_BUDGET.get(p_.name) == item)
                bud_kg = budget_by_item.get(item, 0.0)
                asm["mass_audit"].append(dict(item=item, cad_kg=cad_kg,
                                              budget_kg=bud_kg,
                                              delta_kg=cad_kg - bud_kg))

            asm["mass_vs_budget_kg"] = delta
            asm["budget_margin_kg"] = C["mass"]["margin_kg"]

            # Two DIFFERENT questions, and they used to be one check.
            #
            # The tolerance was the budget margin. The margin is currently
            # -9.2 kg, because the budget does not close, so the test read
            # abs(delta) <= -9.2 and could never be true however well the two
            # sides agreed. A modelling-consistency check must not be gated on
            # an engineering result.
            #
            # Question one: do the two accountings of the SAME hardware agree?
            # That is about modelling quality and wants a fixed tolerance.
            MASS_AGREEMENT_TOL_KG = 3.0
            add("CAD mass agrees with the MATLAB budget",
                abs(delta) <= MASS_AGREEMENT_TOL_KG,
                f"CAD {comparable:.1f} kg against {budget:.1f} kg budgeted, "
                f"{delta:+.1f} kg, tolerance {MASS_AGREEMENT_TOL_KG:.1f} kg. "
                + ("the CAD is the better estimate where they differ, because "
                   "an allowance does not know it forgot the container shell"
                   if abs(delta) > MASS_AGREEMENT_TOL_KG else "within tolerance"))

            # Question two: does the budget close against the 250 kg limit?
            # That is the engineering result, and it is reported separately so
            # a failure here cannot be mistaken for a modelling error.
            margin = C["mass"]["margin_kg"]
            add("the MATLAB mass budget closes under the 250 kg cap",
                margin >= 0.0,
                f"margin {margin:+.1f} kg against ENERGY_REQ_48. "
                + ("over the cap; see cad/scripts/mass.py for closure options"
                   if margin < 0 else "closes"))

    return out


# ---------------------------------------------------------------------------
#  Report
# ---------------------------------------------------------------------------

def export(asm: dict, path: str | None = None) -> str:
    """Write out/powertrain.json for Blender and FreeCAD to consume."""
    if path is None:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(here, "out", "powertrain.json")

    os.makedirs(os.path.dirname(path), exist_ok=True)

    D = dict(
        frame="X forward, Y port, Z up; origin = centreline x hull mid-length "
              "x keel bottom",
        units="mm, kg",
        source=PARAMS_PATH,
        mass_kg=asm.get("mass_kg"),
        cg_mm=list(map(float, asm.get("cg_mm", [0, 0, 0]))),
        parts=[dict(name=p.name, size=list(map(float, p.size)),
                    centre=list(map(float, p.centre)), mass_kg=p.mass_kg,
                    zone=p.zone, parent=p.parent, note=p.note)
               for p in asm["parts"]],
        cables=[dict(name=c.name, points=[list(map(float, q)) for q in c.points],
                     od_mm=c.od_mm, min_bend_mm=c.min_bend_mm,
                     length_mm=c.length_mm,
                     tightest_bend_mm=(None if np.isinf(c.tightest_bend_mm)
                                       else c.tightest_bend_mm),
                     zone=c.zone, note=c.note)
                for c in asm["cables"]],
    )

    with open(path, "w", encoding="utf-8") as f:
        json.dump(D, f, indent=1)

    return path


def main() -> int:
    asm = build()
    results = check(asm)

    parts: list[Part] = asm["parts"]
    cables: list[CableRun] = asm["cables"]

    print()
    print("=" * 74)
    print(" VOLARE POWERTRAIN -- GEOMETRY AND COMPLIANCE")
    print("=" * 74)
    print(f" frame: X fwd, Y port, Z up; origin centreline x mid-length x keel")
    print(f" source: {PARAMS_PATH}")
    print("=" * 74)

    print(f"\n{len(parts)} PARTS\n")
    print(f"  {'name':<22}{'size mm':>22}{'centre mm':>22}{'kg':>7}  zone")
    for p in sorted(parts, key=lambda q: (q.zone, -q.mass_kg)):
        sz = f"{p.size[0]:.0f}x{p.size[1]:.0f}x{p.size[2]:.0f}"
        ce = f"{p.centre[0]:.0f},{p.centre[1]:.0f},{p.centre[2]:.0f}"
        tag = f"  {p.zone}" + (f" in {p.parent}" if p.parent else "")
        print(f"  {p.name:<22}{sz:>22}{ce:>22}{p.mass_kg:>7.1f}{tag}")

    print(f"\n{len(cables)} CABLE RUNS\n")
    print(f"  {'name':<22}{'OD':>6}{'length mm':>11}{'bend mm':>10}"
          f"{'min':>7}")
    for c in cables:
        r = c.tightest_bend_mm
        rs = "straight" if np.isinf(r) else f"{r:.0f}"
        print(f"  {c.name:<22}{c.od_mm:>6.1f}{c.length_mm:>11.0f}"
              f"{rs:>10}{c.min_bend_mm:>7.0f}")

    # Per-line mass audit. Printed because a one-line total hides where the
    # two accountings actually disagree, and that is the number an engineer
    # needs in order to act.
    if asm.get("mass_audit"):
        print("\nMASS AUDIT, CAD against the MATLAB budget\n")
        print(f"  {'budget line':<26}{'CAD kg':>9}{'budget kg':>11}{'delta':>9}")
        tc = tb = 0.0
        for row in asm["mass_audit"]:
            tc += row["cad_kg"]
            tb += row["budget_kg"]
            flag = "  <--" if abs(row["delta_kg"]) > 0.5 else ""
            print(f"  {row['item']:<26}{row['cad_kg']:>9.2f}"
                  f"{row['budget_kg']:>11.2f}{row['delta_kg']:>+9.2f}{flag}")
        print(f"  {'':<26}{'-'*9}{'-'*11}{'-'*9}")
        print(f"  {'TOTAL':<26}{tc:>9.2f}{tb:>11.2f}{tc - tb:>+9.2f}")
        print("\n  Lines marked <-- differ by more than 0.5 kg. Where the two")
        print("  disagree the CAD is usually the better estimate: an allowance")
        print("  does not know it forgot the container shell.")

    print(f"\nCHECKS\n")
    nfail = 0
    for name, ok, detail in results:
        mark = " ok " if ok else "FAIL"
        if not ok:
            nfail += 1
        print(f"  [{mark}] {name:<46} {detail}")

    print()
    print("=" * 74)
    if nfail == 0:
        print(f" ALL {len(results)} CHECKS PASSED")
        print(f" {asm['mass_kg']:.1f} kg, CG X={asm['cg_mm'][0]:.0f} "
              f"Y={asm['cg_mm'][1]:.0f} Z={asm['cg_mm'][2]:.0f} mm")
    else:
        print(f" {nfail} OF {len(results)} CHECKS FAILED")
    print("=" * 74)

    path = export(asm)
    print(f"\nWritten {path}\n")

    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
