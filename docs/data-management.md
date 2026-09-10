# Data management

## The rule

Git stores what a human wrote. It does not store what a tool can regenerate.

That rule is why `.pyc`, `.blend1`, `.FCBak` and build logs are ignored. Blender
writes a `.blend1` backup beside every `.blend` on each save; those alone were
11.3 MB of byte-for-byte redundancy in the first upload.

## The exception, and why it is deliberate

`cad/out/` and `powertrain/output/` hold generated artefacts that **are**
tracked. That breaks the rule on purpose: not everyone on the team has a MATLAB
licence or a Blender install, and the Simscape libraries under
`powertrain/output/` are needed just to open the `.slx` models.

The cost is churn. A rerun marks those files modified even when nothing
meaningful changed. Handle it this way:

- Commit a regenerated artefact **only when its input actually changed**.
- Otherwise `git checkout -- cad/out powertrain/output` to discard the noise.
- Never commit a regenerated binary as part of an unrelated change. It hides the
  real diff.

## Git LFS

**Not enabled yet.** This is a deliberate hold, not an oversight.

The repository is about 49 MB, well inside GitHub's comfortable range, so LFS
buys little today. The cost of turning it on early is real: `.gitattributes`
LFS filters hand pointer files instead of content to anyone who has not run
`git lfs install`, which looks exactly like data corruption to a teammate who
does not know to expect it.

Turn it on when the binaries approach a few hundred megabytes, and do it as a
coordinated switch:

1. Everyone runs `git lfs install` on their machine, and confirms it.
2. One person adds the filters to `.gitattributes`:
   ```
   *.mat   filter=lfs diff=lfs merge=lfs -text
   *.blend filter=lfs diff=lfs merge=lfs -text
   *.stl   filter=lfs diff=lfs merge=lfs -text
   *.slx   filter=lfs diff=lfs merge=lfs -text
   *.pdf   filter=lfs diff=lfs merge=lfs -text
   *.png   filter=lfs diff=lfs merge=lfs -text
   ```
3. Rewrite history so existing blobs move too, otherwise the repository stays
   large and only future versions benefit:
   ```
   git lfs migrate import --include="*.mat,*.blend,*.stl,*.slx,*.pdf,*.png" --everything
   ```
   This rewrites every commit. Coordinate it: everyone re-clones afterwards.

Do not do step 2 without step 1, and do not do step 3 while anyone has unpushed
work.

## What is large today

| Type | Size | Regenerable? |
|---|---|---|
| `.mat` Simscape libraries | 11.6 MB | Yes, by `P50B_BUILD.m`, but slowly |
| `.png` renders | 11.4 MB | Yes, by `cad/blender/render_views.py` |
| `.blend` scenes | 11.3 MB | Yes, by `cad/blender/build_scene.py` |
| `.stl` supplied cockpit | 6.1 MB | **No.** Supplied by the organisers |
| `.pdf` rules and datasheets | 4.7 MB | **No.** Source material |
| `.slx` Simulink models | 1.0 MB | **No.** Hand-built |

The rows marked "No" are the ones that genuinely must be versioned. The rest are
tracked for convenience and could be dropped if the repository ever needs to
shrink in a hurry.
