"""Create the bootstrap admin. Idempotent.

Credentials come from the environment; there is no default password in this file. Run inside the
stack:  ``docker compose exec -T platform-core python /app/../scripts/seed_admin.py``
or locally with DATABASE_URL set.
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


async def main() -> int:
    email = os.environ.get("REGOPS_ADMIN_EMAIL")
    password = os.environ.get("REGOPS_ADMIN_PASSWORD")
    if not email or not password:
        print("Set REGOPS_ADMIN_EMAIL and REGOPS_ADMIN_PASSWORD", file=sys.stderr)
        return 2

    async with get_sessionmaker()() as db:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing is not None:
            print(f"admin already present: {email}")
            return 0
        db.add(
            User(
                email=email,
                hashed_password=hash_password(password),
                full_name="Bootstrap Admin",
                role=Role.ADMIN,
            )
        )
        await db.commit()
    print(f"created admin: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
