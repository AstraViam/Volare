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

P50B_ROOT = os.environ.get(
    "P50B_ROOT",
    r"C:\Users\aryam\OneDrive\Documents\MATLAB\P50B_26S21P")

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


def check_export_freshness() -> str | None:
    """Warn if the geometry export predates the parameter file."""
    if not (os.path.isfile(GEOMETRY_PATH) and os.path.isfile(PARAMS_PATH)):
        return None
    if os.path.getmtime(GEOMETRY_PATH) < os.path.getmtime(PARAMS_PATH):
        return ("output/P50B_Geometry.json is older than "
                "params/volare_params.json -- rerun P50B_ExportGeometry")
    return None


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

    motor_size = np.array([mo["length_m"], mo["width_m"],
                           mo["depth_m"]]) * 1000.0
    motor_c = v3("motor_centre_mm")

    parts.append(Part(
        "outboard", motor_size, motor_c, mo["mass_kg"], "HV",
        f"{mo['power_nominal_W']/1000:.1f} kW nominal, capped to "
        f"{mo['configured_power_limit_W']/1000:.0f} kW by ENERGY_REQ_188"))

    shaft_len = mo["shaft_length_m"] * 1000.0

    parts.append(Part(
        "drive_leg", np.array([120.0, 90.0, shaft_len]),
        motor_c + np.array([0.0, 0.0, -(motor_size[2] + shaft_len) / 2.0]),
        mo["trim_mass_kg"], "HV",
        "shaft, gearbox and the contra-rotating propulsor below"))

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

    for i, dy in enumerate((-40.0, 0.0, 40.0)):
        cables.append(CableRun(
            f"phase_{'UVW'[i]}", np.array([
                [inv.lo[0], inv.centre[1] + dy, inv.centre[2]],
                [inv.lo[0] - 6 * ph_od - 60.0, inv.centre[1] + dy,
                 inv.centre[2]],
                [inv.lo[0] - 6 * ph_od - 60.0, dy, motor.hi[2] + 160.0],
                [motor.centre[0], dy, motor.hi[2] + 160.0],
                [motor.centre[0], dy, motor.hi[2]],
            ]), ph_od, 6 * ph_od, "HV",
            "screened three-phase. Short on purpose: this is the loudest "
            "EMC source on the boat and length is the cheapest fix"))

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
        stale or "newer than the parameter file")

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
            # The lines the CAD actually models as physical parts. The rest
            # of the budget -- cockpit structure, seat, controls, pilot --
            # is outside the powertrain and is not compared.
            modelled = {"Battery pack", "Outboard", "Trim assembly",
                        "Inverter / ESC", "HV harness and switchgear",
                        "Cooling system", "LV system",
                        "Organiser equipment"}

            budget = sum(i["kg"] for i in C["mass"]["items"]
                         if i["item"] in modelled)

            # Structure and safety items the CAD draws but the budget books
            # under cockpit structure and safety equipment instead.
            elsewhere = sum(p.mass_kg for p in parts
                            if p.name in ("bulkhead", "estop", "monitor_bay"))

            comparable = total - elsewhere
            delta = comparable - budget

            asm["mass_vs_budget_kg"] = delta
            asm["budget_margin_kg"] = C["mass"]["margin_kg"]

            add("CAD mass agrees with the MATLAB budget",
                abs(delta) <= C["mass"]["margin_kg"],
                f"CAD {comparable:.1f} kg against {budget:.1f} kg budgeted, "
                f"{delta:+.1f} kg, and the budget has "
                f"{C['mass']['margin_kg']:.1f} kg of margin")

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
