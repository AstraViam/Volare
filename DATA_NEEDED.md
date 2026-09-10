# What I Need To Make This Exact

Everything here is ordered by **how much accuracy it buys per unit of effort**.
Each item states what the model currently assumes, what that assumption costs,
and exactly how to get the real number.

Send things as they come — nothing is blocking, each item slots in independently.

**Current honest status:** the *structure* is right and verified (0.0244 K RMS
against the reference solver, energy exact, Kirchhoff to 1e-12). The
*numbers* are a mix of your measured data (cell curves, cockpit geometry) and
my estimates (everything below marked ESTIMATED).

---

## TIER 1 — Biggest error, cheapest to fix

### 1.1 Demihull STL ⭐ highest single impact
**Currently:** parametric hull, Lwl 4.99 m, Bwl 0.45 m, draft 0.14 m,
wetted area 3.29 m² from a Holtrop-style approximation.

**Why it dominates:** frictional resistance is 60–80 % of total drag at cruise
and scales **linearly** with wetted area. A 20 % wetted-area error is a 12–16 %
drag error, which is a ~7 km/h top-speed error and a ~15 % energy-per-lap error.
Everything downstream — laps completed, energy strategy, pack heating — inherits it.

**Send:** one demihull as STL (or STEP/IGES), plus:
- total displacement: boat + pilot + pack + ballast, in kg
- centre-to-centre hull spacing (I have 2035 mm from your earlier notes — confirm)
- whether the STL includes appendages (strut, shaft, rudder) or is bare hull

**What happens:** `Hull.from_stl()` bisects the waterline for your displacement,
clips every triangle at that plane, and returns real wetted area, real draft,
real Lwl, and a real above/below split. Replaces four estimates at once.

```python
CONFIG['hull']['stl'] = 'demihull.stl'
CONFIG['hull']['displacement_kg'] = 250.0   # your real number
```

---

### 1.2 Planing wetted-area fraction ⭐ most sensitive single parameter
**Currently:** `planing_wetted_frac = 0.30` — ESTIMATED.

**Why:** this is the most sensitive number in the entire drag model. Sweeping
0.20 → 0.55 moves top speed from **47.0 → 41.6 km/h**. It is also the number
you cannot calculate — it depends on your actual running trim.

**Send:** video of a sea trial from **abeam**, at 3–4 steady speeds, with
something of known length on the hull for scale (tape marks every 500 mm are
ideal). I need the **spray root position** — where the water breaks away from
the hull — as a fraction of Lwl.

If you have no boat yet: a towing-tank or CFD run at 3 speeds gives the same thing.

---

### 1.3 Motor and inverter torque–speed map ⭐ resolves a known contradiction
**Currently:** propeller is matched analytically with no motor limit applied,
and the match ran **to the edge of its search bounds** (D = 180 mm, P/D = 1.65,
4735 rpm). That rpm may not be reachable.

**This is also an open compliance issue.** Your Competr spec is internally
inconsistent — 26.9 kW nominal against the 25 kW REQ_188 cap, and the quoted
torque and rpm ceilings don't reconcile.

**Send, from the manufacturer, not the brochure:**
- torque vs speed curve at your bus voltage, **and** at 78 V (your loaded floor)
- efficiency map (torque × speed grid), or at minimum peak efficiency and where
- K_t [Nm/A_rms], phase resistance [mΩ], phase inductance [µH]
- continuous vs 60 s vs peak ratings, and the thermal basis for "continuous"
- maximum bus voltage (does it accept 109.2 V?)
- gearbox ratio if any, and its efficiency
- inverter efficiency map or at least efficiency at 25 %, 50 %, 100 % load

**What it fixes:** replaces a flat 0.96 inverter efficiency and an unbounded
propeller optimum with a real operating envelope. Directly changes achievable
top speed and the energy-per-lap figure the whole strategy rests on.

---

### 1.4 GPS trace of the actual course ⭐ makes timing real
**Currently:** reconstructed stadium, 1 NM, 60 m turn radius — the lap length
and 3 h limit are exact from the rules, the **radius is ESTIMATED**.

**Why:** corner radius sets cornering speed (currently 64.8 km/h min), which
sets how much energy you spend accelerating out of corners. It also decides
whether the published asymmetric shape matters.

