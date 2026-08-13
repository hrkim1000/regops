"""Create an application user at any role. Idempotent.

Supersedes ``seed_admin.py``, which could only make an ``admin``. That was enough while the only
thing a fresh stack needed was a way to log in, and it stopped being enough once the phase 1.6
evaluation harness started acting as a real ``ra`` principal: ``evaluation.cli run`` looks up
``ra@example.com`` so that ``queries.asked_by`` references a person and the audit trail is not
written by a synthetic id — and nothing in the repo could create that user.

Credentials come from the environment; **there is no default password in this file** and there must
never be one. Run inside the stack::

    REGOPS_SEED_EMAIL=ra@example.com REGOPS_SEED_PASSWORD=... REGOPS_SEED_ROLE=ra \\
        docker compose exec -T platform-core python /scripts/seed_user.py

``REGOPS_ADMIN_EMAIL`` / ``REGOPS_ADMIN_PASSWORD`` are still honoured so the documented bootstrap
command keeps working unchanged; with those the role defaults to ``admin``.

A user that already exists is left **exactly as it is** — this never resets a password. If the
existing row holds a different role than the one asked for, that is reported and the exit code is
non-zero rather than silently accepted: quietly leaving a ``viewer`` where the caller asked for an
``ra`` is how a permission test passes for the wrong reason.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select

from regops_shared.auth import hash_password
from regops_shared.constants import Role
from regops_shared.db import get_sessionmaker
from regops_shared.models import User


def _requested() -> tuple[str, str, Role, str | None] | None:
    """Read the request from the environment, preferring the general vars over the admin ones."""
    email = os.environ.get("REGOPS_SEED_EMAIL") or os.environ.get("REGOPS_ADMIN_EMAIL")
    password = os.environ.get("REGOPS_SEED_PASSWORD") or os.environ.get("REGOPS_ADMIN_PASSWORD")
    if not email or not password:
        print(
            "Set REGOPS_SEED_EMAIL and REGOPS_SEED_PASSWORD (and optionally REGOPS_SEED_ROLE, "
            f"one of {', '.join(role.value for role in Role)}).",
            file=sys.stderr,
        )
        return None

    raw_role = os.environ.get("REGOPS_SEED_ROLE", Role.ADMIN.value).strip().lower()
    try:
        role = Role(raw_role)
    except ValueError:
        print(
            f"REGOPS_SEED_ROLE={raw_role!r} is not a role. "
            f"Valid: {', '.join(item.value for item in Role)}.",
            file=sys.stderr,
        )
        return None

    return email, password, role, os.environ.get("REGOPS_SEED_NAME")


async def main() -> int:
    request = _requested()
    if request is None:
        return 2
    email, password, role, name = request

    async with get_sessionmaker()() as db:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing is not None:
            if existing.role is not role:
                print(
                    f"{email} already exists with role {existing.role.value}, not {role.value}. "
                    f"Left unchanged — change the role through platform-core rather than here, so "
                    f"the change reaches the audit trail.",
                    file=sys.stderr,
                )
                return 1
            print(f"already present: {email} ({existing.role.value})")
            return 0

        db.add(
            User(
                email=email,
                hashed_password=hash_password(password),
                full_name=name or f"Seeded {role.value}",
                role=role,
            )
        )
        await db.commit()
    print(f"created: {email} ({role.value})")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(asyncio.run(main()))
