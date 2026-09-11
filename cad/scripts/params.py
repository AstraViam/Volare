"""Shared parameter access for every CAD script, in every runtime.

    import params
    P = params.load()
    cap = params.get("rules.mass_limit_excl_hulls_kg")

WHY THIS EXISTS

`powertrain/params/volare_params.json` is the single source of truth for every
engineering number in the project. MATLAB reads it, the volare Python package
reads it, and the Mission Control browser engine reads it. Until now only three
of the twenty-four scripts under `cad/` did; the rest hardcoded their numbers,
so changing a parameter silently failed to reach the CAD.

That is the thing this module fixes. A parameter change now propagates into the
geometry without anybody editing code, which is what lets design work and
analysis proceed in parallel.

THREE RUNTIMES, ONE LOADER

This module runs unchanged under plain CPython, under Blender's bundled Python
and under FreeCAD's. So it uses the standard library only: no numpy, no scipy,
no third-party anything. Blender ships without scipy and FreeCAD's interpreter
is its own; a loader that needed either would be useless in exactly the places
the geometry is built.

WHERE THE FILE IS

Resolved from this file's own location, not from the working directory, so a
script runs the same whether it was launched from the repository root, from
`cad/scripts`, or by Blender with a `-P` path. `cad/scripts`, `cad/blender` and
`cad/freecad` all sit two levels below the repository root, so one rule covers
all three. Set `P50B_ROOT` to override, which is what you want when pointing at
a working copy of the MATLAB project held outside the repository.

NO DEFAULTS, EVER

A missing parameter raises. It does not fall back to a plausible number. A CAD
model built on invented dimensions looks authoritative and is not, and the
failure is silent until somebody machines a part. If you need a value that does
not exist yet, add it to the parameter file with an ASSUMPTION provenance tag
so it shows up in the assumption register.
"""

from __future__ import annotations

import json
import os

__all__ = [
    "PARAMS_PATH", "MissingParameter", "get", "load", "provenance",
    "raw", "reload", "source", "unwrap",
]


class MissingParameter(KeyError):
    """A parameter was asked for that the file does not define."""


def _repo_root() -> str:
    # cad/scripts/params.py -> cad/scripts -> cad -> <repo>
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def _project_root() -> str:
    return os.environ.get("P50B_ROOT", os.path.join(_repo_root(), "powertrain"))


PARAMS_PATH = os.path.join(_project_root(), "params", "volare_params.json")

_RAW: dict | None = None
_FLAT: dict | None = None


def unwrap(node):
    """Strip the {v, u, s, n} parameter leaves down to their values.

    A leaf is recognised by carrying both a value and a provenance tag. Keys
    beginning with an underscore are treated as file-level commentary and
    dropped.
    """
    if isinstance(node, dict):
        if "v" in node and "s" in node:
            return node["v"]
        return {k: unwrap(v) for k, v in node.items() if not k.startswith("_")}
    return node


def _read() -> dict:
    if not os.path.isfile(PARAMS_PATH):
        raise FileNotFoundError(
            "Shared parameter file not found:\n"
            f"  {PARAMS_PATH}\n"
            "Set P50B_ROOT to the MATLAB project directory, or check that the "
            "repository is intact. No defaults will be substituted: a CAD "
            "model built on invented dimensions looks authoritative and is not."
        )
    with open(PARAMS_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _flatten(node, prefix="", out=None) -> dict:
    """Dotted path -> the full {v, u, s, n} leaf, for provenance lookups."""
    if out is None:
        out = {}
    if isinstance(node, dict):
        for key, value in node.items():
            if key.startswith("_"):
                continue
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict) and "v" in value and "s" in value:
                out[path] = value
            elif isinstance(value, dict):
                _flatten(value, path, out)
    return out


def raw() -> dict:
    """The parameter file as written, leaves intact. Cached."""
    global _RAW
    if _RAW is None:
        _RAW = _read()
    return _RAW


def load() -> dict:
    """The parameter tree with leaves unwrapped to plain values. Cached."""
    return unwrap(raw())


def reload() -> dict:
    """Drop the cache and read again, after editing the file in a session."""
    global _RAW, _FLAT
    _RAW = None
    _FLAT = None
    return load()


def _flat() -> dict:
    global _FLAT
    if _FLAT is None:
        _FLAT = _flatten(raw())
    return _FLAT


_REQUIRED = object()


def get(dotted: str, default=_REQUIRED):
    """Fetch one parameter by dotted path, e.g. ``get("boat.pilot_mass_kg")``.

    Raises :class:`MissingParameter` when absent and no default is given. The
    message lists near-miss paths, because the usual cause is a rename and the
    usual fix is two characters.
    """
    flat = _flat()
    if dotted in flat:
        return flat[dotted]["v"]
    if default is not _REQUIRED:
        return default

    tail = dotted.rsplit(".", 1)[-1].lower()
    near = sorted(k for k in flat if tail in k.lower())[:6]
    hint = ("\n  did you mean: " + ", ".join(near)) if near else ""
    raise MissingParameter(
        f"no parameter '{dotted}' in {os.path.basename(PARAMS_PATH)}{hint}")


def provenance(dotted: str) -> dict:
    """Where a parameter came from: its unit, source tag and note.

    Use it when a script reports a number a reviewer might challenge. A value
    tagged ASSUMPTION should never be presented with the same confidence as one
    tagged MEASURED.
    """
    flat = _flat()
    if dotted not in flat:
        raise MissingParameter(f"no parameter '{dotted}'")
    leaf = flat[dotted]
    return {"value": leaf.get("v"), "unit": leaf.get("u", ""),
            "source": leaf.get("s", ""), "note": leaf.get("n", "")}


def source() -> str:
    """Absolute path of the parameter file actually in use."""
    return PARAMS_PATH


def _selftest() -> bool:
    ok = True
    print("params.py selfcheck")
    print(f"  file: {PARAMS_PATH}")
    print(f"  exists: {os.path.isfile(PARAMS_PATH)}")

    tree = load()
    flat = _flat()
    print(f"  {len(flat)} parameters across {len(tree)} sections")

    # A leaf must unwrap to its value, not to the wrapper.
    probe = "boat.pilot_mass_kg"
    value = get(probe)
    if isinstance(value, dict):
        print(f"  FAIL  {probe} unwrapped to a dict, not a value")
        ok = False
    else:
        print(f"  OK    {probe} = {value} {provenance(probe)['unit']}"
              f" [{provenance(probe)['source']}]")

    # Dotted access and tree access must agree.
    if tree["boat"]["pilot_mass_kg"] != value:
        print("  FAIL  dotted access disagrees with tree access")
        ok = False
    else:
        print("  OK    dotted access agrees with tree access")

    # A missing parameter must raise, not return None.
    try:
        get("boat.does_not_exist")
        print("  FAIL  a missing parameter returned instead of raising")
        ok = False
    except MissingParameter:
        print("  OK    a missing parameter raises")

    # A default must be honoured when one is offered.
    if get("boat.does_not_exist", 42) != 42:
        print("  FAIL  default not honoured")
        ok = False
    else:
        print("  OK    default honoured when offered")

    return ok


if __name__ == "__main__":
    raise SystemExit(0 if _selftest() else 1)
