r"""
volare_thermal.simulator
========================

Turns the batch model in pack_thermal.py into three things:

1.  PackSimulator  -- a STEPPER.  Advance one timestep at a time, driven by
    either a commanded power, or a MEASURED pack current from CAN.  This is
    what lets the same model run offline (design), faster-than-real-time
    (race strategy lookahead), or in lockstep with the boat (digital twin).

2.  EnsembleObserver -- a DIGITAL TWIN correction.  You will have 4-8
    thermistors on 546 cells.  The open-loop model drifts because the drive
    cycle, ambient, flow and cell population are never exactly what you
    assumed.  The observer blends model prediction with live thermistor
    readings and reconstructs the WHOLE spatial field, including the 540
    cells you cannot measure.  That is the difference between a simulation
    and a simulator.

3.  animate_race() -- spatial temperature field over the race, with the power
    trace and energy budget alongside.

WHY AN OBSERVER RATHER THAN JUST THE MODEL
------------------------------------------
Open loop, every modelling error integrates.  Closed loop, the thermistors
pin the estimate down and the model interpolates between them using the
physics -- which is exactly what a bare linear regression on sensor readings
cannot do, because it has no notion of where the heat is going.

The gain is an ensemble Kalman gain:

    K = Cov(x', y') [Cov(y', y') + R]^-1

computed offline from an ensemble of perturbed runs, applied online as

    T_corrected = T_predicted + K (y_measured - H T_predicted)

It is a fixed matrix multiply.  For 546 cells x 6 sensors that is 3276
multiply-accumulates per correction step -- trivial on a Teensy 4.1.
"""

from __future__ import annotations

import time
import numpy as np
from dataclasses import dataclass, field

import pack_thermal as pt


# ============================================================================
#  1.  THE STEPPER
# ============================================================================

