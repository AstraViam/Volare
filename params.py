r"""
volare.params
=============

Reader for the project's single source of truth, ``params/volare_params.json``.

WHY THIS EXISTS
---------------
This project has three independent implementations of the same physics: the
Python reference model, the MATLAB/Simscape model, and the JavaScript engine
inside Mission Control. Three implementations of one design is a strength --
they cross-check each other -- but only if they are all describing the *same*
design.

Before this module existed they were not. The MATLAB side had a cell DCIR of
12.8 mOhm from the datasheet; the Python side had a digitised R0 map. The
MATLAB side had a two-layer pack; the Python side a flat one. Neither was
wrong on its own terms, and nothing in either codebase could have told you
they disagreed.

Every physical parameter now lives in one JSON file, and all three read it.
Add a measurement once and it propagates everywhere.

LEAF FORMAT
-----------
Every physical parameter in the JSON is an object::

    {"v": 5.0, "u": "A*hr", "s": "DATASHEET", "n": "optional note"}

``load()`` returns a :class:`Params` that unwraps ``v`` for you while keeping
the unit, source and note available for auditing.

USAGE
-----
::

    from volare.params import load

    P = load()

    P.cell.capacity_Ah              # -> 5.0        (the value)
    P("cell.capacity_Ah")           # -> 5.0        (dotted path)
    P.meta_of("cell.capacity_Ah")   # -> Leaf(v=5.0, u='A*hr', s='DATASHEET', ...)

    P.report()                      # provenance audit, same tags as MATLAB
    P.assert_no_placeholders()      # raises if any PLACEHOLDER remains

The MATLAB reader ``P50B_LoadParams`` returns the identical structure, so a
parameter path is the same string in both languages.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple


# ---------------------------------------------------------------------------
#  Provenance
# ---------------------------------------------------------------------------

#: Ordered best-to-worst. Index is the confidence rank, matching MATLAB's
#: ``P50B_Param`` so the two provenance reports sort identically.
SOURCE_ORDER: Tuple[str, ...] = (
    "MEASURED",
    "DATASHEET",
    "DIGITISED",
    "PUBLISHED_TEST",
    "CALCULATED",
    "DESIGN_CHOICE",
    "ASSUMPTION",
    "PLACEHOLDER",
)

SOURCE_RANK: Dict[str, int] = {s: i + 1 for i, s in enumerate(SOURCE_ORDER)}


@dataclass(frozen=True)
class Leaf:
    """One provenance-tagged parameter."""

    path: str
    value: Any
    unit: str
    source: str
    note: str = ""

    @property
    def rank(self) -> int:
        return SOURCE_RANK.get(self.source, 99)

    @property
    def is_trustworthy(self) -> bool:
        """True for values traceable to a measurement or a datasheet."""
        return self.source in ("MEASURED", "DATASHEET", "DIGITISED",
                              "PUBLISHED_TEST")

    def __repr__(self) -> str:
        return (f"Leaf({self.path} = {self.value!r} {self.unit} "
                f"[{self.source}])")


# ---------------------------------------------------------------------------
#  Namespace wrapper
# ---------------------------------------------------------------------------

class _Node:
    """Attribute access over one level of the parameter tree.

    Returns bare values for leaves and further ``_Node`` objects for
    subsections, so ``P.cell.capacity_Ah`` reads naturally.
    """

    __slots__ = ("_raw", "_prefix")

    def __init__(self, raw: Dict[str, Any], prefix: str = ""):
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_prefix", prefix)

    def __getattr__(self, name: str) -> Any:
        raw = object.__getattribute__(self, "_raw")

        if name not in raw:
            avail = ", ".join(k for k in raw if not k.startswith("_"))
            raise AttributeError(
                f"No parameter '{name}' in "
                f"'{object.__getattribute__(self, '_prefix') or 'root'}'. "
                f"Available: {avail}")

        v = raw[name]

        if _is_leaf(v):
            return v["v"]

        if isinstance(v, dict):
            pre = object.__getattribute__(self, "_prefix")
            return _Node(v, f"{pre}.{name}" if pre else name)

        return v

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            "Parameters are read-only. Edit params/volare_params.json so the "
            "change reaches MATLAB and Mission Control too.")

    def __dir__(self) -> List[str]:
        return [k for k in object.__getattribute__(self, "_raw")
                if not k.startswith("_")]

    def __repr__(self) -> str:
        return (f"<Params section "
                f"'{object.__getattribute__(self, '_prefix')}': "
                f"{', '.join(self.__dir__())}>")


def _is_leaf(v: Any) -> bool:
    return isinstance(v, dict) and "v" in v and "s" in v


# ---------------------------------------------------------------------------
#  Main container
# ---------------------------------------------------------------------------

class Params:
    """The whole parameter set, with provenance."""

    def __init__(self, raw: Dict[str, Any], path: str):
        self._raw = raw
        self._path = path
        self._leaves: Dict[str, Leaf] = {}
        self._index(raw, "")
        self._validate()

    # -- construction ------------------------------------------------------

    def _index(self, node: Dict[str, Any], prefix: str) -> None:
        for k, v in node.items():
            if k.startswith("_"):
                continue
            p = f"{prefix}.{k}" if prefix else k
            if _is_leaf(v):
                self._leaves[p] = Leaf(
                    path=p,
                    value=v["v"],
                    unit=v.get("u", "-"),
                    source=v["s"],
                    note=v.get("n", ""),
                )
            elif isinstance(v, dict):
                self._index(v, p)

    def _validate(self) -> None:
        """Reject an unusable parameter file loudly rather than late."""
        bad = [l for l in self._leaves.values()
               if l.source not in SOURCE_RANK]

        if bad:
            raise ValueError(
                "Unknown provenance tag(s) in the parameter file:\n" +
                "\n".join(f"  {l.path}: '{l.source}'" for l in bad) +
                f"\nValid tags: {', '.join(SOURCE_ORDER)}")

        missing_unit = [l for l in self._leaves.values() if not l.unit]

        if missing_unit:
            raise ValueError(
                "Parameter(s) with no unit:\n" +
                "\n".join(f"  {l.path}" for l in missing_unit))

    # -- access ------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        raw = object.__getattribute__(self, "_raw")
        if name in raw:
            v = raw[name]
            return _Node(v, name) if isinstance(v, dict) else v
        raise AttributeError(
            f"No section '{name}'. Available: "
            f"{', '.join(k for k in raw if not k.startswith('_'))}")

    def __call__(self, path: str) -> Any:
        """Value at a dotted path. ``P('cell.capacity_Ah')``."""
        if path not in self._leaves:
            raise KeyError(f"No parameter '{path}'. "
                           f"{self._suggest(path)}")
        return self._leaves[path].value

    def meta_of(self, path: str) -> Leaf:
        """Full provenance record for a dotted path."""
        if path not in self._leaves:
            raise KeyError(f"No parameter '{path}'. {self._suggest(path)}")
        return self._leaves[path]

    def _suggest(self, path: str) -> str:
        tail = path.rsplit(".", 1)[-1].lower()
        near = [p for p in self._leaves if tail in p.lower()][:5]
        return f"Did you mean: {', '.join(near)}?" if near else ""

    def get(self, path: str, default: Any = None) -> Any:
        return self._leaves[path].value if path in self._leaves else default

    def leaves(self) -> Iterator[Leaf]:
        return iter(sorted(self._leaves.values(), key=lambda l: l.path))

    def section(self, name: str) -> Dict[str, Any]:
        """Bare ``{name: value}`` dict for one section.

        Convenient for handing a block of parameters straight into a
        dataclass constructor.
        """
        out: Dict[str, Any] = {}
        for p, l in self._leaves.items():
            if p.startswith(name + "."):
                out[p[len(name) + 1:]] = l.value
        if not out:
            raise KeyError(f"No section '{name}'.")
        return out

    # -- auditing ----------------------------------------------------------

    def by_source(self) -> Dict[str, List[Leaf]]:
        out: Dict[str, List[Leaf]] = {s: [] for s in SOURCE_ORDER}
        for l in self._leaves.values():
            out[l.source].append(l)
        return {k: v for k, v in out.items() if v}

    def counts(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self.by_source().items()}

    def assert_no_placeholders(self) -> None:
        """Raise if any parameter is still an invented number.

        A PLACEHOLDER is a value with no defensible origin. Any result that
        depends on one is not quotable, so the test suite treats its presence
        as a failure rather than a warning.
        """
        bad = self.by_source().get("PLACEHOLDER", [])
        if bad:
            raise AssertionError(
                f"{len(bad)} PLACEHOLDER parameter(s) remain:\n" +
                "\n".join(f"  {l.path} = {l.value} {l.unit}"
                          f"{('  -- ' + l.note) if l.note else ''}"
                          for l in bad))

    def report(self, show_assumptions: bool = True) -> str:
        """Provenance audit. Mirrors MATLAB's ``P50B_ProvenanceReport``."""
        w = 64
        out: List[str] = []
        out.append("=" * w)
        out.append(" VOLARE PARAMETER PROVENANCE")
        out.append("=" * w)
        out.append(f" source: {self._path}")
        out.append("")

        counts = self.counts()
        for s in SOURCE_ORDER:
            if s in counts:
                out.append(f"   {s:<16s} {counts[s]:4d}")
        out.append("")
        out.append(f"   {'TOTAL':<16s} {len(self._leaves):4d}")

        ph = self.by_source().get("PLACEHOLDER", [])
        if ph:
            out.append("")
            out.append("-" * w)
            out.append(f" WARNING: {len(ph)} PLACEHOLDER parameter(s)")
            out.append("-" * w)
            out.append(" These were invented to let the model run.")
            out.append(" Any result depending on them is NOT quotable.")
            out.append("")
            for l in ph:
                out.append(f"   {l.path} = {l.value} {l.unit}")
        else:
            out.append("")
            out.append(" No PLACEHOLDER parameters. Every number has a source.")

        if show_assumptions:
            asm = self.by_source().get("ASSUMPTION", [])
            if asm:
                out.append("")
                out.append("-" * w)
                out.append(f" {len(asm)} ASSUMPTION(S) -- defensible, unverified")
                out.append("-" * w)
                for l in sorted(asm, key=lambda x: x.path):
                    out.append(f"   {l.path} = {l.value} {l.unit}")

        out.append("")
        out.append("=" * w)
        return "\n".join(out)

    # -- export ------------------------------------------------------------

    def flat(self, values_only: bool = True) -> Dict[str, Any]:
        """Flat ``{dotted.path: value}`` mapping.

        This is what gets injected into Mission Control, so the browser
        engine runs on exactly the same numbers as Python and MATLAB.
        """
        if values_only:
            return {p: l.value for p, l in sorted(self._leaves.items())}
        return {p: {"v": l.value, "u": l.unit, "s": l.source, "n": l.note}
                for p, l in sorted(self._leaves.items())}

    def __repr__(self) -> str:
        c = self.counts()
        return (f"<Params {len(self._leaves)} parameters from "
                f"{os.path.basename(self._path)}; "
                f"{c.get('PLACEHOLDER', 0)} placeholders>")


