"""The extraction prompt. Versioned, because a reworded prompt produces incomparable IRs.

``IR_PROMPT_VERSION`` is stamped on every row this produces and on the run. Change the text here and
bump it in the same commit — a golden-set score is only meaningful per ``(rule_version,
prompt_version, llm_model)`` triple, and an unversioned prompt change silently invalidates every
earlier score without anything failing.

The prompt states the atomicity rule as rules the model applies, not as a description of what an IR
is. ADR-0004 decision 1 exists because "one atomic regulatory obligation" is unusable as an
instruction; restating it here would reproduce the ambiguity the ADR was written to remove.
"""

from __future__ import annotations

import json
from typing import Any

from .rules import RuleSet

#: The taxonomy is domain-specific and so is the shape of a typical obligation, which is the whole
#: content of the branch (ADR-0004 decision 3). Everything else in the prompt is domain-neutral.
_DOMAIN_GUIDANCE: dict[str, str] = {
    "samd": (
        "These are medical-device / software obligations. Duties are typically process and "
        "lifecycle duties: documentation, design control, risk management, verification and "
        "validation, change control, and post-market surveillance."
    ),
    "cosmetic": (
        "These are cosmetic-product obligations. Duties are typically substance and communication "
        "duties: ingredient limits and prohibitions, concentration ceilings, labelling content, "
        "claim restrictions, manufacturing practice, and notification/reporting."
    ),
}

SYSTEM_PROMPT = """\
You are a regulatory analyst extracting atomic obligations from the text of a regulation.

You do not summarise, interpret, or advise. You restate what the clause requires, in the clause's
own terms, and you attach the clause it came from. If the clause states no obligation, you return an
empty list — that is a correct and common answer.

Reply with JSON only. No prose before or after, no markdown fence.\
"""


def build_prompt(
    *,
    rules: RuleSet,
    clause_path: str,
    heading: str | None,
    text: str,
    detected_modals: tuple[str, ...],
    context: str | None = None,
) -> str:
    """The user message for one clause.

    ``detected_modals`` is passed in rather than left to the model. The inventory is closed and
    matching it is a regex question (see :mod:`.rules`), so telling the model what was found keeps
    it restating obligations instead of re-deciding which words are obligations — and keeps the IR
    count reproducible at temperature 0.
    """
    payload: dict[str, Any] = {
        "clause_path": clause_path,
        "heading": heading or "",
        "text": text,
    }
    if context:
        payload["surrounding_context"] = context

    return f"""\
{_DOMAIN_GUIDANCE[rules.domain.value]}

## Atomicity rules — apply these exactly

1. One IR = **one bearer + one modal + one required action**.
2. Conditions are *attached* to the IR, never split into their own IR. Put them in `condition_text`.
3. A clause containing three obligations yields **three** IRs, each citing that clause.
4. "A 하여야 하며, B 하여야 한다" is a **conjunction of two obligations** — 2 IRs, not 1 compound.
5. Permissive forms ({", ".join(rules.permissive)}) are **not** obligations and yield no IR. If a
   permissive form qualifies an obligation you are already extracting, put it in `condition_text`.
6. Definitions, scope statements, headings and delegations ("…으로 정한다") yield no IR.
7. An obligation that applies only to certain product classes or categories stays **one** IR; the
   restriction goes in `condition_text`. Do not emit one IR per class.

## Modals

The obligation modals found in this clause are: {", ".join(detected_modals) or "(none)"}.
Report the one each IR rests on in `modal`, using exactly one of: {", ".join(rules.modals)}.

## Taxonomy

Classify each IR with one of: {", ".join(rules.taxonomy)}. If none fits, use null.

## Citation

`cites` is a list of clause paths this obligation rests on. **Always include the clause under
examination.** Add another path only when the obligation genuinely cannot be stated without it — for
example a condition that lives in a different article. Never invent a path.

## Clause

{json.dumps(payload, ensure_ascii=False, indent=2)}

## Output

A JSON array. Each element:

{{"bearer": "who must act", "modal": "one of the modals above",
  "statement": "what they must do, in the clause's own terms",
  "condition_text": "when it applies, or null",
  "taxonomy_code": "one of the taxonomy codes, or null",
  "cites": ["{clause_path}"]}}

Return `[]` if the clause states no obligation.\
"""


__all__ = ["SYSTEM_PROMPT", "build_prompt"]
