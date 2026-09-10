r"""
volare_thermal.build_p50b_dataset
=================================

Builds a CellDataset for the Molicel INR21700-P50B from the three datasheet
plots supplied:

    1. Discharge Rate Characteristics    0.2C, 0.5C, 1C, 10 A, 20 A, 30 A,
                                         50 A, 60 A   (x = mAh, y = V)
    2. Discharge Temperature Characteristics
                                         60, 45, 23, 10, 0, -40 degC
    3. Cycle Characteristics             +1C/-1C, +3C/-1C, +5C/-1C,
                                         +1C/-100W, -150W, -200W

    python3 build_p50b_dataset.py        ->  celldata/p50b.json

PROVENANCE AND ACCURACY  --  READ THIS
--------------------------------------
The point arrays below were traced BY EYE from the supplied images. That is
good enough to get the shape and the temperature ordering right, and it is a
large improvement on the synthetic placeholder, but it is NOT a substitute for
proper digitisation. Expect roughly +/-20 mV on voltage and +/-50 mAh on
capacity, which propagates to roughly +/-10 % on the extracted resistance.

To do it properly, spend twenty minutes in WebPlotDigitizer
(https://automeris.io/WebPlotDigitizer/): load each image, set the axis
calibration on the gridlines, auto-trace each coloured curve, export CSV.
Then use `load_digitised_folder()` instead of this file and the numbers become
genuinely yours.

Two curves are TRUNCATED in the source plot: 50 A ends near 2550 mAh and 60 A
near 2150 mAh, both around 3.22 V. That is almost certainly the 80 degC cell
cutoff terminating the test, not the cell running out of charge. They are
included because they still constrain resistance over the range they cover,
but nothing should read them as capacity limits.
"""

from __future__ import annotations
import os
import numpy as np
import celldata as cd


# ---------------------------------------------------------------------------
# 1. DISCHARGE RATE CHARACTERISTICS   (traced at ~23 degC)
#    each entry: (label, current_A, [(mAh, V), ...])
# ---------------------------------------------------------------------------
RATE_CURVES = [
    ("0.2C", 1.0, [
        (20, 4.16), (200, 4.13), (500, 4.10), (1000, 4.05), (1500, 3.98),
        (2000, 3.89), (2500, 3.76), (3000, 3.63), (3500, 3.51), (4000, 3.37),
        (4300, 3.27), (4600, 3.12), (4800, 2.88), (4900, 2.62), (4930, 2.50)]),
    ("0.5C", 2.5, [
        (20, 4.12), (200, 4.09), (500, 4.06), (1000, 4.01), (1500, 3.94),
        (2000, 3.85), (2500, 3.73), (3000, 3.60), (3500, 3.48), (4000, 3.34),
        (4300, 3.23), (4600, 3.07), (4780, 2.85), (4870, 2.58), (4890, 2.50)]),
    ("1C", 5.0, [
        (20, 4.09), (200, 4.06), (500, 4.03), (1000, 3.98), (1500, 3.91),
        (2000, 3.82), (2500, 3.70), (3000, 3.57), (3500, 3.45), (4000, 3.30),
        (4300, 3.19), (4600, 3.02), (4760, 2.80), (4850, 2.55), (4870, 2.50)]),
    ("10A", 10.0, [
        (20, 4.03), (200, 4.00), (500, 3.97), (1000, 3.93), (1500, 3.86),
        (2000, 3.77), (2500, 3.65), (3000, 3.52), (3500, 3.40), (4000, 3.25),
        (4300, 3.13), (4600, 2.95), (4750, 2.72), (4830, 2.52), (4850, 2.50)]),
    ("20A", 20.0, [
        (20, 3.88), (200, 3.85), (500, 3.83), (1000, 3.79), (1500, 3.72),
        (2000, 3.63), (2500, 3.51), (3000, 3.38), (3500, 3.26), (4000, 3.10),
        (4300, 2.97), (4550, 2.79), (4700, 2.62), (4800, 2.50)]),
    ("30A", 30.0, [
        (20, 3.77), (200, 3.74), (500, 3.72), (1000, 3.68), (1500, 3.61),
        (2000, 3.53), (2500, 3.41), (3000, 3.28), (3500, 3.16), (4000, 3.00),
        (4250, 2.88), (4450, 2.74), (4530, 2.68)]),          # truncated
    ("50A", 50.0, [
        (20, 3.57), (150, 3.52), (400, 3.47), (700, 3.42), (1100, 3.37),
        (1500, 3.33), (1900, 3.29), (2300, 3.25), (2550, 3.22)]),  # truncated
    ("60A", 60.0, [
        (20, 3.46), (150, 3.43), (400, 3.39), (700, 3.35), (1100, 3.31),
        (1500, 3.28), (1850, 3.25), (2150, 3.22)]),                # truncated
]
RATE_FAMILY_TEMP_C = 23.0

