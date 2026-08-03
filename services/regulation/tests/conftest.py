"""Import paths for the `regulation` suites.

The service package is ``app`` inside the container (``WORKDIR /app``), so tests import it that
way whether they run in the image or from the repo root.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = TESTS_DIR.parent

for path in (SERVICE_ROOT, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def pytest_configure(config) -> None:
    """Register the marker locally too.

    The root ``pytest.ini`` declares it, but the container runs with ``WORKDIR /app`` and only the
    service directory mounted, so a suite run inside the stack would otherwise warn on every file.
    """
    config.addinivalue_line("markers", "integration: requires the Docker Compose stack")
