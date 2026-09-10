# cad/ — Blender + FreeCAD working package

Geometry pipeline for the Volare cockpit. Built on the STLs in `../source_documents/`
and the frozen constraints in `../notes/`.

Everything here is reproducible from a bare Python install with numpy; only
`blender/` needs Blender. That is deliberate — the measurement and optimisation
maths is testable without a GUI app, and Blender is a consumer of it, not the
place it lives.

## Canonical frame

**X forward, Y port, Z up. Origin = centreline × hull mid-length × hull keel bottom.**

The two supplied STLs do *not* share a frame, and neither matches this one:

| File | Frame |
|---|---|
| `Cockpit_V1_3.stl` | +Y aft, X transverse, Z up, Z≈0 on the pod floor |
| `FULLCOCPITV1_3.stl` | +X aft, Y transverse, Z up |

`scripts/volare.py` holds both transforms. They are verified against three numbers
derived independently in the notes: the 640 mm forward pod cantilever (note 08),
the 2998 mm beam span (note 08), and q = 143.0 Pa (note 01).

## Layout

```
scripts/            pure numpy + scipy, no Blender
  volare.py         canonical frame, measured baseline, frozen rule constants
  geom.py           mesh metrics: areas, sections, slicing, closure angle
  parts.py          splits the assembly into 17 named parts, tagged by CFD zone
  stl_audit.py      raw audit of both STLs
  pod_baseline.py   pod shape signature + re-test of the note 00 defects
  aero.py           component drag model
  parametric.py     NACA fairing section, pole-fit check, fairing mass + mesh
  optimise.py       whole-boat drag+mass optimisation
  plot_results.py   figures
blender/
  build_scene.py    builds the baseline scene, headless
  render_views.py   orthographic side/front/top/iso renders
out/                generated: json, csv, blend, figures/, views/
```

Every script is runnable on its own and self-checks:

```bash
python scripts/volare.py && python scripts/geom.py && python scripts/parts.py && python scripts/aero.py
```

## Building the Blender scene

```bash
blender --background --python blender/build_scene.py
```

Produces `out/volare_baseline.blend` and `out/volare_baseline.json`. The script
re-measures every part inside Blender and fails if any surface area disagrees
with the numpy value by more than 0.01% — a silent unit or transform error
cannot get through.

Collections: `SUPPLIED` (organiser hardware, locked, ENERGY_REQ_3), `COCKPIT`,
`FRAME`, `PROPOSED` (rule-compliant replacements), `REFERENCE` (envelopes and
datums, non-physical).

## What the audit found

Confirms note 00 exactly: pod laminate area 4.5803 m², enclosed volume 320.6 L,
planform 1.5116 m², aft closure 15.59°.

Four things it corrects or adds:

1. **The crossbeam drag is overcharged by ~41%.** Note 00 assigns C_D = 2.05, the
   value for a square section in crossflow, because the STL models the beams as
   104×104 boxes. ENERGY_REQ_3 supplies *round* Ø104 poles; at Re = 1.06×10⁵ a
   circular cylinder sees C_D ≈ 1.2. Baseline drag falls from 168.8 N to 91–113 N
   depending on how much of the span you treat as shadowed by the hulls. The
   beams stay the number one item (57% of the budget rather than 77%), so note
   00's priority order survives, but the "−88%" headline does not.
2. **The two STLs hold different revisions of the pod.** Registered nose-to-nose
   and floor-to-floor, the assembly copy is 5.2 mm longer in the tail and 11.8 mm
   taller at the crown, with the tail face retessellated. Confirm which is current
   before any mould work. The assembly copy is treated as authoritative here.
3. **The aft body is worse than the mean angle suggests.** Mean closure is 15.59°
   as noted, but the *local* slope peaks at 21.3°, and 79% of aft-body stations
   exceed the 12° target. The base patch at the tail is 0.0746 m², 50% larger
   than the ~0.05 m² note 01 §4.4 assumed.
4. **The two crossbeams are not at the same height.** The forward pole sits 91.4 mm
   below the aft one in the STL. Check that against the real hull suspension
   stations — it decides whether the rails are level.

Re-measured: rail/pod interference is 85.7 mm, not 83 mm. Rail spacing is 400 mm
and must go to 750 mm (ENERGY_REQ_38) — 175 mm outboard on each side.

## Priority, from `aero.py`

| Action | Worth |
|---|---|
| Fair both crossbeams | **≈ 49 N** |
| Pilot fairing + windscreen | ≈ 11 N |
| Blended brackets | ≈ 8 N |
| Fix the pod aft body to 12° | **≈ 2 N (32 W)** |

## Optimisation — `optimise.py`

Notes 00 and 01 optimise drag, and note 01 §3 separately observes that mass costs
hull resistance at `dR = (R/W)·dW`, `R/W ≈ 0.12`. Nothing joins them up. Every
fairing that removes drag adds mass, so the objective is

```
R_eff = D_aero(x) + (R/W)·g·m_added(x)        1 kg = 1.18 N
```

