#!/usr/bin/env python3
r"""
volare_thermal.run
==================

One entry point.  Everything is configured in CONFIG below -- change numbers
there, run this, get results.  No editing of model code required.

    python3 run.py                 # everything
    python3 run.py studies         # thermal studies only
    python3 run.py boat            # hull, resistance, prop matching only
    python3 run.py race            # coupled race + interactive dashboard
    python3 run.py cell            # cell characterisation pipeline
    python3 run.py bench           # real-time benchmark

To swap in your own hardware, change only CONFIG:
  * real cell data      -> CONFIG['cell']['dataset_folder'] = 'celldata/'
  * real hull           -> CONFIG['hull']['stl'] = 'volare.stl'
  * different topology   -> CONFIG['pack']['n_series'/'n_parallel'/'n_layers']
  * different cooling    -> CONFIG['pack']['tube_every'/'n_circuits'], ['coolant']
"""

from __future__ import annotations
import os
import sys

# Windows terminals often default to a legacy codepage (cp1252) instead of
# UTF-8, which crashes the moment a print() or file write contains a
# character like degree signs, multiplication signs, or arrows -- all used
# throughout this project's output. Force UTF-8 everywhere, unconditionally.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np

import pack_thermal as pt
import geometry as gm
import celldata as cd
import boat as bt
import simulator as sm
import race as rc
import charge as ch
import webexport as wx
import livesim as ls
import track as tk
import groundstation as gs

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)


# ===========================================================================
#  CONFIG  --  the only place you should need to edit
# ===========================================================================
CONFIG = dict(

    pack=dict(
        n_series=26,            # series groups (sets voltage)
        n_parallel=21,          # cells per group (sets capacity)
        n_layers=1,             # stack depth; must divide n_series
        pitch_x=0.0235,         # column pitch [m]
        pitch_y=0.0235,         # row pitch [m]
        layer_gap=0.010,        # gap between stacked layers [m]
        stagger=False,          # hex packing
        tube_every=2,           # coolant tube in every Nth inter-row gap
        n_circuits=3,           # parallel hydraulic circuits
        counterflow=True,       # alternate circuits run in opposite directions
        interlayer_tubes=False, # also cool the gaps BETWEEN layers
        tube_id_m=0.006,
        R_can_tubewall_KW=2.5,  # bond quality: 2-3 bonded, 8+ lazy
        gap_filler_k_WmK=1.5,   # 0.03 = air, 1.5 = thermal potting
        G_layer_WK=0.05,        # vertical cell-to-cell (weak!)
        busbar_R_ohm=7.0e-5,
    ),

    coolant=dict(
        flow_L_per_min=8.0,
        inlet_T_C=29.0,
        # 50/50 glycol.  For water + inhibitor:
        #   rho=997, cp=4180, mu=0.0008, k=0.62
        rho_kg_m3=1050.0, cp_J_kgK=3500.0, mu_Pa_s=0.0025, k_W_mK=0.38,
    ),

    cell=dict(
        dataset_folder=None,    # a folder of digitised CSVs
        dataset_json="celldata/p50b.json",   # <- your traced datasheet curves
                                # (regenerate with: python build_p50b_dataset.py)
        rc_fraction=(0.53, 0.67),
        taus=(10.0, 120.0),
        sigma_capacity=0.015,   # population spread: 0.015 ungraded, 0.004 graded
        sigma_resistance=0.060, #                   0.060 ungraded, 0.017 graded
        placement="random",     # 'random' | 'balanced' | 'thermal'
        seed=7,
    ),

    hull=dict(
        stl=None,               # DEMIHULL STL (the part in water). None = parametric.
        cockpit_stl="Cockpit_V1_3.stl",   # the pod in AIR -> real frontal area
        cockpit_travel_axis=None,         # None = auto (longest axis)
        displacement_kg=250.0,
        Lwl_m=4.99, Bwl_m=0.45, draft_m=0.14, n_hulls=2,
        cockpit_frontal_area_m2=0.42,     # fallback if no cockpit STL
        cockpit_Cd=0.55,                  # streamlined pod; blunt box ~0.9
        beam_diameter_m=0.104, beam_span_m=2.035, n_beams=2,
        beams_faired=False,
        planing_wetted_frac=0.30,   # most sensitive drag parameter
        planing_LD=5.6,
    ),

    propeller=dict(
        diameter_m=0.240, pitch_ratio=1.05, n_blades=3,
        gear_ratio=1.0,
        auto_match=True,        # iteratively match to the boat's own top speed
        D_bounds=(0.18, 0.34), PD_bounds=(0.75, 1.65), n_max_rps=110.0,
    ),

    race=dict(
        mass_kg=250.0,
        P_shaft_max_W=25_000.0,  # ENERGY_REQ_188 -- never exceeded
        energy_cap_kWh=9.828,    # ENERGY_REQ_7
        reserve_frac=0.03,
        duration_s=1800.0,
        dt=0.5,
        T_ambient_C=30.0,
        T_init_C=28.0,
        sample_every=8,
        wind_ms=0.0,
        scenarios=[
            dict(name="55 km/h target",      target_kmh=55, flow=8.0, ambient=30),
            dict(name="45 km/h economy",     target_kmh=45, flow=8.0, ambient=30),
            dict(name="60 km/h flat out",    target_kmh=60, flow=8.0, ambient=30),
            dict(name="hot day, half flow",  target_kmh=55, flow=4.0, ambient=40),
        ],
    ),

    charging=dict(
        cc_current_A=2.5, cv_voltage_V=4.20, cutoff_current_A=0.25,
        max_cell_temp_C=45.0, min_cell_temp_C=0.0,
        supply_V=220.0, supply_A=16.0, efficiency=0.92,
    ),

    track=dict(
        event="endurance",      # endurance | qualifying | championship_outer
                                # | championship_inner | slalom
        turn_radius_m=60.0,     # working assumption — replace with GPS
        lateral_g_limit=0.55,   # how hard the boat can actually corner
        gps_csv=None,           # a lat,lon polyline from practice overrides all
    ),

    course=dict(
        legs=[dict(name="start straight", length_m=420.0, radius_m=None),
              dict(name="turn 1",         length_m=70.0,  radius_m=28.0),
              dict(name="back straight",  length_m=380.0, radius_m=None),
              dict(name="turn 2",         length_m=70.0,  radius_m=25.0)],
        lateral_g_limit=0.55,
    ),
)