class PackSimulator:
    """Single-step-at-a-time coupled electro-thermal simulator.

    Usage (commanded power, offline):
        sim = PackSimulator(layout, cell, coolant)
        while sim.soc.mean() > 0.05:
            sim.step(power_W=13000)

    Usage (driven by live CAN data, digital twin):
        sim.step(I_pack=meas.current, coolant_inlet_C=meas.t_in,
                 flow_L_min=meas.flow)

    Factorisations are cached per flow-rate bin, so a varying pump speed does
    not force a re-factorisation every step (which would cost ~10 ms and
    destroy the real-time margin).
    """

    def __init__(self,
                 layout: pt.PackLayout,
                 cell: pt.CellParams,
                 coolant: pt.Coolant,
                 dt: float = 1.0,
                 T_init_C: float = 28.0,
                 T_ambient_C: float = 30.0,
                 soc_init: float = 1.0,
                 cap_mult: np.ndarray | None = None,
                 res_mult: np.ndarray | None = None,
                 inverter_eff: float = 0.96,
                 flow_bin_L_min: float = 0.5):
        self.layout, self.cell = layout, cell
        self.base_coolant = coolant
        self.dt = dt
        self.T_ambient_C = T_ambient_C
        self.inverter_eff = inverter_eff
        self.flow_bin = flow_bin_L_min

        N = layout.n_cells
        self.N, self.S, self.P = N, layout.n_series, layout.n_parallel
        self.cap_mult = np.ones(N) if cap_mult is None else cap_mult
        self.res_mult = np.ones(N) if res_mult is None else res_mult
        self.cap_Ah = cell.capacity_Ah * self.cap_mult

        self._cache: dict[float, tuple] = {}
        self.net, self.lu = self._network_for(coolant.flow_L_per_min)

        self.T = np.full(self.net.n_nodes, T_init_C + 273.15)
        self.T[self.net.i_cool] = coolant.inlet_T_C + 273.15
        self.T[self.net.i_air] = T_ambient_C + 273.15
        self.z = np.full(N, float(soc_init))
        self.v1 = np.zeros(N)
        self.v2 = np.zeros(N)

        self.e1 = np.exp(-dt / cell.tau1_s)
        self.e2 = np.exp(-dt / cell.tau2_s)

        self.t = 0.0
        self.energy_Wh = 0.0
        self.I_pack = 0.0
        self.V_pack = float(self.S * cell.ocv(soc_init))
        self.q_cell = np.zeros(N)
        self.last_inlet_C = coolant.inlet_T_C

    # -- network cache ---------------------------------------------------
    def _network_for(self, flow_L_min: float):
        key = round(flow_L_min / self.flow_bin) * self.flow_bin
        key = max(key, self.flow_bin)
        if key not in self._cache:
            c = pt.Coolant(flow_L_per_min=key,
                           inlet_T_C=self.base_coolant.inlet_T_C,
                           rho_kg_m3=self.base_coolant.rho_kg_m3,
                           cp_J_kgK=self.base_coolant.cp_J_kgK,
                           mu_Pa_s=self.base_coolant.mu_Pa_s,
                           k_W_mK=self.base_coolant.k_W_mK)
            net = pt.ThermalNetwork(self.layout, self.cell, c, self.T_ambient_C)
            self._cache[key] = (net, net.factorise(self.dt))
        return self._cache[key]

    # -- one step --------------------------------------------------------
    def step(self, power_W: float | None = None, I_pack: float | None = None,
             coolant_inlet_C: float | None = None,
             flow_L_min: float | None = None):
        """Advance one timestep.

        Provide EITHER power_W (commanded, model solves for current) OR
        I_pack (measured from the shunt, twin mode).  Optionally override the
        coolant boundary conditions from live sensors.
        """
        cell, net = self.cell, self.net
        if flow_L_min is not None:
            self.net, self.lu = self._network_for(flow_L_min)
            net = self.net
        inlet = self.last_inlet_C if coolant_inlet_C is None else coolant_inlet_C
        self.last_inlet_C = inlet

        T_cell = self.T[net.i_core]
        R0 = cell.R0(T_cell, self.z, self.res_mult)
        R1, R2 = cell.R_rc(T_cell, self.res_mult, self.z)
        U = cell.ocv(self.z)

        a = (U - self.v1 - self.v2) / R0
        b = 1.0 / R0
        A = a.reshape(self.S, self.P).sum(axis=1)
        Bs = b.reshape(self.S, self.P).sum(axis=1)
        V_oc_eff = float((A / Bs).sum())
        R_eff = float((1.0 / Bs).sum())

        if I_pack is None:
            P_bus = float(power_W) / self.inverter_eff
            disc = V_oc_eff ** 2 - 4.0 * R_eff * P_bus
            I_pack = (V_oc_eff / (2.0 * R_eff) if disc <= 0.0
                      else (V_oc_eff - np.sqrt(disc)) / (2.0 * R_eff))
        I_pack = float(I_pack)

        V_g = (A - I_pack) / Bs
        Vg_full = np.repeat(V_g, self.P)
        I = a - Vg_full * b
        self.V_pack = float(V_g.sum())
        self.I_pack = I_pack
        self.I_cell = I

        self.q_cell = I * (U - Vg_full) - I * T_cell * cell.dudt(self.z)
        q_bus_each = I_pack ** 2 * self.layout.busbar_R_ohm

        # boundary source, with live coolant inlet
        src = net.s.copy()
        if net.M:
            mcp = net.mdot_cp_per_circuit
            for seg in net.inlet_segments:
                src[net.i_cool[seg]] += mcp * ((inlet + 273.15) -
                                               (self.base_coolant.inlet_T_C
                                                + 273.15))
        src[net.i_core] += self.q_cell
        src[net.i_bus] += q_bus_each

        self.T = self.lu.solve(net.C / self.dt * self.T + src)

        self.v1 = self.v1 * self.e1 + I * R1 * (1 - self.e1)
        self.v2 = self.v2 * self.e2 + I * R2 * (1 - self.e2)
        self.z = self.z - I * self.dt / (3600.0 * self.cap_Ah)
        self.energy_Wh += self.V_pack * I_pack * self.dt / 3600.0
        self.t += self.dt
        return self

    # -- observation / output -------------------------------------------
    @property
    def T_core_C(self):
        return self.T[self.net.i_core] - 273.15

    @property
    def T_can_C(self):
        return self.T[self.net.i_can] - 273.15

    @property
    def T_coolant_C(self):
        return self.T[self.net.i_cool] - 273.15

    def grid(self):
        return self.T_core_C.reshape(self.S, self.P)

    def state_report(self) -> dict:
        Tc = self.T_core_C
        return dict(t_s=self.t, I_pack=self.I_pack, V_pack=self.V_pack,
                    P_kW=self.V_pack * self.I_pack / 1000.0,
                    soc_mean=float(self.z.mean()),
                    soc_min=float(self.z.min()),
                    energy_Wh=self.energy_Wh,
                    T_max=float(Tc.max()), T_mean=float(Tc.mean()),
                    T_min=float(Tc.min()),
                    hotspot_rc=np.unravel_index(int(np.argmax(Tc)),
                                                (self.S, self.P)),
                    q_W=float(self.q_cell.sum()),
                    coolant_out_C=float(self.T_coolant_C.max()))

    # -- derating hook ---------------------------------------------------
    def thermal_power_limit_W(self, P_request_W: float,
                              T_warn: float | None = None,
                              T_max: float | None = None) -> float:
        """Linear thermal derate, the shape the VCU should implement.
        Uses the CORE temperature, which is what the limit applies to --
        not the can temperature your thermistor reads."""
        T_warn = self.cell.T_warn_C if T_warn is None else T_warn
        T_max = self.cell.T_max_C if T_max is None else T_max
        k = np.clip((T_max - self.T_core_C.max()) / (T_max - T_warn), 0.0, 1.0)
        return float(P_request_W * k)