**Send:** a CSV of `lat,lon` at ≥1 Hz from one lap — a phone, a handheld GPS,
or a Garmin watch is fine. Even a hand-clicked polyline off satellite imagery
of the Monaco stadium course beats my reconstruction.

```python
CONFIG['track']['gps_csv'] = 'practice_lap.csv'
```

`Track.from_gps()` projects to a local tangent plane (millimetre-accurate over
2 km), computes curvature and corner speed limits directly from the trace.

---

## TIER 2 — Removes the remaining `[LOW]` confidence tags

### 2.1 HPPC pulse test on your own cells
**Currently:** R₀/R₁/R₂ split as 1 : 0.53 : 0.67 of the measured sustained
resistance. The **total** is measured from your datasheet curves (16.67 mΩ at
23 °C, good to ~1 %). The **split between the three** is ESTIMATED.

**Why it matters:** the split doesn't change steady-state heat — only the
*transient* response. So it affects how fast the pack reacts to a throttle
step, and therefore the accuracy of anything on a <2 minute timescale
(corner exit, sprint, ventilation recovery). Steady-state race numbers are safe.

**Test:** on 3–5 cells, at 10 % SOC intervals:
```
10 s at 1C  →  40 s rest  →  10 s at 3C  →  40 s rest  →  10 s at 5C  →  rest
```
Log at ≥10 Hz. Repeat at **10, 25 and 45 °C** in a chamber.

**Send:** raw CSV `time, current, voltage, temperature`. I fit R₀ from the
instantaneous step and R₁/τ₁, R₂/τ₂ from the relaxation by two-exponential
least squares. Also fixes `Ea/R` properly rather than the range-restricted fit
I'm using now.

### 2.2 Entropic coefficient dU/dT
**Currently:** literature NMC shape, ESTIMATED. It is **19.4 % of your total
heat** — not a rounding error.

**Test:** set SOC, equilibrate at 25 °C, measure OCV; step to 15 °C and 35 °C,
wait 4+ h at each, measure OCV. Slope = dU/dT. Repeat at 6–8 SOC points.
Tedious (a full day) but it's a fifth of your thermal load.

**Cheaper alternative:** calorimetry — measure total heat at a known current
and subtract the computed I²R. The remainder is the entropic term.

### 2.3 Contact resistances — the ones that cannot be calculated
**Currently ESTIMATED:**

| Parameter | Value | What it is |
|---|---|---|
| `R_core_can_KW` | 2.0 K/W | cell core → can, radial |
| `gap_filler_k_WmK` | 1.5 W/m·K | potting between cells |
| `gap_contact_frac` | 0.16 | effective contact area fraction |
| `R_can_tubewall_KW` | 2.5 K/W | can → tube wall, your bond |
| `G_can_busbar_WK` | 0.015 W/K | through the weld tab |
| `G_layer_WK` | 0.05 W/K | vertical, between stacked layers |

These depend on **your potting process and bond-line thickness**. No datasheet
gives them. Published ranges span 3× — which is a 3× error on hotspot ΔT.

**Test:** build **one instrumented module** — even 2S10P is enough. Fit 15–20
thermocouples: 3 at model-predicted hotspots, 1 at a predicted cold spot, the
rest spread. Run a known current profile on a load bank. Send me the log and
I'll tune the four contact parameters until the model matches.

**Also fit PT1000s on coolant inlet and outlet.** `Q = ṁ·c_p·ΔT` gives a direct,
independent measurement of total heat rejection — two €5 sensors that close the
loop on the entire thermal model. This is the single highest-value test on this list.

### 2.4 Your actual cell grading data
**Currently:** synthetic population, σ_capacity 1.5 %, σ_resistance 6 %.

**Why:** the grading study showed SOC divergence goes 0.61 % → 2.89 % → 5.85 %
across graded / ungraded / mixed-source. Which of those you actually are
determines whether passive balancing can cope.

**Send:** the CSV from your grading campaign — `cell_id, capacity_Ah, DCIR_mΩ`
for all 546. I'll use the real distribution instead of a Gaussian, and can
optimise the physical placement of *your specific cells*.

---

## TIER 3 — Currently invisible failure modes

### 3.1 Coolant manifold geometry
**Currently:** flow splits **equally** between circuits. Real manifolds
maldistribute, sometimes 2:1.

**This is the failure mode the model structurally cannot see.** A starved
circuit is a hot region that shows up nowhere in the current output.

