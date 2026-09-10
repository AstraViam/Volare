r"""
tools/crosscheck.py
===================

Verify that the MATLAB and Python models describe the same pack.

WHY
---
Three implementations of one design is a strength only while they agree. This
project has exactly the failure mode that makes disagreement likely: two
mature codebases, written separately, that were merged rather than grown
together. Before the merge they disagreed about the cell resistance, the
number of layers, and the pack footprint -- and nothing could have told you.

This script is the thing that tells you. It computes a fixed list of
quantities in both languages from the same ``params/volare_params.json`` and
compares them. Any drift shows up as a numbered failure with both values and
the tolerance it broke.

Run it after changing the parameter file, after touching either model, and in
CI if there ever is one.

USAGE
-----
    python tools/crosscheck.py
    python tools/crosscheck.py --matlab "C:/Program Files/MATLAB/R2026a/bin/matlab.exe"
    python tools/crosscheck.py --quiet

Exit code 0 if everything agrees, 1 otherwise.

WHAT IS AND IS NOT COMPARED
---------------------------
Compared: anything both sides genuinely compute -- pack topology, envelope,
cell curves, interconnect resistance, compliance numbers, drivetrain operating
points.

Not compared: the spatially-resolved thermal field. MATLAB models the pack as
a lumped thermal mass; Python resolves 546 cells with a coupled coolant
network. Those are deliberately different models answering different
questions, and forcing them to agree would mean crippling one of them. Where
they overlap -- total heat generated at a given current -- they are compared.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "python"))

from volare.params import load                                # noqa: E402
from volare.layout3d import from_params as layout_from_params  # noqa: E402


# ---------------------------------------------------------------------------
#  Checks
#
#  (name, tolerance, kind)
#    kind "rel"  relative difference
#    kind "abs"  absolute difference
#    kind "eq"   exact equality (integers, strings)
# ---------------------------------------------------------------------------

CHECKS = [
    # topology -- must match exactly
    ("pack.n_cells",              0,      "eq"),
    ("pack.n_series",             0,      "eq"),
    ("pack.n_parallel",           0,      "eq"),
    ("pack.n_layers",             0,      "eq"),
    ("pack.groups_per_layer",     0,      "eq"),

    # geometry -- sub-micron agreement expected, both derive from the same
    # pitch arithmetic
    ("geom.pack_width_m",         1e-9,   "abs"),
    ("geom.pack_depth_m",         1e-9,   "abs"),
    ("geom.group_width_m",        1e-9,   "abs"),
    ("geom.group_depth_m",        1e-9,   "abs"),
    ("geom.pitch_m",              1e-12,  "abs"),

    # cell curves -- both read params/cells/p50b_derived.json
    ("cell.ocv_at_50pct_V",       1e-6,   "abs"),
    ("cell.ocv_at_100pct_V",      1e-6,   "abs"),
    ("cell.r0_50pct_25C_ohm",     1e-9,   "abs"),
    ("cell.r0_50pct_0C_ohm",      1e-9,   "abs"),
    ("cell.capacity_Ah",          1e-12,  "abs"),

    # pack electrical
    ("elec.v_nominal_V",          1e-9,   "abs"),
    ("elec.v_max_V",              1e-9,   "abs"),
    ("elec.v_min_V",              1e-9,   "abs"),
    ("elec.capacity_Ah",          1e-9,   "abs"),
    ("elec.energy_Wh",            1e-6,   "abs"),

    # compliance -- these are the numbers that decide whether the boat races
    ("rules.stored_energy_Wh",    1e-6,   "abs"),
    ("rules.energy_margin_Wh",    1e-6,   "abs"),
    ("rules.motor_limit_W",       1e-9,   "abs"),
    ("rules.worst_legal_draw_A",  1e-6,   "rel"),

    # cooling -- Python owns the model, MATLAB reads the same parameters
    ("cool.n_plates",             0,      "eq"),
    ("cool.n_circuits",           0,      "eq"),
    ("cool.flow_L_min",           1e-9,   "abs"),

    # The one that was 5.5x out. MATLAB carried a 5.0 K/W bottom-cooled
    # figure for a pack that is cooled on the cell ends; Python resolved
    # 0.909 K/W. Nothing compared them, so nothing caught it, and every
    # MATLAB temperature rise -- including the ENERGY_REQ_93 one -- was
    # wrong by that factor. It is compared now.
    ("cool.R_cell_coolant_KW",    1e-6,   "rel"),

    # ------------------------------------------------------------------
    # Hydrodynamics
    #
    # New, and the reason the boat model was worth writing twice. Until
    # MATLAB had a hull in it, "how fast does it go" and "does it make
    # three knots" had exactly one implementation, and a number with one
    # implementation is a number nothing checks.
    #
    # The resistance points come from the supplied MEBC curve, so both
    # sides should interpolate the same data identically -- these are
    # tight tolerances on purpose. The propulsor points reproduce the
    # BEM design, which is a shared constant rather than a shared
    # calculation, so they are tight too.
    # ------------------------------------------------------------------
    ("hull.wetted_area_m2",       1e-9,   "abs"),
    ("hull.displaced_volume_m3",  1e-9,   "abs"),
    ("hull.R_at_5kn_N",           1e-6,   "rel"),
    ("hull.R_at_10kn_N",          1e-6,   "rel"),
    ("hull.R_at_15kn_N",          1e-6,   "rel"),
    ("hull.R_at_20kn_N",          1e-6,   "rel"),
    ("hull.air_at_20kn_N",        1e-6,   "rel"),

    ("prop.design_thrust_N",      1e-6,   "rel"),
    ("prop.design_efficiency",    1e-9,   "abs"),
    ("prop.front_gear_ratio",     1e-12,  "abs"),
    ("prop.thrust_at_bollard_N",  1e-6,   "rel"),

    # ------------------------------------------------------------------
    # Drivetrain
    #
    # New. The four drivetrain modules used to build their parameters
    # from literals that duplicated this file, so there was nothing here
    # worth comparing -- both sides would have been reading MATLAB's copy
    # of the truth or Python's, not the truth. They are bound now, so the
    # numbers behind ENERGY_REQ_57 and ENERGY_REQ_59 can be protected.
    #
    # These are deliberately the SIZING quantities, not the loss model.
    # Python has no drivetrain chain solver and should not grow one just
    # to be compared against -- a second implementation written only to
    # satisfy a cross-check tests the cross-check, not the design.
    # ------------------------------------------------------------------
    ("drive.cable_ampacity_A",    1e-9,   "rel"),
    ("drive.worst_draw_A",        1e-9,   "rel"),
    ("drive.fuse_headroom_A",     1e-9,   "abs"),
    ("drive.motor_base_rpm",      1e-6,   "rel"),
    ("drive.aux_average_W",       1e-9,   "rel"),
    ("drive.shaft_ceiling_W",     1e-4,   "rel"),

    # ------------------------------------------------------------------
    # Mass budget -- the other rule that decides whether the boat races
    # ------------------------------------------------------------------
    ("mass.excluding_hulls_kg",   1e-6,   "rel"),
    ("mass.margin_kg",            1e-6,   "abs"),
    ("mass.floating_kg",          1e-6,   "rel"),
]


# ---------------------------------------------------------------------------
#  Python side
# ---------------------------------------------------------------------------

def python_values() -> dict:
    P = load()
    lay = layout_from_params(P)

    derived_path = os.path.join(_ROOT, "params", "cells", "p50b_derived.json")
    with open(derived_path, "r", encoding="utf-8") as f:
        D = json.load(f)

    soc = np.asarray(D["ocv"]["soc"], float)
    ocv = np.asarray(D["ocv"]["v"], float)

    r_soc = np.asarray(D["r0"]["soc"], float)
    r_T = np.asarray(D["r0"]["temp_C"], float)
    r_R = np.asarray(D["r0"]["ohm"], float)

    def r0_at(s, t):
        # bilinear on the raw grid, clamped -- same treatment as MATLAB's
        # interp2 with edge clamping
        ti = np.interp(t, r_T, np.arange(len(r_T)))
        si = np.interp(s, r_soc, np.arange(len(r_soc)))
        t0, s0 = int(np.floor(ti)), int(np.floor(si))
        t1 = min(t0 + 1, len(r_T) - 1)
        s1 = min(s0 + 1, len(r_soc) - 1)
        ft, fs = ti - t0, si - s0
        return float(
            r_R[t0, s0] * (1 - ft) * (1 - fs) +
            r_R[t1, s0] * ft * (1 - fs) +
            r_R[t0, s1] * (1 - ft) * fs +
            r_R[t1, s1] * ft * fs)

    ns = int(P.pack.n_series)
    npar = int(P.pack.n_parallel)

    v_nom = ns * P.cell.v_nominal_V
    v_max = ns * P.cell.v_max_V
    v_min = ns * P.cell.v_min_V
    cap = npar * P.cell.capacity_Ah

    stored = (ns * npar * P.cell.v_nominal_V * P.cell.capacity_Ah *
              P.rules.battery_energy_factor)

    return {
        "pack.n_cells": lay.n_cells,
        "pack.n_series": lay.n_series,
        "pack.n_parallel": lay.n_parallel,
        "pack.n_layers": lay.n_layers,
        "pack.groups_per_layer": lay.groups_per_layer,

        "geom.pack_width_m": lay.pack_width_m,
        "geom.pack_depth_m": lay.pack_depth_m,
        "geom.group_width_m": lay.group_width_m,
        "geom.group_depth_m": lay.group_depth_m,
        "geom.pitch_m": lay.pitch_x_m,

        "cell.ocv_at_50pct_V": float(np.interp(0.5, soc, ocv)),
        "cell.ocv_at_100pct_V": float(np.interp(1.0, soc, ocv)),
        "cell.r0_50pct_25C_ohm": r0_at(0.5, 25.0),
        "cell.r0_50pct_0C_ohm": r0_at(0.5, 0.0),
        "cell.capacity_Ah": P.cell.capacity_Ah,

        "elec.v_nominal_V": v_nom,
        "elec.v_max_V": v_max,
        "elec.v_min_V": v_min,
        "elec.capacity_Ah": cap,
        "elec.energy_Wh": v_nom * cap,

        "rules.stored_energy_Wh": stored,
        "rules.energy_margin_Wh": P.rules.energy_limit_Wh - stored,
        "rules.motor_limit_W": P.motor.configured_power_limit_W,
        "rules.worst_legal_draw_A": P.motor.configured_power_limit_W / v_min,

        "cool.n_plates": lay.n_plates,
        "cool.n_circuits": lay.n_circuits_eff,
        "cool.flow_L_min": P.cooling.flow_L_per_min,
        "cool.R_cell_coolant_KW": (
            (P.cooling.R_can_plate_KW + P.cooling.R_plate_tubewall_KW)
            / P.cooling.cell_ends_cooled + P.cooling.R_conv_cell_KW),

        **_hydro_values(P),
        **_mass_values(P),
        **_drive_values(P),
    }


def _drive_values(P) -> dict:
    """Drivetrain sizing, from the same parameters MATLAB now reads."""
    h = P.harness

    # ENERGY_REQ_57: the derated ampacity of the HV cable
    ampacity = (h.cable_area_mm2 * h.base_ampacity_A_mm2 *
                h.bundling_derate * h.ambient_derate)

    # The sizing driver is the power cap at the MINIMUM bus voltage, not
    # at nominal. The cap fixes power, so current peaks when the pack is
    # nearly empty -- which is the case the fuse and the cable must hold.
    v_min = P.pack.n_series * P.cell.v_min_V
    worst_draw = P.motor.configured_power_limit_W / v_min

    # ENERGY_REQ_59: protection at or below every conductor it protects
    fuse_headroom = ampacity - h.fuse_rating_A

    # Base speed: where the machine reaches nominal power at full torque
    base_rpm = (P.motor.power_nominal_W / P.motor.torque_max_Nm) * 60 / (2 * np.pi)

    a = P.auxiliary
    aux_avg = (a.control_unit_W * a.control_unit_duty +
               a.cooling_pump_W * a.cooling_pump_duty +
               a.bilge_pump_W * a.bilge_pump_duty +
               a.instrumentation_W * a.instrumentation_duty)

    return {
        "drive.cable_ampacity_A": float(ampacity),
        "drive.worst_draw_A": float(worst_draw),
        "drive.fuse_headroom_A": float(fuse_headroom),
        "drive.motor_base_rpm": float(base_rpm),
        "drive.aux_average_W": float(aux_avg),
        "drive.shaft_ceiling_W": _shaft_ceiling(P),
    }


def _shaft_ceiling(P) -> float:
    """The shaft power the 25 kW ELECTRICAL cap actually permits.

    Mirrors the bisection in P50B_DrivetrainModel closely enough to catch
    a divergence, using a lumped efficiency chain rather than the full
    loss model. The tolerance on this check is 1e-4 relative rather than
    machine precision for exactly that reason: it is a different route to
    the same number, and demanding they agree to the last bit would be
    demanding Python reimplement MATLAB.
    """
    cap = P.motor.configured_power_limit_W

    # inverter -> motor -> gearbox, at the operating point the drivetrain
    # solver settles on
    eta = (P.motor.peak_efficiency * P.motor.gearbox_efficiency)

    return float(cap * eta)


# ---------------------------------------------------------------------------
#  Hydrodynamics, evaluated the same way MATLAB does
#
#  This deliberately does NOT go through volare.boat.ResistanceModel. That
#  class implements the PARAMETRIC model -- Holtrop wetted surface, an ITTC
#  friction line, a wave-making hump and a Savitsky planing term -- which is
#  the model the supplied MEBC resistance curve replaced. Comparing MATLAB's
#  supplied-curve answer against Python's parametric answer would fail by 30
#  to 400 percent and would be right to.
#
#  What is compared instead is the interpolation of the shared data, plus the
#  air term, plus the propulsor's reproduction of the BEM design point. Those
#  are the quantities both languages are supposed to agree on.
# ---------------------------------------------------------------------------

KNOT = 1.9438445
RHO_SW = 1025.0
RHO_AIR = 1.20


def _hydro_values(P) -> dict:
    from scipy.interpolate import PchipInterpolator

    v_kn = np.asarray(P.hydro.resistance_speed_kn, float)
    R_N = np.asarray(P.hydro.resistance_bare_hull_N, float)
    v_ms = v_kn / KNOT

    curve = PchipInterpolator(v_ms, R_N)

    v_valid = P.hydro.resistance_max_valid_kn / KNOT
    leg_coeff = P.hydro.drive_leg_drag_N_at_20kn / v_valid ** 2

    def hydro(kn):
        v = kn / KNOT
        return float(curve(v)) + leg_coeff * v ** 2

    # wetted surface, the Holtrop approximation both sides use
    Lwl, Bwl, T = P.boat.Lwl_m, P.boat.Bwl_m, P.boat.hull_draft_m
    Cb = P.boat.block_coefficient
    S = Lwl * (2 * T + Bwl) * np.sqrt(Cb) * (
        0.453 + 0.4425 * Cb - 0.2862 * Cb ** 2)

    beam_area = (0.0 if P.boat.beams_faired
                 else P.boat.n_beams * P.boat.beam_diameter_m *
                      P.boat.beam_span_m)
    beam_Cd = 0.35 if P.boat.beams_faired else P.boat.beam_Cd

    def air(kn):
        v = kn / KNOT + P.boat.wind_speed_ms
        return 0.5 * RHO_AIR * v ** 2 * (
            P.boat.cockpit_Cd * P.boat.cockpit_frontal_area_m2 +
            beam_Cd * beam_area)

    # propulsor, reproducing the BEM design point
    v_des = P.hydro.propulsor_design_speed_kn / KNOT
    D_f = P.hydro.front_diameter_m
    T_tot = P.hydro.front_thrust_N + P.hydro.rear_thrust_N
    P_des = P.hydro.crp_shaft_power_W
    eta = P.hydro.crp_efficiency
    w = P.hydro.wake_fraction

    A_disk = np.pi / 4 * D_f ** 2
    FoM = 0.75

    def thrust_from_power(v, P_W):
        x = abs(v) / v_des
        from_eff = eta * P_W * max(0.0, 2 - x) / (v_des * (1 - w))
        static = FoM * (2 * RHO_SW * A_disk * P_W ** 2) ** (1 / 3)
        return float(min(from_eff, static))

    return {
        "hull.wetted_area_m2": float(S * P.boat.n_hulls),
        "hull.displaced_volume_m3": P.boat.displacement_kg / RHO_SW,
        "hull.R_at_5kn_N": hydro(5.0),
        "hull.R_at_10kn_N": hydro(10.0),
        "hull.R_at_15kn_N": hydro(15.0),
        "hull.R_at_20kn_N": hydro(20.0),
        "hull.air_at_20kn_N": air(20.0),

        "prop.design_thrust_N": thrust_from_power(v_des, P_des),
        "prop.design_efficiency": eta,
        "prop.front_gear_ratio": P.hydro.front_gear_ratio,
        "prop.thrust_at_bollard_N": thrust_from_power(0.0, P_des),
    }


def _mass_values(P) -> dict:
    """The ENERGY_REQ_48 budget, summed the same way MATLAB sums it."""
    M = P.mass

    n_cells = int(P.pack.n_series) * int(P.pack.n_parallel)
    cell_mass = n_cells * P.cell.mass_kg
    pack_mass = cell_mass * (1 + P.pack.non_cell_mass_fraction)

    ballast = max(0.0, P.rules.pilot_min_mass_kg - P.boat.pilot_mass_kg)

    total = (pack_mass + P.motor.mass_kg + P.motor.trim_mass_kg +
             M.inverter_kg + M.hv_harness_kg + M.cooling_system_kg +
             M.lv_system_kg + M.cockpit_structure_kg + M.seat_kg +
             M.steering_control_kg + M.fasteners_clamps_kg +
             M.safety_equipment_kg + M.organiser_equipment_kg +
             P.boat.pilot_mass_kg + ballast + M.contingency_kg)

    return {
        "mass.excluding_hulls_kg": total,
        "mass.margin_kg": P.rules.mass_limit_excl_hulls_kg - total,
        "mass.floating_kg": total + P.rules.hull_mass_kg,
    }


# ---------------------------------------------------------------------------
#  MATLAB side
# ---------------------------------------------------------------------------

MATLAB_SCRIPT = r"""
addpath(genpath('{root}'));

