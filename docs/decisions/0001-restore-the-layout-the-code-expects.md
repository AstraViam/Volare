# 1. Restore the layout the code already expected

Date: 2026-09-10 · Status: accepted

## Context

The repository arrived as 202 files flat at the root, with no subdirectories.
Both codebases were broken by this, in ways that were silent rather than loud.

`P50B_ProjectRoot.m` computes the project root as the parent of its own
directory, because it is written to live in `<root>/00_common/`. Flat at the
repository root, it returned `/home/user` — outside the repository entirely.
Every data path built from it pointed somewhere wrong.

The Python modules in what is now `cad/scripts/` resolve the repository root as
`Path(__file__).resolve().parents[2]`, which only works if they sit exactly two
levels down.

## Decision

Restore the structure that the code itself specifies, rather than inventing a
new one.

The structure was not a matter of taste. It was recoverable from three sources:

- `powertrain/TEST_ALL.m` contains a 23-entry manifest of required paths,
  naming `00_common/`, `01_cell/`, `02_pack/`, `03_mechanical/`,
  `06_drivetrain/`, `07_simulation/` and `08_compliance/`.
- Other MATLAB files reference `04_data/`, `05_tests/`, `09_hydro/`, `params/`,
  `output/` and `tools/`.
- `CLAUDE.md` and the Blender scripts' own docstrings specify `cad/scripts/`,
  `cad/blender/`, `cad/out/figures/`, `source_documents/` and `notes/`.

## Consequences

Both projects work with **zero code changes**. The 23-path manifest passes, all
24 Python cross-imports resolve, and 14 of 16 `cad/scripts` modules pass their
self-tests.

The tree must not be flattened again. `README.md`, `CLAUDE.md` and each folder
README now say so explicitly, because the failure mode is silent: paths resolve
to somewhere plausible and wrong rather than raising.