# ---------------------------------------------------------------------------
# 2. DISCHARGE TEMPERATURE CHARACTERISTICS
#    Rate is NOT printed on the source plot. TEMP_FAMILY_C_RATE below is
#    inferred by matching the 23 degC curve against the rate family; the
#    inferred value is printed when you run this file. If you know the real
#    rate, set it explicitly -- R0(T) scales inversely with it.
# ---------------------------------------------------------------------------
TEMP_CURVES = [
    (60.0, [
        (20, 4.12), (300, 4.03), (600, 3.99), (1000, 3.95), (1500, 3.88),
        (2000, 3.80), (2500, 3.68), (3000, 3.57), (3500, 3.45), (4000, 3.31),
        (4400, 3.15), (4700, 2.90), (4880, 2.55), (4900, 2.50)]),
    (45.0, [
        (20, 4.10), (300, 4.01), (600, 3.97), (1000, 3.93), (1500, 3.86),
        (2000, 3.78), (2500, 3.66), (3000, 3.55), (3500, 3.43), (4000, 3.29),
        (4400, 3.12), (4700, 2.87), (4850, 2.55), (4870, 2.50)]),
    (23.0, [
        (20, 4.08), (300, 3.99), (600, 3.95), (1000, 3.90), (1500, 3.83),
        (2000, 3.75), (2500, 3.63), (3000, 3.52), (3500, 3.40), (4000, 3.25),
        (4350, 3.08), (4650, 2.83), (4800, 2.55), (4820, 2.50)]),
    (10.0, [
        (20, 4.05), (300, 3.96), (600, 3.92), (1000, 3.87), (1500, 3.80),
        (2000, 3.72), (2500, 3.60), (3000, 3.48), (3500, 3.36), (4000, 3.20),
        (4300, 3.02), (4520, 2.78), (4650, 2.52), (4660, 2.50)]),
    (0.0, [
        (20, 4.00), (300, 3.92), (600, 3.88), (1000, 3.83), (1500, 3.76),
        (2000, 3.68), (2500, 3.56), (3000, 3.44), (3500, 3.31), (4000, 3.13),
        (4250, 2.94), (4430, 2.70), (4500, 2.50)]),
    (-40.0, [
        (30, 2.62), (120, 3.10), (300, 3.38), (600, 3.48), (900, 3.47),
        (1300, 3.42), (1800, 3.35), (2300, 3.27), (2800, 3.17), (3300, 3.05),
        (3700, 2.92), (4000, 2.78), (4150, 2.55), (4170, 2.50)]),
]

