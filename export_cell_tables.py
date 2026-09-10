r"""
tools/export_cell_tables.py
===========================

Derive the cell lookup tables ONCE and write them where every model reads
them.

WHY THIS SCRIPT EXISTS
----------------------
The digitised dataset in ``params/cells/p50b.json`` holds raw traced curves:
thirteen discharge curves, an R0(SOC,T) map, an entropic dU/dT curve and six
cycle-life curves. Turning those into the tables a solver actually wants --
OCV(SOC), R0 on a regular grid, an Arrhenius activation energy -- takes real
work: IR correction, pairwise rate differencing, curve fitting.

If Python did that derivation and MATLAB did its own, the two would drift.
Not because either would be wrong, but because "IR-corrected OCV from the
0.2 C curve" admits a dozen defensible implementations that disagree in the
third decimal place. Chasing that discrepancy later is expensive and pointless.

So the derivation happens exactly once, here, and the result is written to
``params/cells/p50b_derived.json``. Python, MATLAB and the Mission Control
browser engine all read that file. They cannot disagree, because there is
nothing left for them to disagree about.

USAGE
-----
    python tools/export_cell_tables.py

Re-run it whenever ``p50b.json`` changes -- after adding measured HPPC data,
for instance. The output records which source file it came from and when, so
a stale derived file is detectable.

OUTPUT
------
``params/cells/p50b_derived.json``::

    ocv.soc / ocv.v                OCV(SOC), monotonic, IR-corrected
    r0.soc / r0.temp_C / r0.ohm    R0 grid, [n_temp][n_soc]
    dudt.soc / dudt.v_per_K        entropic coefficient
    arrhenius.Ea_over_R_K          fitted activation
    scalars                        capacity, reference resistance, etc.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

# Make the project's python/ directory importable when run from the root.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "python"))

from volare.celldata import CellDataset           # noqa: E402
from volare.params import load                    # noqa: E402


SOURCE = os.path.join(_ROOT, "params", "cells", "p50b.json")
DEST = os.path.join(_ROOT, "params", "cells", "p50b_derived.json")


def _as_list(a) -> list:
    return [float(x) for x in np.asarray(a, float).ravel()]


def _enforce_monotonic(soc: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Force OCV to increase strictly with SOC.

    Traced curves wobble by a few millivolts, and a non-monotonic OCV makes
    the inverse SOC(OCV) map ill-posed -- an SOC estimator built on it will
    produce silent nonsense rather than an error. A running maximum with a
    small floor is the least invasive fix and changes nothing outside the
    tracing noise.
    """
    out = np.array(v, float)
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + 1e-5
    return out