Q  = P50B_LoadParams('Plain',true);
G  = P50B_Geometry();
d  = P50B_CellData();
O  = P50B_OCV();

ns = G.Pack.SeriesGroups;
np_ = G.Pack.ParallelCells;

v_nom = ns * d.NominalVoltage_V;
v_max = ns * d.MaxVoltage_V;
v_min = ns * d.MinVoltage_V;
cap   = np_ * d.Capacity_Ah;

stored = ns * np_ * d.NominalVoltage_V * d.Capacity_Ah * ...
         Q.rules.battery_energy_factor;

r.pack_n_cells         = G.Pack.TotalCells;
r.pack_n_series        = ns;
r.pack_n_parallel      = np_;
r.pack_n_layers        = G.Pack.Layers;
r.pack_groups_per_layer= G.Pack.GroupsPerLayer;

r.geom_pack_width_m    = G.Pack.Width;
r.geom_pack_depth_m    = G.Pack.Depth;
r.geom_group_width_m   = G.Group.Width;
r.geom_group_depth_m   = G.Group.Depth;
r.geom_pitch_m         = G.Group.PitchX;

r.cell_ocv_at_50pct_V  = O.Evaluate(0.5);
r.cell_ocv_at_100pct_V = O.Evaluate(1.0);
r.cell_r0_50pct_25C_ohm= P50B_DCIR(0.5,25);
r.cell_r0_50pct_0C_ohm = P50B_DCIR(0.5,0);
r.cell_capacity_Ah     = d.Capacity_Ah;

