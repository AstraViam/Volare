# Validating the tests

A test suite that has never failed is not evidence of correctness — it is
evidence of nothing. Every layer here has been validated by deliberately
breaking the code and confirming the layer notices.

Run everything with:

```
python3 verify.py
```

---

## The four layers

| Layer | Command | What only it can catch |
|---|---|---|
| **Physics** | `studies.study_validation()` | The solver disagreeing with an analytic result — wrong conductance, wrong heat term, broken Kirchhoff |
| **Invariants** | `invariants.py` | Properties that only break across a *sweep*: non-monotonic response, wrong sign, conservation violations |
| **Static** | `audit.py` | The artefact being malformed — missing elements, dead controls, competing class writers, a script that will not load |
| **Functional** | `functest.py` | A control that is wired but does nothing, a view that renders nothing, a theme that does not apply |

---

## Sabotage matrix

Each row is a real defect introduced into a working build, then the suite run.

| Defect | Caught by | Result |
|---|---|---|
| UI flag ignored (**the reported day/night bug**) | functional | CAUGHT |
| A view stops rendering | functional | CAUGHT |
| NaN reaches a canvas coordinate | functional | CAUGHT |
| Report emits `undefined` | functional | CAUGHT |
| Boot never hands off to the main loop | functional | CAUGHT |
| `const` used before its declaration | static | CAUGHT |
| Script references a missing element | static | CAUGHT |
| Busbar dropped from source impedance | invariants | CAUGHT |
| Busbar drop not applied at terminals | invariants | CAUGHT |
| Core-can conductance inverted | physics | CAUGHT |
| Cell heat halved | invariants | CAUGHT |
| Kirchhoff broken | physics + invariants | CAUGHT |

**12 of 12.**

---

## Three findings from building this

**A validation that only prints is not a validation.** `study_validation()`
originally printed a 75 % error on the core-can gradient and returned success,
so the consolidated suite reported PASS with an inverted conductance. It now
asserts against explicit tolerances. This was found by sabotage, not by
reading the code.

**A test that cannot fail is worse than no test.** The first energy-conservation
invariant compared `V_cells` against `V_pack + I·R`, but `V_cells` was
*defined* that way — the identity held by construction and could never detect
the solver forgetting the busbar. Replaced with a check against an independent
quantity: delivered power must equal commanded power. That version catches
both busbar regressions.

**"It didn't throw" is a weak assertion.** The functional test originally
passed a view that rendered nothing at all. It now counts canvas operations
and fails a view that draws fewer than 40 — which is how "a view stops
rendering" became detectable.

---

## Invariants that turned out to be wrong

Two invariants failed on correct code, and the model was right both times:

- *"core is never cooler than can"* — false during startup. The pack begins at
  28 °C with coolant inlet at 29 °C, so the coolant **heats** the cells, heat
  flows inward, and the can correctly leads the core.
- *"coolant never colder than its inlet"* — false for the same reason. Coolant
  giving up heat to colder cells drops below inlet, exactly as it should.

Both were restated as what actually holds: the gradient is bounded by what the
heat flow supports, and coolant stays bracketed by its inlet and the cells it
touches. When a validation fails, the assumption is as likely to be wrong as
the code.