# ===========================================================================
#  BUILDERS
# ===========================================================================

def build_geometry(cfg=CONFIG):
    p = cfg["pack"]
    return gm.stacked_grid_pack(
        n_series=p["n_series"], n_parallel=p["n_parallel"],
        n_layers=p["n_layers"], pitch_x=p["pitch_x"], pitch_y=p["pitch_y"],
        layer_gap=p["layer_gap"], stagger=p["stagger"],
        tube_every=p["tube_every"], n_circuits=p["n_circuits"],
        counterflow=p["counterflow"], interlayer_tubes=p["interlayer_tubes"],
        tube_id_m=p["tube_id_m"], R_can_tubewall_KW=p["R_can_tubewall_KW"],
        gap_filler_k_WmK=p["gap_filler_k_WmK"], G_layer_WK=p["G_layer_WK"],
        busbar_R_ohm=p["busbar_R_ohm"])


def build_cell(cfg=CONFIG):
    c = cfg["cell"]
    if c["dataset_json"]:
        ds = cd.CellDataset.from_json(c["dataset_json"])
    elif c["dataset_folder"]:
        ds = cd.load_digitised_folder(c["dataset_folder"])
    else:
        ds = cd.synthetic_p50b()
    return ds.to_cell_params(rc_fraction=c["rc_fraction"], taus=c["taus"]), ds


def build_coolant(cfg=CONFIG, **over):
    k = dict(cfg["coolant"]); k.update(over)
    return pt.Coolant(**k)


