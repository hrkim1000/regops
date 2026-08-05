"""Print the local access table with values filled in for *this* machine.

Nothing is stored here. Every value is read from the file that owns it — `docker-compose.yml` for
the infrastructure defaults, the shell or project-root `.env` for overrides, `.env.dev` for the one
real secret — so this cannot drift from reality the way a hand-maintained cheat sheet does.

That is also why the companion page (`docs/local-development.md`) names *sources* rather than
values: it is published to the shared `startup` repository, and a credential written into a
published document cannot be unpublished.

    python scripts/local_access.py

The 국가법령정보 key is reported as set/unset only. It is the single real secret in the stack, and
printing it to a terminal is how it ends up in a scrollback buffer or a screenshot.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The primary dev machine is Windows, where the console codepage is cp949 — printing an em dash or
# any 한글 raises UnicodeEncodeError before a single row appears. Ask for UTF-8 explicitly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: `${VAR:-default}` as written in docker-compose.yml.
INTERPOLATION = re.compile(r"\$\{([A-Z0-9_]+):-([^}]*)\}")

#: A plain `KEY: value` line. Some compose entries are literals rather than interpolations —
#: PGADMIN_DEFAULT_EMAIL among them — and reading only the interpolated form reports them unset.
LITERAL = re.compile(r"^ +([A-Z][A-Z0-9_]+): +([^${}#\r\n]+?) *$", re.MULTILINE)


def compose_defaults() -> dict[str, str]:
    """What compose would use with no shell override — interpolation fallbacks and literals."""
    text = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    values = {name: value.strip("\"'") for name, value in LITERAL.findall(text)}
    # An interpolation default is more specific than a literal, so it wins.
    values.update(dict(INTERPOLATION.findall(text)))
    return values


def dotenv(path: Path) -> dict[str, str]:
    """Parse a `KEY=value` file. Absent is normal — most machines have no project-root `.env`."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def resolve(name: str, defaults: dict[str, str], root_env: dict[str, str]) -> str:
    """Compose interpolation order: shell, then project-root `.env`, then the inline default.

    `.env.dev` is deliberately absent from this chain — it is injected *into* containers via
    `env_file:` and cannot drive `${...}` interpolation. Getting that backwards is what made
    `.env.test` inert until it was fixed.
    """
    return os.environ.get(name) or root_env.get(name) or defaults.get(name, "(unset)")


def app_accounts() -> list[tuple[str, str, str]]:
    """The dev accounts, read from the phase 0 acceptance fixtures that assert them."""
    path = REPO / "services/platform-core/tests/integration/test_phase0_acceptance.py"
    if not path.exists():
        return []
    found = re.findall(
        r'^([A-Z]+) = \("([^"]+)", "([^"]+)"\)',
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return [(role.lower(), email, password) for role, email, password in found]


def build_rows(value: Callable[[str], str]) -> list[tuple[str, str, str, str]]:
    """Surfaces in the order someone actually opens them."""
    return [
        ("frontend", "http://localhost:23000", "(accounts below)", ""),
        (
            "MinIO console",
            "http://localhost:29001",
            value("MINIO_ACCESS_KEY"),
            value("MINIO_SECRET_KEY"),
        ),
        (
            "pgAdmin",
            "http://localhost:25051",
            value("PGADMIN_DEFAULT_EMAIL"),
            value("PGADMIN_PASSWORD"),
        ),
        ("Postgres (owner)", "localhost:25432/regops", "regops", value("POSTGRES_PASSWORD")),
        (
            "Postgres (app)",
            "localhost:25432/regops",
            "regops_app",
            value("REGOPS_APP_DB_PASSWORD"),
        ),
        ("Flower", "http://localhost:25555", "(no auth)", ""),
    ]


def main() -> int:
    defaults = compose_defaults()
    root_env = dotenv(REPO / ".env")
    dev_env = dotenv(REPO / ".env.dev")

    table = build_rows(lambda name: resolve(name, defaults, root_env))
    width = max(len(row[0]) for row in table)

    print("\nRegOps — local access (resolved for this machine)\n")
    for surface, url, user, secret in table:
        credential = f"{user} / {secret}" if secret else user
        print(f"  {surface:<{width}}  {url:<32}  {credential}")

    accounts = app_accounts()
    if accounts:
        print("\n  frontend login — seeded dev accounts:")
        for role, email, password in accounts:
            print(f"    {role:<8} {email:<24} {password}")

    key_set = bool(os.environ.get("LAW_GO_KR_OC") or dev_env.get("LAW_GO_KR_OC", "").strip())
    print(f"\n  LAW_GO_KR_OC (.env.dev): {'set' if key_set else 'NOT SET'} — value not printed")
    print(
        "\n  Local dev defaults only, except LAW_GO_KR_OC. Never reuse them off this machine.\n"
        "  Sources and the change procedure: docs/local-development.md\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
