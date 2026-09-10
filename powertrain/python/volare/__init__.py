r"""
volare
======

Coupled electro-thermal pack model, boat dynamics and race simulation for the
Monaco Energy Class P50B 26S21P.

TWO WAYS TO USE THIS, BOTH SUPPORTED
------------------------------------
The modules in this package were originally written to be run directly from
inside the package directory::

    cd python/volare
    python studies.py

and they import each other flatly (``import pack_thermal as pt``). That
workflow still works and is not disturbed.

They are now *also* importable as a package from the project root::

    from volare.layout3d import from_params
    from volare.params import load

Flat imports would normally break in that mode, because ``pack_thermal`` is
not a top-level module. The line below puts this directory on ``sys.path`` at
import time, so both spellings resolve to the same modules.

That is a small amount of path manipulation in exchange for not rewriting the
import statements in seventeen thousand lines of working, validated code --
and for not forcing the team to change how they already run it.

WHERE THE NUMBERS COME FROM
---------------------------
Nothing in this package should hard-code a physical parameter. Everything
comes from ``params/volare_params.json`` via :mod:`volare.params`, which
MATLAB and the Mission Control browser engine also read.

    from volare.params import load
    P = load()
    P.cell.capacity_Ah        # 5.0
    P.cooling.n_circuits      # 3

KEY MODULES
-----------
    params        the single source of truth, and its provenance audit
    layout3d      two-layer pack with end-plate cooling  (current design)
    pack_thermal  the coupled electro-thermal solver
    simulator     stepper, digital-twin observer, race animation
    boat          hull resistance, propeller, boat dynamics
    celldata      import and fit real cell characterisation
    webexport     export the model for the browser engine
    studies       the six design investigations
"""

from __future__ import annotations

import os as _os
import sys as _sys

# Make the flat intra-package imports resolve when this is imported as a
# package rather than run from inside the directory.
_HERE = _os.path.dirname(_os.path.abspath(__file__))

if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)


def project_root() -> str:
    """Absolute path to the project root, resolved from this file."""
    return _os.path.dirname(_os.path.dirname(_HERE))


__all__ = ["project_root"]
