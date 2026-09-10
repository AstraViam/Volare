r"""
volare_thermal.charge
=====================

Charging: CC-CV profile, thermal load during charge, and the between-race
turnaround question.

WHY THIS IS A RACE CONSTRAINT, NOT A CONVENIENCE
------------------------------------------------
A 16 A / 220 V shore outlet delivers ~3.34 kW.  A 9.83 kWh pack therefore
needs ~3.2 hours from empty at 100 % charger efficiency, and longer in
reality.  If the schedule puts two races closer together than that, you do
not start the second one full, and every downstream calculation -- range,
energy-budget derate, achievable lap time -- has to use the ACTUAL starting
SOC, not 100 %.

CC-CV makes this worse than the naive division suggests.  The constant-
voltage tail delivers progressively less current while still consuming wall
time: the last 10 % of capacity can take 25-30 % of the total charge time.
This model resolves that tail rather than assuming a flat rate.

CHARGE ALSO HEATS THE PACK
--------------------------
Charging at 0.5C into a pack you have just raced is not thermally free.  The
entropic term REVERSES sign on charge, and the pack starts hot.  This module
returns per-cell heat so you can feed it into the same thermal network and
answer "can I charge at 0.5C with the boat on the trailer and no coolant
flow", which is a question teams usually discover the answer to the hard way.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class ChargeProfile:
    """CC-CV charging limits, at the CELL level."""
    cc_current_A: float = 2.5          # per cell; P50B datasheet max is 25 A
    cv_voltage_V: float = 4.20         # per cell
    cutoff_current_A: float = 0.25     # terminate CV at this current (C/20)
    max_cell_temp_C: float = 45.0      # derate above this
    min_cell_temp_C: float = 0.0       # NEVER charge below this
    derate_start_C: float = 40.0

    def allowed_current(self, T_C):
        """Temperature-derated charge current [A/cell].

        Charging a lithium cell below 0 degC plates metallic lithium on the
        anode. It is permanent, it is a safety hazard, and it is invisible
        until the cell fails. This returns exactly zero below min_cell_temp_C
        and there is no override.
        """
        T = np.asarray(T_C, float)
        k = np.clip((self.max_cell_temp_C - T) /
                    max(1e-6, self.max_cell_temp_C - self.derate_start_C),
                    0.0, 1.0)
        return np.where(T < self.min_cell_temp_C, 0.0, self.cc_current_A * k)


@dataclass
class Charger:
    """Wall-side supply and converter."""
    supply_V: float = 220.0
    supply_A: float = 16.0
    power_factor: float = 0.95
    efficiency: float = 0.92
    max_output_W: float | None = None    # converter limit, if lower

    @property
    def wall_W(self):
        return self.supply_V * self.supply_A * self.power_factor

    @property
    def dc_W(self):
        p = self.wall_W * self.efficiency
        return min(p, self.max_output_W) if self.max_output_W else p


def simulate_charge(cell, n_series, n_parallel, profile: ChargeProfile,
                    charger: Charger, soc_init=0.05, soc_target=1.0,
                    T_cell_C=25.0, dt=10.0, max_hours=8.0,
                    cap_mult=None):
    """CC-CV charge at constant cell temperature.  Returns a trace dict.

    The pack-level current is the minimum of three limits:
      * what the charger can deliver at the present pack voltage
      * the cell CC limit x n_parallel, temperature-derated
      * whatever the CV clamp allows once the pack reaches its voltage ceiling
    """
    N = n_series * n_parallel
    cap = cell.capacity_Ah * (1.0 if cap_mult is None else float(np.mean(cap_mult)))
    z = float(soc_init)
    v_rc1 = v_rc2 = 0.0
    t, rec = 0.0, {k: [] for k in ("t_h", "soc", "I_pack", "I_cell",
                                   "V_pack", "V_cell", "P_dc_W", "q_cell_W",
                                   "mode")}
    e1, e2 = np.exp(-dt / cell.tau1_s), np.exp(-dt / cell.tau2_s)
    T_K = T_cell_C + 273.15
    mode = "CC"
    n = int(max_hours * 3600 / dt)

    for _ in range(n):
        R0 = float(cell.R0(np.array([T_K]), np.array([z]))[0])
        R1, R2 = cell.R_rc(np.array([T_K]), 1.0, np.array([z]))
        U = float(cell.ocv(z))

        I_cc = float(profile.allowed_current(T_cell_C))
        if I_cc <= 0:
            mode = "BLOCKED (too cold)"
            break

        # CV clamp: current that lands the terminal voltage exactly on the limit
        v_pol = v_rc1 + v_rc2
        I_cv = max(0.0, (profile.cv_voltage_V - U - v_pol) / R0)
        I_cell = min(I_cc, I_cv)
        mode = "CC" if I_cell >= I_cc - 1e-9 else "CV"

        # charger power limit at the present pack voltage
        V_cell = U + I_cell * R0 + v_pol
        V_pack = V_cell * n_series
        I_charger = charger.dc_W / max(V_pack, 1e-6) if V_pack > 0 else 0.0
        I_pack = min(I_cell * n_parallel, I_charger)
        if I_pack < I_cell * n_parallel - 1e-9:
            mode = "supply limited"
        I_cell = I_pack / n_parallel
        V_cell = U + I_cell * R0 + v_pol
        V_pack = V_cell * n_series

        # heat: entropic term REVERSES on charge (I negative in the discharge
        # convention), so q_rev = +I*T*dU/dT here
        q_irr = I_cell ** 2 * R0 + (v_rc1 ** 2 / max(R1[0], 1e-9)
                                    + v_rc2 ** 2 / max(R2[0], 1e-9))
        q_rev = I_cell * T_K * float(cell.dudt(z))
        q = q_irr + q_rev

        rec["t_h"].append(t / 3600.0); rec["soc"].append(z)
        rec["I_pack"].append(I_pack); rec["I_cell"].append(I_cell)
        rec["V_pack"].append(V_pack); rec["V_cell"].append(V_cell)
        rec["P_dc_W"].append(V_pack * I_pack); rec["q_cell_W"].append(q)
        rec["mode"].append(mode)

        v_rc1 = v_rc1 * e1 + I_cell * float(R1[0]) * (1 - e1)
        v_rc2 = v_rc2 * e2 + I_cell * float(R2[0]) * (1 - e2)
        z = min(1.0, z + I_cell * dt / (3600.0 * cap))
        t += dt
        if z >= soc_target - 1e-6 or I_cell <= profile.cutoff_current_A:
            break

    out = {k: (np.array(v) if k != "mode" else v) for k, v in rec.items()}
    out["hours"] = t / 3600.0
    out["soc_final"] = z
    out["energy_in_kWh"] = float(np.trapezoid(out["P_dc_W"], out["t_h"]) / 1000
                                 ) if len(out["t_h"]) > 1 else 0.0
    out["wall_hours"] = out["hours"]
    out["pack_heat_W_max"] = float(out["q_cell_W"].max() * N) if len(out["q_cell_W"]) else 0.0
    cc = sum(1 for m in rec["mode"] if m == "CC")
    out["cc_fraction"] = cc / max(1, len(rec["mode"]))
    return out


def turnaround_table(cell, n_series, n_parallel, profile, charger,
                     start_socs=(0.05, 0.15, 0.30, 0.50),
                     windows_h=(1.0, 2.0, 3.0, 4.0), T_cell_C=30.0):
    """How full will you be after W hours, starting from SOC z?

    This is the table to put on the pit wall.  It answers the only charging
    question that matters between races.
    """
    rows = []
    for z0 in start_socs:
        r = simulate_charge(cell, n_series, n_parallel, profile, charger,
                            soc_init=z0, T_cell_C=T_cell_C, dt=20.0)
        for W in windows_h:
            if len(r["t_h"]) == 0:
                rows.append((z0, W, z0)); continue
            z_at = float(np.interp(W, r["t_h"], r["soc"],
                                   left=z0, right=r["soc"][-1]))
            rows.append((z0, W, z_at))
    return rows


def full_charge_time(cell, n_series, n_parallel, profile, charger,
                     soc_init=0.05, T_cell_C=30.0):
    r = simulate_charge(cell, n_series, n_parallel, profile, charger,
                        soc_init=soc_init, T_cell_C=T_cell_C, dt=20.0)
    return r["hours"], r


if __name__ == "__main__":
    import pack_thermal as pt
    import celldata as cd
    C = cd.synthetic_p50b().to_cell_params()
    S, P = 26, 21
    prof, chg = ChargeProfile(), Charger()
    print(f"charger: {chg.wall_W:.0f} W wall -> {chg.dc_W:.0f} W DC")
    h, r = full_charge_time(C, S, P, prof, chg)
    print(f"empty -> full: {h:.2f} h, {r['energy_in_kWh']:.2f} kWh delivered, "
          f"CC fraction {r['cc_fraction']*100:.0f} %")
    print(f"peak pack heat during charge: {r['pack_heat_W_max']:.0f} W")
    print("\nTURNAROUND TABLE (SOC reached after W hours)")
    print(f"  {'start':>6} " + " ".join(f"{w:>6.1f}h" for w in (1., 2., 3., 4.)))
    rows = turnaround_table(C, S, P, prof, chg)
    for z0 in (0.05, 0.15, 0.30, 0.50):
        vals = [f"{z*100:>6.0f}%" for (a, w, z) in rows if abs(a - z0) < 1e-9]
        print(f"  {z0*100:>5.0f}% " + " ".join(vals))
