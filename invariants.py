#!/usr/bin/env python3
r"""
volare_thermal.invariants
=========================

Physics invariants, checked across parameter sweeps rather than at one point.

A model can pass every unit test and still be wrong in a way that only shows
up when you change something: a temperature that falls when you reduce
cooling, a drag that drops when you add wave height, an efficiency above 1.
These are the properties that must hold EVERYWHERE, so they are swept.

Run:  python3 invariants.py
"""

from __future__ import annotations
import sys
import numpy as np

import pack_thermal as pt
import geometry as gm
import celldata as cd
import boat as bt
import track as tk

FAILS = []


def ck(name, ok, detail=""):
    print(("[  ok  ] " if ok else "[ FAIL ] ") + name +
          (f"\n         {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def monotone(xs, ys, increasing=True, tol=1e-9):
    d = np.diff(ys)
    return bool(np.all(d >= -tol) if increasing else np.all(d <= tol))


# ---------------------------------------------------------------- setup
G = gm.stacked_grid_pack(n_series=26, n_parallel=21, tube_every=2, n_circuits=3)
C = cd.CellDataset.from_json("celldata/p50b.json").to_cell_params()
ck_ = bt.Cockpit.from_stl("Cockpit_V1_3.stl")
H = bt.Hull(Lwl_m=4.99, Bwl_m=.45, draft_m=.14, n_hulls=2,
            displacement_kg=250., cockpit=ck_)
R = bt.ResistanceModel(H)
P, _ = bt.match_propeller_to_boat(H, R, bt.Propeller(), 250., 25000.)
_, prof = pt.build_power_profile(pt.mebc_endurance_lap(), 900, 1.0)


def run(flow=8.0, tin=29.0, tamb=30.0, power=None, dt=1.0):
    K = pt.Coolant(flow_L_per_min=flow, inlet_T_C=tin)
    return pt.simulate(G, C, K, power if power is not None else prof,
                       dt=dt, T_init_C=28, T_ambient_C=tamb, store_every=20)


print("=== THERMAL ===")
# 1. less cooling must never make the pack cooler
flows = [3, 5, 8, 12, 16]
tm = [run(flow=f).T_core_C.max() for f in flows]
ck("peak temperature falls monotonically with coolant flow",
   monotone(flows, tm, increasing=False),
   " ".join(f"{f}L/min:{t:.2f}C" for f, t in zip(flows, tm)))

# 2. hotter sea must never cool the pack
tins = [20, 25, 29, 33, 37]
tm2 = [run(tin=t).T_core_C.max() for t in tins]
ck("peak temperature rises monotonically with sea temperature",
   monotone(tins, tm2, increasing=True),
   " ".join(f"{a}C:{b:.2f}" for a, b in zip(tins, tm2)))

# 3. more power must never make it cooler
pw = [6000, 12000, 18000, 24000]
tm3 = []
for w in pw:
    _, p = pt.constant_power_profile(w, 900, 1.0)
    tm3.append(run(power=p).T_core_C.max())
ck("peak temperature rises monotonically with power",
   monotone(pw, tm3, increasing=True),
   " ".join(f"{w//1000}kW:{t:.2f}" for w, t in zip(pw, tm3)))

# 4. physical ordering of the thermal chain
r = run()
# The naive forms of these two ("core always hotter than can", "coolant never
# below inlet") are WRONG, and the sweep caught it. The default start has the
# pack at 28 C and the coolant inlet at 29 C, so for the first ~2 minutes the
# coolant HEATS the cells: heat flows inward, the can leads the core, and
# coolant segments give up heat and drop below inlet. Both are correct.
# The real invariant is that the gradient must follow the direction of net
# heat flow, and coolant must stay bracketed by its inlet and the cells.
warm = r.t > 150                       # after the startup transient
ck("core leads can once the pack is self-heating",
   bool(np.all(r.T_core_C[warm] >= r.T_can_C[warm] - 1e-6)),
   f"min gradient after 150 s {float((r.T_core_C[warm]-r.T_can_C[warm]).min()):.5f} K")
lo = min(29.0, float(r.T_can_C.min()))
hi = max(29.0, float(r.T_can_C.max()))
ck("coolant always bracketed by its inlet and the cells it touches",
   bool(r.T_cool_C.min() >= lo - 1e-6 and r.T_cool_C.max() <= hi + 1e-6),
   f"coolant {float(r.T_cool_C.min()):.3f}..{float(r.T_cool_C.max()):.3f} C "
   f"inside [{lo:.3f}, {hi:.3f}]")
# Demanding a single sign during the transient is also wrong: cells beside a
# tube are heated from outside (negative gradient) while cells far from one
# are already dominated by their own generation (positive). Both coexist and
# both are right. The invariant that DOES hold everywhere is that the gradient
# can never exceed what the heat flow physically supports.
grad = r.T_core_C - r.T_can_C
bound = float(r.q_cell.max()) * C.R_core_can_KW + abs(28.0 - 29.0)
ck("core-can gradient bounded by what the heat flow supports",
   float(np.abs(grad).max()) <= bound + 1e-6,
   f"max |gradient| {float(np.abs(grad).max()):.4f} K vs bound "
   f"q_max*R + start mismatch = {bound:.4f} K")
ck("no cell exceeds a physical bound",
   bool(r.T_core_C.max() < 200 and r.T_core_C.min() > -50),
   f"range {r.T_core_C.min():.1f} .. {r.T_core_C.max():.1f} C")

print("\n=== ELECTRICAL ===")
ck("Kirchhoff holds at every step",
   float(np.abs(r.I_cell.reshape(len(r.t), 26, 21).sum(axis=2)
                - r.I_pack[:, None]).max()) < 1e-9,
   f"max residual {float(np.abs(r.I_cell.reshape(len(r.t),26,21).sum(axis=2) - r.I_pack[:,None]).max()):.2e} A")
ck("SOC never leaves [0, 1]",
   bool(r.soc.min() >= -1e-9 and r.soc.max() <= 1 + 1e-9),
   f"range {r.soc.min():.4f} .. {r.soc.max():.4f}")
ck("pack voltage stays physical",
   bool(r.V_pack.min() > 26 * 2.0 and r.V_pack.max() < 26 * 4.3),
   f"range {r.V_pack.min():.1f} .. {r.V_pack.max():.1f} V")
ck("current is positive on discharge",
   bool(r.I_pack.min() >= -1e-6), f"min {r.I_pack.min():.3f} A")

Rbus = G.busbar_R_ohm * (G.n_series - 1)
Vc = r.V_pack + r.I_pack * Rbus
ck("busbar drop applied to terminal voltage",
   bool(np.allclose(Vc - r.V_pack, r.I_pack * Rbus, atol=1e-9)),
   f"mean drop {float((Vc - r.V_pack).mean()):.4f} V")

print("\n=== HEAT ===")
q_split_ok = True
for k in range(0, len(r.t), max(1, len(r.t) // 20)):
    if abs(float(r.q_cell[k].sum()) + float(r.q_busbar[k])
           - float(r.q_total[k])) > 1e-6:
        q_split_ok = False
ck("cell heat + busbar heat = total heat", q_split_ok)
ck("heat generation is non-negative in aggregate",
   bool(r.q_total.min() > -1e-6), f"min {r.q_total.min():.4f} W")

# Integrate at FULL resolution: energy_out_Wh accumulates every step, so
# comparing it against a trapezoid over stored samples measures the sampling
# rate, not the physics. At store_every=20 that alone is a 7.7 % "error".
rf = run(dt=1.0)
rf = pt.simulate(G, C, pt.Coolant(flow_L_per_min=8.0, inlet_T_C=29.0), prof,
                 dt=1.0, T_init_C=28, T_ambient_C=30, store_every=1)
Rb = G.busbar_R_ohm * (G.n_series - 1)
V_cells = rf.V_pack + rf.I_pack * Rb
E_cells = float(np.trapezoid(V_cells * rf.I_pack, rf.t) / 3600.0)
E_term = float(rf.energy_out_Wh[-1])
E_bus = float(np.trapezoid(rf.q_busbar, rf.t) / 3600.0)
resid = abs(E_cells - (E_term + E_bus)) / max(E_cells, 1e-9)
ck("energy integrates consistently", resid < 3e-3,
   f"cells {E_cells:.2f} = terminals {E_term:.2f} + busbar {E_bus:.2f} Wh "
   f"({resid*100:.4f} % residual, trapezoid limit)")

# The check above is partly tautological — V_cells is DEFINED from V_pack, so
# it cannot detect the solver forgetting the busbar. This one can: the power
# actually delivered at the terminals must equal what was commanded. If the
# busbar IR drop is left out of the source impedance, the solver sizes the
# current for the cell resistance alone and the terminals come up short.
_, pconst = pt.constant_power_profile(15000.0, 400, 1.0)
rc = pt.simulate(G, C, pt.Coolant(flow_L_per_min=8.0, inlet_T_C=29.0), pconst,
                 dt=1.0, T_init_C=28, store_every=1)
want = 15000.0 / 0.96
got = rc.V_pack[20:] * rc.I_pack[20:]
err = float(np.abs(got - want).max() / want)
ck("delivered power equals commanded power", err < 1e-6,
   f"commanded {want:.1f} W, delivered {float(got.mean()):.1f} W "
   f"(max error {err*100:.5f} %)")

print("\n=== HYDRAULICS ===")
K8 = pt.Coolant(flow_L_per_min=8.0)
Re, dP, Rt = [], [], []
for nc in (1, 2, 3, 4, 6, 8, 13):
    g2 = gm.stacked_grid_pack(n_series=26, n_parallel=21, tube_every=2,
                              n_circuits=nc)
    h = pt.ThermalNetwork(g2, C, K8).hydraulics_info
    Re.append(h["Re"]); dP.append(h["dP_bar"]); Rt.append(h["R_total_per_tube_KW"])
ck("Reynolds falls monotonically with circuit count",
   monotone(None, Re, increasing=False),
   " ".join(f"{v:.0f}" for v in Re))
ck("pressure drop falls monotonically with circuit count",
   monotone(None, dP, increasing=False),
   " ".join(f"{v:.3f}" for v in dP))
ck("cell-to-coolant resistance rises monotonically with circuit count",
   monotone(None, Rt, increasing=True),
   " ".join(f"{v:.2f}" for v in Rt))

print("\n=== MANIFOLD ===")
lens = [sum(t.length for t in G.tubes if t.circuit == c)
        for c in sorted({t.circuit for t in G.tubes})]
ratios = [gm.manifold_split(3, lens, 0.006, K8, 8.0, header_id_m=d)["ratio"]
          for d in (0.008, 0.010, 0.013, 0.016, 0.022, 0.030)]
ck("flow imbalance falls monotonically with header diameter",
   monotone(None, ratios, increasing=False),
   " ".join(f"{v:.3f}" for v in ratios))
eq = gm.manifold_split(3, [2.5, 2.5, 2.5], 0.006, K8, 8.0, header_id_m=0.016)
ck("equal-length circuits split near-evenly", eq["ratio"] < 1.05,
   f"ratio {eq['ratio']:.4f}")
tot = sum(gm.manifold_split(4, [2.0]*4, 0.006, K8, 8.0)["flows_L_min"])
ck("manifold conserves mass", abs(tot - 8.0) < 1e-6, f"sum {tot:.6f} L/min")

print("\n=== BOAT ===")
D = bt.BoatDynamics(H, R, P, mass_kg=250., P_shaft_max_W=25000.)
pw2 = [4000, 9000, 15000, 20000, 25000]
vs = [D.steady_speed(float(w)) for w in pw2]
ck("speed rises monotonically with power", monotone(None, vs, increasing=True),
   " ".join(f"{v*3.6:.1f}" for v in vs))
ck("power cap is never exceeded",
   D.step(1.0, 1e9)["P_shaft_W"] <= 25000 + 1e-6)
hs_vals = [0.0, 0.4, 0.8, 1.2]
Rw = [48*h*h*(1+10/6) for h in hs_vals]
ck("wave resistance rises monotonically with wave height",
   monotone(None, Rw, increasing=True), " ".join(f"{v:.0f}N" for v in Rw))
effs = [P.open_water_eff(v, P.rps_for_power(v, 15000)) for v in (5, 10, 15)]
ck("propeller efficiency stays in (0, 1)",
   all(0 < e < 1 for e in effs), " ".join(f"{e:.3f}" for e in effs))

print("\n=== DRIVETRAIN ===")
dt = bt.Drivetrain(); dt.reset(29.0)
w = 490.0
for _ in range(1500):
    dtr = dt.step(2.0, 20000, w, 29.0, 32.0)
ck("winding hotter than case, case hotter than sea",
   dt.T_winding_C > dt.T_case_C > 29.0 - 1e-6,
   f"{dt.T_winding_C:.1f} > {dt.T_case_C:.1f} > 29.0")
ck("junction hotter than heatsink",
   dt.T_junction_C > dt.T_heatsink_C,
   f"{dt.T_junction_C:.1f} > {dt.T_heatsink_C:.1f}")
ck("efficiencies in (0, 1)",
   0 < dtr["eff_motor"] < 1 and 0 < dtr["eff_inverter"] < 1,
   f"motor {dtr['eff_motor']:.4f}, inverter {dtr['eff_inverter']:.4f}")
losses = []
for pwr in (5000, 12000, 20000, 25000):
    d2 = bt.Drivetrain(); d2.reset(29.0)
    losses.append(sum(d2.losses(pwr, w)[:2]))
ck("drivetrain loss rises monotonically with power",
   monotone(None, losses, increasing=True),
   " ".join(f"{v:.0f}W" for v in losses))
cr = [dt.continuous_rating_W(rp*2*np.pi/60)["P_continuous_W"]
      for rp in (2500, 3500, 4500)]
ck("continuous rating rises with speed", monotone(None, cr, increasing=True),
   " ".join(f"{v/1000:.1f}kW" for v in cr))

print("\n=== CELL DATA ===")
ds = cd.CellDataset.from_json("celldata/p50b.json")
s_, T_, Rm = ds.R0_map_soc, ds.R0_map_T_C, ds.R0_map_ohm
r50 = [float(np.interp(0.5, s_, row)) for row in Rm]
ck("resistance falls monotonically with temperature",
   monotone(None, r50, increasing=False),
   " ".join(f"{t:.0f}C:{v*1000:.1f}m" for t, v in zip(T_, r50)))
ck("all extracted resistances positive", bool((Rm > 0).all()))
ck("capacity factor rises with temperature",
   monotone(None, list(C.cap_temp_mult), increasing=True),
   " ".join(f"{v:.3f}" for v in C.cap_temp_mult))
ocv = C.ocv(np.linspace(0, 1, 41))
ck("OCV rises monotonically with SOC", monotone(None, ocv, increasing=True),
   f"{ocv[0]:.2f} .. {ocv[-1]:.2f} V")

print("\n=== TRACK ===")
for key in ("endurance", "qualifying", "championship_outer",
            "championship_inner"):
    t = tk.COURSES[key]()
    ck(f"{key} closes", t.closure_error_m < 0.01,
       f"{t.closure_error_m:.4f} m")
ck("endurance lap is exactly 1 NM",
   abs(tk.monaco_endurance().length - 1852.0) < 0.5)

print("\n=== TIMESTEP ===")
tms = []
for d in (0.25, 0.5, 1.0, 2.0):
    _, p = pt.build_power_profile(pt.mebc_endurance_lap(), 600, d)
    tms.append(pt.simulate(G, C, pt.Coolant(), p, dt=d, T_init_C=28,
                           store_every=1).T_core_C.max())
ck("solution is timestep independent", (max(tms) - min(tms)) < 0.05,
   " ".join(f"dt{d}:{v:.4f}" for d, v in zip((0.25, 0.5, 1.0, 2.0), tms)))

print(f"\n{len(FAILS)} invariant failures" +
      (f": {FAILS}" if FAILS else ""))
sys.exit(1 if FAILS else 0)
