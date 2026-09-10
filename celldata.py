r"""
volare_thermal.celldata
=======================

Import real cell characterisation and turn it into model parameters.

WHAT YOU CAN IMPORT
-------------------
  * Discharge curves   V vs Ah, at several C-rates      (25 degC)
  * Discharge curves   V vs Ah, at several temperatures (one C-rate)
  * Charge curve       CC-CV profile
  * Direct resistance  R vs SOC vs T, if the vendor gives it
  * Entropic coeff.    dU/dT vs SOC
  * Cycle life         capacity retention vs cycle, per C-rate / DOD / T

WHAT IT DERIVES
---------------
  * OCV(SOC)            from the lowest-rate curve, IR-corrected
  * R0(SOC, T)          a 2D MAP, extracted pairwise between rate curves
  * Ea/R                Arrhenius activation, fitted across temperatures
  * RC branches         from the relaxation shape, or from HPPC if you have it
  * Capacity fade       for end-of-life "will it still finish the race" runs

THE KEY EXTRACTION
------------------
Two discharge curves at different rates, same temperature, compared at the
same depth of discharge, differ almost entirely by the ohmic drop:

    V_lo(Q) - V_hi(Q) = (I_hi - I_lo) * R0(SOC, T)

so

    R0(SOC, T) = (V_lo - V_hi) / (I_hi - I_lo)

This is exact for the ohmic part and slightly overestimates R0 by including
whatever polarisation has built up at that point in the discharge -- which is
the right conservative error for thermal work, because it is the *sustained*
resistance that generates heat over a 20-minute race, not the 10 ms value.

GETTING DATA OFF A DATASHEET GRAPH
----------------------------------
Trace the curves in WebPlotDigitizer (free, browser-based), export CSV per
curve, and drop them in a folder.  `load_digitised_folder()` expects files
named like:

    discharge_1.0C_25C.csv        # C-rate and temperature in the name
    discharge_5.0C_25C.csv
    discharge_1.0C_0C.csv
    discharge_1.0C_-20C.csv
    charge_0.5C_25C.csv
    cycle_1.0C_100DOD_25C.csv

each a two-column CSV of x,y with no header, x in Ah (or mAh, auto-detected)
and y in volts.  Twenty minutes of tracing gets you a model that is *yours*.
"""

from __future__ import annotations

import json
import os
import re
import numpy as np
from dataclasses import dataclass, field, asdict


# ============================================================================
#  CURVE CONTAINERS
# ============================================================================

@dataclass
class DischargeCurve:
    """One measured or digitised discharge curve."""
    c_rate: float
    temperature_C: float
    capacity_Ah: np.ndarray        # monotonically increasing, from 0
    voltage_V: np.ndarray
    label: str = ""

    def __post_init__(self):
        self.capacity_Ah = np.asarray(self.capacity_Ah, float)
        self.voltage_V = np.asarray(self.voltage_V, float)
        o = np.argsort(self.capacity_Ah)
        self.capacity_Ah, self.voltage_V = self.capacity_Ah[o], self.voltage_V[o]
        if self.capacity_Ah.max() > 100:          # looks like mAh
            self.capacity_Ah = self.capacity_Ah / 1000.0

    @property
    def delivered_Ah(self) -> float:
        return float(self.capacity_Ah.max())

    def v_at_dod(self, dod: np.ndarray) -> np.ndarray:
        """Voltage at fractional depth-of-discharge of THIS curve."""
        return np.interp(np.clip(dod, 0, 1) * self.delivered_Ah,
                         self.capacity_Ah, self.voltage_V)

    def v_at_throughput(self, Ah, nominal_Ah=None):
        """Voltage at an ABSOLUTE discharged charge [Ah].

        This is the correct basis for comparing curves at different rates: a
        10C curve delivers less total capacity, so matching on fractional DOD
        compares two different real states of charge and biases the extracted
        R0 low by ~8 %. Matching on absolute throughput does not.
        Returns NaN beyond the end of the curve rather than extrapolating.
        """
        Ah = np.asarray(Ah, float)
        v = np.interp(Ah, self.capacity_Ah, self.voltage_V,
                      left=np.nan, right=np.nan)
        return v


