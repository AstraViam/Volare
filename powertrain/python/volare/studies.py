"""
volare_thermal.studies
======================
Six investigations against the coupled model.  Run:  python3 studies.py
Figures are written to ./figures/.
"""

from __future__ import annotations
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pack_thermal as pt

FIG = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG, exist_ok=True)

CELL = pt.CellParams()


def baseline_layout(**kw):
    d = dict(n_series=26, n_parallel=21, tube_every=2, n_circuits=3)
    d.update(kw)
    return pt.PackLayout(**d)


def rule(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------------------
# STUDY 0 -- VALIDATION
# ---------------------------------------------------------------------------
def study_validation(strict=True):
    """Analytic validations of the reference solver.

    strict=True makes this ASSERT rather than merely print. Printing a 75 %
    error and returning success is not a validation, it is a log line — and
    that is exactly how an inverted core-can conductance slipped past the
    consolidated suite until the sabotage matrix exposed it.
    """
    fails = []

    def need(name, value, limit, detail=""):
        bad = not (abs(value) <= limit)
        print(f"      {'FAIL' if bad else 'ok  '}  {name}: {value:.4f} "
              f"(limit {limit}) {detail}")
        if bad:
            fails.append(name)

    rule("STUDY 0 — VALIDATION AGAINST ANALYTIC RESULTS")
    L, K = baseline_layout(), pt.Coolant()

    # (a) adiabatic energy balance
    t, p = pt.constant_power_profile(26000, 600, 0.5)
    r = pt.simulate(L, CELL, K, p, dt=0.5, T_init_C=25,
                    adiabatic=True, store_every=1)
    dT_sim = r.T_core_C[-1].mean() - 25.0
    q_int = np.trapezoid(r.q_total - r.q_busbar, r.t)
    dT_an = q_int / (L.n_cells * CELL.thermal_capacity_JK)
    print(f"(a) adiabatic rise      sim {dT_sim:7.3f} K   analytic {dT_an:7.3f} K"
          f"   err {abs(dT_sim-dT_an)/dT_an*100:5.2f} %")
    need("adiabatic energy balance", abs(dT_sim-dT_an)/dT_an*100, 3.0, "%")

    # (b) core->can gradient at TRUE steady state (SOC frozen via huge capacity)
    big = np.full(L.n_cells, 200.0)          # 200x capacity => SOC ~ constant
    t, p = pt.constant_power_profile(13000, 4000, 0.5)
    r = pt.simulate(L, CELL, K, p, dt=0.5, T_init_C=28,
                    cap_mult=big, store_every=200)
    q = r.q_cell[-1].mean()
    g = (r.T_core_C[-1] - r.T_can_C[-1]).mean()
    print(f"(b) core-can gradient   sim {g:7.3f} K   analytic {q*CELL.R_core_can_KW:7.3f} K"
          f"   err {abs(g-q*CELL.R_core_can_KW)/(q*CELL.R_core_can_KW)*100:5.2f} %")
    need("core-can gradient at steady state",
         abs(g-q*CELL.R_core_can_KW)/(q*CELL.R_core_can_KW)*100, 2.0, "%")

    # (c) coolant energy balance
    q_tot = r.q_total[-1]
    env = (r.T_air_C[-1] - 30.0) * L.enclosure_UA_WK
    dT_an = (q_tot - env) / (K.mdot_kg_s * K.cp_J_kgK)
    print(f"(c) coolant mixed rise  analytic {dT_an:7.3f} K "
          f"(pack {q_tot:.0f} W, envelope {env:.0f} W)")

    # (d) Kirchhoff
    S, P = L.n_series, L.n_parallel
    Ig = r.I_cell.reshape(len(r.t), S, P).sum(axis=2)
    kerr = float(np.abs(Ig - r.I_pack[:, None]).max())
    print(f"(d) Kirchhoff           max |sum(I_cell)-I_pack| = {kerr:.2e} A")
    need("Kirchhoff residual", kerr, 1e-6, "A")

    # (e) timestep independence
    print("(e) timestep independence:")
    tms = []
    for dt in (2.0, 1.0, 0.5, 0.25):
        _, p = pt.build_power_profile(pt.mebc_endurance_lap(), 900, dt)
        rr = pt.simulate(L, CELL, K, p, dt=dt, T_init_C=28, store_every=1)
        tms.append(float(rr.T_core_C.max()))
        print(f"      dt={dt:5.2f} s -> T_max {rr.T_core_C.max():7.4f} C")
    need("timestep spread", max(tms) - min(tms), 0.05, "K")

    print()
    if fails:
        print(f"  {len(fails)} VALIDATION FAILURE(S): {fails}")
        if strict:
            raise AssertionError("solver validation failed: " + ", ".join(fails))
    else:
        print("  all analytic validations within tolerance")
    return fails


# ---------------------------------------------------------------------------
# STUDY 1 -- BASELINE + SPATIAL MAP
# ---------------------------------------------------------------------------
def study_baseline():
    rule("STUDY 1 — BASELINE 26S21P, ENDURANCE CYCLE, SPATIAL MAP")
    L, K = baseline_layout(), pt.Coolant()
    hyd = L.hydraulics(K)
    print(f"  routing: {hyd['n_tubes']} tubes in {hyd['n_circuits']} circuits, "
          f"{hyd['flow_per_circuit_L_min']:.2f} L/min each")
    print(f"  Re {hyd['Re']:.0f} ({hyd['regime']}), h {hyd['h_W_m2K']:.0f} W/m2K, "
          f"dP {hyd['dP_bar']:.3f} bar")
    print(f"  R_cell->coolant = {L.R_can_tubewall_KW:.2f} (wall) + "
          f"{hyd['R_conv_per_cell_KW']:.2f} (convection) = "
          f"{hyd['R_total_per_tube_KW']:.2f} K/W per tube")

    _, p = pt.build_power_profile(pt.mebc_endurance_lap(), 2400, 0.5)
    r = pt.simulate(L, CELL, K, p, dt=0.5, T_init_C=28, T_ambient_C=30)
    s = pt.summarise(r, L, "baseline")
    for k, v in s.items():
        print(f"    {k:24s} {v if isinstance(v, str) else round(v, 3)}")

    grid = pt.temperature_grid(r, L)
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    im = ax[0].imshow(grid, aspect="auto", cmap="inferno", origin="lower")
    ax[0].set_xlabel("parallel position (column)")
    ax[0].set_ylabel("series group (row)")
    ax[0].set_title("Cell core temperature at end of run [degC]")
    plt.colorbar(im, ax=ax[0])
    ax[1].plot(r.t / 60, r.T_core_C.max(axis=1), label="hottest cell")
    ax[1].plot(r.t / 60, r.T_core_C.mean(axis=1), label="mean cell")
    ax[1].plot(r.t / 60, r.T_core_C.min(axis=1), label="coolest cell")
    ax[1].plot(r.t / 60, r.T_bus_C.max(axis=1), "--", label="hottest busbar")
    ax[1].plot(r.t / 60, r.T_cool_C.max(axis=1), ":", label="coolant outlet")
    ax[1].axhline(CELL.T_warn_C, color="orange", lw=0.8)
    ax[1].axhline(CELL.T_max_C, color="red", lw=0.8)
    ax[1].set_xlabel("time [min]"); ax[1].set_ylabel("temperature [degC]")
    ax[1].legend(fontsize=8); ax[1].grid(alpha=0.3)
    ax[1].set_title("Thermal history")
    fig.tight_layout(); fig.savefig(f"{FIG}/01_baseline.png", dpi=130)
    plt.close(fig)
    print(f"  -> {FIG}/01_baseline.png")
    return r


# ---------------------------------------------------------------------------
# STUDY 2 -- COOLING ARCHITECTURE SWEEP
# ---------------------------------------------------------------------------
def study_cooling_sweep():
    rule("STUDY 2 — COOLING ARCHITECTURE SWEEP (the central design trade)")
    K = pt.Coolant()
    _, p = pt.build_power_profile(pt.mebc_endurance_lap(), 2400, 1.0)

    print(f"{'tube_every':>10} {'circuits':>9} {'Re':>7} {'regime':>13} "
          f"{'h':>7} {'Rtot':>6} {'dP bar':>7} {'T_max':>7} {'spread':>7}")
    print("-" * 82)
    rows = []
    for te in (1, 2, 3):
        for nc in (1, 2, 3, 4, 6, 13, 25):
            L = baseline_layout(tube_every=te, n_circuits=nc)
            if nc > L.n_tubes:
                continue
            h = L.hydraulics(K)
            r = pt.simulate(L, CELL, K, p, dt=1.0, T_init_C=28,
                            T_ambient_C=30, store_every=10)
            s = pt.summarise(r, L)
            rows.append((te, L.n_circuits_eff, h["Re"], h["regime"],
                         h["h_W_m2K"], h["R_total_per_tube_KW"],
                         h["dP_bar"], s["T_max_C"], s["T_spread_K"]))
            print(f"{te:>10} {L.n_circuits_eff:>9} {h['Re']:>7.0f} "
                  f"{h['regime']:>13} {h['h_W_m2K']:>7.0f} "
                  f"{h['R_total_per_tube_KW']:>6.2f} {h['dP_bar']:>7.3f} "
                  f"{s['T_max_C']:>7.2f} {s['T_spread_K']:>7.2f}")

    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    for te, mk in zip((1, 2, 3), ("o-", "s-", "^-")):
        sub = [x for x in rows if x[0] == te]
        ax[0].plot([x[1] for x in sub], [x[7] for x in sub], mk,
                   label=f"tube every {te} gap(s)")
        ax[1].plot([x[6] for x in sub], [x[7] for x in sub], mk,
                   label=f"tube every {te} gap(s)")
    ax[0].set_xlabel("number of parallel hydraulic circuits")
    ax[0].set_ylabel("peak cell temperature [degC]")
    ax[0].set_title("Fewer circuits = faster flow = turbulent = colder")
    ax[1].set_xlabel("circuit pressure drop [bar]")
    ax[1].set_ylabel("peak cell temperature [degC]")
    ax[1].axvline(0.5, color="red", ls="--", lw=0.9)
    ax[1].text(0.52, ax[1].get_ylim()[1]*0.98, "typical 12 V pump limit",
               color="red", fontsize=8, va="top")
    ax[1].set_title("The real constraint: pump head")
    for a in ax:
        a.grid(alpha=0.3); a.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(f"{FIG}/02_cooling_sweep.png", dpi=130)
    plt.close(fig)
    print(f"  -> {FIG}/02_cooling_sweep.png")


# ---------------------------------------------------------------------------
# STUDY 3 -- CELL VARIATION, CURRENT HOGGING, GRADING PAYOFF
# ---------------------------------------------------------------------------
def study_grading():
    rule("STUDY 3 — CELL VARIATION, CURRENT HOGGING, AND THE GRADING PAYOFF")
    L, K = baseline_layout(), pt.Coolant()
    _, p = pt.build_power_profile(pt.mebc_endurance_lap(), 2400, 0.5)
    rng = np.random.default_rng(42)

    # baseline uniform run gives the "coolness" map for thermal placement
    r0 = pt.simulate(L, CELL, K, p, dt=0.5, T_init_C=28, store_every=20)
    coolness = -r0.T_core_C[-1]

    cases = [
        ("identical cells (fiction)", 0.000, 0.000, "random"),
        ("ungraded batch",            0.015, 0.060, "random"),
        ("graded +/-1% / +/-5%",      0.004, 0.017, "random"),
        ("graded + capacity-balanced", 0.004, 0.017, "balanced"),
        ("graded + thermal placement", 0.004, 0.017, "thermal"),
        ("BAD batch (mixed sources)", 0.040, 0.150, "random"),
    ]

    print(f"{'case':<28} {'hog':>6} {'T_max':>7} {'spread':>7} "
          f"{'SOCspread%':>11} {'Wh':>7}")
    print("-" * 76)
    results = []
    for label, sq, sr, strat in cases:
        cap, res = pt.make_population(L.n_cells, sq, sr, -0.4,
                                      np.random.default_rng(7))
        cap, res = pt.place_cells(L, cap, res, strat, rng, coolness)
        r = pt.simulate(L, CELL, K, p, dt=0.5, T_init_C=28,
                        cap_mult=cap, res_mult=res, store_every=20)
        s = pt.summarise(r, L, label)
        results.append((label, r, s))
        print(f"{label:<28} {s['I_hog_ratio']:>6.3f} {s['T_max_C']:>7.2f} "
              f"{s['T_spread_K']:>7.2f} {s['soc_spread_final_pct']:>11.2f} "
              f"{s['energy_Wh']:>7.0f}")

    # current sharing inside one parallel group, ungraded vs graded
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    for label, r, s in results:
        if label.startswith(("ungraded", "graded +/-1", "BAD")):
            S, P = L.n_series, L.n_parallel
            Ig = r.I_cell.reshape(len(r.t), S, P)[:, S // 2, :]
            ax[0].plot(r.t / 60, Ig[:, np.argmax(Ig[-1])], lw=1.2,
                       label=f"{label} (hottest cell)")
            ax[0].plot(r.t / 60, Ig[:, np.argmin(Ig[-1])], lw=1.2, ls="--",
                       label=f"{label} (coldest cell)")
    ax[0].set_xlabel("time [min]"); ax[0].set_ylabel("cell current [A]")
    ax[0].set_title("Current sharing within one parallel group")
    ax[0].legend(fontsize=7); ax[0].grid(alpha=0.3)

    labels = [x[0] for x in results]
    ax[1].barh(labels, [x[2]["T_max_C"] for x in results], color="firebrick")
    ax[1].set_xlabel("peak cell temperature [degC]")
    ax[1].set_xlim(min(x[2]["T_max_C"] for x in results) - 1,
                   max(x[2]["T_max_C"] for x in results) + 1)
    ax[1].grid(alpha=0.3, axis="x")
    ax[2].barh(labels, [x[2]["soc_spread_final_pct"] for x in results],
               color="steelblue")
    ax[2].set_xlabel("end-of-run SOC spread [%]")
    ax[2].grid(alpha=0.3, axis="x")
    for a in (ax[1], ax[2]):
        a.tick_params(labelsize=8)
    fig.tight_layout(); fig.savefig(f"{FIG}/03_grading.png", dpi=130)
    plt.close(fig)
    print(f"  -> {FIG}/03_grading.png")

    # how much of the imbalance is thermal feedback vs manufacturing spread?
    rule("  3b — decomposition: manufacturing spread vs thermal feedback")
    cap, res = pt.make_population(L.n_cells, 0.015, 0.060, -0.4,
                                  np.random.default_rng(7))
    cap, res = pt.place_cells(L, cap, res, "random", np.random.default_rng(1))
    for tag, Ea in (("thermal feedback ON  (Ea/R=2500)", 2500.0),
                    ("thermal feedback OFF (Ea/R=0)", 0.0)):
        c2 = pt.CellParams(Ea_over_R_K=Ea)
        r = pt.simulate(L, c2, K, p, dt=0.5, T_init_C=28,
                        cap_mult=cap, res_mult=res, store_every=20)
        s = pt.summarise(r, L)
        print(f"    {tag:36s} hog {s['I_hog_ratio']:.4f}  "
              f"T_max {s['T_max_C']:.2f} C  spread {s['T_spread_K']:.2f} K")


# ---------------------------------------------------------------------------
# STUDY 4 -- WORST CASE
# ---------------------------------------------------------------------------
def study_worst_case():
    rule("STUDY 4 — WORST CASE: SUSTAINED 25 kW, HOT DAY, PUMP FAILURE")
    K = pt.Coolant()
    scenarios = [
        ("25 kW sustained, cooling OK", dict(), K, 30.0, False),
        ("25 kW, hot day (ambient 40C, sea 30C)", dict(),
         pt.Coolant(inlet_T_C=33.0), 40.0, False),
        ("25 kW, HALF flow (partial blockage)", dict(),
         pt.Coolant(flow_L_per_min=4.0), 30.0, False),
        ("25 kW, PUMP DEAD (adiabatic bound)", dict(), K, 30.0, True),
        ("25 kW, water+inhibitor not glycol", dict(),
         pt.Coolant(rho_kg_m3=997, cp_J_kgK=4180, mu_Pa_s=0.0008,
                    k_W_mK=0.62), 30.0, False),
    ]
    _, p = pt.constant_power_profile(25000, 1500, 0.5)
    print(f"{'scenario':<42} {'t_end':>7} {'T_max':>7} {'>45C?':>6} {'>60C?':>6}")
    print("-" * 74)
    for label, kw, cool, tamb, adia in scenarios:
        L = baseline_layout(**kw)
        r = pt.simulate(L, CELL, cool, p, dt=0.5, T_init_C=tamb - 2,
                        T_ambient_C=tamb, adiabatic=adia, store_every=20)
        s = pt.summarise(r, L, label)
        print(f"{label:<42} {s['t_end_s']:>7.0f} {s['T_max_C']:>7.1f} "
              f"{'YES' if s['T_max_C'] > 45 else 'no':>6} "
              f"{'YES' if s['T_max_C'] > 60 else 'no':>6}")


# ---------------------------------------------------------------------------
# STUDY 5 -- SENSOR PLACEMENT (ENERGY_REQ_67 / _68)
# ---------------------------------------------------------------------------
SENSOR_NOISE_K = 0.5      # realistic 10k NTC + ADC + self-heating


def _realisation(seed):
    """One randomised operating condition: population, ambient, flow, cycle."""
    r0 = np.random.default_rng(seed)
    L = pt.PackLayout(n_series=26, n_parallel=21, tube_every=2, n_circuits=3)
    K = pt.Coolant(flow_L_per_min=float(r0.uniform(6.5, 9.5)),
                   inlet_T_C=float(r0.uniform(26, 33)))
    segs = [(int(d * r0.uniform(0.8, 1.2)), int(w * r0.uniform(0.85, 1.15)))
            for d, w in pt.mebc_endurance_lap()]
    _, p = pt.build_power_profile(segs, 1800, 1.0)
    cap, res = pt.make_population(L.n_cells, 0.015, 0.060, -0.4, r0)
    cap, res = pt.place_cells(L, cap, res, "random", r0)
    r = pt.simulate(L, CELL, K, p, dt=1.0, T_init_C=float(r0.uniform(26, 34)),
                    T_ambient_C=float(r0.uniform(28, 40)),
                    cap_mult=cap, res_mult=res, store_every=10)
    return L, r


def study_sensors():
    """How many thermistors, and where?

    CRITICAL METHOD NOTE: the estimator is FITTED on one set of realisations
    and EVALUATED on held-out ones, with realistic sensor noise added.  Fitting
    and evaluating on the same deterministic run gives ~0.05 K errors and is
    meaningless -- it measures interpolation, not prediction.
    """
    rule("STUDY 5 — THERMISTOR PLACEMENT FOR ENERGY_REQ_67 / _68")
    rng = np.random.default_rng(11)
    L, _ = _realisation(0)

    def stack(seeds):
        X, y = [], []
        for s in seeds:
            _, r = _realisation(s)
            X.append(r.T_can_C); y.append(r.T_core_C.max(axis=1))
        X = np.vstack(X)
        return X + rng.normal(0, SENSOR_NOISE_K, X.shape), np.concatenate(y)

    print(f"  ensemble: 8 train + 4 held-out realisations, "
          f"{SENSOR_NOISE_K} K sensor noise")
    Xtr, ytr = stack(range(8))
    Xte, yte = stack(range(100, 104))

    def fit_eval(cols):
        A = np.column_stack([Xtr[:, cols], np.ones(len(ytr))])
        c, *_ = np.linalg.lstsq(A, ytr, rcond=None)
        pred = np.column_stack([Xte[:, cols], np.ones(len(yte))]) @ c
        return (float(np.sqrt(np.mean((pred - yte) ** 2))),
                float(np.max(np.abs(pred - yte))))

    cands = list(range(0, L.n_cells, 3))
    chosen = []
    print(f"\n  greedy placement, scored on HELD-OUT data:")
    print(f"  {'n':>3} {'row':>4} {'col':>4} {'RMS K':>8} {'worst K':>9}")
    for _ in range(8):
        best = (np.inf, None)
        for j in cands:
            if j in chosen:
                continue
            e, _m = fit_eval(chosen + [j])
            if e < best[0]:
                best = (e, j)
        chosen.append(best[1])
        rms, mx = fit_eval(chosen)
        print(f"  {len(chosen):>3} {int(L.row[best[1]]):>4} "
              f"{int(L.col[best[1]]):>4} {rms:>8.3f} {mx:>9.3f}")

    print("\n  naive placements, same evaluation:")
    for n in (1, 4, 8):
        stride = max(1, L.n_cells // n)
        rms, mx = fit_eval(list(range(0, L.n_cells, stride))[:n])
        print(f"    {n:>2} evenly spaced      RMS {rms:6.3f} K  worst {mx:6.3f} K")
    cols = [g * L.n_parallel + L.n_parallel // 2 for g in range(L.n_series)]
    rms, mx = fit_eval(cols)
    print(f"    {len(cols):>2} one per group     RMS {rms:6.3f} K  worst {mx:6.3f} K")

    print("\n  redundancy: drop each chosen sensor, refit on the other 7")
    for k in range(len(chosen)):
        rms, mx = fit_eval([c for i, c in enumerate(chosen) if i != k])
        print(f"    without #{k+1} (row {int(L.row[chosen[k]]):2d}): "
              f"RMS {rms:.3f} K, worst {mx:.3f} K")

    _, rr = _realisation(0)
    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.imshow(pt.temperature_grid(rr, L), aspect="auto",
                   cmap="inferno", origin="lower")
    ax.scatter([int(L.col[c]) for c in chosen], [int(L.row[c]) for c in chosen],
               s=110, marker="x", c="cyan", linewidths=2.2,
               label="optimal sensor positions")
    ax.set_xlabel("parallel position"); ax.set_ylabel("series group")
    ax.set_title("Where to put 8 thermistors")
    ax.legend(fontsize=8); plt.colorbar(im, ax=ax)
    fig.tight_layout(); fig.savefig(f"{FIG}/05_sensors.png", dpi=130)
    plt.close(fig)
    print(f"  -> {FIG}/05_sensors.png")


# ---------------------------------------------------------------------------
# STUDY 6 -- TUBE COVERAGE AND THE ORPHANED EDGE ROW
# ---------------------------------------------------------------------------
def study_coverage():
    rule("STUDY 6 — TUBE COVERAGE: THE ORPHANED EDGE ROW")
    K = pt.Coolant()
    _, p = pt.build_power_profile(pt.mebc_endurance_lap(), 2400, 1.0)
    print(f"{'layout':<34} {'tubes':>6} {'uncooled rows':>28} {'T_max':>7}")
    print("-" * 80)
    for ns, te, tag in [(26, 1, "26 rows, tube every gap"),
                        (26, 2, "26 rows, tube every 2nd gap"),
                        (26, 3, "26 rows, tube every 3rd gap"),
                        (26, 4, "26 rows, tube every 4th gap"),
                        (25, 2, "25 rows (ODD), tube every 2nd gap")]:
        L = pt.PackLayout(n_series=ns, n_parallel=21, tube_every=te,
                          n_circuits=3)
        cooled = {int(L.row[i]) for i, _ in L.cell_coolant_pairs}
        unc = [r for r in range(ns) if r not in cooled]
        r = pt.simulate(L, CELL, K, p, dt=1.0, T_init_C=28, store_every=20)
        print(f"{tag:<34} {L.n_tubes:>6} {str(unc):>28} "
              f"{r.T_core_C.max():>7.2f}")


if __name__ == "__main__":
    study_validation()
    study_baseline()
    study_cooling_sweep()
    study_grading()
    study_worst_case()
    study_sensors()
    study_coverage()
    print("\nAll studies complete. Figures in ./figures/\n")