def build_population(geom, cfg=CONFIG):
    c = cfg["cell"]
    rng = np.random.default_rng(c["seed"])
    cap, res = pt.make_population(geom.n_cells, c["sigma_capacity"],
                                  c["sigma_resistance"], -0.4, rng)
    return pt.place_cells(geom, cap, res, c["placement"],
                          np.random.default_rng(c["seed"]))


def build_boat(cfg=CONFIG):
    h = cfg["hull"]
    ck = None
    cpath = h.get("cockpit_stl")
    if cpath and os.path.exists(cpath):
        ck = bt.Cockpit.from_stl(cpath, travel_axis=h.get("cockpit_travel_axis"),
                                 Cd=h["cockpit_Cd"])
    if h["stl"] and os.path.exists(h["stl"]):
        hull = bt.Hull.from_stl(
            h["stl"], displacement_kg=h["displacement_kg"],
            cockpit=ck,
            cockpit_frontal_area_m2=h["cockpit_frontal_area_m2"],
            cockpit_Cd=h["cockpit_Cd"], beam_diameter_m=h["beam_diameter_m"],
            beam_span_m=h["beam_span_m"], n_beams=h["n_beams"],
            beams_faired=h["beams_faired"])
    else:
        hull = bt.Hull(Lwl_m=h["Lwl_m"], Bwl_m=h["Bwl_m"], draft_m=h["draft_m"],
                       n_hulls=h["n_hulls"],
                       displacement_kg=h["displacement_kg"], cockpit=ck,
                       cockpit_frontal_area_m2=h["cockpit_frontal_area_m2"],
                       cockpit_Cd=h["cockpit_Cd"],
                       beam_diameter_m=h["beam_diameter_m"],
                       beam_span_m=h["beam_span_m"], n_beams=h["n_beams"],
                       beams_faired=h["beams_faired"])
    resist = bt.ResistanceModel(hull,
                                planing_wetted_frac=h["planing_wetted_frac"],
                                planing_LD=h["planing_LD"])
    pc = cfg["propeller"]
    prop = bt.Propeller(diameter_m=pc["diameter_m"],
                        pitch_ratio=pc["pitch_ratio"],
                        n_blades=pc["n_blades"], gear_ratio=pc["gear_ratio"])
    info = {}
    if pc["auto_match"]:
        prop, info = bt.match_propeller_to_boat(
            hull, resist, prop, cfg["race"]["mass_kg"],
            cfg["race"]["P_shaft_max_W"], D_bounds=pc["D_bounds"],
            PD_bounds=pc["PD_bounds"], n_max_rps=pc["n_max_rps"])
    return hull, resist, prop, info


def build_track(cfg=CONFIG):
    t = cfg["track"]
    if t.get("gps_csv") and os.path.exists(t["gps_csv"]):
        d = np.loadtxt(t["gps_csv"], delimiter=",", ndmin=2)
        trk = tk.Track.from_gps(d[:, 0], d[:, 1], name="GPS practice trace")
        trk.lateral_g_limit = t["lateral_g_limit"]
        return trk
    ev = t["event"]
    if ev == "endurance":
        trk = tk.monaco_endurance(radius_m=t["turn_radius_m"])
    else:
        trk = tk.COURSES[ev]()
    trk.lateral_g_limit = t["lateral_g_limit"]
    trk._build()
    return trk


def build_course(cfg=CONFIG):
    return bt.RaceCourse(legs=cfg["course"]["legs"],
                         lateral_g_limit=cfg["course"]["lateral_g_limit"])


# ===========================================================================
#  TASKS
# ===========================================================================