**Send:** manifold CAD or a dimensioned sketch — header bore, take-off spacing,
take-off bore, any restrictors. I'll build a 1D hydraulic resistance network
and compute the real split.

### 3.2 Pump curve
**Currently:** flow is an input; I assume you get what you ask for.

**Send:** the pump's head–flow curve (ΔP vs L/min) and its 12 V power draw.
Then flow becomes an *output* — the intersection of pump curve and circuit
resistance — and changing tube ID will correctly change flow rather than
silently assuming it's free.

### 3.3 Heat exchanger performance
**Currently:** coolant inlet is a fixed temperature you set.

**Why:** in reality, inlet temperature is set by the seawater HX rejecting your
~750 W into the sea. If the HX is undersized, inlet climbs over the race and
everything shifts with it.

**Send:** HX type, plate count/area, UA or the manufacturer's performance curve,
raw-water pump flow rate, and expected Mediterranean sea temperature in July.

### 3.4 Enclosure construction
**Currently:** `enclosure_UA_WK = 3.0`, air volume 0.05 m³, both ESTIMATED.

**Send:** box internal dimensions, wall material and thickness, insulation if
any, and whether it's sealed (REQ_62 IP56) or vented.

### 3.5 Real mass and weight distribution
**Currently:** 250 kg total, ESTIMATED, with 10 % added mass.

**Send:** your mass budget spreadsheet with LCG. Mass sets acceleration, running
trim, and displacement (hence waterline and wetted area). The 250 kg limit
excluding hulls is tight — I flagged the NMC pack subtotal at 207–227 kg earlier.

---

## TIER 4 — Refinement

### 4.1 Logged sea trial ⭐ the single best validation
Once the boat runs, log at ≥5 Hz: `time, pack voltage, pack current, motor rpm,
throttle, GPS speed, ≥4 cell temperatures, coolant in/out, ambient`.

One 20-minute run validates hull drag, propeller efficiency, thermal model and
cell model **simultaneously**. It converts the whole thing from a model into a
digital twin. This outranks everything in Tier 2 and 3 if you can get it.

### 4.2 Propeller data
Actual P/D, diameter, blade area ratio, blade count, and the manufacturer's
open-water KT/KQ curves if they exist. Currently a generic Wageningen-like
polynomial. Given prop matching was worth 14 km/h, this deserves real numbers.

### 4.3 Cockpit Cd
**Currently:** 0.55 ESTIMATED (frontal area 0.2755 m² is measured from your STL).
A CFD run or wind-tunnel number would firm it up. Note the cockpit is only
21 N of your 92 N air drag — the crossbeams are 71 N, so **fairing the beams
matters more**.

### 4.4 Charger specification
Actual charger model, its efficiency curve, and whether shore power is really
16 A/220 V at Monaco. Currently 92 % flat.

### 4.5 BMS configuration
Orion BMS 2 settings as configured: cell voltage limits, temperature derate map,
balance current and threshold, contactor logic. Then the model's limits match
what will actually happen on the boat.

---

## Quick reference — what each unlock changes

| You send | Fixes | Accuracy gain |
|---|---|---|
| Demihull STL | wetted area, draft, Lwl, displacement | **±15 % → ±3 % on drag** |
| Sea-trial video | planing wetted fraction | **±5 km/h → ±1 km/h top speed** |
| Motor torque map | operating envelope, real prop match | resolves REQ_188 conflict |
| GPS lap | corner radii, sector layout | real lap times |
| HPPC pulses | R₀/R₁/R₂ split, Ea/R | transient response |
| Instrumented module | 4 contact resistances | **±3× → ±15 % on hotspot ΔT** |
| Coolant in/out PT1000s | total heat rejection | independent validation |
| Grading CSV | real cell population | true SOC divergence |
| Manifold CAD | flow maldistribution | **reveals an invisible failure mode** |
| Logged sea trial | everything, simultaneously | model → digital twin |

---

## If you can only do three things

1. **Demihull STL + displacement** — one file, fixes the largest error.
2. **Instrumented module with coolant in/out PT1000s** — one weekend, converts
   six estimated thermal parameters into measured ones and independently
   validates the energy balance.
3. **Motor torque–speed map from the manufacturer** — one email, and it also
   resolves an open compliance question you have to answer anyway.