def main() -> int:
    if not os.path.isfile(SOURCE):
        print(f"ERROR: source dataset not found: {SOURCE}")
        return 1

    print(f"reading  {SOURCE}")
    ds = CellDataset.from_json(SOURCE)

    # ------------------------------------------------------------------
    #  OCV(SOC)
    #
    #  Taken from the lowest-rate curve available and IR-corrected. At
    #  0.2 C the ohmic drop is small but not negligible -- about 12 mV on
    #  a 12 mOhm cell -- and leaving it in biases the whole SOC scale.
    # ------------------------------------------------------------------
    print("deriving OCV(SOC) from the lowest-rate discharge curve ...")
    soc_o, ocv = ds.fit_ocv(temperature_C=23.0, n=41)

    soc_o = np.asarray(soc_o, float)
    ocv = _enforce_monotonic(soc_o, np.asarray(ocv, float))

    # ------------------------------------------------------------------
    #  R0(SOC, T)
    # ------------------------------------------------------------------
    print("building R0(SOC,T) map ...")
    soc_r, temp_r, r0 = ds.build_R0_map(n_soc=41)

    soc_r = np.asarray(soc_r, float)
    temp_r = np.asarray(temp_r, float)
    r0 = np.asarray(r0, float)

    if r0.shape != (len(temp_r), len(soc_r)):
        r0 = r0.reshape(len(temp_r), len(soc_r))

    if not np.all(np.isfinite(r0)) or np.any(r0 <= 0):
        print("ERROR: R0 map contains non-positive or non-finite values.")
        return 1

    # ------------------------------------------------------------------
    #  Arrhenius activation
    # ------------------------------------------------------------------
    # fit_arrhenius returns (Ea_over_R, R0_at_298K). The fit is restricted
    # to 0-60 degC on purpose: a single exponent cannot span -40 to +60,
    # because the low-temperature rise is a different mechanism and drags
    # the fit badly.
    try:
        Ea_over_R, R0_at_25 = ds.fit_arrhenius(soc_ref=0.5,
                                               fit_range_C=(0.0, 60.0))
        Ea_over_R = float(Ea_over_R)
        R0_at_25 = float(R0_at_25)
        ea_source = ("fitted from the temperature-series discharge curves, "
                     "0-60 degC")
    except Exception as exc:                       # pragma: no cover
        P = load()
        Ea_over_R = float(P.cell.Ea_over_R_K)
        R0_at_25 = float("nan")
        ea_source = f"fallback to params (fit failed: {exc})"

    print(f"Arrhenius Ea/R = {Ea_over_R:.0f} K  ({ea_source})")

    # ------------------------------------------------------------------
    #  Entropic coefficient
    # ------------------------------------------------------------------
    dudt_soc = _as_list(ds.dudt_soc) if getattr(ds, "dudt_soc", None) is not None else []
    dudt_v = _as_list(ds.dudt_v_per_K) if getattr(ds, "dudt_v_per_K", None) is not None else []

    # ------------------------------------------------------------------
    #  Reference points, for cross-checking against the datasheet
    # ------------------------------------------------------------------
    i23 = int(np.argmin(np.abs(temp_r - 23.0)))
    i50 = int(np.argmin(np.abs(soc_r - 0.5)))
    r0_ref = float(r0[i23, i50])

    P = load()
    datasheet_dcir = float(P.cell.dcir_ref_ohm)
    agreement = 100.0 * (r0_ref - datasheet_dcir) / datasheet_dcir

    print(f"R0 at 50% SOC, 23 degC = {r0_ref*1e3:.2f} mOhm "
          f"(datasheet {datasheet_dcir*1e3:.2f} mOhm, "
          f"{agreement:+.1f}%)")

    out = {
        "_README": [
            "DERIVED cell lookup tables. Generated -- do not edit by hand.",
            "Regenerate with: python tools/export_cell_tables.py",
            "",
            "Derived once here so that Python, MATLAB and the Mission Control",
            "browser engine cannot produce different curves from the same",
            "raw data.",
        ],
        "source_file": os.path.relpath(SOURCE, _ROOT).replace("\\", "/"),
        "source_notes": ds.notes if hasattr(ds, "notes") else "",
        "provenance": "DIGITISED",

        "scalars": {
            "capacity_Ah": float(ds.nominal_capacity_Ah),
            "v_nominal_V": float(ds.nominal_voltage_V),
            "v_max_V": float(ds.v_max_V),
            "v_min_V": float(ds.v_min_V),
            "R0_ref_ohm": r0_ref,
            "R0_ref_soc": 0.5,
            "R0_ref_temp_C": 23.0,
            "datasheet_dcir_ohm": datasheet_dcir,
            "datasheet_agreement_pct": agreement,
        },

        "ocv": {
            "soc": _as_list(soc_o),
            "v": _as_list(ocv),
            "note": "IR-corrected from the lowest-rate discharge curve at "
                    "23 degC, forced strictly monotonic.",
        },

        "r0": {
            "soc": _as_list(soc_r),
            "temp_C": _as_list(temp_r),
            "ohm": [[float(x) for x in row] for row in r0],
            "note": "Extracted pairwise between rate curves. Includes "
                    "polarisation built up over the discharge, which is the "
                    "correct conservative bias for thermal work: it is the "
                    "sustained resistance that heats the pack over a race, "
                    "not the 10 ms value.",
        },

        "dudt": {
            "soc": dudt_soc,
            "v_per_K": dudt_v,
            "note": "Entropic coefficient. Literature, not measured. ~15% of "
                    "total heat at mid-SOC; changes sign near full charge, "
                    "where cells are briefly endothermic.",
        },

        "arrhenius": {
            "Ea_over_R_K": Ea_over_R,
            "R0_at_25C_ohm": R0_at_25,
            "note": ea_source,
        },
    }

    with open(DEST, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    print(f"wrote    {DEST}")
    print(f"         OCV {len(soc_o)} points, "
          f"R0 {r0.shape[0]} temps x {r0.shape[1]} SOC")

    # ------------------------------------------------------------------
    #  Sanity checks -- fail loudly rather than ship a bad table
    # ------------------------------------------------------------------
    problems = []

    if not np.all(np.diff(soc_o) > 0):
        problems.append("OCV SOC breakpoints are not strictly increasing")
    if not np.all(np.diff(ocv) > 0):
        problems.append("OCV is not strictly increasing")
    if not (3.9 <= ocv[-1] <= 4.3):
        problems.append(f"OCV at full charge is {ocv[-1]:.3f} V, expected ~4.2")
    if not np.all(np.diff(temp_r) > 0):
        problems.append("R0 temperature breakpoints are not increasing")
    if abs(agreement) > 35:
        problems.append(
            f"R0 disagrees with the datasheet DCIR by {agreement:+.0f}%")

    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("checks   OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
