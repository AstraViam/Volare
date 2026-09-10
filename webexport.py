r"""
volare_thermal.webexport
========================

Export the coupled model so it can run LIVE in a browser, and verify that the
browser-side numerical scheme matches the reference implicit solver.

WHY A DIFFERENT SCHEME IN THE BROWSER
-------------------------------------
The reference solver uses implicit Euler with a sparse LU factorisation.  That
is unconditionally stable but needs a sparse linear algebra library, which is
not something to ship into a browser.

The browser engine instead uses:
  * EXPLICIT Euler on the cell core and can nodes
  * a QUASI-STATIC forward sweep on the coolant chain

This is valid because of a stiffness separation.  Node time constants:

    cell core   C 55.1 J/K,  G 0.50 W/K   -> tau 110 s
    cell can    C 18.4 J/K,  G ~4.4 W/K   -> tau  4.2 s   -> dt < 8.5 s
    busbar      C  173 J/K,  G ~1.1 W/K   -> tau 153 s
    enclosure   C   60 J/K,  G ~19  W/K   -> tau  3.1 s   -> dt < 6.2 s
    COOLANT     C 0.03 J/K,  G ~1500 W/K  -> tau 2e-5 s   <-- the problem

Only the coolant is stiff, and it is stiff because its thermal mass is
genuinely negligible.  Solving it as a steady balance rather than integrating
it removes the entire stiffness problem, and the coolant chain is a directed
acyclic graph, so one forward sweep in flow order is exact:

    T_seg = (mdotCp*T_upstream + sum_i G_i*T_can_i) / (mdotCp + sum_i G_i)

Everything else is then comfortably stable at dt = 0.5 s.

`verify_scheme()` runs the Python mirror of the JS engine against the implicit
reference and reports the discrepancy.  Do not trust the browser numbers until
that check passes.
"""

from __future__ import annotations

import json
import numpy as np

import pack_thermal as pt
import boat as bt


# ============================================================================
#  EXPORT
# ============================================================================

def export_track(track, n=520):
    """Resample a Track to a fixed-length polyline for the browser map."""
    idx = np.linspace(0, len(track.s) - 1, n).astype(int)
    return dict(name=track.name, event=track.event,
                length=float(track.length),
                timeLimit=float(track.time_limit_s),
                x=[round(float(v), 2) for v in track.x[idx]],
                y=[round(float(v), 2) for v in track.y[idx]],
                s=[round(float(v), 2) for v in track.s[idx]],
                vlim=[round(float(min(v, 999)), 3) for v in track.v_limit[idx]],
                curv=[round(float(v), 5) for v in track.curvature[idx]],
                hdg=[round(float(v), 4) for v in track.heading[idx]],
                sectors=[float(b) for b in track.sector_bounds],
                marks=[dict(name=m["name"], s=float(m["s"]))
                       for m in track.marks],
                segNames=[g.get("name", "") for g in track.segments],
                closure=float(track.closure_error_m))