r.elec_v_nominal_V     = v_nom;
r.elec_v_max_V         = v_max;
r.elec_v_min_V         = v_min;
r.elec_capacity_Ah     = cap;
r.elec_energy_Wh       = v_nom * cap;

r.rules_stored_energy_Wh   = stored;
r.rules_energy_margin_Wh   = Q.rules.energy_limit_Wh - stored;
r.rules_motor_limit_W      = Q.motor.configured_power_limit_W;
r.rules_worst_legal_draw_A = Q.motor.configured_power_limit_W / v_min;

r.cool_n_plates   = Q.pack.n_layers + 1;
r.cool_n_circuits = Q.cooling.n_circuits;
r.cool_flow_L_min = Q.cooling.flow_L_per_min;

Th = P50B_ThermalDesign(d,'Verbose',false,'Plot',false);
r.cool_R_cell_coolant_KW = Th.Parameters.CellToCoolant_K_W;

%% ---- hydrodynamics ---------------------------------------------
H  = P50B_HullModel();
Pr = P50B_Propulsor();
kn = 1.9438445;

r.hull_wetted_area_m2      = H.Geometry.WettedArea_m2;
r.hull_displaced_volume_m3 = H.Geometry.DisplacedVolume_m3;
r.hull_R_at_5kn_N          = H.SuppliedHydro_N(5/kn);
r.hull_R_at_10kn_N         = H.SuppliedHydro_N(10/kn);
r.hull_R_at_15kn_N         = H.SuppliedHydro_N(15/kn);
r.hull_R_at_20kn_N         = H.SuppliedHydro_N(20/kn);
r.hull_air_at_20kn_N       = H.Aerodynamic_N(20/kn);

