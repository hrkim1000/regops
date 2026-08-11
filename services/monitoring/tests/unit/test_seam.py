"""The seam, checked statically — phase1.4 acceptance: zero ``regulation`` writes from `monitoring`.

"Enforce in review" is what the phase plan asks for, and a review is a person who might be tired.
This is the same check as a test, and it proves it from both sides:

- **No ORM route in.** `monitoring` imports exactly three models — its own. It cannot write a
  ``regulation`` table through the ORM because it never has one in scope.
- **No SQL route in.** Every ``text()`` statement in the service is a ``SELECT``. A write verb
  anywhere in one fails this test.

Together those close both doors. The database grant in migration 0006 is the third, and the only one
that survives someone deleting this file.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

#: The only models `monitoring` owns (CLAUDE.md § Table ownership; ADR-0009 decision 3).
OWNED_MODELS = frozenset({"Alert", "AlertDelivery", "AlertSubscription"})

#: Import-safe names from the models package that are not tables — helpers and the base metadata.
MODEL_HELPERS = frozenset({"Base", "TimestampMixin", "UUIDPrimaryKey", "utcnow"})

#: Anything that mutates. ``text()`` bodies are matched against these, case-insensitively.
WRITE_VERBS = ("insert", "update", "delete", "truncate", "drop", "alter", "create", "grant")


def _modules() -> list[Path]:
    files = sorted(APP_ROOT.rglob("*.py"))
    assert files, f"no service modules found under {APP_ROOT}"
    return files


def test_monitoring_imports_no_other_services_orm_model() -> None:
    """Reads across a boundary are raw SQL; never another service's ORM model (CLAUDE.md)."""
    offenders: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith("regops_shared.models"):
                continue
            for alias in node.names:
                if alias.name in OWNED_MODELS or alias.name in MODEL_HELPERS:
                    continue
                offenders.append(f"{path.name}: {alias.name}")

    assert not offenders, f"monitoring imported models it does not own: {offenders}"


def test_every_raw_statement_in_monitoring_is_a_read() -> None:
    """The seam is one-way. A write verb in any ``text()`` body fails here, before review."""
    offenders: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
            if name != "text" or not node.args:
                continue
            argument = node.args[0]
            if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                # A statement built at runtime cannot be checked here. None exists, and one that
                # appeared would be worth failing on rather than skipping.
                offenders.append(f"{path.name}: non-literal statement")
                continue
            body = argument.value.lower()
            found = [verb for verb in WRITE_VERBS if verb in body]
            if found:
                offenders.append(f"{path.name}: {found} in {argument.value.strip()[:60]!r}")

    assert not offenders, f"monitoring raw SQL is not read-only: {offenders}"


def test_the_seam_lives_in_one_module() -> None:
    """Every cross-boundary read is in ``store.py``, so the boundary is one file to audit.

    A ``text()`` call anywhere else in the service is not necessarily wrong — but it is a read
    nobody would find when checking the seam, which is the same thing a year later.
    """
    elsewhere: list[str] = []
    for path in _modules():
        if path.name == "store.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                callee = node.func
                name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
                if name == "text" and node.args:
                    elsewhere.append(path.name)

    assert not elsewhere, f"raw SQL outside the seam module: {sorted(set(elsewhere))}"
