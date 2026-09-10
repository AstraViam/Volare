r"""
tools/build_mission_control.py
==============================

Regenerate Mission Control from the unified parameter file.

WHAT THIS FIXES
---------------
``web/mission_control.html`` carries a generated model blob -- pack geometry,
tube paths, thermal network, cell curves -- baked in as a JavaScript literal.
That blob was produced from the *flat* 26x21 layout and says ``nLayers: 1``.

Meanwhile the MATLAB model describes a two-layer pack, and the cell curves now
come from the digitised datasheet rather than a typical-NMC shape. Left alone,
Mission Control would keep showing a boat that no longer exists.

This script rebuilds that blob from ``params/volare_params.json`` and the
two-layer end-plate layout, then splices it back into the page. It also injects
two new blocks the page did not previously have:

* ``VOLARE_PARAMS``     every parameter with its unit and provenance tag
* ``VOLARE_COMPLIANCE`` the Monaco rule results

so the dashboard can show where a number came from, not just what it is.

USAGE
-----
    python tools/build_mission_control.py

    --check     verify the page is up to date without writing (exit 1 if not)
    --out PATH  write somewhere other than web/mission_control.html

The page keeps its own physics engine and every existing feature. Only the
data it is built on is replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "python"))

from volare.params import load, load_cell_dataset          # noqa: E402
from volare.celldata import CellDataset                     # noqa: E402
from volare.layout3d import from_params as layout_from_params  # noqa: E402
import volare.pack_thermal as pt                            # noqa: E402
import volare.boat as bt                                    # noqa: E402
import volare.track as tk                                   # noqa: E402
from volare import webexport                                # noqa: E402


HTML = os.path.join(_ROOT, "web", "mission_control.html")
MATLAB_COMPLIANCE = os.path.join(_ROOT, "output", "P50B_Compliance.json")
DERIVED = os.path.join(_ROOT, "params", "cells", "p50b_derived.json")
RAW_CELLS = os.path.join(_ROOT, "params", "cells", "p50b.json")

MARK_BEGIN = "/* ---- VOLARE GENERATED BLOCK: do not edit by hand ---- */"
MARK_END = "/* ---- END VOLARE GENERATED BLOCK ---- */"


# ---------------------------------------------------------------------------
#  Build the model objects from the shared parameters
# ---------------------------------------------------------------------------

def build_cell(P) -> "pt.CellParams":
    """Cell parameters, with the digitised R0 map and OCV attached."""
    cell = pt.CellParams(
        capacity_Ah=P.cell.capacity_Ah,
        v_nominal=P.cell.v_nominal_V,
        v_max=P.cell.v_max_V,
        v_min=P.cell.v_min_V,
        mass_kg=P.cell.mass_kg,
        diameter_m=P.cell.diameter_m,
        height_m=P.cell.height_m,
        cp_J_kgK=P.cell.cp_J_kgK,
        R_core_can_KW=P.cell.R_core_can_KW,
        core_mass_fraction=P.cell.core_mass_fraction,
        R1_ref_ohm=P.cell.R1_ref_ohm,
        tau1_s=P.cell.tau1_s,
        R2_ref_ohm=P.cell.R2_ref_ohm,
        tau2_s=P.cell.tau2_s,
        Ea_over_R_K=P.cell.Ea_over_R_K,
        T_warn_C=P.cell.T_warn_C,
        T_max_C=P.cell.T_max_C,
    )

    # --- attach the derived curves ------------------------------------
    if os.path.isfile(DERIVED):
        with open(DERIVED, "r", encoding="utf-8") as f:
            D = json.load(f)

        cell.ocv_soc = np.asarray(D["ocv"]["soc"], float)
        cell.ocv_v = np.asarray(D["ocv"]["v"], float)

        # Use the class's own attach method rather than poking at private
        # attributes: it owns the interpolation setup and the unit
        # conversion, and has_R0_map is a read-only property derived from it.
        cell.attach_R0_map(
            np.asarray(D["r0"]["soc"], float),
            np.asarray(D["r0"]["temp_C"], float),
            np.asarray(D["r0"]["ohm"], float),
        )

        if D.get("dudt", {}).get("soc"):
            cell.dudt_soc = np.asarray(D["dudt"]["soc"], float)
            cell.dudt_v_per_K = np.asarray(D["dudt"]["v_per_K"], float)

        cell.R0_ref_ohm = float(D["scalars"]["R0_ref_ohm"])

    else:
        # Refuse rather than silently exporting a dashboard built on the
        # analytic fallback curves. A page that looks right but is drawn
        # from different physics than MATLAB is worse than no page.
        raise FileNotFoundError(
            f"Derived cell tables not found:\n  {DERIVED}\n"
            "Run:  python tools/export_cell_tables.py\n"
            "Mission Control must be built from the same curves as the "
            "MATLAB and Python models, not from a fallback.")

    # --- cycle-life curves --------------------------------------------
    # The exporter reads these off the cell as ``_cycle_curves``. They
    # come from the raw digitised dataset rather than the derived tables,
    # because they are used as-is and need no fitting. Without them the
    # dashboard's degradation view has nothing to plot.
    try:
        ds = CellDataset.from_json(RAW_CELLS)
        curves = getattr(ds, "cycle_curves", None) or []
        cell._cycle_curves = curves
        if curves:
            rates = sorted({round(float(c.c_rate), 1) for c in curves})
            print(f"  cycle-life: {len(curves)} curves at {rates} C")
        else:
            print("  cycle-life: no curves in the dataset")
    except Exception as exc:
        print(f"  cycle-life curves unavailable ({exc})")
        cell._cycle_curves = []

    return cell


def build_coolant(P) -> "pt.Coolant":
    return pt.Coolant(
        flow_L_per_min=P.cooling.flow_L_per_min,
        inlet_T_C=P.cooling.inlet_T_C,
        rho_kg_m3=P.cooling.rho_kg_m3,
        cp_J_kgK=P.cooling.cp_J_kgK,
        mu_Pa_s=P.cooling.mu_Pa_s,
        k_W_mK=P.cooling.k_W_mK,
    )


def build_boat(P):
    """Hull, resistance model, propeller and course from the parameters."""
    hull = bt.Hull(
        Lwl_m=P.boat.Lwl_m,
        Bwl_m=P.boat.Bwl_m,
        cockpit_frontal_area_m2=P.boat.cockpit_frontal_area_m2,
        cockpit_Cd=P.boat.cockpit_Cd,
        beam_Cd=P.boat.beam_Cd,
        beams_faired=bool(P.boat.beams_faired),
        draft_m=P.boat.hull_draft_m,
        n_hulls=int(P.boat.n_hulls),
        block_coefficient=P.boat.block_coefficient,
        prismatic_coefficient=P.boat.prismatic_coefficient,
        displacement_kg=P.boat.displacement_kg,
        beam_diameter_m=P.boat.beam_diameter_m,
        beam_span_m=P.boat.beam_span_m,
        n_beams=int(P.boat.n_beams),
    )

    # ResistanceModel takes the hull directly. Verified against the
    # dataclass fields rather than guessed: a "try this signature, fall
    # back to that one" pattern hides which one actually ran, and a
    # silently different resistance model is a silently different range.
    # The MEBC-supplied resistance curve, not the parametric correlation.
    # The correlation applied a planing model to a slender demihull that
    # does not plane and was 30 to 400 percent high; see the class
    # docstring. The browser engine gets this sampled onto a speed grid,
    # so replacing it here reaches the dashboard's own physics too.
    resistance = bt.SuppliedResistance.from_params(P, hull)

    prop = bt.Propeller(
        diameter_m=P.boat.prop_diameter_m,
        pitch_ratio=P.boat.prop_pitch_ratio,
        blade_area_ratio=P.boat.prop_blade_area_ratio,
        n_blades=int(P.boat.prop_n_blades),
        wake_fraction=P.boat.wake_fraction,
        thrust_deduction=P.boat.thrust_deduction,
        rel_rotative_eff=P.boat.rel_rotative_eff,
        gear_ratio=P.motor.gearbox_ratio,
    )

    course = bt.RaceCourse(lateral_g_limit=P.boat.lateral_g_limit)

    return hull, resistance, prop, course


def build_courses(P, hull, resistance, prop, energy_kWh):
    """Every official Monaco course, plus a pacing strategy for each.

    The dashboard lets the event be switched live, so all five are
    exported rather than only the one selected here. Without this the
    Circuit card has nothing to draw and the whole Strategy view is
    empty -- which is exactly the state the page was in before.
    """
    courses = {}

    keys = ("endurance", "qualifying", "championship_outer",
            "championship_inner", "slalom")

    for key in keys:
        if key not in tk.COURSES:
            print(f"  (course '{key}' not available, skipping)")
            continue

        t = tk.COURSES[key]()
        t.lateral_g_limit = P.boat.lateral_g_limit
        t._build()

        dyn = bt.BoatDynamics(
            hull, resistance, prop,
            mass_kg=P.boat.displacement_kg,
            P_shaft_max_W=P.motor.configured_power_limit_W)

        best, rows = tk.endurance_strategy(dyn, t, energy_kWh=energy_kWh)

        courses[key] = dict(
            track=webexport.export_track(t),
            strategy=dict(
                best=best, rows=rows,
                note=(f"{t.event}: {t.length:.0f} m lap, "
                      f"{t.time_limit_s/60:.0f} min limit")))

    return courses


# ---------------------------------------------------------------------------
#  Compliance summary for the dashboard
# ---------------------------------------------------------------------------

def matlab_compliance() -> dict | None:
    """The authoritative compliance result, if MATLAB has exported one.

    The rules are read once, in MATLAB, by ``P50B_MonacoCompliance``. A
    second reading here would not cross-check anything -- it would just be
    a second thing that can be wrong, in a file nobody opens. So the full
    result is imported rather than recomputed, and only the handful of
    quantities the browser engine needs live are kept below.

    Returns None if the export is missing or stale-looking, in which case
    the dashboard falls back to the small recomputed subset and says so.
    """
    if not os.path.isfile(MATLAB_COMPLIANCE):
        print("  (no MATLAB compliance export -- run "
              "matlab -batch P50B_ExportCompliance)")
        return None

    try:
        with open(MATLAB_COMPLIANCE, "r", encoding="utf-8") as f:
            D = json.load(f)
    except Exception as exc:
        print(f"  WARNING: could not read the compliance export ({exc})")
        return None

    n = D.get("summary", {}).get("total", 0)

    if not n:
        print("  WARNING: the compliance export has no checks in it")
        return None

    age_s = os.path.getmtime(HTML) - os.path.getmtime(MATLAB_COMPLIANCE)

    if age_s > 0:
        print(f"  NOTE: the compliance export is older than the page it is "
              f"going into. Rerun P50B_ExportCompliance if the model has "
              f"changed since.")

    print(f"  MATLAB compliance: {n} checks, "
          f"{D['summary']['pass']} pass, {D['summary']['fail']} fail, "
          f"{D['summary']['action']} to action")

    return D


def compliance_block(P) -> dict:
    """The Monaco numbers the dashboard should be able to show live.

    Mirrors MATLAB's ``P50B_MonacoCompliance``, restricted to the quantities
    that can be recomputed in the browser as the boat runs.
    """
    n_cells = int(P.pack.n_series) * int(P.pack.n_parallel)

    stored_Wh = (n_cells * P.cell.v_nominal_V * P.cell.capacity_Ah *
                 P.rules.battery_energy_factor)

    limit_Wh = P.rules.energy_limit_Wh

    v_max = P.pack.n_series * P.cell.v_max_V
    v_min = P.pack.n_series * P.cell.v_min_V
    v_nom = P.pack.n_series * P.cell.v_nominal_V

    return dict(
        rulesDocument=P.rules.document,
        rulesIssued=P.rules.issued,

        energy=dict(
            req="ENERGY_REQ_7",
            storedWh=round(stored_Wh, 1),
            limitWh=limit_Wh,
            marginWh=round(limit_Wh - stored_Wh, 1),
            marginPct=round(100.0 * (limit_Wh - stored_Wh) / limit_Wh, 3),
            maxCellsAllowed=int(limit_Wh //
                                (P.cell.v_nominal_V * P.cell.capacity_Ah)),
            pass_=stored_Wh < limit_Wh,
        ),

        power=dict(
            req="ENERGY_REQ_188",
            hardwareNominalW=P.motor.power_nominal_W,
            hardwarePeakW=P.motor.power_max_W,
            configuredLimitW=P.motor.configured_power_limit_W,
            limitW=P.rules.motor_power_limit_W,
            derateRequired=P.motor.power_nominal_W > P.rules.motor_power_limit_W,
            note=("Cap applies to motor ELECTRICAL input, not shaft power. "
                  "A 25 kW shaft cap would draw 26.9 kW and break the rule."),
        ),

        voltage=dict(
            req="ENERGY_REQ_187 / 191",
            packMaxV=round(v_max, 2),
            packNomV=round(v_nom, 2),
            packMinV=round(v_min, 2),
            thresholdV=P.rules.hv_approval_threshold_V,
            approvalRequired=v_max > P.rules.hv_approval_threshold_V,
        ),

        thermal=dict(
            req="ENERGY_REQ_68 / 93",
            cellMaxC=P.cell.T_cutoff_C,
            warnAtC=round(P.rules.temp_warn_fraction * P.cell.T_cutoff_C, 1),
            designLimitC=P.cell.T_warn_C,
            exposedMaxC=P.rules.exposed_part_max_C,
        ),

        protection=dict(
            req="ENERGY_REQ_59",
            fuseA=P.harness.fuse_rating_A,
            worstLegalDrawA=round(
                P.motor.configured_power_limit_W / v_min, 1),
        ),
    )


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------

def build_payload() -> dict:
    P = load()

    print("building pack layout ...")
    geom = layout_from_params(P)

    print(f"  {geom.n_series}S{geom.n_parallel}P, {geom.n_cells} cells, "
          f"{geom.n_layers} layers")
    print(f"  {geom.n_plates} cold plates, {geom.n_tubes} tubes, "
          f"{geom.n_circuits_eff} circuits")

    if geom.has_orphans:
        print(f"  WARNING: {len(geom.orphaned_cells)} orphaned cells")

    cell = build_cell(P)
    coolant = build_coolant(P)
    hull, resistance, prop, course = build_boat(P)

    # --- what the boat actually has, not what the rules allow ---------
    # The regulatory ceiling is 10 kWh; this pack holds 9.828 kWh. Pacing
    # and range must use the real number. Using the cap would overstate
    # endurance by 1.7% -- small, but it is the difference between
    # finishing and not, and the compliance block already carries the
    # cap separately for the REQ_7 check.
    pack_energy_kWh = (int(P.pack.n_series) * int(P.pack.n_parallel) *
                       P.cell.v_nominal_V * P.cell.capacity_Ah) / 1000.0

    print(f"  pack energy {pack_energy_kWh:.3f} kWh "
          f"(regulatory cap {P.rules.energy_limit_Wh/1000:.1f} kWh)")

    # --- cell population spread ---------------------------------------
    # The pack is not 546 identical cells. Manufacturing spread is what
    # actually drives current hogging, so the dashboard should show a
    # realistic population rather than a fiction.
    cap_mult, res_mult = pt.make_population(
        geom.n_cells,
        sigma_capacity=P.simulation.sigma_capacity,
        sigma_resistance=P.simulation.sigma_resistance,
        correlation=P.simulation.population_correlation,
        rng=np.random.default_rng(17))

    # --- courses and pacing strategy ----------------------------------
    print("building courses and pacing strategy ...")
    courses = build_courses(P, hull, resistance, prop, pack_energy_kWh)
    print(f"  {len(courses)} course(s): {', '.join(courses)}")

    default_key = "endurance" if "endurance" in courses else next(iter(courses))
    track_obj = tk.COURSES[default_key]()
    track_obj.lateral_g_limit = P.boat.lateral_g_limit
    track_obj._build()

    strategy = courses[default_key]["strategy"]
    best = strategy["best"]
    print(f"  optimum pace {best['P_shaft_W']/1000:.1f} kW -> "
          f"{best['v_kmh']:.1f} km/h, {best['laps']:.1f} laps, "
          f"limited by {best['limited_by'].upper()}")

    # --- digital-twin observer ----------------------------------------
    # Six thermistors reconstructing all 546 cells. Without this the
    # dashboard runs open loop, which is exactly the failure mode the
    # observer exists to prevent.
    print("fitting digital-twin observer ...")
    try:
        observer = webexport.build_observer(
            geom, cell, coolant, n_sensors=6, n_ensemble=12,
            seconds=720, dt=2.0)
        print(f"  {len(observer['cells'])} thermistors, field error "
              f"{observer['rms_open']:.3f} K open loop -> "
              f"{observer['rms_closed']:.3f} K with the observer "
              f"({observer['rms_open']/max(observer['rms_closed'],1e-9):.1f}x)")
    except Exception as exc:
        print(f"  observer fit failed ({exc}); exporting without it")
        observer = None

    print("exporting model for the browser engine ...")
    model = webexport.export_model(
        geom, cell, coolant, hull, resistance, prop, course,
        mass_kg=P.boat.displacement_kg,
        P_shaft_max_W=P.motor.configured_power_limit_W,
        energy_cap_kWh=pack_energy_kWh,
        T_ambient_C=P.simulation.ambient_C,
        cap_mult=cap_mult, res_mult=res_mult,
        track=track_obj,
        strategy=strategy,
        observer=observer,
        courses=courses,
    )

    # --- provenance strip shown on the dashboard ----------------------
    counts = P.counts()
    model["provenance"] = [
        ["cell curves", "digitised datasheet (params/cells/p50b.json)"],
        ["pack layout", f"{geom.n_layers}-layer, {geom.n_series}S"
                        f"{geom.n_parallel}P"],
        ["cooling", f"end plates, {geom.n_tubes} tubes / "
                    f"{geom.n_circuits_eff} circuits"],
        ["course", track_obj.name],
        ["drivetrain", "ESTIMATED - awaiting manufacturer torque map"],
        ["inverter", "NOT SELECTED - Competr lists it on request"],
        ["parameters", f"{len(P.flat())} tracked, "
                       f"{counts.get('ASSUMPTION',0)} assumptions, "
                       f"{counts.get('PLACEHOLDER',0)} placeholders"],
        ["rules", P.rules.document],
    ]

    if observer is not None:
        model["provenance"].insert(4, [
            "observer",
            f"{len(observer['cells'])} thermistors, "
            f"{observer['rms_closed']:.3f} K field reconstruction"])

    # make the two-layer nature explicit for the page
    model["meta"]["nLayers"] = int(geom.n_layers)
    model["meta"]["nPlates"] = int(geom.n_plates)
    model["meta"]["coolingMode"] = P.cooling.mode
    model["meta"]["groupRows"] = int(P.pack.group_rows)
    model["meta"]["groupCols"] = int(P.pack.group_cols)
    model["meta"]["packEnergyKWh"] = round(pack_energy_kWh, 3)
    model["meta"]["ruleEnergyCapKWh"] = P.rules.energy_limit_Wh / 1000.0

    hyd = geom.hydraulics(coolant)
    model["meta"]["ReCoolant"] = float(hyd["Re"])
    model["meta"]["regime"] = hyd["regime"]
    model["meta"]["dPbar"] = float(hyd["dP_bar"])
    model["meta"]["RcellCoolant"] = float(hyd["R_solid_KW"] + hyd["R_conv_KW"])
    model["meta"]["nTubes"] = int(geom.n_tubes)
    model["meta"]["nCircuits"] = int(geom.n_circuits_eff)

    # --- hydrodynamics, so the page can show the real boat -------------
    # The supplied MEBC resistance curve and the contra-rotating propulsor
    # replaced the parametric hull and the single-screw stand-in. Without
    # these the dashboard would keep drawing drag from a planing model
    # applied to a hull that does not plane.
    model["meta"]["resistanceSource"] = P.hydro.resistance_source
    model["meta"]["resistanceCurve_kn"] = list(P.hydro.resistance_speed_kn)
    model["meta"]["resistanceCurve_N"] = list(P.hydro.resistance_bare_hull_N)
    model["meta"]["resistanceMaxValid_kn"] = P.hydro.resistance_max_valid_kn
    model["meta"]["resistanceDisplacement_kg"] = \
        P.hydro.resistance_displacement_kg
    model["meta"]["propulsorType"] = P.hydro.propulsor_type
    model["meta"]["crpEfficiency"] = P.hydro.crp_efficiency
    model["meta"]["frontDiameter_m"] = P.hydro.front_diameter_m
    model["meta"]["rearDiameter_m"] = P.hydro.rear_diameter_m
    model["meta"]["frontGearRatio"] = P.hydro.front_gear_ratio
    model["meta"]["rearGearRatio"] = P.hydro.rear_gear_ratio
    model["meta"]["swirlRecovery"] = P.hydro.swirl_recovery_frac
    model["meta"]["designSpeed_kn"] = P.hydro.propulsor_design_speed_kn
    model["meta"]["cockpitStl"] = P.boat.cockpit_stl
    model["meta"]["cockpitFrontalArea_m2"] = P.boat.cockpit_frontal_area_m2

    print("reading the MATLAB compliance export ...")
    full = matlab_compliance()

    live = compliance_block(P)

    if full is not None:
        # The live block stays -- the browser engine recomputes those few
        # numbers as the boat runs, against the state it is actually in.
        # The full table sits beside it, not on top of it.
        live["full"] = full

    return dict(
        model=model,
        params=P.flat(values_only=False),
        compliance=live,
        buildInfo=dict(
            source="params/volare_params.json",
            cellDataset="params/cells/p50b_derived.json",
            nParams=len(P.flat()),
            provenanceCounts=P.counts(),
        ),
    )


def render_block(payload: dict) -> str:
    def dump(o):
        return json.dumps(o, separators=(",", ":"), allow_nan=False)

    lines = [
        MARK_BEGIN,
        "/* Regenerate with: python tools/build_mission_control.py         */",
        "/* Source of truth: params/volare_params.json                      */",
        f"const M = {dump(payload['model'])};",
        f"const VOLARE_PARAMS = {dump(payload['params'])};",
        f"const VOLARE_COMPLIANCE = {dump(payload['compliance'])};",
        f"const VOLARE_BUILD = {dump(payload['buildInfo'])};",
        MARK_END,
    ]
    return "\n".join(lines)


def splice(html: str, block: str) -> str:
    """Replace the generated block, or the legacy ``const M = {...};`` line."""
    if MARK_BEGIN in html and MARK_END in html:
        pattern = re.compile(
            re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END),
            re.DOTALL)
        return pattern.sub(lambda _: block, html, count=1)

    # First run: replace the legacy single-line model literal.
    pattern = re.compile(r"^const M = \{.*?\};\s*$", re.MULTILINE | re.DOTALL)

    if not pattern.search(html):
        raise RuntimeError(
            "Could not find the generated model block or a legacy "
            "'const M = {...};' line in the page. Refusing to guess where "
            "to splice.")

    return pattern.sub(lambda _: block, html, count=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the page is current; do not write")
    ap.add_argument("--out", default=HTML)
    args = ap.parse_args()

    if not os.path.isfile(HTML):
        print(f"ERROR: {HTML} not found")
        return 1

    payload = build_payload()
    block = render_block(payload)

    with open(HTML, "r", encoding="utf-8") as f:
        html = f.read()

    new_html = splice(html, block)

    if args.check:
        same = (hashlib.sha256(new_html.encode()).hexdigest() ==
                hashlib.sha256(html.encode()).hexdigest())
        print("up to date" if same else
              "STALE -- run tools/build_mission_control.py")
        return 0 if same else 1

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(new_html)

    kb = len(block) / 1024
    print(f"wrote {args.out}")
    print(f"  generated block {kb:.0f} kB")
    print(f"  {payload['buildInfo']['nParams']} parameters injected")
    print(f"  provenance: {payload['buildInfo']['provenanceCounts']}")

    c = payload["compliance"]
    print(f"  energy {c['energy']['storedWh']:.0f} Wh of "
          f"{c['energy']['limitWh']} Wh "
          f"({c['energy']['marginPct']:.2f}% margin)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
