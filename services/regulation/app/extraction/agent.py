"""The Requirement Extraction agent — RegOps' first LLM unit.

It earns the name under all three of ADR-0008's tests: it invokes an LLM, it writes rows carrying
provenance, and its output cannot be trusted without a separate check (here, an ``ra`` locking the
draft). A module named ``*_agent`` that never calls :func:`get_llm_client` is a defect; this one
calls it and records what answered.

What this module does **not** do is decide what an obligation is. The modal inventory is closed and
matched deterministically in :mod:`.rules`; the model's job is to restate the duties in a clause
whose modals have already been found, and every field it returns is validated back against the rule
set before it can reach a row:

- ``modal`` outside the inventory → the proposal is dropped
- ``taxonomy_code`` outside the domain taxonomy → nulled, not stored as invented
- ``cites`` that resolves to no clause in this version → the proposal is **rejected**, and the
  rejection is counted on the run (ADR-0004 decision 2)

Sampling is pinned to :data:`EXTRACTION_TEMPERATURE` (ADR-0017 decision 1). Determinism is treated
as a regression target rather than a guarantee — the same clause at the same
``(rule_version, prompt_version, llm_model)`` should yield the same IRs, and a delta is a bug to
investigate, not variance to accept.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

import structlog

from regops_shared.constants import EXTRACTION_TEMPERATURE
from regops_shared.llm import Completion, LLMClient

from .prompt import SYSTEM_PROMPT, build_prompt
from .rules import RuleSet

log = structlog.get_logger(__name__)

#: A chatty model wraps JSON in a fence or a sentence. Pull the outermost array rather than failing:
#: the alternative is discarding a correct extraction over formatting, which shows up as a recall
#: loss that no amount of prompt work explains.
_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)

#: Guard against a model that repeats itself forever. Real clauses top out well below this; the
#: densest article in the gated corpus carries a single-digit number of obligations.
MAX_PROPOSALS_PER_CLAUSE = 20


@dataclass(slots=True)
class Proposal:
    """One obligation the model proposed, after validation. Not yet a row."""

    bearer: str | None
    modal: str
    statement: str
    condition_text: str | None
    taxonomy_code: str | None
    #: Clause paths the model named. Resolved against the version by the orchestrator; a proposal
    #: whose paths all fail to resolve never becomes an IR.
    cites: tuple[str, ...]


@dataclass(slots=True)
class AgentResult:
    """What one clause's extraction produced, and what was thrown away doing it."""

    proposals: list[Proposal] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    #: Proposals discarded before reaching the orchestrator, with why. Logged rather than stored:
    #: a malformed proposal has no citation and so, by decision 2, has nowhere to live.
    discarded: list[str] = field(default_factory=list)
    #: The agent answered, but with nothing parseable. Distinct from "answered with an empty list",
    #: which is a legitimate and common verdict.
    unparseable: bool = False


def extract_clause(
    client: LLMClient,
    *,
    rules: RuleSet,
    clause_path: str,
    heading: str | None,
    text: str,
    detected_modals: tuple[str, ...],
    context: str | None = None,
) -> AgentResult:
    """Propose IRs for one clause. Synchronous, because Celery workers are.

    ``asyncio.run`` per call rather than one long-lived loop: a prefork worker has no event loop of
    its own, and the shared ``db`` module already draws the same line for the same reason. The HTTP
    client is created and torn down inside the call, so nothing is cached across loops.
    """
    prompt = build_prompt(
        rules=rules,
        clause_path=clause_path,
        heading=heading,
        text=text,
        detected_modals=detected_modals,
        context=context,
    )
    completion = asyncio.run(
        client.complete(prompt, system=SYSTEM_PROMPT, temperature=EXTRACTION_TEMPERATURE)
    )
    return parse_completion(completion, rules=rules, clause_path=clause_path)