Six design variables: fairing t/c on each beam, windscreen / bracket / rail
treatment completeness, and pod aft-closure angle. Chord is not free — it is set
to the smallest that actually swallows the Ø104 pole with 6 mm clearance, which
`parametric.py` solves geometrically. That check found the naive `chord = D/(t/c)`
gives **zero** clearance; a real fairing needs 12% more chord.

**Result:**

| | drag-only | drag + mass |
|---|---|---|
| fairing t/c | 0.246 (**4.1:1**) | 0.369 (**2.7:1**) |
| chord | 472 mm | 310 mm |
| added mass | 12.6 kg | **10.4 kg** |
| aero drag | 18.5 N | 19.4 N |
| effective resistance | 33.4 N | **31.6 N** |

Optimising drag alone reproduces note 01's 4:1 recommendation almost exactly —
good independent confirmation of that note. But 4:1 is only right if mass is
free. Counting mass at note 01's own exchange rate, the optimum is a **fatter,
shorter 2.7:1 fairing**: 0.9 N more aero drag, 2.2 kg less mass, 1.8 N better
overall. It is also 162 mm shorter in chord, which matters under the pod nose.

Against the bare round-pole baseline (91.1 N) the optimised boat is **31.6 N, a
65% / 0.91 kW saving**. Note 00 claimed 88%, but measured against a baseline
inflated by the square-beam error.

Pareto front (`--pareto`) — returns diminish hard past about 8 kg:

| added-mass budget | 4 kg | 6 kg | 8 kg | 10 kg | unlimited |
|---|---|---|---|---|---|
| effective resistance | 47.9 N | 38.9 N | 33.8 N | 31.8 N | 31.6 N |

Caveats, in order of how much they could move the answer:

- **The mass model is estimated, not weighed.** 2.2 kg/m² for the fairing shell,
  4.8 kg/m² for a 4 mm screen. The 4:1-vs-2.7:1 conclusion turns directly on
  this — weigh a test panel before committing.
- `R/W = 0.12` is the top of note 01's 0.10–0.12 range. At 0.10 the optimum moves
  back toward 3:1.
- Pilot / bracket / rail treatments are a linear blend between note 00's
  untreated and optimised C_D values. That is an interpolation, not physics.
  CFD cases 2–8 replace it.
- The design space has no "leave this beam bare" option, so the Pareto front
  bottoms out at 3.59 kg rather than zero. Academic here — fairing always wins.

Figures in `out/figures/`: `drag_budget.png`, `fairing_trade.png`,
`pod_profile.png`.

## Static hydrostatics — `hydrostatics.py`

Mass basis confirmed by the team 2026-09-04: the 250 kg cap covers the **entire
cockpit including the pilot**, and the supplied hulls + beams are 65 kg. Maximum
all-up displacement is therefore **315 kg**. That settles note 09's Q-TC-2 and
note 06's "governing unknown" — and settles it the expensive way: note 06 §8
budgets 282 kg for the boat alone before the pilot, so the design is **102 kg
over**.

At 315 kg in Mediterranean seawater (1028 kg/m³, not the 1025 usually quoted —
Monaco harbour is Med water), level trim:

| | |
|---|---|
| **Water level above keel** | **157.6 mm** |
| **Wetted area** | **4.790 m² of 13.851 m² moulded** |
| **Wetted fraction** | **34.6 %** |
| Displaced volume | 306.4 L |
| Freeboard to deck | 442.4 mm |
| Pod floor above water | 420.1 mm |
| Waterplane area | 2.982 m² |
| LWL / BWL demihull | 4343 / 453 mm, L/B = 9.58 |
| Slenderness L/∇^⅓ | 6.44 |
| Cb / Cwp | 0.494 / 0.757 |
| LCB / LCF | +363.5 / −121.3 mm |
| KB | 96.2 mm |
| BMt / KMt | 10 205 / 10 302 mm |
| BMl / KMl | 11 209 / 11 305 mm |
| Immersion | 30.7 kg per cm |

What it constrains:

- **For level trim the whole-boat LCG must sit at X = +363.5 mm.** That is 363 mm
  forward of hull mid-length, and the pod centroid is at +338 — close, but the
  outboard hangs well aft, so this needs checking once the real mass breakdown
  exists.
- Every 10 kg of overload sinks the boat 3.3 mm and adds ~9 dm² of wetted area.
  At note 06's 417 kg the wetted fraction goes 34.6% → 40.8%.
- Reserve buoyancy is huge: 1090 kg before the hulls are fully immersed.
- BMt = 10.2 m. Transverse stability is a non-issue at this hull spacing, and BMl
  = 11.2 m means trim is set entirely by LCG, not by hull form.

**This is the at-rest condition.** At 55 km/h the boat planes (volumetric Froude
6.65) and the running wetted area is a small aft patch, nothing like 4.79 m².
These figures are for freeboard and reserve buoyancy, stability, the float-off at
handover, and the slow end of the endurance event.

Two caveats:

