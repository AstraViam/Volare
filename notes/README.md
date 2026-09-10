# notes/ — the original design discussion

**Partly superseded. Not ground truth.**

These ten notes are the design discussion as it happened. Where a note and a
script disagree, **the script wins**: every number in `cad/scripts/` was
re-derived or re-measured from the supplied STLs, and the scripts self-check.

Known correction: note 06 conflates cockpit mass with supplied mass and
overstates the overage against the 250 kg cap by roughly 80 kg. Use
`cad/scripts/mass.py`.

| Note | Subject |
|---|---|
| `00-master-brief.md` | Scope, objective, frozen constraints |
| `01-aerodynamic-redesign.md` | Aero redesign |
| `02-support-frame-design.md` | Support frame |
| `03-composite-structure.md` | Composite layup |
| `04-fluent-cfd-setup.md` | Fluent CFD setup |
| `05-manufacturable-optimisation-workflow.md` | Optimisation workflow |
| `06-powertrain-battery-and-solar.md` | Powertrain, battery, solar |
| `07-why-beam-position-beats-beam-size.md` | Beam position argument |
| `08-frame-solution-at-fixed-span.md` | Frame at fixed span |
| `09-rules-audit-and-open-questions.md` | Rules audit, open questions |

Filenames were kebab-cased from their original spaced form so they no longer
need quoting in shell commands and scripts. All references were updated.
