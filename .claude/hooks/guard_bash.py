#!/usr/bin/env python3
"""PreToolUse guard (Bash): block a short list of destructive / policy-violating commands.

Deterministic guardrail (Layer 3):
- `git ... --no-verify` / `-c commit.gpgsign=false`  → hooks and signing are never bypassed
- `git push --force` (incl. `-f`) to origin main     → protected branch
- printing secret env files (`cat .env*`)            → secrets never enter the transcript
Exit 2 blocks and feeds stderr to the model; exit 0 allows.
"""

import json
import re
import sys

RULES: list[tuple[str, str]] = [
    (
        r"git\b[^|;&]*--no-verify",
        "BLOCKED: --no-verify skips hooks; fix the underlying failure instead.",
    ),
    (
        r"git\b[^|;&]*push\b[^|;&]*(--force|\s-f\b)[^|;&]*\b(main|master)\b",
        "BLOCKED: force-pushing a protected branch is not allowed.",
    ),
    (
        # Match only a real invocation: command word and the .env path argument on
        # the SAME line ([^|;&\n] — a heredoc body or a later line can't trigger),
        # with the .env token preceded by a separator so prose like "the .env.dev
        # file" inside quoted text still matches but `mytail`/`.envelope` don't.
        r"\b(cat|type|less|more|head|tail)\b[^|;&\n]*[\s='\"/<]\.env(?!\.example\b)(\.[a-z0-9_-]+)?\b",
        "BLOCKED: env files hold real secrets - never print them. Read .env.example instead.",
    ),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = (payload.get("tool_input") or {}).get("command") or ""
    for pattern, message in RULES:
        if re.search(pattern, command, flags=re.IGNORECASE):
            sys.stderr.write(message)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