# ---------------------------------------------------------------------------
# 3. CYCLE CHARACTERISTICS   (capacity % vs cycle number, 0-500)
# ---------------------------------------------------------------------------
CYCLE_CURVES = [
    # (label, charge_C, discharge_C_equivalent, dod%, T, [(cycle, %), ...])
    ("+1C/-1C",    1.0,  1.0, 100.0, 25.0,
     [(0, 100.5), (50, 99.3), (100, 98.2), (150, 97.1), (200, 96.0),
      (250, 95.0), (300, 94.0), (350, 93.0), (400, 92.1), (450, 91.2),
      (500, 90.5)]),
    ("+3C/-1C",    3.0,  1.0, 100.0, 25.0,
     [(0, 100.5), (50, 99.2), (100, 98.0), (150, 96.8), (200, 95.7),
      (250, 94.6), (300, 93.6), (350, 92.6), (400, 91.6), (450, 90.7),
      (500, 90.0)]),
    ("+5C/-1C",    5.0,  1.0, 100.0, 25.0,
     [(0, 100.5), (50, 99.0), (100, 97.5), (150, 96.1), (200, 94.8),
      (250, 93.5), (300, 92.3), (350, 91.1), (400, 90.0), (450, 88.5),
      (500, 87.0)]),
    ("+1C/-100W", 1.0,  5.6, 100.0, 25.0,        # 100 W / 3.6 V ~ 27.8 A ~ 5.6C
     [(0, 100.5), (50, 98.8), (100, 97.0), (150, 95.2), (200, 93.4),
      (250, 91.7), (300, 90.0), (350, 88.4), (400, 86.8), (450, 85.3),
      (500, 84.0)]),
    ("+1C/-150W", 1.0,  8.3, 100.0, 25.0,        # ~41.7 A
     [(0, 100.5), (50, 98.5), (100, 96.4), (150, 94.2), (200, 92.1),
      (250, 90.0), (300, 88.0), (350, 86.0), (400, 84.0), (450, 82.0),
      (500, 80.0)]),
    ("+1C/-200W", 1.0, 11.1, 100.0, 25.0,        # ~55.6 A
     [(0, 101.0), (50, 98.5), (100, 95.8), (150, 93.0), (200, 90.2),
      (250, 87.8), (300, 85.6), (350, 83.6), (400, 81.6), (450, 78.5),
      (500, 75.5)]),
]

# ---------------------------------------------------------------------------
# entropic coefficient dU/dT -- NOT in the supplied plots. [LOW confidence]
# literature NMC shape; negative means exothermic on discharge.
# ---------------------------------------------------------------------------
DUDT_SOC = [0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0]
DUDT_V_K = [-3.0e-4, -2.2e-4, -1.6e-4, -1.0e-4, -0.6e-4, 0.0, 0.5e-4]


