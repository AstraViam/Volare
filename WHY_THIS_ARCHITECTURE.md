# Why this architecture

`ARCHITECTURE.md` describes what the project is built from. This describes why
it is built that way, what it is defending against, and where it is still weak.

It is worth reading because the architecture is unusual — three independent
implementations of the same physics is normally a mistake — and because the
reasoning is the part that does not survive being inferred from the code.

---

## 1. The failure this is built to catch

Not a crash. A crash announces itself.

The failure mode is **two parts of the project quietly describing different
boats**, each internally consistent, each producing plausible numbers, and
nothing anywhere able to notice.

It has happened eight times in this project. Every one was found by adding a
comparison, never by reading the code:

| What disagreed | Was | Should have been | How it was found |
|---|---|---|---|
| Pack layout | flat 26×21 in Python, 2 layers in MATLAB | two layers | first cross-check |
| Cell resistance | 12.8 mΩ datasheet vs digitised map | the map | first cross-check |
| Cell-to-coolant | 5.0 K/W in MATLAB, 0.909 in Python | 0.909 | adding it to the cross-check |
| Hull resistance | parametric estimate | supplied curve, up to 5× lower | a third team's data arrived |
| Displacement | 250 kg in both | 315 kg | reading the rule's note carefully |
| Propeller | single screw | contra-rotating | reading the datasheet |
| Driveline efficiency | gearbox counted twice | once | tracing a 10 % power gap |
| **Pack topology** | **literal 26/21 in `P50B_Geometry`** | **from the file** | **smoke test, by breaking it on purpose** |

The last one is the most instructive. `P50B_Geometry` loaded the parameter file
on line 43 and then hardcoded `SeriesGroups = 26` on line 119. Every model in
the project asks that module for the pack topology. Editing `pack.n_series`
would have changed Python, the dashboard and the compliance limits, and left
MATLAB silently building the old pack.

**The cross-check passed the whole time**, because it compared a literal
against the file and they happened to agree. A test that compares two things
that are equal by coincidence proves nothing, and looks exactly like a test
that proves something.

---

## 2. Three implementations, on purpose

The instinct is to write the physics once. That is right for a library and
wrong here, for one reason: **there is no reference answer.** Nobody has built
this boat. There is no measurement to validate against, and there will not be
one until a sea trial.

When you cannot check a model against reality, the next best thing is to check
it against a differently-written model of the same thing. Two independent
implementations agreeing to machine precision does not prove they are right —
they can share an error in the parameters they both read — but it does prove
they are not *differently* wrong, which is the failure that actually happens.

So the redundancy is deliberate, and each implementation is allowed to be best
at something:

| | Owns |
|---|---|
| **MATLAB** | Interconnect, drivetrain chain, compliance, Simscape, mass |
| **Python** | Resolved 546-cell thermal field, hydraulics, cell curves, courses |
| **Browser** | Running the boat forward in time, in front of a person, at 60 fps |

They are not three copies. They are three specialists that overlap enough to
audit each other.

### What the cross-check actually proves

`tools/crosscheck.py` compares 42 quantities to machine precision. Read
honestly, that means:

- ✅ Both implementations read the same parameters and did the same arithmetic.
- ✅ A change to one that breaks agreement is caught immediately.
- ❌ It does **not** mean either is physically correct.
- ❌ It does **not** cover anything not on the list — which is why the list
  grew from 27 to 42 and why the two largest errors found this month were both
  in quantities that were not on it.

**The list is the coverage.** Anything absent from it is unprotected, and the
right instinct on finding a disagreement is to add the quantity rather than
just fix the number.

---

## 3. One parameter file, and what "one" costs

Every physical number lives in `params/volare_params.json`, tagged with unit,
provenance and a note. MATLAB, Python and the browser all read it.

The benefits are obvious. The costs are not, and they are real:

