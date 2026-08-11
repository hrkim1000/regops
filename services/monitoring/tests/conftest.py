"""Import paths for the `monitoring` suites.

The service package is ``app`` inside the container (``WORKDIR /app``), so tests import it that way
whether they run in the image or from the repo root.

**Every service's package is called ``app``.** A host-side run of the documented gate

    python -m pytest shared/tests services/*/tests/unit -q

imports whichever service the shell globbed first and caches it in ``sys.modules``; every later
``from app.grade import ...`` then resolves against that package and fails. pytest loads a
directory's ``conftest.py`` before collecting the files in it, so evicting the stale package here is
early enough — and it is the *service root* that decides, not the glob order.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = TESTS_DIR.parent


def _claim_app_package() -> None:
    """Make ``import app`` mean *this* service's app, whatever ran before it."""
    cached = sys.modules.get("app")
    location = getattr(cached, "__file__", None) if cached is not None else None
    if location is not None and SERVICE_ROOT not in Path(location).resolve().parents:
        for name in [key for key in sys.modules if key == "app" or key.startswith("app.")]:
            del sys.modules[name]

    for path in (str(TESTS_DIR), str(SERVICE_ROOT)):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


_claim_app_package()


def pytest_collectstart(collector) -> None:
    """Re-claim before each collection step, since another service's suite may have run between."""
    _claim_app_package()


def pytest_configure(config) -> None:
    """Register the marker locally too.

    The root ``pytest.ini`` declares it, but the container runs with ``WORKDIR /app`` and only the
    service directory mounted, so a suite run inside the stack would otherwise warn on every file.
    """
    config.addinivalue_line("markers", "integration: requires the Docker Compose stack")
