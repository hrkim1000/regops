"""Make ``scripts/`` importable so ``evaluation`` resolves the same way here as in the container.

Inside the stack the harness runs with ``-w /scripts``, so ``evaluation`` is a top-level package.
On the host, pytest's rootdir is the repo, and without this the same import fails — which would
mean the suite that guards the scoring math could only run in one of the two places it is used.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = str(Path(__file__).resolve().parent)
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