# ---------------------------------------------------------------------------
#  Loading
# ---------------------------------------------------------------------------

def project_root() -> str:
    """Project root, resolved from this file rather than from cwd."""
    here = os.path.dirname(os.path.abspath(__file__))    # python/volare
    return os.path.dirname(os.path.dirname(here))        # project root


def params_path() -> str:
    return os.path.join(project_root(), "params", "volare_params.json")


_CACHE: Dict[str, Params] = {}


def load(path: Optional[str] = None, use_cache: bool = True) -> Params:
    """Load the parameter set.

    Cached by path, because every module wants it and re-parsing the JSON
    hundreds of times in a sweep is pure waste. Pass ``use_cache=False``
    after editing the file in a live session.
    """
    p = path or params_path()

    if use_cache and p in _CACHE:
        return _CACHE[p]

    if not os.path.isfile(p):
        raise FileNotFoundError(
            f"Parameter file not found: {p}\n"
            "This is the project's single source of truth and every model "
            "needs it.")

    with open(p, "r", encoding="utf-8") as f:
        raw = json.load(f)

    obj = Params(raw, p)
    _CACHE[p] = obj
    return obj


def load_cell_dataset(path: Optional[str] = None) -> Dict[str, Any]:
    """Load the digitised cell dataset (OCV, R0 map, dU/dT, cycle life).

    Kept separate from the main parameter file because it is bulky, changes
    as a unit, and is produced by a different process (curve tracing).
    """
    if path is None:
        P = load()
        rel = P.get("meta.cell_dataset", "params/cells/p50b.json")
        path = os.path.join(project_root(), *rel.split("/"))

    if not os.path.isfile(path):
        raise FileNotFoundError(f"Cell dataset not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":                                  # pragma: no cover
    P = load()
    print(P.report())
    print()
    print(f"Pack: {P.pack.n_series}S{P.pack.n_parallel}P "
          f"in {P.pack.n_layers} layers")
    print(f"Cooling mode: {P.cooling.mode}")
    print(f"Motor cap: {P.motor.configured_power_limit_W/1000:.0f} kW")
