#!/usr/bin/env python3
"""Repository hygiene check.

Guards the three things that actually went wrong in this repository, rather
than a generic lint. Run it before a commit, or let CI run it:

    python tools/check_repo_hygiene.py

Exit code 0 if clean, 1 if anything is wrong.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 1. Backups and build artefacts that no human wrote. These cost 11.7 MB once.
JUNK_SUFFIXES = {".pyc", ".pyo", ".blend1", ".blend2", ".FCBak", ".FCStd1", ".asv"}
JUNK_DIRS = {"__pycache__", ".ruff_cache", ".pytest_cache", "slprj", "sccprj"}

# 2. Paths whose position is load-bearing. Moving any of these silently breaks
#    path resolution rather than raising, which is how this repo broke before.
LOAD_BEARING = [
    ("powertrain/00_common/P50B_ProjectRoot.m",
     "P50B_ProjectRoot() returns the parent of its own folder; it must sit in "
     "powertrain/00_common/ or the whole MATLAB project resolves elsewhere"),
    ("cad/scripts/volare.py",
     "cad/scripts modules resolve the repo root as parents[2]; they must stay "
     "exactly two levels below the repository root"),
    ("cad/out/figures",
     "render_views.py writes here via parents[2]/cad/out/figures"),
    ("source_documents/Cockpit_V1_3.stl",
     "geom.py reads the supplied STLs from source_documents/"),
    ("HANDOFF.md",
     "the entry point every session is required to update"),
    ("powertrain/params/volare_params.json",
     "the single parameter file MATLAB, the volare package and the CAD "
     "scripts all read; everything downstream fails without it"),
    ("powertrain/python/volare/params.py",
     "params.py resolves project_root() two levels up, so the package must "
     "stay at powertrain/python/volare"),
    ("powertrain/tools/crosscheck.py",
     "P50B_ArchitectureAudit.m looks for it at <project root>/tools/"),
    ("powertrain/web/mission_control.html",
     "build_mission_control.py reads the shell from _ROOT/web/"),
]

# 3. The MATLAB manifest that TEST_ALL.m asserts. Kept in sync by hand; if
#    TEST_ALL.m changes, change this too.
MATLAB_MANIFEST = [
    "08_compliance/P50B_MonacoCompliance.m", "00_common/P50B_Param.m",
    "00_common/P50B_Value.m", "00_common/P50B_Unwrap.m",
    "00_common/P50B_ProjectRoot.m", "00_common/P50B_ProvenanceReport.m",
    "01_cell/P50B_CellData.m", "01_cell/P50B_OCV.m", "01_cell/P50B_DCIR.m",
    "02_pack/P50B_21P.m", "02_pack/P50B_13S21P.m", "02_pack/P50B_26S21P.m",
    "03_mechanical/P50B_Geometry.m", "03_mechanical/P50B_GroupLayout.m",
    "03_mechanical/P50B_CellCoordinates.m", "03_mechanical/P50B_Busbars.m",
    "06_drivetrain/P50B_MotorData.m", "06_drivetrain/P50B_InverterData.m",
    "06_drivetrain/P50B_HarnessData.m", "06_drivetrain/P50B_AuxiliaryLoads.m",
    "06_drivetrain/P50B_DrivetrainModel.m", "07_simulation/P50B_MissionProfile.m",
    "07_simulation/P50B_RunMission.m",
]

LARGE_FILE_MB = 25.0


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [ROOT / p for p in out.split("\0") if p]


def main() -> int:
    problems: list[str] = []
    files = tracked_files()

    for path in files:
        rel = path.relative_to(ROOT)
        if path.suffix in JUNK_SUFFIXES:
            problems.append(f"regenerable artefact is tracked: {rel}")
        if JUNK_DIRS & set(rel.parts):
            problems.append(f"cache directory is tracked: {rel}")

    for rel, why in LOAD_BEARING:
        if not (ROOT / rel).exists():
            problems.append(f"load-bearing path missing: {rel}\n      {why}")

    powertrain = ROOT / "powertrain"
    if powertrain.is_dir():
        missing = [m for m in MATLAB_MANIFEST if not (powertrain / m).exists()]
        if missing:
            problems.append(
                "TEST_ALL.m's manifest would fail; missing under powertrain/:\n      "
                + "\n      ".join(missing)
            )

    for path in files:
        if path.exists() and path.stat().st_size > LARGE_FILE_MB * 1024 * 1024:
            size = path.stat().st_size / 1024 / 1024
            problems.append(
                f"{path.relative_to(ROOT)} is {size:.1f} MB. Consider Git LFS; "
                "see docs/data-management.md"
            )

    if problems:
        print(f"repo hygiene: {len(problems)} problem(s)\n")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"repo hygiene: clean ({len(files)} tracked files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
