"""Seed the `regulation` source registry from the catalog projection. Idempotent.

Run inside the stack:
    docker compose exec -T regulation python /scripts/seed_sources.py
or locally with DATABASE_URL set.

The rows come from ``services/regulation/app/seed.py``, which projects
``docs/import-source-map.md``. Re-run it after the map changes; existing rows are updated in place
and a schedule that an operator disabled stays disabled.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: The service package is ``app`` at ``/app`` in the container and at
#: ``services/regulation`` in a checkout. Try both rather than assuming one layout.
_CANDIDATES = (
    Path("/app"),
    Path(__file__).resolve().parents[1] / "services" / "regulation",
)
for candidate in _CANDIDATES:
    if (candidate / "app" / "seed.py").exists():
        sys.path.insert(0, str(candidate))
        break

from app.seed import seed_sources  # noqa: E402
from regops_shared.db import sync_session  # noqa: E402


def main() -> int:
    with sync_session() as session:
        result = seed_sources(session)
    print(
        f"sources seeded: {result['created']} created, "
        f"{result['updated']} updated, {result['retired']} retired"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
