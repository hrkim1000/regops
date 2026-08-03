"""Tier D guard — fail CI if copyright-protected standard text enters the repository.

Tier D source text is never ingested (CLAUDE.md § Architecture rules). A developer saving an
ISO/IEC PDF into the archive is an execution failure, not just a policy one (development-plan.md
§ 9, risk 5), so this runs as a gate rather than a review checklist item.

What it catches: standard *body text* committed as a fixture or asset. What it deliberately does
not catch: standard *identifiers* in prose — citing "ISO 13485" is required behaviour, and
StandardReference exists precisely to hold that metadata.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Binary/document extensions that could carry standard text.
SUSPECT_SUFFIXES = {".pdf", ".doc", ".docx", ".hwp", ".hwpx", ".epub"}

#: Paths where a standards document would be a Tier D breach.
GUARDED_DIRS = ("fixtures", "archive", "assets", "data/standards", "tests")

STANDARD_ID = re.compile(
    r"\b(?:ISO(?:/IEC)?|IEC|USP-NF|Ph\.?\s?Eur\.?)[\s\-]?\d{3,5}(?:[-:]\d+)*\b", re.IGNORECASE
)

#: Phrases that appear in the front matter of an actual standard, not in a citation of one.
BODY_TEXT_MARKERS = (
    "all rights reserved. unless otherwise specified",
    "no part of this publication may be reproduced",
    "iso copyright office",
    "iec central office",
    "permission can be requested from either iso",
)


def scanned_files() -> list[Path]:
    """Tracked files **plus** untracked-but-not-ignored ones.

    Scanning only tracked files means a newly added file passes until it is committed — which is
    how this script once passed locally and failed in CI on the very next push. A guard that only
    sees history cannot stop something entering it.
    """
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO / line for line in dict.fromkeys(out.stdout.splitlines()) if line]


#: This file necessarily contains every marker it searches for, so it would always flag itself.
#: Excluded by path rather than by obfuscating the markers — the list should stay greppable.
SELF = Path(__file__).resolve().relative_to(REPO).as_posix()


def main() -> int:
    violations: list[str] = []

    for path in scanned_files():
        rel = path.relative_to(REPO).as_posix()
        if rel == SELF:
            continue
        if rel.startswith("docs/"):
            continue  # prose cites standards by design

        if path.suffix.lower() in SUSPECT_SUFFIXES and any(g in rel for g in GUARDED_DIRS):
            violations.append(f"{rel}: document in a guarded path — Tier D risk")
            continue

        if not path.is_file() or path.suffix.lower() in SUSPECT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue

        for marker in BODY_TEXT_MARKERS:
            if marker in text:
                violations.append(f"{rel}: contains standard front-matter text ({marker!r})")
                break

    if violations:
        print("Tier D violations — standard body text must never be stored:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nStore only the recognition record (number, edition, dates, status) and deep-link "
            "the official copy.",
            file=sys.stderr,
        )
        return 1

    print(f"Tier D scan clean ({len(scanned_files())} files scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