def build(out_dir="celldata", filename="p50b.json", verbose=True):
    ds = cd.CellDataset(
        part_number="INR21700-P50B", manufacturer="Molicel", chemistry="NMC",
        nominal_capacity_Ah=5.0, nominal_voltage_V=3.6,
        v_max_V=4.20, v_min_V=2.50, mass_kg=0.070,
        diameter_m=0.02155, height_m=0.07015, cp_J_kgK=1050.0,
        max_continuous_discharge_A=60.0, max_charge_A=25.0,
        notes=("Traced by eye from the supplied datasheet plots (rate, "
               "temperature, cycle). ~+/-20 mV, ~+/-50 mAh. 30/50/60 A rate "
               "curves are truncated by the test's temperature cutoff, not by "
               "capacity. dU/dT is literature, not measured."))

    for label, I, pts in RATE_CURVES:
        q, v = zip(*pts)
        ds.add_discharge(I / 5.0, RATE_FAMILY_TEMP_C, np.array(q, float),
                         np.array(v, float), label=f"rate {label}")

    inf = ds.infer_c_rate(RATE_FAMILY_TEMP_C, RATE_FAMILY_TEMP_C)

    # temperature family: add at the inferred rate, tagged at its own temp
    probe = cd.CellDataset(nominal_capacity_Ah=5.0)
    for T, pts in TEMP_CURVES:
        q, v = zip(*pts)
        probe.add_discharge(1.0, T, np.array(q, float), np.array(v, float))
    for c in ds.curves_at(RATE_FAMILY_TEMP_C):
        probe.add_discharge(c.c_rate, 999.0, c.capacity_Ah, c.voltage_V)
    # match the 23 degC temperature curve against the rate family
    tgt = [c for c in probe.discharge_curves
           if abs(c.temperature_C - 23.0) <= 1.0][0]
    Ah = np.linspace(0.1, 0.85, 30) * 5.0
    vt = tgt.v_at_throughput(Ah)
    best = (np.inf, 1.0)
    for c in ds.curves_at(RATE_FAMILY_TEMP_C):
        vc = c.v_at_throughput(Ah)
        m = np.isfinite(vt) & np.isfinite(vc)
        if m.sum() < 8:
            continue
        e = float(np.sqrt(np.mean((vt[m] - vc[m]) ** 2)))
        if e < best[0]:
            best = (e, c.c_rate)
    TEMP_C_RATE = best[1]

    for T, pts in TEMP_CURVES:
        if abs(T - RATE_FAMILY_TEMP_C) <= 1.0:
            continue                      # already covered by the rate family
        q, v = zip(*pts)
        ds.add_discharge(TEMP_C_RATE, T, np.array(q, float),
                         np.array(v, float), label=f"temp {T:.0f}C")

    for label, cC, dC, dod, T, pts in CYCLE_CURVES:
        n, r = zip(*pts)
        ds.add_cycle_life(dC, dod, T, np.array(n, float), np.array(r, float))

    ds.dudt_soc = np.array(DUDT_SOC)
    ds.dudt_v_per_K = np.array(DUDT_V_K)

    ds.fit_R0_vs_temperature(ref_temperature_C=RATE_FAMILY_TEMP_C,
                             family_c_rate=TEMP_C_RATE)

    os.makedirs(out_dir, exist_ok=True)
    path = ds.to_json(os.path.join(out_dir, filename))

    if verbose:
        print(f"temperature family rate inferred as {TEMP_C_RATE:g}C "
              f"(match RMS {best[0]*1000:.0f} mV)")
        print(f"wrote {path}")
    return ds, path


if __name__ == "__main__":
    ds, path = build()
    print(f"\n{ds.part_number}: {len(ds.discharge_curves)} discharge curves, "
          f"{len(ds.cycle_curves)} cycle curves")
    print(f"temperatures: {ds.temperatures}")
    s, T, R = ds.R0_map_soc, ds.R0_map_T_C, ds.R0_map_ohm
    print("\nEXTRACTED SUSTAINED RESISTANCE (mOhm)")
    print("   T degC " + "".join(f"{z*100:>8.0f}%" for z in
                                 (0.9, 0.7, 0.5, 0.3, 0.1)))
    for i, t in enumerate(T):
        print(f"  {t:7.0f} " + "".join(
            f"{np.interp(z, s, R[i])*1000:>9.2f}" for z in
            (0.9, 0.7, 0.5, 0.3, 0.1)))
    EaR, R0ref = ds.fit_arrhenius()
    print(f"\nArrhenius Ea/R = {abs(EaR):.0f} K, "
          f"R_sustained(50 % SOC, 23 degC) = {R0ref*1000:.2f} mOhm")
    C = ds.to_cell_params()
    r0 = C.R0(np.array([296.15]), np.array([0.5]))[0]
    r1, r2 = C.R_rc(np.array([296.15]), 1.0, np.array([0.5]))
    print(f"ECM split: R0 {r0*1000:.2f} + R1 {r1[0]*1000:.2f} + "
          f"R2 {r2[0]*1000:.2f} = {(r0+r1[0]+r2[0])*1000:.2f} mOhm")
    print("\nCYCLE LIFE")
    for c in ds.cycle_curves:
        print(f"  {c.c_rate:5.1f}C discharge: {c.retention_at(500)*100:5.1f} % "
              f"at 500 cycles")