# ============================================================================
#  2.  DIGITAL TWIN OBSERVER
# ============================================================================

@dataclass
class EnsembleObserver:
    """Ensemble Kalman gain mapping thermistor innovations to the full field.

    Fit once offline, then apply online as a fixed matrix multiply.
    """
    sensor_cells: np.ndarray
    K: np.ndarray = field(default=None)          # (N_cells, n_sensors)
    sensor_noise_K: float = 0.5

    def fit(self, make_sim, n_ensemble: int = 24, n_steps: int = 900,
            sample_every: int = 30, rng=None):
        """`make_sim(seed)` must return a configured PackSimulator plus a
        power profile: (sim, power_array).  Perturb whatever you are
        uncertain about -- population, ambient, flow, inlet, drive cycle."""
        rng = rng or np.random.default_rng(0)
        Xs, Ys = [], []
        for m in range(n_ensemble):
            sim, power = make_sim(m)
            xs, ys = [], []
            for k in range(min(n_steps, len(power))):
                sim.step(power_W=power[k])
                if k % sample_every == 0:
                    xs.append(sim.T_core_C.copy())
                    ys.append(sim.T_can_C[self.sensor_cells].copy())
            Xs.append(np.array(xs)); Ys.append(np.array(ys))
        n_t = min(len(x) for x in Xs)
        X = np.stack([x[:n_t] for x in Xs])       # (M, T, N)
        Y = np.stack([y[:n_t] for y in Ys])       # (M, T, S)

        # anomalies about the ensemble mean at each sample time
        Xa = (X - X.mean(axis=0, keepdims=True)).reshape(-1, X.shape[2])
        Ya = (Y - Y.mean(axis=0, keepdims=True)).reshape(-1, Y.shape[2])
        n = len(Xa)
        Pxy = Xa.T @ Ya / (n - 1)
        Pyy = Ya.T @ Ya / (n - 1) + np.eye(Ya.shape[1]) * self.sensor_noise_K ** 2
        self.K = Pxy @ np.linalg.inv(Pyy)
        return self

    def correct(self, T_pred_core_C: np.ndarray, T_pred_can_C: np.ndarray,
                y_measured_C: np.ndarray) -> np.ndarray:
        """Return the corrected full core-temperature field."""
        innovation = y_measured_C - T_pred_can_C[self.sensor_cells]
        return T_pred_core_C + self.K @ innovation


# ============================================================================
#  3.  BENCHMARK + ANIMATION
# ============================================================================

