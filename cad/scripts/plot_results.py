"""Figures for the cockpit optimisation. Writes cad/out/figures/*.png."""
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
import aero
import geom
import optimise as O
import parametric as PM
import volare as V

OUT = Path(__file__).resolve().parents[2] / "cad" / "out" / "figures"
plt.rcParams.update({"figure.dpi": 130, "font.size": 8.5,
                     "axes.grid": True, "grid.alpha": 0.25,
                     "axes.spines.top": False, "axes.spines.right": False})


def fig_fairing_trade():
    """The headline result: where the optimum sits with and without mass."""
    tc = np.linspace(0.16, 0.55, 90)
    d, m, reff = [], [], []
    for t in tc:
        c = PM.min_chord_for_pole(t)
        f = aero.beam_fairing(t, span_mm=O.SPAN_BEAM, chord_mm=c)
        fa = aero.beam_fairing(t, span_mm=O.SPAN_BEAM, wake=0.85, chord_mm=c)
        d.append(f["D_N"] + fa["D_N"])
        m.append(f["mass_kg"] + fa["mass_kg"])
    d, m = np.array(d), np.array(m)
    reff = d + O.R_OVER_W * O.G * m

    fig, ax = plt.subplots(1, 2, figsize=(9.4, 3.6))

    ax[0].plot(tc, d, label="aero drag only", lw=1.8)
    ax[0].plot(tc, O.R_OVER_W * O.G * m, label="mass penalty", lw=1.4, ls="--")
    ax[0].plot(tc, reff, label="effective resistance", lw=2.2, color="k")
    i_d, i_r = int(np.argmin(d)), int(np.argmin(reff))
    ax[0].plot(tc[i_d], d[i_d], "o", ms=6, mfc="none", mec="C0")
    ax[0].plot(tc[i_r], reff[i_r], "o", ms=6, color="k")
    ax[0].annotate(f"drag optimum\nt/c = {tc[i_d]:.2f}  ({1/tc[i_d]:.1f}:1)",
                   (tc[i_d], d[i_d]), textcoords="offset points", xytext=(6, 26),
                   fontsize=7.5, color="C0")
    ax[0].annotate(f"real optimum\nt/c = {tc[i_r]:.2f}  ({1/tc[i_r]:.1f}:1)",
                   (tc[i_r], reff[i_r]), textcoords="offset points", xytext=(10, 18),
                   fontsize=7.5, fontweight="bold")
    ax[0].axvline(0.25, color="C3", lw=0.9, ls=":", zorder=0)
    ax[0].text(0.253, ax[0].get_ylim()[1] * 0.93, "note 01\n4:1", fontsize=7, color="C3")
    ax[0].set_xlabel("fairing thickness ratio  t/c")
    ax[0].set_ylabel("resistance  [N]")
    ax[0].set_title("Both crossbeam fairings: drag vs mass", fontsize=9)
    ax[0].legend(fontsize=7.5, frameon=False)

    ax2 = ax[1]
    ax2.plot(tc, [PM.min_chord_for_pole(t) for t in tc], lw=1.8, label="minimum chord that fits the pole")
    ax2.plot(tc, V.BEAM_DIAMETER / tc, lw=1.3, ls="--", label="naive  D / (t/c)")
    ax2.axhline(O.CHORD_MAX_FWD, color="C3", lw=0.9, ls=":")
    ax2.text(0.44, O.CHORD_MAX_FWD + 12, "fwd packaging limit", fontsize=7, color="C3")
    ax2.set_xlabel("fairing thickness ratio  t/c")
    ax2.set_ylabel("chord  [mm]")
    ax2.set_title("Chord needed to swallow the D104 pole", fontsize=9)
    ax2.legend(fontsize=7.5, frameon=False)

    fig.suptitle("Volare crossbeam fairing — counting mass moves the optimum from 4:1 to 2.7:1",
                 fontsize=10, y=1.0)
    fig.tight_layout()
    p = OUT / "fairing_trade.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_drag_budget():
    """Where the drag actually is, three ways."""
    note00, t00 = aero.budget(aero.NOTE00_BASELINE)
    rows, _ = aero.corrected_baseline(shadowed=True)
    corr, tc = aero.budget(rows)
    x_o, r_o = O.solve()

    labels = ["beams", "pilot", "brackets", "pod", "rails"]
    a = [note00[0]["D_N"] + note00[1]["D_N"], note00[2]["D_N"],
         note00[3]["D_N"], note00[4]["D_N"], note00[5]["D_N"]]
    b = [corr[0]["D_N"] + corr[1]["D_N"], corr[2]["D_N"],
         corr[3]["D_N"], corr[4]["D_N"], corr[5]["D_N"]]
    it = {i["name"]: i for i in r_o["items"]}
    c = [it["beam_fwd"]["D_N"] + it["beam_aft"]["D_N"], it["pilot"]["D_N"],
         it["brackets"]["D_N"], it["pod_shell"]["D_N"], it["rails"]["D_N"]]

    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    y = np.arange(len(labels))
    h = 0.26
    ax.barh(y + h, a, h, label=f"note 00, square beams  ({sum(a):.0f} N)")
    ax.barh(y, b, h, label=f"corrected, round D104 poles  ({sum(b):.0f} N)")
    ax.barh(y - h, c, h, label=f"optimised  ({sum(c):.0f} N aero)", color="k")
    for yy, v in zip(y + h, a):
        ax.text(v + 1.2, yy, f"{v:.0f}", va="center", fontsize=7)
    for yy, v in zip(y, b):
        ax.text(v + 1.2, yy, f"{v:.0f}", va="center", fontsize=7)
    for yy, v in zip(y - h, c):
        ax.text(v + 1.2, yy, f"{v:.1f}", va="center", fontsize=7)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("drag at 15.28 m/s  [N]")
    ax.set_title("Drag budget: the round-pole correction takes 46% off the baseline",
                 fontsize=9.5)
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    fig.tight_layout()
    p = OUT / "drag_budget.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_pod_profile():
    """Aft-body closure: what has to change and what it is worth."""
    P = geom.read_stl(Path(__file__).resolve().parents[2] / "source_documents"
                      / "Cockpit_V1_3.stl")
    T = V.pod_to_boat(P.reshape(-1, 3)).reshape(-1, 3, 3)
    xs, top, bot = geom.centreline_profile(T, 0.0, 400)
    ok = np.isfinite(top)
    xs, top, bot = xs[ok], top[ok], bot[ok]
    x_peak = xs[int(np.argmax(top))]
    slope = np.degrees(np.arctan(np.gradient(top, xs)))

    fig, ax = plt.subplots(2, 1, figsize=(8.2, 4.8), sharex=True,
                           gridspec_kw={"height_ratios": [2, 1]})
    ax[0].plot(xs, top, lw=1.8, color="k", label="crown, Y=0")
    ax[0].plot(xs, bot, lw=1.2, color="0.55", label="floor")
    ax[0].axvline(x_peak, color="C1", lw=0.9, ls=":")
    ax[0].text(x_peak - 30, top.max() + 8, f"coaming peak  X={x_peak:.0f}",
               fontsize=7, color="C1", ha="right")
    ax[0].axhline(V.BASELINE["rail"]["z_top"], color="C3", lw=0.9, ls="--")
    ax[0].text(1500, V.BASELINE["rail"]["z_top"] + 6,
               f"rail top — {V.RAIL_POD_INTERFERENCE:.0f} mm into the floor",
               fontsize=7, color="C3")
    ax[0].set_ylabel("Z  [mm]")
    ax[0].legend(fontsize=7.5, frameon=False, loc="upper left")
    ax[0].set_title("V1.3 pod centreline — aft body is over the 12° target for 79% of its length",
                    fontsize=9.5)

    aft = xs <= x_peak
    ax[1].plot(xs, np.abs(slope), lw=1.5, color="C0")
    ax[1].fill_between(xs[aft], 12, np.abs(slope[aft]),
                       where=np.abs(slope[aft]) > 12, color="C3", alpha=0.30,
                       label="over target — separation risk")
    ax[1].axhline(12, color="C3", lw=1.0, ls="--")
    ax[1].text(1500, 13, "12° target (note 01 §4.2)", fontsize=7, color="C3")
    ax[1].set_ylabel("surface slope  [deg]")
    ax[1].set_xlabel("X, forward positive  [mm]")
    ax[1].legend(fontsize=7.5, frameon=False, loc="upper left")
    ax[1].set_ylim(0, 25)
    fig.tight_layout()
    p = OUT / "pod_profile.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_hydrostatics():
    """Static float at the 315 kg theoretical maximum."""
    import hydrostatics as H
    import parts as PT

    plist = PT.split_assembly()
    hulls = [q for q in plist if q["name"].startswith("hull_")]
    T = np.concatenate([q["tris"] for q in hulls]).copy()
    total_area = sum(q["area_m2"] for q in hulls)
    T[:, :, 2] -= T[:, :, 2].min()
    deck = float(T[:, :, 2].max())

    d = H.condition(T, total_area, H.DESIGN_MAX_KG, deck_z=deck)
    zw = d["waterline_z_mm"]

    fig, ax = plt.subplots(1, 2, figsize=(10.2, 3.6))

    # --- hull profile with the waterline ---
    port = next(q for q in hulls if q["name"] == "hull_port")["tris"].copy()
    port[:, :, 2] -= np.concatenate([q["tris"] for q in hulls])[:, :, 2].min()
    xs, top, bot = geom.centreline_profile(
        port, float(np.median(port[:, :, 1])), 400)
    ok = np.isfinite(top)
    ax[0].fill_between(xs[ok], bot[ok], np.minimum(top[ok], zw),
                       where=bot[ok] < zw, color="C0", alpha=0.45,
                       label=f"submerged — {d['wetted_fraction']*100:.0f}% of hull area")
    ax[0].plot(xs[ok], top[ok], color="k", lw=1.5)
    ax[0].plot(xs[ok], bot[ok], color="k", lw=1.5)
    ax[0].axhline(zw, color="C0", lw=1.8)
    ax[0].text(xs[ok].min() + 80, zw + 22, f"WL  {zw:.0f} mm", color="C0",
               fontsize=8, fontweight="bold")
    ax[0].set_xlabel("X, forward positive  [mm]   (Z exaggerated ~2x)")
    ax[0].set_ylabel("Z above keel  [mm]")
    ax[0].set_ylim(-40, 700)
    ax[0].set_title(f"Demihull at {H.DESIGN_MAX_KG:.0f} kg — draft {d['draft_mm']:.0f} mm, "
                    f"freeboard {d['freeboard_mm']:.0f} mm", fontsize=9)
    ax[0].legend(fontsize=7.5, frameon=False, loc="upper right")

    # --- sweep ---
    ms = np.array([150, 200, 250, 280, 315, 350, 400, 450, 500])
    dr, wf = [], []
    for m in ms:
        c = H.condition(T, total_area, float(m), deck_z=deck)
        dr.append(c["draft_mm"])
        wf.append(c["wetted_fraction"] * 100)
    a2 = ax[1]
    a2.plot(ms, dr, "o-", ms=3.5, color="C0", label="draft")
    a2.set_xlabel("displacement  [kg]")
    a2.set_ylabel("draft  [mm]", color="C0")
    a2.tick_params(axis="y", labelcolor="C0")
    a3 = a2.twinx()
    a3.plot(ms, wf, "s--", ms=3.5, color="C1", label="wetted fraction")
    a3.set_ylabel("wetted fraction  [%]", color="C1")
    a3.tick_params(axis="y", labelcolor="C1")
    a3.grid(False)
    a2.axvline(H.DESIGN_MAX_KG, color="k", lw=1.0, ls=":")
    a2.annotate(f"cap\n{H.DESIGN_MAX_KG:.0f} kg", (H.DESIGN_MAX_KG, dr[4]),
                textcoords="offset points", xytext=(6, -30), fontsize=7.5)
    a2.axvline(417, color="C3", lw=1.0, ls=":")
    a2.annotate("note 06\nbudget\n417 kg", (417, min(dr)),
                textcoords="offset points", xytext=(-40, 6),
                fontsize=7.5, color="C3")
    a2.set_title("Draft and wetted fraction vs displacement", fontsize=9)

    fig.suptitle("Volare static hydrostatics — 250 kg cockpit incl. pilot + 65 kg hulls, "
                 "Mediterranean seawater 1028 kg/m³", fontsize=9.5, y=1.02)
    fig.tight_layout()
    pth = OUT / "hydrostatics.png"
    fig.savefig(pth, bbox_inches="tight")
    plt.close(fig)
    return pth


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (fig_drag_budget, fig_fairing_trade, fig_pod_profile, fig_hydrostatics):
        print("wrote", f())


if __name__ == "__main__":
    main()