def rule(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


def task_cell():
    rule("CELL CHARACTERISATION")
    C, ds = build_cell()
    print(f"  {ds.part_number} — {len(ds.discharge_curves)} discharge curves, "
          f"temperatures {ds.temperatures}")
    if ds.notes:
        print(f"  NOTE: {ds.notes}")
    s, T, R = ds.build_R0_map()
    for i, t in enumerate(T):
        print(f"    R0(50% SOC, {t:6.1f} °C) = "
              f"{np.interp(0.5, s, R[i])*1000:6.2f} mΩ  (sustained)")
    EaR, R0ref = ds.fit_arrhenius()
    print(f"  fitted Ea/R = {EaR:.0f} K, R_sustained(25 °C) = {R0ref*1000:.2f} mΩ")
    r0 = C.R0(np.array([298.15]), np.array([0.5]))[0]
    r1, r2 = C.R_rc(np.array([298.15]), 1.0, np.array([0.5]))
    print(f"  ECM split: R0 {r0*1000:.2f} + R1 {r1[0]*1000:.2f} + "
          f"R2 {r2[0]*1000:.2f} = {(r0+r1[0]+r2[0])*1000:.2f} mΩ")
    if ds.cycle_curves:
        for c in ds.cycle_curves:
            print(f"  cycle life @{c.c_rate:.0f}C: {c.cycles_to(0.80):.0f} "
                  f"cycles to 80 %")
    return C, ds


def task_geometry():
    rule("PACK GEOMETRY")
    G = build_geometry()
    for k, v in G.summary().items():
        print(f"  {k:22s} {v}")
    net = pt.ThermalNetwork(G, build_cell()[0], build_coolant())
    for k, v in net.hydraulics_info.items():
        print(f"  {k:22s} {round(v, 4) if isinstance(v, float) else v}")
    unc = G.uncooled_cells()
    if len(unc):
        rows = sorted({int(G.series_index[i]) for i in unc})
        print(f"  WARNING: {len(unc)} cells have no tube contact, "
              f"in series groups {rows}")
    return G


def task_boat():
    rule("BOAT — HULL, RESISTANCE, PROPULSION")
    hull, resist, prop, info = build_boat()
    if hull.cockpit is not None:
        print("  COCKPIT (in air, from STL):")
        for k, v in hull.cockpit.summary().items():
            print(f"    {k:22s} {v}")
        print("  HULL (in water):")
    for k, v in hull.summary().items():
        print(f"    {k:22s} {v}")
    if hull.cockpit is not None and not hull.from_geometry:
        print("  NOTE: the hull is still PARAMETRIC — a cockpit STL gives real")
        print("        aerodynamics but no waterline. Supply the demihull STL")
        print("        for real wetted area, which drives 60-80 % of your drag.")
    if info.get("matched"):
        print(f"\n  propeller matched: D {info['diameter_m']*1000:.0f} mm, "
              f"P/D {info['pitch_ratio']:.2f}, eff {info['eff']:.3f}, "
              f"{info['n_rpm']:.0f} rpm, J {info['J']:.2f}, "
              f"cav σ {info['cav_number']:.2f}")
        print(f"  convergence (km/h): {info['iterations_kmh']}")
        if (abs(info['diameter_m'] - CONFIG['propeller']['D_bounds'][0]) < 1e-6
                or abs(info['pitch_ratio'] -
                       CONFIG['propeller']['PD_bounds'][1]) < 1e-6):
            print("  CAUTION: the match ran to the edge of its search bounds, "
                  "so the true optimum lies outside them. Widen D_bounds / "
                  "PD_bounds, or accept this as a lower bound.")
    dyn = bt.BoatDynamics(hull, resist, prop, mass_kg=CONFIG["race"]["mass_kg"],
                          P_shaft_max_W=CONFIG["race"]["P_shaft_max_W"])
    print(f"\n  {'kW':>5} {'km/h':>7} {'kn':>6} {'rpm':>7} {'eff':>6} {'Wh/km':>8}")
    for row in dyn.power_speed_curve(np.array([5e3, 1e4, 1.5e4, 2e4, 2.5e4])):
        whkm = row["P_shaft_W"] / max(row["v_kmh"], 1e-9)
        print(f"  {row['P_shaft_W']/1000:>5.0f} {row['v_kmh']:>7.2f} "
              f"{row['v_kn']:>6.2f} {row['n_rpm']:>7.0f} "
              f"{row['prop_eff']:>6.3f} {whkm:>8.1f}")
    v = dyn.steady_speed(CONFIG["race"]["P_shaft_max_W"])
    print(f"\n  TOP SPEED at the {CONFIG['race']['P_shaft_max_W']/1000:.0f} kW "
          f"cap: {v*3.6:.1f} km/h ({v*1.9438:.1f} kn)")
    return hull, resist, prop


def task_bench():
    rule("REAL-TIME BENCHMARK")
    G, C, K = build_geometry(), build_cell()[0], build_coolant()
    for dt in (0.25, 0.5, 1.0):
        b = sm.benchmark(G, C, K, dt=dt, sim_seconds=1200)
        print(f"  dt={dt:4.2f}s  {b['nodes']:5d} nodes  "
              f"{b['us_per_step']:7.0f} µs/step  "
              f"-> {b['realtime_factor']:8.0f}× real time")


def task_race():
    rule("COUPLED RACE + INTERACTIVE DASHBOARD")
    G = build_geometry()
    C, _ = build_cell()
    hull, resist, prop, _ = build_boat()
    course = build_course()
    cap, res = build_population(G)
    r_cfg = CONFIG["race"]

    scen = []
    print(f"  {'scenario':<24} {'min':>6} {'laps':>6} {'km/h':>6} {'kWh':>6} "
          f"{'Tmax':>6} {'derate%':>8}")
    print("  " + "-" * 70)
    for s in r_cfg["scenarios"]:
        K = build_coolant(flow_L_per_min=s["flow"])
        r = rc.simulate_race(
            G, C, K, hull, resist, prop, course=course,
            target_speed_kmh=s["target_kmh"], duration_s=r_cfg["duration_s"],
            dt=r_cfg["dt"], mass_kg=r_cfg["mass_kg"],
            P_shaft_max_W=r_cfg["P_shaft_max_W"], T_init_C=r_cfg["T_init_C"],
            T_ambient_C=s["ambient"], cap_mult=cap, res_mult=res,
            energy_cap_kWh=r_cfg["energy_cap_kWh"],
            reserve_frac=r_cfg["reserve_frac"],
            sample_every=r_cfg["sample_every"], wind_ms=r_cfg["wind_ms"])
        d = float(np.mean(r["derate"] < 0.999) * 100)
        print(f"  {s['name']:<24} {r['t'][-1]/60:>6.2f} {r['lap'][-1]:>6.2f} "
              f"{r['v_kmh'].mean():>6.1f} {r['energy_kWh'][-1]:>6.3f} "
              f"{r['T_max'].max():>6.1f} {d:>8.1f}")
        scen.append((s["name"],
                     f"target {s['target_kmh']} km/h · {s['flow']} L/min · "
                     f"ambient {s['ambient']} °C · {G.n_cells} cells "
                     f"{G.n_series}S{G.n_parallel}P · {r['stop_reason']}",
                     r, G))
    out, size = rc.build_dashboard(scen, os.path.join(FIG,
                                                      "race_simulator.html"))
    print(f"\n  -> {out}  ({size/1e6:.2f} MB, self-contained, open in a browser)")


def task_charge():
    rule("CHARGING — CC-CV AND BETWEEN-RACE TURNAROUND")
    C, _ = build_cell()
    cc = CONFIG["charging"]
    prof = ch.ChargeProfile(cc_current_A=cc["cc_current_A"],
                            cv_voltage_V=cc["cv_voltage_V"],
                            cutoff_current_A=cc["cutoff_current_A"],
                            max_cell_temp_C=cc["max_cell_temp_C"],
                            min_cell_temp_C=cc["min_cell_temp_C"])
    chg = ch.Charger(supply_V=cc["supply_V"], supply_A=cc["supply_A"],
                     efficiency=cc["efficiency"])
    S, P = CONFIG["pack"]["n_series"], CONFIG["pack"]["n_parallel"]
    print(f"  supply {chg.wall_W:.0f} W wall -> {chg.dc_W:.0f} W DC")
    h, r = ch.full_charge_time(C, S, P, prof, chg)
    print(f"  empty -> full: {h:.2f} h, {r['energy_in_kWh']:.2f} kWh delivered")
    print(f"  time in true CC: {r['cc_fraction']*100:.0f} %  "
          f"(0 % means the SUPPLY is the binding limit, not the cell)")
    print(f"  peak pack heat while charging: {r['pack_heat_W_max']:.0f} W")
    print("\n  TURNAROUND — SOC reached after W hours:")
    ws = (1.0, 2.0, 3.0, 4.0)
    print("    " + f"{'start':>6} " + " ".join(f"{w:>6.1f}h" for w in ws))
    rows = ch.turnaround_table(C, S, P, prof, chg, windows_h=ws)
    for z0 in (0.05, 0.15, 0.30, 0.50):
        vals = [f"{z*100:>6.0f}%" for (a, w, z) in rows if abs(a - z0) < 1e-9]
        print("    " + f"{z0*100:>5.0f}% " + " ".join(vals))
    print(f"\n  NOTE: charging is blocked below {prof.min_cell_temp_C} °C "
          f"(lithium plating) and derated above {prof.derate_start_C} °C.")


def task_live():
    rule("LIVE SIMULATOR — real physics in the browser")
    G = build_geometry(); C, _ = build_cell(); K = build_coolant()
    hull, resist, prop, _ = build_boat()
    course = build_course(); cap, res = build_population(G)
    r = CONFIG["race"]
    v = wx.verify_scheme(G, C, K, hull, resist, prop, course, cap, res,
                         dt=0.5, seconds=900, T_ambient_C=r["T_ambient_C"])
    print(f"  scheme verification vs the implicit reference solver:")
    print(f"    T_max RMS error   {v['Tmax_rms_K']:.4f} K")
    print(f"    T_max worst error {v['Tmax_worst_K']:.4f} K")
    print(f"    energy error      {v['Wh_err_pct']:.4f} %")
    print(f"    bus current RMS   {v['I_rms_A']:.4f} A")
    if v["Tmax_rms_K"] > 0.5:
        print("    WARNING: browser scheme has drifted from the reference. "
              "Reduce the browser timestep or check node stiffness.")
    out, size = ls.write_live_sim(v["model"],
                                  os.path.join(FIG, "live_simulator.html"))
    print(f"\n  -> {out}  ({size/1024:.0f} KB, self-contained)")
    print("     open it in a browser: throttle, autopilot, live coolant flow, "
          "sea and air temperature, headwind.")


def task_modules():
    rule("MODULE LAYOUT — moving blocks of cells as units")
    S, P = CONFIG["pack"]["n_series"], CONFIG["pack"]["n_parallel"]
    half = S // 2
    mods = [gm.Module(rows=half, cols=P, origin=(0, 0, 0), series_offset=0,
                      name="fwd"),
            gm.Module(rows=S - half, cols=P, origin=(0.02, 0.36, 0),
                      yaw_deg=6.0, series_offset=half, name="aft")]
    for m in mods:
        print(f"  {m.footprint()}")
    issues = gm.check_module_clearance(mods)
    print(f"  clearance: {issues if issues else 'OK'}")
    G = gm.modules_to_geometry(mods, tube_every=CONFIG["pack"]["tube_every"],
                               n_circuits=CONFIG["pack"]["n_circuits"])
    for k, v in G.summary().items():
        print(f"  {k:20s} {v}")
    C, _ = build_cell()
    _, p = pt.build_power_profile(pt.mebc_endurance_lap(), 1200, 1.0)
    r = pt.simulate(G, C, build_coolant(), p, dt=1.0, T_init_C=28,
                    store_every=20)
    print(f"  T_max {r.T_core_C.max():.2f} °C, "
          f"spread {float(np.ptp(r.T_core_C[-1])):.2f} K")
    print("  NOTE: each module got its own circuits, so total circuits "
          f"= {G.n_circuits_eff}. Flow per circuit falls accordingly — set "
          "n_circuits per module so the TOTAL stays near 3.")


def task_track():
    rule("RACE COURSE — MEBC 2026 Energy")
    for k in ("endurance", "qualifying", "championship_outer",
              "championship_inner", "slalom"):
        t = tk.COURSES[k]()
        s = t.summary()
        print(f"  {s['name']:<40} {s['length_m']:>7.1f} m "
              f"({s['length_NM']:.3f} NM)  closure {s['closure_error_m']:>5.2f} m  "
              f"min corner {s['min_corner_speed_kmh']:>5.1f} km/h  "
              f"limit {s['time_limit_min']:.0f} min")
    print("\n  NOTE: lap distances, time limits and the no-recharge rule are")
    print("  exact from the course description. Corner radii are reconstructed")
    print("  from the published maps, which are marked 'illustration only' —")
    print("  set CONFIG['track']['gps_csv'] to a practice trace to replace them.")


def task_mission():
    rule("MISSION CONTROL — ground station")
    G = build_geometry(); C, _ = build_cell(); K = build_coolant()
    hull, resist, prop, _ = build_boat()
    course = build_course(); trk = build_track(); cap, res = build_population(G)
    r = CONFIG["race"]

    dyn = bt.BoatDynamics(hull, resist, prop, mass_kg=r["mass_kg"],
                          P_shaft_max_W=r["P_shaft_max_W"])
    best, rows = tk.endurance_strategy(dyn, trk,
                                       energy_kWh=r["energy_cap_kWh"],
                                       reserve_frac=r["reserve_frac"])
    print(f"  course: {trk.name}  {trk.length:.0f} m, "
          f"closure {trk.closure_error_m:.2f} m")
    print(f"  ENDURANCE OPTIMUM: {best['P_shaft_W']/1000:.1f} kW -> "
          f"{best['v_kmh']:.1f} km/h, {best['laps']:.1f} laps "
          f"({best['distance_km']:.1f} km) in {best['duration_h']:.2f} h, "
          f"limited by {best['limited_by'].upper()}")
    flat = dyn.steady_speed(r["P_shaft_max_W"])
    e_flat = [x for x in rows if x["P_shaft_W"] >= r["P_shaft_max_W"] * 0.98]
    if e_flat:
        print(f"  flat out ({flat*3.6:.1f} km/h) would give only "
              f"{e_flat[0]['laps']:.1f} laps — "
              f"{(1 - e_flat[0]['laps']/best['laps'])*100:.0f} % less distance.")
    note = (f"3 h limit is NOT the binding constraint: at the optimum you "
            f"exhaust the {r['energy_cap_kWh']} kWh in "
            f"{best['duration_h']:.2f} h. Endurance here is an energy race, "
            f"not a time race — pace for efficiency, not lap time.")
    print(f"  {note}")

    v = wx.verify_scheme(G, C, K, hull, resist, prop, course, cap, res,
                         dt=0.5, seconds=900, T_ambient_C=r["T_ambient_C"])
    print(f"\n  scheme verification vs implicit reference:")
    print(f"    T_max RMS {v['Tmax_rms_K']:.4f} K   worst "
          f"{v['Tmax_worst_K']:.4f} K   energy {v['Wh_err_pct']:.4f} %")

    print("  fitting digital-twin observer...")
    obs = wx.build_observer(G, C, K, n_sensors=6, n_ensemble=12,
                            seconds=720, dt=2.0)
    print(f"    {len(obs['cells'])} thermistors at groups "
          f"{[int(G.series_index[c]) for c in obs['cells']]}")
    print(f"    field reconstruction {obs['rms_open']:.3f} K open loop -> "
          f"{obs['rms_closed']:.3f} K with the observer "
          f"({obs['rms_open']/max(obs['rms_closed'],1e-9):.1f}x)")

    # every official course, so the event can be switched live
    allc = {}
    for key in ("endurance", "qualifying", "championship_outer",
                "championship_inner", "slalom"):
        t2 = tk.COURSES[key]()
        t2.lateral_g_limit = CONFIG["track"]["lateral_g_limit"]
        t2._build()
        d2 = bt.BoatDynamics(hull, resist, prop, mass_kg=r["mass_kg"],
                             P_shaft_max_W=r["P_shaft_max_W"])
        b2, rows2 = tk.endurance_strategy(d2, t2,
                                          energy_kWh=r["energy_cap_kWh"],
                                          reserve_frac=r["reserve_frac"])
        allc[key] = dict(track=wx.export_track(t2),
                         strategy=dict(best=b2, rows=rows2,
                                       note=f"{t2.event}: "
                                            f"{t2.length:.0f} m lap, "
                                            f"{t2.time_limit_s/60:.0f} min limit"))
    print(f"  courses exported: {', '.join(allc)}")

    dt_model = bt.Drivetrain()
    for rpm in (3000, 4700):
        cr = dt_model.continuous_rating_W(rpm * 2 * np.pi / 60)
        print(f"  drivetrain continuous at {rpm} rpm: "
              f"{cr['P_continuous_W']/1000:.1f} kW "
              f"(winding {cr['T_winding_C']:.0f} °C)")

    model = wx.export_model(G, C, K, hull, resist, prop, course,
                            mass_kg=r["mass_kg"],
                            P_shaft_max_W=r["P_shaft_max_W"],
                            energy_cap_kWh=r["energy_cap_kWh"],
                            T_ambient_C=r["T_ambient_C"],
                            cap_mult=cap, res_mult=res,
                            track=trk,
                            strategy=dict(best=best, rows=rows, note=note),
                            observer=obs, courses=allc)
    model["provenance"] = [
        ["cell curves", CONFIG["cell"]["dataset_json"] or "synthetic"],
        ["cockpit", CONFIG["hull"]["cockpit_stl"] or "assumed"],
        ["hull", CONFIG["hull"]["stl"] or "PARAMETRIC — send the demihull STL"],
        ["course", trk.name],
        ["corner radii", "reconstructed from published map"],
        ["scheme error", f"{v['Tmax_rms_K']:.4f} K RMS vs implicit solver"],
        ["drivetrain", "ESTIMATED — awaiting manufacturer torque map"],
        ["observer", f"{len(obs['cells'])} thermistors, "
                     f"{obs['rms_closed']:.3f} K field reconstruction"],
        ["cooling", f"{M_tubes(G)} tubes / {G.n_circuits_eff} circuits"],
    ]
    out, size = gs.write_ground_station(
        model, os.path.join(FIG, "mission_control.html"))
    print(f"\n  -> {out}  ({size/1024:.0f} KB, self-contained)")
    ok, msg = gs.validate_html(out)
    print(f"  javascript check: {msg}")
    if not ok:
        print("  THE DASHBOARD WILL NOT RUN. Fix before opening it.")


def M_tubes(G):
    return len(getattr(G, "tubes", []))


def task_studies():
    import studies
    studies.study_validation()
    studies.study_baseline()
    studies.study_cooling_sweep()
    studies.study_grading()
    studies.study_worst_case()
    studies.study_coverage()


TASKS = dict(cell=task_cell, geometry=task_geometry, boat=task_boat,
             charge=task_charge, modules=task_modules, bench=task_bench,
             race=task_race, live=task_live, track=task_track,
             mission=task_mission, studies=task_studies)

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        args = ["cell", "geometry", "boat", "track", "charge",
                "modules", "bench", "mission"]
    for a in args:
        if a not in TASKS:
            print(f"unknown task {a!r}; choose from {list(TASKS)}")
            sys.exit(1)
        TASKS[a]()
    print("\ndone.\n")
