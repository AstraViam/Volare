#!/usr/bin/env python3
r"""
volare_thermal.verify
=====================

One command that runs every check in the project.

    python3 verify.py

Four independent layers, because each catches a class the others cannot:

  1  PHYSICS      pack_thermal's own analytic validations — adiabatic energy
                  balance, core-can gradient at steady state, Kirchhoff,
                  timestep independence
  2  INVARIANTS   properties that must hold across parameter SWEEPS, not at a
                  point: monotonicity, physical ordering, conservation
  3  STATIC       the generated dashboard as an artefact — unique ids, every
                  lookup resolves, every control wired, no competing class
                  writers, script parses and executes top to bottom
  4  FUNCTIONAL   every control actually fired, every view actually drawn,
                  in every theme, with canvas-op counting so a view that
                  silently renders nothing is a failure

Each layer has been validated by deliberate sabotage — see SABOTAGE.md.
"""

from __future__ import annotations
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(label, args, grep=None):
    t0 = time.time()
    print("\n" + "=" * 74)
    print(f"  {label}")
    print("=" * 74)
    r = subprocess.run([PY] + args, cwd=HERE, capture_output=True, text=True,
                       timeout=900)
    out = r.stdout
    if grep:
        keep = [l for l in out.splitlines()
                if any(g in l for g in grep) or l.startswith(("[ FAIL", "  FAIL"))]
        out = "\n".join(keep)
    print(out.strip())
    if r.returncode and r.stderr:
        print(r.stderr[:1500])
    print(f"  -> {'PASS' if r.returncode == 0 else 'FAIL'} in {time.time()-t0:.1f} s")
    return r.returncode == 0


def main():
    ok = []
    ok.append(("physics validations", run(
        "1. PHYSICS — analytic validations of the reference solver",
        ["-c", "import studies; studies.study_validation()"],
        grep=["(a)", "(b)", "(c)", "(d)", "(e)", "dt="])))
    ok.append(("invariants", run(
        "2. INVARIANTS — properties swept across the parameter space",
        ["invariants.py"], grep=["invariant failures", "[ FAIL"])))
    ok.append(("build + static audit", run(
        "3. STATIC — rebuild the dashboard and audit the artefact",
        ["-c", "import run as R; R.task_mission()"],
        grep=["T_max RMS", "javascript check", "reconstruction", "->"])))
    ok.append(("audit", run("   static checklist", ["audit.py"],
                            grep=["checks ·", "[ FAIL", "[ warn"])))
    ok.append(("functional", run(
        "4. FUNCTIONAL — every control fired, every view drawn",
        ["functest.py"], grep=["assertions", "FAIL", "boot dismissed",
                               "t=", "pop-out"])))

    print("\n" + "=" * 74)
    print("  SUMMARY")
    print("=" * 74)
    for name, good in ok:
        print(f"  {'PASS' if good else 'FAIL'}  {name}")
    bad = [n for n, g in ok if not g]
    print(f"\n  {len(ok) - len(bad)}/{len(ok)} layers passing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
