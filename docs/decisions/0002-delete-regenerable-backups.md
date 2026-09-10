# 2. Delete regenerable backups, keep generated deliverables

Date: 2026-09-10 · Status: accepted

## Context

The upload contained 11.7 MB of files no human wrote: 18 `.pyc` compiled
modules (duplicated across Python 3.13 and 3.14), 5 Blender `.blend1` autosave
backups, 1 FreeCAD `.FCBak`, and a build log.

The repository's own `.gitignore` already listed `__pycache__/`, `*.pyc`,
`*.blend1` and `*.FCBak`, so these had been force-added, or added before that
file existed.

## Decision

Delete them, and keep the ignore rules that prevent their return.

Keep the generated artefacts in `cad/out/` and `powertrain/output/` tracked,
even though they are also machine-produced.

## Consequences

The distinction is who needs the output. A `.blend1` is a backup of a file
sitting next to it and serves nobody. A Simscape `.mat` library is needed to
open the `.slx` models, and not every teammate has a MATLAB licence to rebuild
it.

The cost of that exception is diff churn on every rerun, documented in
`docs/data-management.md` along with how to discard it.