**Derived values have to live somewhere.** Some numbers cannot be computed by
whoever needs them — the convective film resistance needs the resolved tube
hydraulics; the cell OCV curve needs a fitting pass. These are derived once and
written back (`params/cells/p50b_derived.json`, `cooling.R_conv_cell_KW`). That
is a small violation of the single-source principle in exchange for not
reimplementing a solver three times. It is marked `CALCULATED` and the note
says what regenerates it.

**A parameter file makes it easy to add a number and forget to use it.** Which
is exactly what happened with `boat.Lwl_m`: the parameter existed and the
resistance model used a hardcoded default instead. Loading a file is not the
same as reading it.

**Provenance tags are load-bearing.** `ASSUMPTION` and `DATASHEET` mean very
different things when a number reaches a build decision, and the difference is
invisible in the value. 145 of the 459 parameters are assumptions. That is not
a problem to be fixed — it is a preliminary design, and pretending otherwise
would be worse — but it has to be *visible*, which is why the dashboard shows
the breakdown and both languages refuse to run with a `PLACEHOLDER` present.

---

## 4. Compliance is read once, not recomputed

The dashboard could recompute the Monaco rules in JavaScript. It deliberately
does not.

A second implementation of *physics* is a cross-check, because physics has a
right answer that both should find. A second implementation of a *rule book* is
not. Rules are read, not derived, and two readings that differ mean somebody
misread — with no way to tell which. It would be a second thing that can be
wrong, in a file nobody opens.

So `P50B_MonacoCompliance` evaluates the rules once, `P50B_ExportCompliance`
writes the result, and the dashboard displays it. If the export is missing, the
page falls back to the handful of numbers the browser can recompute **and says
so**, rather than showing a partial check that looks like a complete one.

The one exception is the Annex III telemetry payload, which is genuinely live —
built from the running state so the format can be tested against the
organiser's endpoint before the event.

---

## 5. Three tiers of confidence, kept apart

The 94 compliance checks are not equivalent, and collapsing them into a single
"0 violations" number would be dishonest:

| Tier | Count | A PASS means |
|---|---|---|
| **Computed** | ~35 | Derived from the model. As good as the model is. |
| **Declared** | ~35 | Matches a value the team wrote down. The *design* complies. |
| **Checklist** | 24 | Not evaluated. Listed so it is not forgotten. |

The declared tier is the interesting one, and it was the largest change to the
compliance module. Most of the 2026 rules are a number and a direction — *at
least 30 mm*, *no more than 50 mm* — checked at scrutineering by a person with
a tape measure. That used to make them checklist items.

But a rule with a number in it is a number the team must commit to **before**
the tape measure appears. Recording the intended value turns "verify at
inspection" into "we intend 40 mm against a 30–50 mm window", and surfaces the
four items with under 5 % margin months early. When a value is measured on the
boat its tag changes from `DESIGN_CHOICE` to `MEASURED` and the same check
becomes evidence.

That progression — checklist → declared → measured — is the whole design of the
compliance layer, and it is why the tags matter more than the values.

---

## 6. Enforce limits in one place, or in none

ENERGY_REQ_188 caps motor power at 25 kW. The temptation is to check it
everywhere: in the mission profile, in the inverter sizing, in the busbar
model.

A limit enforced in three places is a limit enforced in none of them, because
the three will drift and the loosest one wins. So the cap is applied by
bisection inside `P50B_DrivetrainModel` and nowhere else. Every other module
receives an already-capped operating point and cannot exceed it if it tries.

The same rule governs the two ceilings in `P50B_BoatDynamics`. Power and torque
are both clipped inside `Step`, once, and the binding one is reported per step
so it is visible which is which.

### And know what the limit is on

The cap is on **electrical power consumed**, not shaft power. A boat set up to
deliver 25 kW at the shaft would draw about 26.9 kW and be in breach. The shaft
figure that satisfies the rule is 22.8 kW and depends on where the motor is
operating, so it is solved at the operating point rather than fixed.