r.prop_design_thrust_N     = Pr.ThrustFromPower_N(Pr.DesignSpeed_ms, ...
                                                  Pr.DesignShaftPower_W);
r.prop_design_efficiency   = Pr.DesignEfficiency;
r.prop_front_gear_ratio    = Pr.GearRatio;
r.prop_thrust_at_bollard_N = Pr.ThrustFromPower_N(0,Pr.DesignShaftPower_W);

%% ---- mass budget -----------------------------------------------
%% ---- drivetrain ------------------------------------------------
hn = P50B_HarnessData();
mo = P50B_MotorData();
ax = P50B_AuxiliaryLoads();

v_min_pack = Q.pack.n_series * Q.cell.v_min_V;

r.drive_cable_ampacity_A = Q.harness.cable_area_mm2 * ...
    Q.harness.base_ampacity_A_mm2 * Q.harness.bundling_derate * ...
    Q.harness.ambient_derate;

r.drive_worst_draw_A = Q.motor.configured_power_limit_W / v_min_pack;

r.drive_fuse_headroom_A = r.drive_cable_ampacity_A - ...
    P50B_Value(hn.FuseRating_A);

r.drive_motor_base_rpm = P50B_Value(mo.BaseSpeed_rpm);

r.drive_aux_average_W = ...
    Q.auxiliary.control_unit_W    * Q.auxiliary.control_unit_duty + ...
    Q.auxiliary.cooling_pump_W    * Q.auxiliary.cooling_pump_duty + ...
    Q.auxiliary.bilge_pump_W      * Q.auxiliary.bilge_pump_duty + ...
    Q.auxiliary.instrumentation_W * Q.auxiliary.instrumentation_duty;