@dataclass
class CycleLifeCurve:
    """Capacity retention vs cycle number at one condition."""
    c_rate: float
    dod_pct: float
    temperature_C: float
    cycles: np.ndarray
    retention: np.ndarray          # 1.0 = new; accepts % and converts

    def __post_init__(self):
        self.cycles = np.asarray(self.cycles, float)
        self.retention = np.asarray(self.retention, float)
        if self.retention.max() > 2.0:
            self.retention = self.retention / 100.0

    def retention_at(self, n_cycles: float) -> float:
        return float(np.interp(n_cycles, self.cycles, self.retention))

    def cycles_to(self, retention: float = 0.80) -> float:
        r, c = self.retention[::-1], self.cycles[::-1]
        return float(np.interp(retention, r, c))


# ============================================================================
#  DATASET
# ============================================================================

@dataclass
class CellDataset:
    """Everything you know about one cell part number."""
    part_number: str = "INR21700-P50B"
    manufacturer: str = "Molicel"
    chemistry: str = "NMC"
    nominal_capacity_Ah: float = 5.0
    nominal_voltage_V: float = 3.6
    v_max_V: float = 4.20
    v_min_V: float = 2.50
    mass_kg: float = 0.070
    diameter_m: float = 0.02155
    height_m: float = 0.07015
    cp_J_kgK: float = 1050.0
    max_continuous_discharge_A: float = 60.0
    max_charge_A: float = 25.0

    discharge_curves: list = field(default_factory=list)
    charge_curves: list = field(default_factory=list)
    cycle_curves: list = field(default_factory=list)

    # optional direct measurements
    dudt_soc: np.ndarray | None = None
    dudt_v_per_K: np.ndarray | None = None
    R0_map_soc: np.ndarray | None = None       # (n_soc,)
    R0_map_T_C: np.ndarray | None = None       # (n_T,)
    R0_map_ohm: np.ndarray | None = None       # (n_T, n_soc)

    notes: str = ""

    # -- add data --------------------------------------------------------
    def add_discharge(self, c_rate, temperature_C, capacity_Ah, voltage_V,
                      label=""):
        self.discharge_curves.append(
            DischargeCurve(c_rate, temperature_C, capacity_Ah, voltage_V, label))
        return self

    def add_cycle_life(self, c_rate, dod_pct, temperature_C, cycles, retention):
        self.cycle_curves.append(
            CycleLifeCurve(c_rate, dod_pct, temperature_C, cycles, retention))
        return self

    def curves_at(self, temperature_C, tol=2.0):
        return sorted([c for c in self.discharge_curves
                       if abs(c.temperature_C - temperature_C) <= tol],
                      key=lambda c: c.c_rate)

    @property
    def temperatures(self):
        return sorted({round(c.temperature_C, 1) for c in self.discharge_curves})

    # -- derive OCV ------------------------------------------------------
    def fit_ocv(self, temperature_C=25.0, n=41, r0_guess=None):
        """OCV from the lowest-rate curve, corrected for its own IR drop.

        A C/2 curve is NOT the OCV -- at 2.5 A through ~15 mOhm it sits ~40 mV
        low. Correcting matters: an uncorrected OCV biases every SOC estimate
        and weakens the negative feedback that limits current hogging.
        """
        cs = self.curves_at(temperature_C)
        if not cs:
            raise ValueError(f"no discharge curves near {temperature_C} degC")
        lo = cs[0]
        dod = np.linspace(0, 1, n)
        v = lo.v_at_dod(dod)
        I = lo.c_rate * self.nominal_capacity_Ah
        if r0_guess is None and len(cs) > 1:
            soc_m, _, R = self.fit_R0_vs_soc(temperature_C)
            r0_guess = np.interp(1 - dod, soc_m, R)
        elif r0_guess is None:
            r0_guess = 0.0
        return (1 - dod)[::-1], (v + I * np.asarray(r0_guess))[::-1]

    # -- derive R0(SOC) at one temperature --------------------------------
    def fit_R0_vs_soc(self, temperature_C=25.0, n=41):
        """R0 = dV / dI between rate pairs, averaged over all available pairs."""
        cs = self.curves_at(temperature_C)
        if len(cs) < 2:
            raise ValueError(
                f"need >=2 discharge curves at {temperature_C} degC to extract "
                f"R0; found {len(cs)}")
        Qn = self.nominal_capacity_Ah
        dod = np.linspace(0.02, 0.98, n)
        Ah = dod * Qn                      # ABSOLUTE throughput, not fractional
        est = []
        for a in range(len(cs)):
            for b in range(a + 1, len(cs)):
                lo, hi = cs[a], cs[b]
                dI = (hi.c_rate - lo.c_rate) * Qn
                if dI <= 1e-6:
                    continue
                dV = lo.v_at_throughput(Ah) - hi.v_at_throughput(Ah)
                est.append(dV / dI)
        E = np.array(est)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            R = np.nanmedian(E, axis=0)
        # fill any all-NaN tail (beyond the shortest curve) with the last good
        good = np.isfinite(R)
        if good.any():
            R = np.interp(np.arange(n), np.arange(n)[good], R[good])
        else:
            raise ValueError("no overlapping range between rate curves")
        return (1 - dod)[::-1], dod[::-1], np.maximum(R, 1e-4)[::-1]

    # -- infer the rate of a single-rate family ---------------------------
    def infer_c_rate(self, temperature_C, ref_temperature_C=23.0):
        """Work out what C-rate a single-rate curve was measured at, by
        matching it against the multi-rate family at the reference temperature.

        Datasheets routinely omit the rate on the temperature-characteristics
        plot. Guessing wrong scales the whole R0(T) extraction by the ratio of
        the true to assumed current, so it is worth pinning down.
        """
        target = [c for c in self.discharge_curves
                  if abs(c.temperature_C - temperature_C) <= 1.0]
        fam = self.curves_at(ref_temperature_C)
        if not target or len(fam) < 2:
            return None
        tgt = target[0]
        Ah = np.linspace(0.1, 0.85, 30) * self.nominal_capacity_Ah
        vt = tgt.v_at_throughput(Ah)
        best = (np.inf, None)
        for c in fam:
            vc = c.v_at_throughput(Ah)
            m = np.isfinite(vt) & np.isfinite(vc)
            if m.sum() < 8:
                continue
            e = float(np.sqrt(np.mean((vt[m] - vc[m]) ** 2)))
            if e < best[0]:
                best = (e, c.c_rate)
        return dict(c_rate=best[1], rms_V=best[0])

    # -- R0(T) from a single-rate temperature family ----------------------
    def fit_R0_vs_temperature(self, ref_temperature_C=23.0,
                              family_c_rate=None, n_soc=41):
        """Build R0(SOC, T) from ONE multi-rate family plus a single-rate
        temperature sweep.

        The multi-rate family at the reference temperature gives R0(SOC, Tref)
        directly. Each temperature curve then differs from the reference curve
        only by the extra ohmic drop at that temperature:

            R0(SOC, T) = R0(SOC, Tref) + (V_Tref(Q) - V_T(Q)) / I_family

        This is how you get a full 2D map from the two plots a datasheet
        actually prints, without needing multiple rates at every temperature.
        """
        soc, dod, R_ref = self.fit_R0_vs_soc(ref_temperature_C, n_soc)
        if family_c_rate is None:
            # pick the C-rate that appears at the MOST distinct temperatures --
            # that is by definition the temperature-sweep family. Inferring it
            # by self-matching at the reference temperature just returns
            # whichever rate happens to be listed first, which is wrong.
            tally = {}
            for c in self.discharge_curves:
                tally.setdefault(round(c.c_rate, 4), set()).add(
                    round(c.temperature_C, 1))
            family_c_rate = max(tally, key=lambda r: (len(tally[r]), -r))
        I = family_c_rate * self.nominal_capacity_Ah
        Ah = dod * self.nominal_capacity_Ah

        ref_curves = [c for c in self.discharge_curves
                      if abs(c.temperature_C - ref_temperature_C) <= 1.0
                      and abs(c.c_rate - family_c_rate) < 1e-6]
        if not ref_curves:
            raise ValueError(
                f"no curve at {ref_temperature_C} degC and {family_c_rate}C to "
                "anchor the temperature family against")
        v_ref = ref_curves[0].v_at_throughput(Ah)

        Ts, rows = [], []
        for T in sorted({round(c.temperature_C, 1)
                         for c in self.discharge_curves}):
            cs = [c for c in self.discharge_curves
                  if abs(c.temperature_C - T) <= 1.0
                  and abs(c.c_rate - family_c_rate) < 1e-6]
            if not cs:
                continue
            dV = v_ref - cs[0].v_at_throughput(Ah)
            R = R_ref + dV / I
            good = np.isfinite(R)
            if good.sum() < 5:
                continue
            R = np.interp(np.arange(len(R)), np.arange(len(R))[good], R[good])
            Ts.append(float(T)); rows.append(np.maximum(R, 1e-4))
        self.R0_map_soc = soc
        self.R0_map_T_C = np.array(Ts)
        self.R0_map_ohm = np.array(rows)
        return self.R0_map_soc, self.R0_map_T_C, self.R0_map_ohm

    # -- build the full R0(SOC, T) map ------------------------------------
    def build_R0_map(self, n_soc=41, ref_temperature_C=None):
        """Build R0(SOC, T). Dispatches on what data you actually have.

        Preferred  : >=2 rates at every temperature -> direct extraction.
        Fallback   : >=2 rates at ONE reference temperature, plus a single-rate
                     sweep across temperatures -> anchor and offset. This is
                     the layout every real datasheet uses, so it is the path
                     that will normally run.
        """
        Ts = [T for T in self.temperatures if len(self.curves_at(T)) >= 2]
        if len(Ts) < 2:
            anchors = sorted(Ts) or [t for t in self.temperatures]
            if not anchors:
                raise ValueError("need >=2 rates at >=1 temperature")
            ref = ref_temperature_C if ref_temperature_C is not None else anchors[0]
            return self.fit_R0_vs_temperature(ref_temperature_C=ref,
                                              n_soc=n_soc)
        if not Ts:
            raise ValueError("need >=2 rates at >=1 temperature")
        soc = None
        rows = []
        for T in Ts:
            s, _, R = self.fit_R0_vs_soc(T, n_soc)
            soc = s
            rows.append(R)
        self.R0_map_soc = np.asarray(soc)
        self.R0_map_T_C = np.asarray(Ts, float)
        self.R0_map_ohm = np.asarray(rows)
        return self.R0_map_soc, self.R0_map_T_C, self.R0_map_ohm

    def fit_arrhenius(self, soc_ref=0.5, fit_range_C=(0.0, 60.0)):
        """Ea/R [K] from R0 at a reference SOC across temperatures.

        `fit_range_C` restricts the fit, because a single Arrhenius exponent
        cannot describe -40 to +60 degC: the low-temperature rise is dominated
        by a different mechanism and drags the fit badly. Restricting to the
        range you actually operate in gives a number that is useful there.
        When a measured map is attached the map is used directly and this
        value only matters as a fallback.
        """
        if self.R0_map_ohm is None:
            self.build_R0_map()
        if len(self.R0_map_T_C) < 2:
            raise ValueError("need >=2 temperatures to fit Arrhenius")
        m = ((self.R0_map_T_C >= fit_range_C[0]) &
             (self.R0_map_T_C <= fit_range_C[1]))
        if m.sum() < 2:
            m = np.ones(len(self.R0_map_T_C), bool)
        R_ref = np.array([np.interp(soc_ref, self.R0_map_soc, row)
                          for row in self.R0_map_ohm[m]])
        invT = 1.0 / (self.R0_map_T_C[m] + 273.15)
        A = np.polyfit(invT, np.log(R_ref), 1)
        return float(A[0]), float(np.exp(np.polyval(A, 1 / 298.15)))

    # -- ageing -----------------------------------------------------------
    def capacity_retention(self, n_cycles, c_rate=1.0, dod_pct=100.0,
                           temperature_C=25.0):
        """Nearest-condition retention. Crude, but it lets you answer
        'will the pack still finish the race at 300 cycles'."""
        if not self.cycle_curves:
            return 1.0
        def dist(c):
            return (abs(c.c_rate - c_rate) + abs(c.dod_pct - dod_pct) / 50
                    + abs(c.temperature_C - temperature_C) / 20)
        return min(self.cycle_curves, key=dist).retention_at(n_cycles)

    # -- export to a model ------------------------------------------------
    def to_cell_params(self, temperature_C=25.0, rc_fraction=(0.53, 0.67),
                       taus=(10.0, 120.0)):
        """Produce a CellParams driven by the measured maps.

        IMPORTANT -- WHY THE MAP IS SCALED DOWN
        ---------------------------------------
        Resistance extracted from steady discharge curves is the SUSTAINED
        total resistance: it already contains ohmic plus fully-developed
        polarisation. The ECM represents that same total as R0 + R1 + R2. So
        the extracted value must be SPLIT across the three, not assigned to R0
        with RC branches added on top -- that double-counts and inflates heat
        generation by ~2.2x.

            R0 = R_extracted / (1 + f1 + f2)
            R1 = f1 * R0,  R2 = f2 * R0     ->  R0+R1+R2 = R_extracted

        rc_fraction = (f1, f2). Defaults reproduce the P50B reconciliation
        (7.5 / 4.0 / 5.0 mOhm summing to 16.5). They are the weakest link in
        the whole chain -- replace with an HPPC relaxation fit if you can, and
        note that they only affect the TRANSIENT response, not the steady heat.
        """
        from pack_thermal import CellParams
        soc_g, ocv_g = self.fit_ocv(temperature_C)
        try:
            self.build_R0_map()
            EaR, R0_ref = self.fit_arrhenius()
        except Exception:
            s, _, R = self.fit_R0_vs_soc(temperature_C)
            self.R0_map_soc, self.R0_map_T_C = s, np.array([temperature_C])
            self.R0_map_ohm = R[None, :]
            EaR, R0_ref = 2500.0, float(np.interp(0.5, s, R))

        f1, f2 = rc_fraction
        split = 1.0 / (1.0 + f1 + f2)      # see docstring
        R0_ref = R0_ref * split
        cp = CellParams(
            capacity_Ah=self.nominal_capacity_Ah,
            v_nominal=self.nominal_voltage_V, v_max=self.v_max_V,
            v_min=self.v_min_V, mass_kg=self.mass_kg,
            diameter_m=self.diameter_m, height_m=self.height_m,
            cp_J_kgK=self.cp_J_kgK,
            R0_ref_ohm=R0_ref, R1_ref_ohm=R0_ref * f1,
            R2_ref_ohm=R0_ref * f2,
            tau1_s=taus[0], tau2_s=taus[1],
            Ea_over_R_K=abs(EaR),
            ocv_soc=soc_g, ocv_v=ocv_g)
        if self.dudt_soc is not None:
            cp.dudt_soc = np.asarray(self.dudt_soc)
            cp.dudt_v_per_K = np.asarray(self.dudt_v_per_K)
        # attach the measured map so CellParams.R0 uses it
        cp.attach_R0_map(self.R0_map_soc, self.R0_map_T_C,
                         self.R0_map_ohm * split)
        cp.R_sustained_ref_ohm = float(R0_ref / split)   # for reporting
        cp._cycle_curves = self.cycle_curves             # for ageing models
        # capacity vs temperature, straight off the temperature-sweep curves
        try:
            fam = {}
            for cv in self.discharge_curves:
                fam.setdefault(round(cv.c_rate, 4), []).append(cv)
            rate = max(fam, key=lambda r: len({round(x.temperature_C, 1)
                                               for x in fam[r]}))
            pts = sorted((cv.temperature_C, cv.delivered_Ah) for cv in fam[rate])
            if len(pts) >= 2:
                Ts = np.array([p[0] for p in pts])
                Ah = np.array([p[1] for p in pts])
                ref = float(np.interp(25.0, Ts, Ah))
                cp.cap_temp_C = Ts
                cp.cap_temp_mult = Ah / max(ref, 1e-9)
        except Exception:
            pass
        return cp

    # -- persistence -------------------------------------------------------
    def to_json(self, path):
        def arr(a):
            return None if a is None else np.asarray(a).tolist()
        d = dict(part_number=self.part_number, manufacturer=self.manufacturer,
                 chemistry=self.chemistry,
                 nominal_capacity_Ah=self.nominal_capacity_Ah,
                 nominal_voltage_V=self.nominal_voltage_V,
                 v_max_V=self.v_max_V, v_min_V=self.v_min_V,
                 mass_kg=self.mass_kg, diameter_m=self.diameter_m,
                 height_m=self.height_m, cp_J_kgK=self.cp_J_kgK,
                 max_continuous_discharge_A=self.max_continuous_discharge_A,
                 max_charge_A=self.max_charge_A, notes=self.notes,
                 dudt_soc=arr(self.dudt_soc),
                 dudt_v_per_K=arr(self.dudt_v_per_K),
                 R0_map_soc=arr(self.R0_map_soc),
                 R0_map_T_C=arr(self.R0_map_T_C),
                 R0_map_ohm=arr(self.R0_map_ohm),
                 discharge_curves=[dict(c_rate=c.c_rate,
                                        temperature_C=c.temperature_C,
                                        capacity_Ah=arr(c.capacity_Ah),
                                        voltage_V=arr(c.voltage_V),
                                        label=c.label)
                                   for c in self.discharge_curves],
                 cycle_curves=[dict(c_rate=c.c_rate, dod_pct=c.dod_pct,
                                    temperature_C=c.temperature_C,
                                    cycles=arr(c.cycles),
                                    retention=arr(c.retention))
                               for c in self.cycle_curves])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        return path

    @classmethod
    def from_json(cls, path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        dc = d.pop("discharge_curves", [])
        cc = d.pop("cycle_curves", [])
        for k in ("dudt_soc", "dudt_v_per_K", "R0_map_soc", "R0_map_T_C",
                  "R0_map_ohm"):
            if d.get(k) is not None:
                d[k] = np.array(d[k])
        obj = cls(**d)
        for c in dc:
            obj.add_discharge(c["c_rate"], c["temperature_C"],
                              c["capacity_Ah"], c["voltage_V"],
                              c.get("label", ""))
        for c in cc:
            obj.add_cycle_life(c["c_rate"], c["dod_pct"], c["temperature_C"],
                               c["cycles"], c["retention"])
        return obj


# ============================================================================
#  DIGITISED-GRAPH LOADER
# ============================================================================

_PAT = re.compile(
    r"(?P<kind>discharge|charge|cycle)[_-]"
    r"(?P<rate>[-\d.]+)C[_-]"
    r"(?:(?P<dod>[\d.]+)DOD[_-])?"
    r"(?P<temp>-?[\d.]+)C", re.I)


def load_digitised_folder(folder, dataset: CellDataset | None = None,
                          verbose=True) -> CellDataset:
    """Load every CSV in `folder` whose name encodes rate and temperature."""
    ds = dataset or CellDataset()
    found = 0
    for fn in sorted(os.listdir(folder)):
        if not fn.lower().endswith((".csv", ".txt")):
            continue
        m = _PAT.search(fn)
        if not m:
            if verbose:
                print(f"  skipped (name does not match pattern): {fn}")
            continue
        d = np.loadtxt(os.path.join(folder, fn), delimiter=",", ndmin=2)
        if d.shape[1] < 2:
            d = np.loadtxt(os.path.join(folder, fn), ndmin=2)
        rate, temp = float(m["rate"]), float(m["temp"])
        kind = m["kind"].lower()
        if kind == "discharge":
            ds.add_discharge(rate, temp, d[:, 0], d[:, 1], label=fn)
        elif kind == "cycle":
            ds.add_cycle_life(rate, float(m["dod"] or 100.0), temp,
                              d[:, 0], d[:, 1])
        found += 1
        if verbose:
            print(f"  loaded {fn}: {kind} {rate}C @ {temp} degC, "
                  f"{len(d)} points")
    if verbose:
        print(f"  -> {found} curves, temperatures {ds.temperatures}")
    return ds


# ============================================================================
#  SYNTHETIC P50B DATASET  (placeholder until you trace the real graphs)
# ============================================================================

def synthetic_p50b() -> CellDataset:
    """A plausible P50B dataset generated from the ECM, so every downstream
    function is exercisable before you have traced anything.

    THIS IS NOT MEASURED DATA. It exists so the pipeline runs end to end.
    Replace it with `load_digitised_folder('celldata/')` as soon as you have
    traced the real curves.
    """
    ds = CellDataset(notes="SYNTHETIC - generated from the ECM, not measured.")
    soc = np.array([0, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, .95, 1.])
    ocv = np.array([2.80, 3.15, 3.30, 3.45, 3.55, 3.63, 3.72, 3.81, 3.89,
                    3.98, 4.08, 4.14, 4.20])
    rsoc = np.array([0, .05, .15, .30, .70, .90, 1.0])
    rmul = np.array([2.20, 1.60, 1.20, 1.02, 1.00, 1.05, 1.15])
    R0_25, EaR = 0.0165, 2500.0

    dod = np.linspace(0, 1, 60)
    for T in (-20.0, 0.0, 25.0, 45.0):
        arr = np.exp(EaR * (1 / (T + 273.15) - 1 / 298.15))
        cap_fac = np.interp(T, [-20, 0, 25, 45], [0.82, 0.93, 1.00, 1.01])
        for c_rate in (0.2, 1.0, 3.0, 5.0, 10.0):
            if T < 10 and c_rate > 3.0:
                continue
            I = c_rate * 5.0
            R = R0_25 * arr * np.interp(1 - dod, rsoc, rmul)
            v = np.interp(1 - dod, soc, ocv) - I * R
            keep = v >= 2.50
            ds.add_discharge(c_rate, T, dod[keep] * 5.0 * cap_fac, v[keep],
                             label=f"synthetic {c_rate}C {T}C")
    ds.dudt_soc = np.array([0, .1, .2, .4, .6, .8, 1.])
    ds.dudt_v_per_K = np.array([-3.0e-4, -2.2e-4, -1.6e-4, -1.0e-4,
                                -0.6e-4, 0.0, 0.5e-4])
    n = np.array([0, 100, 200, 300, 500, 800, 1000])
    for cr, ret in ((1.0, [1, .985, .972, .960, .938, .906, .885]),
                    (3.0, [1, .975, .955, .937, .905, .860, .832])):
        ds.add_cycle_life(cr, 100.0, 25.0, n, np.array(ret))
    return ds


if __name__ == "__main__":
    ds = synthetic_p50b()
    print(f"{ds.part_number}: {len(ds.discharge_curves)} discharge curves, "
          f"temperatures {ds.temperatures}")
    s, T, R = ds.build_R0_map()
    print(f"R0 map: {R.shape[0]} temperatures x {R.shape[1]} SOC points")
    for i, t in enumerate(T):
        print(f"  {t:6.1f} degC: R0(50%) = {np.interp(0.5, s, R[i])*1000:6.2f} mOhm")
    EaR, R0ref = ds.fit_arrhenius()
    print(f"fitted Ea/R = {EaR:.0f} K (input was 2500), "
          f"R0_ref = {R0ref*1000:.2f} mOhm")
    print(f"cycles to 80 % at 1C = {ds.cycle_curves[0].cycles_to(0.80):.0f}")