Getting this backwards would produce a model reporting a legal boat that is not
legal, and the error would surface at scrutineering with a wattmeter on the DC
link. It is the single most expensive misreading available in this rule set.

---

## 7. Assertions on relationships, not values

The old geometry module asserted `TotalCells == 546`. That assertion would have
caught nothing useful and hidden the topology bug just as effectively as the
literals did — a design change to 25S22P would have tripped it, and the correct
response would have been to edit the assertion.

The replacement asserts **relationships**:

```matlab
layers × groupsPerLayer == seriesGroups
groupRows × groupCols   == parallelCells
storedEnergy            <  rules.energy_limit_Wh
```

A design change is a data edit. Only an *inconsistent* design fails. And the
energy assertion is the rule itself rather than a cell count someone once
worked out from it, so it stays correct if the cell changes.

The failure messages name the parameters to fix, because an assertion that
tells you something is wrong without telling you where is an assertion you
learn to skip past.

---

## 8. Two test layers, and why not one

| | Runtime | Catches |
|---|---|---|
| `SMOKE_TEST` | ~25 s | Does everything still build, and are the answers the right shape? |
| `TEST_ALL` | ~2 min | 14-stage regression: Simscape, missions, thermal networks, numerical agreement |
| `crosscheck.py` | ~30 s | Do MATLAB and Python still describe the same boat? |

The smoke test exists because **a test nobody runs because it is slow is a test
that is not protecting anything.** After changing a number you want an answer in
the time it takes to read the output, and that is a different tool from the one
you run before a commit.

It is also the layer that found the topology bug — not by being clever, but by
being cheap enough to run a deliberate breakage through. A test suite that has
never been shown to fail is a test suite of unknown value; both layers have now
been verified by breaking things on purpose and watching them catch it.

The smoke test deliberately does *not* check numerical accuracy or compare
languages. A smoke test that tried to do everything would be as slow as the
thing it exists to avoid.

---

## 9. Where this is still weak

Stated plainly, because an architecture document that only lists strengths is
marketing.

**The cross-check covers 42 quantities out of thousands.** Everything else is
unprotected. Both major errors found this month were in quantities not on the
list. There is no systematic way to know what is missing — it is judgement, and
judgement has already been wrong twice.

**Most of the drivetrain still hardcodes its parameters.** `P50B_MotorData`,
`P50B_InverterData`, `P50B_HarnessData` and `P50B_AuxiliaryLoads` build their
values with literal `P50B_Param` calls rather than reading the JSON. They
currently agree with the file, but by coincidence and inspection rather than by
construction — exactly the state `P50B_Geometry` was in. **This is the largest
known remaining hole and the obvious next job.**

**The declared-dimension checks test intent, not the boat.** They are a design
the team has written down and can be held to. They are not evidence, and a
compliance report showing 55 passes should not be shown to anyone without that
caveat attached.

**The physics is unvalidated.** No sea trial, no towing tank, no cavitation
tunnel, no instrumented module. Contact resistances cannot be calculated; the
hydrodynamics team's section polars are analytical; the resistance curve stops
at 20 knots and was measured at a displacement 65 kg lighter than the boat.
Agreement between models is not correctness.

**The browser engine is a third implementation with the weakest coverage.** It
is compared through exported sample grids rather than function by function.
A divergence in its stepper would be visible only as a plot that looks slightly
wrong.

---

## 10. If you change one thing

Read the note on the parameter first. It usually says why the value is what it
is, and roughly half the notes in this file exist because somebody already got
that particular thing wrong once.

Then:

```bash
matlab -batch SMOKE_TEST          # seconds — did anything break?
matlab -batch TEST_ALL            # minutes — does the regression hold?
python tools/crosscheck.py        # do both languages still agree?
matlab -batch P50B_ExportCompliance
python tools/build_mission_control.py
```

If you add a quantity that two implementations both compute, **add it to
`CHECKS` in `crosscheck.py` at the same time.** That list is the only thing
standing between this project and the failure mode in section 1, and it only
protects what is on it.
