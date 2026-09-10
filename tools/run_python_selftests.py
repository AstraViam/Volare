#!/usr/bin/env python3
"""Run every cad/scripts self-test and report.

Each module in cad/scripts is designed to run standalone and exit non-zero on
failure. Two of them are currently expected to fail on a missing shared
parameter file, and one exits non-zero because real design checks fail; those
are listed explicitly so a genuine regression is still visible.

    python tools/run_python_selftests.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "cad" / "scripts"

# Known non-zero exits that are not regressions. Remove an entry the moment its
# cause is fixed, so the failure starts being reported again.
EXPECTED_FAILURES = {
    "powertrain.py": "3 of 15 design checks fail. These are real open "
                     "engineering issues, documented in CLAUDE.md. Do not "
                     "loosen a check to make this pass",
}

TIMEOUT_S = 300


def main() -> int:
    modules = sorted(SCRIPTS.glob("*.py"))
    if not modules:
        print(f"no modules found in {SCRIPTS}")
        return 1

    unexpected: list[str] = []
    for path in modules:
        try:
            proc = subprocess.run(
                [sys.executable, path.name], cwd=SCRIPTS,
                capture_output=True, text=True, timeout=TIMEOUT_S,
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc, proc = 124, None

        if rc == 0:
            print(f"  PASS      {path.name}")
        elif path.name in EXPECTED_FAILURES:
            print(f"  EXPECTED  {path.name}  ({EXPECTED_FAILURES[path.name]})")
        else:
            print(f"  FAIL      {path.name}  (exit {rc})")
            if proc is not None:
                for line in proc.stderr.strip().splitlines()[-5:]:
                    print(f"            {line}")
            unexpected.append(path.name)

    print()
    if unexpected:
        print(f"{len(unexpected)} unexpected failure(s): {', '.join(unexpected)}")
        return 1
    print(f"all {len(modules)} modules behaved as expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
