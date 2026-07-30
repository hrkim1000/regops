#!/usr/bin/env python3
"""PreToolUse guard (Edit|Write): block writes to secret-bearing env files.

Deterministic guardrail (Layer 3) — not AI judgment. `.env`, `.env.dev`, `.env.test`,
`.env.prod`, … hold real API keys and tokens and are gitignored; the agent must never
edit or overwrite them. `.env.example` (the committed template) stays editable.

Contract: hook input JSON on stdin; exit 2 blocks the tool call and feeds stderr back
to the model; exit 0 allows.
"""

import json
import re
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # malformed input — do not block

    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    name = file_path.replace("\\", "/").rsplit("/", 1)[-1].lower()

    if re.fullmatch(r"\.env(\.[a-z0-9_-]+)?", name) and name != ".env.example":
        sys.stderr.write(
            f"BLOCKED: '{name}' holds real secrets and must not be edited by the agent. "
            "Change '.env.example' instead, or ask the user to update their env file."
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