def export_model(geom, cell, coolant, hull, resistance, propeller, course,
                 mass_kg=250.0, P_shaft_max_W=25_000.0, energy_cap_kWh=9.828,
                 T_ambient_C=30.0, cap_mult=None, res_mult=None,
                 inverter_eff=0.96, v_grid_max_kmh=90.0,
                 track=None, strategy=None, observer=None,
                 courses=None) -> dict:
    """Everything the browser engine needs, as plain JSON-able data."""
    net = pt.ThermalNetwork(geom, cell, coolant, T_ambient_C)
    N = geom.n_cells
    S, P = geom.n_series, geom.n_parallel
    hyd = net.hydraulics_info

    # --- thermal network, in solver (group-major) order -----------------
    order = geom.order if hasattr(geom, "order") else np.arange(N)
    pos = {int(c): k for k, c in enumerate(order)}

    pairs = geom.neighbour_pairs
    gpair = getattr(geom, "neighbour_G", np.full(len(pairs),
                                                 geom.G_cell_cell(cell)
                                                 if hasattr(geom, "G_cell_cell")
                                                 else 0.5))
    nb = [[pos[int(a)], pos[int(b)], float(g)]
          for (a, b), g in zip(pairs, gpair)]

    cc = getattr(geom, "cell_coolant_pairs", np.zeros((0, 2), int))
    cw = getattr(geom, "cell_coolant_weight", np.ones(len(cc)))
    g_ct = 1.0 / net.R_cell_to_coolant_KW
    cool = [[pos[int(i)], int(s), float(w * g_ct)] for (i, s), w in zip(cc, cw)]

    # coolant chain in topological (flow) order
    up = geom.upstream if hasattr(geom, "upstream") else np.array([], int)
    M = int(getattr(geom, "n_coolant_segs", 0))
    seen, chain = set(), []
    def emit(s):
        if s in seen:
            return
        u = int(up[s])
        if u >= 0:
            emit(u)
        seen.add(s); chain.append([int(s), u])
    for s in range(M):
        emit(s)

    G_air = net.G_cell_air()[order] if hasattr(net, "G_cell_air") else \
        np.full(N, 0.03)

    # --- cell electro-thermal parameters --------------------------------
    if getattr(cell, "has_R0_map", False):
        soc_g, T_g, R_g = cell._map_soc, cell._map_T - 273.15, cell._map_R
    else:
        soc_g = np.linspace(0, 1, 21)
        T_g = np.array([0.0, 25.0, 45.0])
        R_g = np.array([cell.R0(np.full(21, t + 273.15), soc_g) for t in T_g])

    # --- boat: resistance sampled, propeller analytic --------------------
    v_g = np.linspace(0.0, v_grid_max_kmh / 3.6, 121)
    R_g_v = resistance.total(np.maximum(v_g, 1e-3))

    return dict(
        meta=dict(nCells=N, nSeries=S, nParallel=P,
                  nLayers=int(getattr(geom, "n_layers", 1)),
                  energyCapKWh=float(energy_cap_kWh),
                  PmaxW=float(P_shaft_max_W),
                  inverterEff=float(inverter_eff),
                  ReCoolant=float(hyd["Re"]), regime=hyd["regime"],
                  dPbar=float(hyd["dP_bar"]),
                  RcellCoolant=float(net.R_cell_to_coolant_KW),
                  nTubes=int(hyd["n_tubes"]),
                  nCircuits=int(hyd["n_circuits"])),
        tubes=[dict(circuit=int(t.circuit),
                    x=[round(float(v), 4) for v in t.seg_centres[:, 0]],
                    y=[round(float(v), 4) for v in t.seg_centres[:, 1]],
                    z=[round(float(v), 4) for v in t.seg_centres[:, 2]],
                    length=round(float(t.length), 3))
               for t in getattr(geom, "tubes", [])],
        display=dict(
            x=[float(geom.x[c]) for c in order],
            y=[float(geom.y[c]) for c in order],
            layer=[int(geom.layer_id[c]) if hasattr(geom, "layer_id") else 0
                   for c in order],
            series=[int(geom.series_index[c]) for c in order],
            par=[int(geom.parallel_index[c]) for c in order],
            cellD=float(getattr(geom, "cell_diameter_m", 0.02155)),
            tubeD=float(getattr(geom, "tube_id_m", 0.006)),
            pitch=float(getattr(geom, "pitch_x_m",
                                getattr(geom, "pitch_x", 0.0235))),
            nTubeContact=[float(getattr(geom, "tube_contact_score",
                                        np.zeros(N))[c]) for c in order]),
        thermal=dict(
            Ccore=float(cell.thermal_capacity_JK * cell.core_mass_fraction),
            Ccan=float(cell.thermal_capacity_JK * (1 - cell.core_mass_fraction)),
            gCoreCan=float(1.0 / cell.R_core_can_KW),
            neighbours=nb, coolPairs=cool, coolChain=chain, nSeg=M,
            gAir=[float(g) for g in G_air],
            Cair=float(geom.enclosure_air_volume_m3 * 1.2 * 1005.0),
            UAair=float(geom.enclosure_UA_WK),
            Cbus=float(geom.busbar_mass_kg * geom.busbar_cp_J_kgK),
            gCanBus=float(geom.G_can_busbar_WK),
            busR=float(geom.busbar_R_ohm), nBus=int(S - 1),
            mdotCpPerCircuit=float(net.mdot_cp_per_circuit),
            segCircuit=[int(c) for c in
                        getattr(geom, "coolant_seg_circuit",
                                np.zeros(M, int))]),
        cell=dict(
            capAh=float(cell.capacity_Ah),
            socGrid=[float(v) for v in soc_g],
            Tgrid=[float(v) for v in T_g],
            R0map=[[float(v) for v in row] for row in R_g],
            f1=float(cell.R1_ref_ohm / max(cell.R0_ref_ohm, 1e-12)),
            f2=float(cell.R2_ref_ohm / max(cell.R0_ref_ohm, 1e-12)),
            tau1=float(cell.tau1_s), tau2=float(cell.tau2_s),
            ocvSoc=[float(v) for v in cell.ocv_soc],
            ocvV=[float(v) for v in cell.ocv_v],
            dudtSoc=[float(v) for v in cell.dudt_soc],
            dudtV=[float(v) for v in cell.dudt_v_per_K],
            TwarnC=float(cell.T_warn_C), TmaxC=float(cell.T_max_C),
            capT=([float(v) for v in cell.cap_temp_C]
                  if getattr(cell, "cap_temp_C", None) is not None else None),
            capF=([float(v) for v in cell.cap_temp_mult]
                  if getattr(cell, "cap_temp_mult", None) is not None else None),
            capMult=[float(v) for v in (cap_mult[order] if cap_mult is not None
                                        else np.ones(N))],
            resMult=[float(v) for v in (res_mult[order] if res_mult is not None
                                        else np.ones(N))]),
        cycles=[dict(c_rate=float(c.c_rate), dod=float(c.dod_pct),
                     T=float(c.temperature_C),
                     n=[float(v) for v in c.cycles],
                     ret=[float(v) for v in c.retention])
                for c in getattr(cell, "_cycle_curves", [])],
        drive=dict(
            Kt=0.30, Rph=0.012, cuTc=0.00393, feRef=300.0, wRef=490.0,
            Vce=1.20, kSw=1.25,
            Cw=3200.0, Cc=6000.0, Rwc=0.020, Rcs=0.0055,
            Cj=90.0, Chs=2400.0, Rjh=0.030, Rhc=0.020,
            TwWarn=130.0, TwMax=155.0, TjWarn=100.0, TjMax=125.0),
        cooling=dict(
            tubeID=float(getattr(geom, "tube_id_m", 0.006)),
            nTubes=int(len(getattr(geom, "tubes", []))),
            Rwall=float(getattr(geom, "R_can_tubewall_KW", 2.5)),
            rho=float(coolant.rho_kg_m3), cp=float(coolant.cp_J_kgK),
            mu=float(coolant.mu_Pa_s), k=float(coolant.k_W_mK),
            tubeLen=float(sum(t.length for t in getattr(geom, "tubes", [])) or 1.0),
            # pressure drop is set by the LONGEST circuit, not the average --
            # every circuit sees the same manifold-to-manifold pressure, so the
            # worst one governs what the pump must deliver.
            maxCircuitLen=float(max(
                [sum(t.length for t in getattr(geom, "tubes", [])
                     if t.circuit == c)
                 for c in {t.circuit for t in getattr(geom, "tubes", [])}] or [1.0])),
            nCircuitsBase=int(getattr(geom, "n_circuits_eff", 1)),
            circuitLengths=[float(sum(t.length for t in getattr(geom,"tubes",[])
                                      if t.circuit == c))
                            for c in sorted({t.circuit
                                             for t in getattr(geom,"tubes",[])})],
            maxBends=int(max(
                [sum(t.n_bends for t in getattr(geom, "tubes", [])
                     if t.circuit == c)
                 for c in {t.circuit for t in getattr(geom, "tubes", [])}] or [0])),
            cellD=float(getattr(geom, "cell_diameter_m", 0.02155))),
        boat=dict(
            massKg=float(mass_kg),
            addedMass=0.10,
            vGrid=[float(v) for v in v_g],
            Rgrid=[float(v) for v in R_g_v],
            propD=float(propeller.diameter_m),
            propPD=float(propeller.pitch_ratio),
            wake=float(propeller.wake_fraction),
            thrustDed=float(propeller.thrust_deduction),
            gearRatio=float(propeller.gear_ratio),
            drivelineEff=0.97,
            LwlM=float(hull.Lwl_m), BwlM=float(hull.Bwl_m),
            draftM=float(hull.draft_m),
            dryAreaM2=float(hull.dry_area_m2),
            wettedM2=float(hull.wetted_area_m2),
            nHulls=int(hull.n_hulls),
            beamD=float(hull.beam_diameter_m), beamSpan=float(hull.beam_span_m)),
        course=dict(
            legs=[dict(name=l["name"], length=float(l["length_m"]),
                       radius=(float(l["radius_m"]) if l["radius_m"] else 0.0))
                  for l in course.legs],
            lapLength=float(course.lap_length_m),
            latG=float(course.lateral_g_limit)),
        env=dict(TambC=float(T_ambient_C), TinC=float(coolant.inlet_T_C),
                 flowLmin=float(coolant.flow_L_per_min)),
        track=export_track(track) if track is not None else None,
        observer=observer or {},
        courses=courses or {},
        strategy=strategy or {})