def benchmark(layout, cell, coolant, dt=1.0, sim_seconds=1200):
    """How much faster than real time does this run?"""
    sim = PackSimulator(layout, cell, coolant, dt=dt)
    n = int(sim_seconds / dt)
    t0 = time.perf_counter()
    for _ in range(n):
        sim.step(power_W=13000)
    wall = time.perf_counter() - t0
    return dict(cells=layout.n_cells, nodes=sim.net.n_nodes, dt=dt,
                sim_seconds=sim_seconds, wall_seconds=wall,
                realtime_factor=sim_seconds / wall,
                us_per_step=wall / n * 1e6)


def animate_race(layout, cell, coolant, power, dt=1.0, stride=10,
                 out="figures/race_animation.mp4", cap_mult=None,
                 res_mult=None):
    """Spatial field + power trace + energy budget, over the race."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter

    sim = PackSimulator(layout, cell, coolant, dt=dt,
                        cap_mult=cap_mult, res_mult=res_mult)
    frames = []
    for k in range(len(power)):
        sim.step(power_W=power[k])
        if k % stride == 0:
            frames.append((sim.t, sim.grid().copy(), sim.state_report()))
        if sim.z.min() <= 0.03:
            break

    vmin = min(f[1].min() for f in frames)
    vmax = max(f[1].max() for f in frames)

    fig = plt.figure(figsize=(13, 5.6))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.05, 1.35], hspace=0.42)
    axm = fig.add_subplot(gs[:, 0])
    axp = fig.add_subplot(gs[0, 1])
    axe = fig.add_subplot(gs[1, 1])

    im = axm.imshow(frames[0][1], cmap="inferno", origin="lower",
                    aspect="auto", vmin=vmin, vmax=vmax)
    plt.colorbar(im, ax=axm, label="cell core temperature [degC]")
    axm.set_xlabel("parallel position"); axm.set_ylabel("series group")
    hot, = axm.plot([], [], "co", ms=9, mfc="none", mew=2)
    ttl = axm.set_title("")

    t_all = np.array([f[0] for f in frames]) / 60
    p_all = np.array([f[2]["P_kW"] for f in frames])
    e_all = np.array([f[2]["energy_Wh"] for f in frames]) / 1000
    axp.plot(t_all, p_all, color="0.8", lw=1)
    lp, = axp.plot([], [], color="tab:blue", lw=1.6)
    axp.set_ylabel("bus power [kW]"); axp.grid(alpha=0.3)
    axp.set_xlim(0, t_all[-1]); axp.set_ylim(0, max(p_all) * 1.1)

    cap_kWh = layout.n_cells * cell.v_nominal * cell.capacity_Ah / 1000
    axe.axhline(cap_kWh, color="red", ls="--", lw=1)
    axe.text(0.02, cap_kWh * 0.94, f"REQ_7 cap {cap_kWh:.2f} kWh",
             color="red", fontsize=8)
    axe.plot(t_all, e_all, color="0.8", lw=1)
    le, = axe.plot([], [], color="tab:green", lw=1.6)
    axe.set_xlabel("time [min]"); axe.set_ylabel("energy used [kWh]")
    axe.grid(alpha=0.3); axe.set_xlim(0, t_all[-1])
    axe.set_ylim(0, cap_kWh * 1.08)

    def update(i):
        t, g, s = frames[i]
        im.set_data(g)
        hot.set_data([s["hotspot_rc"][1]], [s["hotspot_rc"][0]])
        ttl.set_text(f"t = {t/60:5.2f} min    T_max {s['T_max']:.1f} degC "
                     f"(row {s['hotspot_rc'][0]}, col {s['hotspot_rc'][1]})\n"
                     f"SOC {s['soc_mean']*100:4.1f} %    "
                     f"pack heat {s['q_W']:.0f} W    "
                     f"coolant out {s['coolant_out_C']:.1f} degC")
        lp.set_data(t_all[:i+1], p_all[:i+1])
        le.set_data(t_all[:i+1], e_all[:i+1])
        return im, hot, lp, le, ttl

    ani = FuncAnimation(fig, update, frames=len(frames), interval=60,
                        blit=False)
    try:
        ani.save(out, fps=18, dpi=110)
    except Exception:
        out = out.rsplit(".", 1)[0] + ".gif"
        ani.save(out, writer=PillowWriter(fps=18), dpi=90)
    plt.close(fig)
    return out, len(frames)