- The hull STL has ~16 000 open edges. They are coincident-but-unmerged rather
  than real holes — three independent volume methods (divergence theorem,
  horizontal section integral, transverse section integral) agree to 0.3%, and
  the submerged volume to 0.003%, so the hydrostatics stand. **But Fluent will
  need a watertight surface**, so this has to be repaired before CFD meshing.
- 65 kg is the supplied hull + beam mass from the rulebook, not a weighing. Note
  06 assumes 80 kg and flags "UNKNOWN — weigh them". Weigh them.

## Mass — `mass.py`

**The gap is 22 kg, not 102 kg.** Note 06 §8's "+32 / +102 over cap" compares its
282 kg subtotal — which *includes 80 kg of demihulls* — against a cap that
excludes hulls. Cockpit items alone are 202 kg; with a 70 kg pilot that is 272 kg
against the 250 kg cap.

That distinction decides the project. 102 kg is not closable by trimming; 22 kg
is. Adding the aero work's windscreen and bracket fairings (+3.7 kg, not in note
06) widens it to 25.7 kg, and the ENERGY_REQ_38 floor rebuild adds ~4 kg more.

Cheapest closure is `solar + pack6 + schedB`, but it lands **0.3 kg** under the
cap — inside the scatter of a wet hand layup, so it is not a plan. Requiring ≥5 kg
margin gives **`solar + pack6 + carbonrail`**: 32 kg saved, lands at 243.7 kg,
6.3 kg of margin, 308.7 kg all-up.

Pilot mass matters directly, since the cap includes them: at 60 kg two levers
suffice; at 80 kg you need four; past that the powertrain has to change.

**This does not fix ENERGY_REQ_188.** The Competr outboard is 26.9 kW nominal
against a 25 kW cap. That is a compliance failure independent of mass, and if it
forces a different outboard the 38 kg powertrain block and the 10 kg inverter
question all reopen — invalidating every plan above. Settle it first.

## Frame — `frame.py` + `blender/frame_redesign.py`

Note 05 puts this second in the sequence, before anything else: the frame sets the
pod's boundary conditions, so the FE model is not valid until it is frozen.

`frame_redesign.py` builds the compliant frame and passes 12/12 checks. Two fixes
are done together because they interact — once the pod sits *on* the rails rather
than through them, the rails can move outboard without cutting the floor:

| | |
|---|---|
| Rails | ±200 → **±375 mm** (750 mm clamp spacing, ENERGY_REQ_38) |
| Clamps | 60 mm wide, envelop Ø104 + 2 mm gasket, 2 per beam |
| Pod | **raised 103.7 mm** onto 10 mm pads (note 00's preferred option b) |
| Forward shim | **91.3 mm** |

Three things the geometry forced out that the notes do not carry:

1. **The 91.4 mm pole height step is structural, not cosmetic.** A level rail has
   to be packed 91.3 mm at the forward station — and note 08 §1 says that station
   carries **79%** of the load. That packer is a structural part needing its own
   check, not a washer.
2. **The clamps barely fit.** At ±375 the clamp inner face clears the pod edge by
   **5 mm**. If note 09's Q-TC-5 comes back "750 mm between inner faces" rather
   than centre-to-centre, centres go to 800 mm and the clamps no longer tuck under
   the pod at all — they need outboard brackets. Ask before building.
3. **The rails now protrude 75 mm** past the pod edge each side. That is new
   exposed frontal area and a new drag item.

### Floor panel

Moving the rails nearly doubles the floor span. Note 09 A2 calls it "a 12.4×
penalty" but its own table shows 1.80 → 9.20 mm, which is 5.1×. Neither is right:
core shear carries 31% of the deflection at 400 mm and only 11% at 750 mm, so the
correct ratio is **9.6×** (1.06 → 10.23 mm on the same schedule). The conclusion
holds — the floor is under-built — but the fix is cheaper than note 09 implies.

Three fixes, all within 0.7 kg of each other, so **do not choose on mass**:

| | core | plies/skin | total |
|---|---|---|---|
| A: thicken the panel | 40 mm | 3 | 7.02 kg |
| B: + centreline keel beam (span 375) | 20 mm | 2 | 6.60 kg |
| C: + 3 transverse frames (span 400) | 20 mm | 2 | 6.34 kg |

B also carries the seat mount and gives one clean centreline load path; C spreads
load better but adds three more core-removal/insert details, which note 05 §3 says
is where student composite builds actually fail. Budget **+4 kg** against note
06's 27 kg shell line either way — it does not currently carry this.

## Open questions this package cannot answer

- Which pod revision is current (see finding 2).
- Is the 91.4 mm beam height step real, or an STL artefact (finding 4)?
- Real pilot anthropometry — `build_scene.py` uses a 95th-percentile placeholder,
  and the egress and ENERGY_REQ_25 standoff checks are only as good as that.
- How much of the crossbeam span is genuinely shadowed by the hulls. The drag
  budget swings 91 N ↔ 113 N on this; CFD case 1 settles it.