# ============================================================================
#  DIGITAL TWIN OBSERVER
# ============================================================================

def build_observer(geom, cell, coolant, n_sensors=6, n_ensemble=14,
                   seconds=900.0, dt=2.0, sample_every=6,
                   sensor_noise_K=0.5, rng_seed=17):
    """Pick thermistor positions and fit the gain that reconstructs the field.

    You will fit 4-8 thermistors to 546 cells. The BMS therefore never sees the
    pack -- it sees a handful of CAN temperatures and has to infer the rest.
    This computes:

      * WHERE to put them (greedy forward selection against pack maximum), and
      * an ensemble Kalman gain K that turns those few readings back into a
        full-field estimate:  T_est = T_model + K (y_measured - H T_model)

    K is fitted offline across an ensemble of perturbed runs, then applied
    online as a fixed matrix multiply -- 546 x 6 is 3276 MACs, nothing.
    """
    import simulator as sm
    N = geom.n_cells
    rng = np.random.default_rng(rng_seed)

    def make(seed):
        r0 = np.random.default_rng(1000 + seed)
        K = pt.Coolant(flow_L_per_min=float(r0.uniform(6.0, 10.0)),
                       inlet_T_C=float(r0.uniform(25, 34)),
                       rho_kg_m3=coolant.rho_kg_m3, cp_J_kgK=coolant.cp_J_kgK,
                       mu_Pa_s=coolant.mu_Pa_s, k_W_mK=coolant.k_W_mK)
        segs = [(int(d * r0.uniform(.8, 1.2)), int(w * r0.uniform(.85, 1.15)))
                for d, w in pt.mebc_endurance_lap()]
        _, p = pt.build_power_profile(segs, seconds, dt)
        cap, res = pt.make_population(N, 0.015, 0.060, -0.4, r0)
        cap, res = pt.place_cells(geom, cap, res, "random", r0)
        sim = sm.PackSimulator(geom, cell, K, dt=dt,
                               T_init_C=float(r0.uniform(26, 33)),
                               T_ambient_C=float(r0.uniform(28, 40)),
                               cap_mult=cap, res_mult=res)
        return sim, p

    # --- collect the ensemble once, reuse for both placement and gain ---
    X, Y = [], []
    for m in range(n_ensemble):
        sim, p = make(m)
        xs, ys = [], []
        for k in range(len(p)):
            sim.step(power_W=p[k])
            if k % sample_every == 0:
                xs.append(sim.T_core_C.copy())
                ys.append(sim.T_can_C.copy())
        X.append(np.array(xs)); Y.append(np.array(ys))
    nt = min(len(a) for a in X)
    X = np.stack([a[:nt] for a in X])          # (M, T, N) truth cores
    Y = np.stack([a[:nt] for a in Y])          # (M, T, N) can temperatures

    # --- greedy sensor placement against the pack maximum ---
    Yf = Y.reshape(-1, N)
    tgt = X.reshape(-1, N).max(axis=1)
    Yn = Yf + rng.normal(0, sensor_noise_K, Yf.shape)
    cands = list(range(0, N, max(1, N // 220)))
    chosen = []
    for _ in range(n_sensors):
        best, bj = np.inf, None
        for j in cands:
            if j in chosen:
                continue
            A = np.column_stack([Yn[:, chosen + [j]], np.ones(len(tgt))])
            c, *_ = np.linalg.lstsq(A, tgt, rcond=None)
            e = float(np.sqrt(np.mean((A @ c - tgt) ** 2)))
            if e < best:
                best, bj = e, j
        chosen.append(bj)
    chosen = np.array(chosen)

    # --- ensemble Kalman gain on anomalies about the ensemble mean ---
    Xa = (X - X.mean(axis=0, keepdims=True)).reshape(-1, N)
    Ya = (Y[:, :, chosen] - Y[:, :, chosen].mean(axis=0, keepdims=True)
          ).reshape(-1, len(chosen))
    n = len(Xa)
    Pxy = Xa.T @ Ya / (n - 1)
    Pyy = Ya.T @ Ya / (n - 1) + np.eye(len(chosen)) * sensor_noise_K ** 2
    K = Pxy @ np.linalg.inv(Pyy)

    # --- score on a held-out truth, against a model with WRONG assumptions ---
    # The open-loop baseline has to be an honest one: a model that does not
    # know the real ambient, flow, inlet temperature or cell population, which
    # is exactly the situation on the boat. Scoring against the truth's own
    # mean would be circular and would make the observer look useless.
    truth_sim, p = make(500)
    model = sm.PackSimulator(geom, cell, coolant, dt=dt, T_init_C=28.0,
                             T_ambient_C=30.0)
    errs_ol, errs_cl = [], []
    for k in range(len(p)):
        truth_sim.step(power_W=p[k])
        model.step(I_pack=truth_sim.I_pack)      # twin is driven by the shunt
        if k % sample_every == 0 and k > 60:
            truth = truth_sim.T_core_C
            pred = model.T_core_C
            y = truth_sim.T_can_C[chosen] + rng.normal(0, sensor_noise_K,
                                                       len(chosen))
            est = pred + K @ (y - model.T_can_C[chosen])
            errs_ol.append(float(np.sqrt(np.mean((pred - truth) ** 2))))
            errs_cl.append(float(np.sqrt(np.mean((est - truth) ** 2))))
    return dict(cells=[int(c) for c in chosen],
                K=[[float(v) for v in row] for row in K],
                noise=float(sensor_noise_K),
                rms_open=float(np.mean(errs_ol)),
                rms_closed=float(np.mean(errs_cl)),
                n_ensemble=int(n_ensemble))


# ============================================================================
#  PYTHON MIRROR OF THE BROWSER ENGINE  (for verification)
# ============================================================================

def _interp(x, xs, ys):
    return np.interp(x, xs, ys)


def run_mirror(model, power_W, dt=0.5, T_init_C=28.0):
    """Bit-for-bit mirror of the JS engine, in Python, so it can be checked
    against the implicit reference solver."""
    m, th, cl = model["meta"], model["thermal"], model["cell"]
    N, S, P = m["nCells"], m["nSeries"], m["nParallel"]
    nSeg = th["nSeg"]

    Tcore = np.full(N, T_init_C); Tcan = np.full(N, T_init_C)
    Tbus = np.full(m["nSeries"] - 1, T_init_C)
    Tair = model["env"]["TambC"]
    Tseg = np.full(max(nSeg, 1), model["env"]["TinC"])
    z = np.ones(N); v1 = np.zeros(N); v2 = np.zeros(N)

    nb = np.array(th["neighbours"]) if th["neighbours"] else np.zeros((0, 3))
    cp = np.array(th["coolPairs"]) if th["coolPairs"] else np.zeros((0, 3))
    gAir = np.array(th["gAir"])
    capAh = cl["capAh"] * np.array(cl["capMult"])
    resM = np.array(cl["resMult"])
    socG = np.array(cl["socGrid"]); Tg = np.array(cl["Tgrid"])
    R0map = np.array(cl["R0map"])
    e1, e2 = np.exp(-dt / cl["tau1"]), np.exp(-dt / cl["tau2"])
    mcp = th["mdotCpPerCircuit"]

    def R0_of(T, zz):
        Tc = np.clip(T, Tg[0], Tg[-1])
        if len(Tg) == 1:
            return np.interp(zz, socG, R0map[0]) * resM
        i = np.clip(np.searchsorted(Tg, Tc) - 1, 0, len(Tg) - 2)
        w = (Tc - Tg[i]) / (Tg[i + 1] - Tg[i])
        lo = np.array([np.interp(zz, socG, R0map[k]) for k in range(len(Tg))])
        return (lo[i, np.arange(len(zz))] * (1 - w)
                + lo[i + 1, np.arange(len(zz))] * w) * resM

    out = {k: [] for k in ("Tmax", "Tmean", "Ipack", "Vpack", "Wh")}
    Wh = 0.0
    gsum = gbus = None; gair_tot = 0.0
    for k in range(len(power_W)):
        R0 = R0_of(Tcore, z)
        R1, R2 = R0 * cl["f1"], R0 * cl["f2"]
        U = np.interp(z, cl["ocvSoc"], cl["ocvV"])

        a = (U - v1 - v2) / R0
        b = 1.0 / R0
        A = a.reshape(S, P).sum(axis=1)
        B = b.reshape(S, P).sum(axis=1)
        Voc = float((A / B).sum()); Rc = float((1.0 / B).sum())
        Rbus = th["busR"] * th["nBus"]      # interconnects carry pack current
        Reff = Rc + Rbus
        Pbus = power_W[k] / m["inverterEff"]
        disc = Voc * Voc - 4 * Reff * Pbus
        Ip = Voc / (2 * Reff) if disc <= 0 else (Voc - np.sqrt(disc)) / (2 * Reff)
        Vg = (A - Ip) / B
        Vterm = float(Vg.sum()) - Ip * Rbus
        Vf = np.repeat(Vg, P)
        I = a - Vf * b
        q = I * (U - Vf) - I * (Tcore + 273.15) * np.interp(
            z, cl["dudtSoc"], cl["dudtV"])
        qbus = Ip * Ip * th["busR"]

        # --- coolant: quasi-static forward sweep in flow order -----------
        if nSeg:
            num = np.zeros(nSeg); den = np.zeros(nSeg)
            if len(cp):
                np.add.at(num, cp[:, 1].astype(int), cp[:, 2] * Tcan[cp[:, 0].astype(int)])
                np.add.at(den, cp[:, 1].astype(int), cp[:, 2])
            for seg, upn in th["coolChain"]:
                Tup = model["env"]["TinC"] if upn < 0 else Tseg[upn]
                Tseg[seg] = (mcp * Tup + num[seg]) / (mcp + den[seg])

        # --- EXPONENTIAL Euler (mirrors the browser engine) --------------
        gcc = th["gCoreCan"]
        sidx = np.array(model["display"]["series"]); gcb = th["gCanBus"]
        if gsum is None:
            gsum = np.full(N, gcc) + gAir
            if len(nb):
                np.add.at(gsum, nb[:, 0].astype(int), nb[:, 2])
                np.add.at(gsum, nb[:, 1].astype(int), nb[:, 2])
            if len(cp):
                np.add.at(gsum, cp[:, 0].astype(int), cp[:, 2])
            gsum += gcb * ((sidx < th["nBus"]).astype(float)
                           + (sidx - 1 >= 0).astype(float))
            gbus = np.full(max(th["nBus"], 1), 0.5)
            for b in range(th["nBus"]):
                gbus[b] += gcb * (((sidx == b).sum()) + ((sidx == b + 1).sum()))
            gair_tot = th["UAair"] + gAir.sum()

        nbsum = np.zeros(N)
        if len(nb):
            i0 = nb[:, 0].astype(int); j0 = nb[:, 1].astype(int); g = nb[:, 2]
            np.add.at(nbsum, i0, g * Tcan[j0]); np.add.at(nbsum, j0, g * Tcan[i0])
        if len(cp):
            np.add.at(nbsum, cp[:, 0].astype(int),
                      cp[:, 2] * Tseg[cp[:, 1].astype(int)])
        for b in range(th["nBus"]):
            nbsum[sidx == b] += gcb * Tbus[b]
            nbsum[sidx == b + 1] += gcb * Tbus[b]

        fb = np.zeros(max(th["nBus"], 1))
        for b in range(th["nBus"]):
            fb[b] = gcb * (Tcan[sidx == b].sum() + Tcan[sidx == b + 1].sum())
        air_src = th["UAair"] * model["env"]["TambC"] + (gAir * Tcan).sum()

        ssC = (q + gcc * Tcan) / gcc
        Tcore = ssC + (Tcore - ssC) * np.exp(-(gcc / th["Ccore"]) * dt)
        ssA = (gcc * Tcore + nbsum + gAir * Tair) / gsum
        Tcan = ssA + (Tcan - ssA) * np.exp(-(gsum / th["Ccan"]) * dt)
        for b in range(th["nBus"]):
            ss = (qbus + fb[b] + 0.5 * Tair) / gbus[b]
            Tbus[b] = ss + (Tbus[b] - ss) * np.exp(-(gbus[b] / th["Cbus"]) * dt)
        ssAir = air_src / gair_tot
        Tair = ssAir + (Tair - ssAir) * np.exp(-(gair_tot / th["Cair"]) * dt)

        v1 = v1 * e1 + I * R1 * (1 - e1)
        v2 = v2 * e2 + I * R2 * (1 - e2)
        cf = (np.interp(Tcore, cl["capT"], cl["capF"])
              if cl.get("capT") else 1.0)
        z = z - I * dt / (3600.0 * capAh * cf)
        Wh += Vterm * Ip * dt / 3600.0

        out["Tmax"].append(Tcore.max()); out["Tmean"].append(Tcore.mean())
        out["Ipack"].append(Ip); out["Vpack"].append(float(Vg.sum()))
        out["Wh"].append(Wh)
    return {k: np.array(v) for k, v in out.items()}


def verify_scheme(geom, cell, coolant, hull, resistance, propeller, course,
                  cap_mult=None, res_mult=None, dt=0.5, seconds=900.0,
                  T_init_C=28.0, T_ambient_C=30.0):
    """Run the mirror against the implicit reference and report the error."""
    model = export_model(geom, cell, coolant, hull, resistance, propeller,
                         course, T_ambient_C=T_ambient_C,
                         cap_mult=cap_mult, res_mult=res_mult)
    _, p = pt.build_power_profile(pt.mebc_endurance_lap(), seconds, dt)

    ref = pt.simulate(geom, cell, coolant, p, dt=dt, T_init_C=T_init_C,
                      T_ambient_C=T_ambient_C, cap_mult=cap_mult,
                      res_mult=res_mult, store_every=1)
    mir = run_mirror(model, p, dt=dt, T_init_C=T_init_C)
    n = min(len(ref.t), len(mir["Tmax"]))
    return dict(
        model=model,
        Tmax_ref=float(ref.T_core_C.max()), Tmax_mirror=float(mir["Tmax"].max()),
        Tmax_rms_K=float(np.sqrt(np.mean(
            (ref.T_core_C.max(axis=1)[:n] - mir["Tmax"][:n]) ** 2))),
        Tmax_worst_K=float(np.max(np.abs(
            ref.T_core_C.max(axis=1)[:n] - mir["Tmax"][:n]))),
        Wh_ref=float(ref.energy_out_Wh[-1]), Wh_mirror=float(mir["Wh"][-1]),
        Wh_err_pct=float(abs(mir["Wh"][-1] - ref.energy_out_Wh[-1])
                         / max(ref.energy_out_Wh[-1], 1e-9) * 100),
        I_rms_A=float(np.sqrt(np.mean((ref.I_pack[:n] - mir["Ipack"][:n]) ** 2))))


def write_model_json(model, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, separators=(",", ":"))
    import os
    return path, os.path.getsize(path)
