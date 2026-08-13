"""Reset one user's password. Explicit by design, and the only way to do it.

:mod:`seed_user` deliberately refuses to touch an existing user's password: a seeder that can
rotate a credential as a side effect of being re-run is a hazard. Refusing to do it *implicitly*
is not the same as refusing to do it at all, though, and until this script existed there was no
recovery path for a locked-out account at all — ``platform-core`` exposes login, ``/me``, logout and
an admin *create*, and nothing that changes a password.

Deleting and re-seeding the user is **not** the workaround it looks like. A user id is referenced by
``queries.asked_by``, ``irs.locked_by``, ``alerts.owner_id`` and every ``audit_log`` row that names
them as actor; recreating the account mints a new id and orphans all of it. The whole point of the
audit chain is that a human assertion stays attached to the human who made it.

Run inside the stack — ``users`` is `platform-core`'s table::

    REGOPS_RESET_EMAIL=ra@example.com REGOPS_RESET_PASSWORD=... \\
        docker compose exec -T platform-core python /scripts/reset_password.py

The password comes from the environment and is never defaulted, never printed, and never written to
a file. The row's id, role and history are left exactly as they were — this changes one column.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select

from regops_shared.auth import hash_password
from regops_shared.db import get_sessionmaker
from regops_shared.models import User

#: Short enough to be memorable, long enough that a local dev account is not trivially guessable.
#: Not a policy statement for production — that belongs behind `platform-core` when it grows one.
MIN_PASSWORD_LENGTH = 8


async def main() -> int:
    email = os.environ.get("REGOPS_RESET_EMAIL")
    password = os.environ.get("REGOPS_RESET_PASSWORD")
    if not email or not password:
        print("Set REGOPS_RESET_EMAIL and REGOPS_RESET_PASSWORD", file=sys.stderr)
        return 2
    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"REGOPS_RESET_PASSWORD is shorter than {MIN_PASSWORD_LENGTH} characters",
            file=sys.stderr,
        )
        return 2

    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            # Not created here on purpose: this script's whole contract is that it changes exactly
            # one column of an existing row. Creating a user is `seed_user.py`, where the role is
            # an explicit input rather than something this would have to guess.
            print(f"no such user: {email} — create it with seed_user.py", file=sys.stderr)
            return 1
        user.hashed_password = hash_password(password)
        await db.commit()

    # The email and role, never the password. A terminal scrollback is a file too.
    print(f"password reset: {email} ({user.role.value}); id and history unchanged")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(asyncio.run(main()))