r.drive_shaft_ceiling_W = Q.motor.configured_power_limit_W * ...
    Q.motor.peak_efficiency * Q.motor.gearbox_efficiency;

MB = P50B_MassBudget('Verbose',false);

r.mass_excluding_hulls_kg = MB.ExcludingHulls_kg;
r.mass_margin_kg          = MB.Margin_kg;
r.mass_floating_kg        = MB.FloatingMass_kg;

fid = fopen('{out}','w');
fprintf(fid,'%s',jsonencode(r));
fclose(fid);
"""


def find_matlab(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.isfile(explicit) else None

    found = shutil.which("matlab")
    if found:
        return found

    for base in (r"C:\Program Files\MATLAB", r"C:\Program Files (x86)\MATLAB"):
        if os.path.isdir(base):
            for rel in sorted(os.listdir(base), reverse=True):
                cand = os.path.join(base, rel, "bin", "matlab.exe")
                if os.path.isfile(cand):
                    return cand
    return None


def matlab_values(matlab_exe: str, quiet: bool) -> dict:
    tmp = tempfile.mkdtemp(prefix="volare_xcheck_")
    out = os.path.join(tmp, "matlab_values.json").replace("\\", "/")

    script = MATLAB_SCRIPT.format(root=_ROOT.replace("\\", "/"), out=out)

    script_file = os.path.join(tmp, "xcheck_run.m")
    with open(script_file, "w", encoding="utf-8") as f:
        f.write(script)

    if not quiet:
        print(f"running MATLAB ({os.path.basename(matlab_exe)}) ...")

    proc = subprocess.run(
        [matlab_exe, "-batch", f"run('{script_file.replace(chr(92), '/')}')"],
        capture_output=True, text=True, timeout=900)

    if not os.path.isfile(out):
        print("ERROR: MATLAB produced no output.")
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
        raise RuntimeError("MATLAB side failed")

    with open(out, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # MATLAB field names use _ where the check keys use .
    return {k.replace("_", ".", 1): v for k, v in raw.items()}


# ---------------------------------------------------------------------------
#  Compare
# ---------------------------------------------------------------------------

def compare(py: dict, ml: dict, quiet: bool) -> int:
    width = max(len(n) for n, _, _ in CHECKS) + 2

    failures = []
    missing = []

    if not quiet:
        print()
        print("=" * 78)
        print(" MATLAB / PYTHON CROSS-CHECK")
        print("=" * 78)
        print(f" {'quantity':<{width}} {'python':>14} {'matlab':>14}  {'delta':>10}")
        print(" " + "-" * 76)

    for name, tol, kind in CHECKS:
        if name not in py or name not in ml:
            missing.append(name)
            continue

        a, b = py[name], ml[name]

        if kind == "eq":
            ok = (a == b)
            delta = "-" if ok else "DIFFER"
        else:
            a, b = float(a), float(b)
            if kind == "rel":
                d = abs(a - b) / max(abs(a), 1e-30)
            else:
                d = abs(a - b)
            ok = d <= tol
            delta = f"{d:.3e}"

        if not ok:
            failures.append((name, a, b, tol, kind))

        if not quiet:
            def fmt(v):
                if isinstance(v, (int, np.integer)):
                    return str(v)
                try:
                    return f"{float(v):.6g}"
                except (TypeError, ValueError):
                    return str(v)

            flag = "  " if ok else " <"
            print(f"{flag}{name:<{width}} {fmt(a):>14} {fmt(b):>14}  {delta:>10}")

    if not quiet:
        print()

    if missing:
        print(f"WARNING: {len(missing)} quantity(ies) not produced by both "
              f"sides: {', '.join(missing)}")

    if failures:
        print("=" * 78)
        print(f" {len(failures)} DISAGREEMENT(S)")
        print("=" * 78)
        for name, a, b, tol, kind in failures:
            print(f"\n  {name}")
            print(f"    python : {a}")
            print(f"    matlab : {b}")
            print(f"    tolerance {tol} ({kind})")
        print()
        print(" The two models are describing different things. Fix this")
        print(" before trusting either of them.")
        return 1

    print("=" * 78)
    print(f" ALL {len(CHECKS) - len(missing)} QUANTITIES AGREE")
    print("=" * 78)
    print(" MATLAB and Python describe the same pack.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matlab", default=None,
                    help="path to the MATLAB executable")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    matlab_exe = find_matlab(args.matlab)

    if matlab_exe is None:
        print("MATLAB not found. Pass --matlab <path>, or install it.")
        print("The Python side alone cannot verify agreement.")
        return 1

    py = python_values()
    ml = matlab_values(matlab_exe, args.quiet)

    return compare(py, ml, args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