def parse_completion(completion: Completion, *, rules: RuleSet, clause_path: str) -> AgentResult:
    """Validate a raw completion into proposals. Split out so it is testable without a model."""
    result = AgentResult(provider=completion.provider, model=completion.model)

    raw = _decode(completion.text)
    if raw is None:
        result.unparseable = True
        log.warning("extract.unparseable", clause_path=clause_path, model=completion.model)
        return result

    for index, item in enumerate(raw[:MAX_PROPOSALS_PER_CLAUSE]):
        proposal, reason = _validate(item, rules=rules)
        if proposal is None:
            result.discarded.append(f"[{index}] {reason}")
            continue
        result.proposals.append(proposal)

    if len(raw) > MAX_PROPOSALS_PER_CLAUSE:
        result.discarded.append(f"truncated at {MAX_PROPOSALS_PER_CLAUSE} of {len(raw)} proposals")
        log.warning(
            "extract.truncated",
            clause_path=clause_path,
            proposed=len(raw),
            kept=MAX_PROPOSALS_PER_CLAUSE,
        )
    return result


def _decode(text: str) -> list[dict] | None:
    """The outermost JSON array, or ``None``. An object is accepted as a one-element array."""
    stripped = (text or "").strip()
    if not stripped:
        return None

    for candidate in _candidates(stripped):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            # Some models answer a single obligation as a bare object, and some wrap the list in
            # {"irs": [...]}. Both are the model being helpful, not the extraction being wrong.
            for key in ("irs", "obligations", "results"):
                inner = parsed.get(key)
                if isinstance(inner, list):
                    return [item for item in inner if isinstance(item, dict)]
            return [parsed]
    return None


def _candidates(text: str) -> list[str]:
    """The whole reply first, then the first bracketed span inside it."""
    out = [text]
    match = _JSON_ARRAY.search(text)
    if match:
        out.append(match.group(0))
    return out


def _validate(item: dict, *, rules: RuleSet) -> tuple[Proposal | None, str]:
    """One proposal, or ``(None, reason)``. Every field is checked against the rule set."""
    statement = _text(item.get("statement"))
    if not statement:
        return None, "no statement"

    modal = rules.canonical_modal(_text(item.get("modal")))
    if modal is None:
        # "One bearer + one modal + one required action" is only a rule while the modal set is
        # closed. A modal outside the inventory means the model found something the rule does not
        # cover — that is a rule question for an RA, not a row to write.
        return None, f"modal outside the inventory: {item.get('modal')!r}"

    condition_text = _text(item.get("condition_text")) or None

    # The prompt asks for the clause's language; this is what makes the answer checkable. An IR is
    # read side by side with the clause it cites, and that only works while the two are in the same
    # language — otherwise the reviewer must translate before they can verify, which is the work
    # citation enforcement exists to spare them. The row would contradict itself besides: `modal` is
    # normalised against this language's closed inventory. Observed 2026-08-27: three of 133 IRs on
    # 의료기기법 carried an English `statement` beside `하여야 한다`.
    #
    # Rejected rather than flagged, exactly as a modal outside the inventory is. The recall cost is
    # real and is 1.6's to measure — the reason lands in `discarded`, which is logged and marks the
    # clause for review, so it is a stated limit rather than a silent gap.
    for field_name, value in (("statement", statement), ("condition_text", condition_text)):
        if value and not rules.written_in_language(value):
            return None, f"{field_name} is not written in {rules.language}: {value[:60]!r}"

    cites = tuple(path for path in (_text(value) for value in _as_list(item.get("cites"))) if path)
    if not cites:
        return None, "no cites"

    return (
        Proposal(
            bearer=_text(item.get("bearer")) or None,
            modal=modal,
            statement=statement,
            condition_text=condition_text,
            taxonomy_code=rules.canonical_taxonomy(_text(item.get("taxonomy_code"))),
            cites=cites,
        ),
        "",
    )


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return [value] if value is not None else []


def _text(value: object) -> str:
    """Coerce to trimmed text, mapping JSON ``null`` and the string "null" to empty."""
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"null", "none", "n/a"} else text


__all__ = [
    "MAX_PROPOSALS_PER_CLAUSE",
    "AgentResult",
    "Proposal",
    "extract_clause",
    "parse_completion",
]
