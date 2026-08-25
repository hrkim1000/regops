"""The domain branch: a rule set, not a code path (ADR-0004 decision 3).

``domain_profile`` selects a modal inventory, an obligation taxonomy and a prompt — and nothing
else. Same tables, same stages, same lifecycle, same storage. Everything in this module is data
about *what counts as an obligation*; nothing here branches on domain in control flow, and the
falsification criterion in ADR-0004 decision 3 is that it must stay that way.

Two things are deterministic and deliberately kept out of the LLM's hands:

- **Modal detection.** The inventory is closed (decision 1), so "does this clause contain an
  obligation modal" is a regex question, not a judgement. That is what makes the atomicity rule
  operative rather than advisory: a clause with no inventory modal yields no IR *by definition*, and
  the model is never asked to decide otherwise.
- **Structural exclusion.** A heading, a blank 서식, a table container, an empty stub — these are
  classified from the clause's own ``kind`` and text. Spending an LLM call to be told that 제2장 is
  a heading buys nothing and adds a way to be wrong.

The recall cost is real and is 1.6's to measure: an obligation phrased outside the inventory is
invisible here. That is a *stated* limit of the rule rather than a silent gap — the clause is still
classified ``excluded`` with a reason, so it shows up in coverage as examined-and-empty and the
ground-truth markup can contradict it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from regops_shared.constants import (
    IR_PROMPT_VERSION,
    IR_RULE_VERSION,
    MODAL_INVENTORY,
    PERMISSIVE_MODALS,
    TAXONOMY_CODES,
    ClassificationKind,
    ClauseKind,
    Domain,
    ExclusionReason,
)

#: Canonical modal → the pattern that recognises it *and its conjunctive forms*.
#:
#: The conjugations matter for atomicity. ADR-0004 decision 1's worked example —
#: "A 하여야 하며, B 하여야 한다" → **2 IRs** — only yields two if ``하여야 하며`` is recognised as
#: an obligation modal. Matching the citation form alone would see one obligation and a fragment,
#: which is precisely the compound-vs-conjunction error the rule exists to settle.
#:
#: The dict *value* is detection; the dict *key* is what gets stored on the IR, so an IR's ``modal``
#: is always one of the closed inventory values however the clause conjugated it.
_KO_MODAL_PATTERNS: Final[dict[str, str]] = {
    "하여야 한다": r"하여야\s*(?:한다|하며|하고|하는|할|함)",
    "해야 한다": r"해야\s*(?:한다|하며|하고|하는|할|함)",
    "도록 한다": r"도록\s*(?:한다|하며|하고|하여야)",
    "금지한다": r"금지(?:한다|하며|된다|되며)",
    # 하여서는 아니 된다 / 아니된다 — prohibition. Spacing is inconsistent across MFDS 고시.
    "아니 된다": r"아니\s*(?:된다|되며|하다)",
}

#: ``may not`` is an obligation (a prohibition) and must not be swallowed by the permissive ``may``.
#: The permissive pattern below carries the negative lookahead that keeps them apart.
_EN_MODAL_PATTERNS: Final[dict[str, str]] = {
    "shall": r"\bshall\b(?!\s+not\s+be\s+construed)",
    "must": r"\bmust\b",
    "is required to": r"\b(?:is|are)\s+required\s+to\b",
    "may not": r"\bmay\s+not\b",
}

_MODAL_PATTERNS: Final[dict[str, dict[str, str]]] = {
    "ko": _KO_MODAL_PATTERNS,
    "en": _EN_MODAL_PATTERNS,
}

_PERMISSIVE_PATTERNS: Final[dict[str, str]] = {
    "ko": r"할\s*수\s*있다|수\s*있다",
    "en": r"\bmay\b(?!\s+not)|\bcan\b|\bis\s+permitted\s+to\b",
}

#: Headings that mark a clause as definitional or scope-setting whatever its body says. Matched
#: against the clause heading, and against the parenthetical title 조문내용 embeds — "제2조(정의)".
_DEFINITION_HEADINGS: Final[tuple[str, ...]] = ("정의", "용어", "definitions")
_SCOPE_HEADINGS: Final[tuple[str, ...]] = ("목적", "적용범위", "적용 범위", "purpose", "scope")

#: "…는 총리령으로 정한다" — the clause defers the duty to another instrument rather than stating
#: one. Extracting an IR here would assert an obligation whose content lives somewhere else.
#: **Korean-only, and deliberately so — the CFR has no counterpart.** Searched across the whole FDA
#: corpus on 2026-08-25: "by regulation prescribe", "as the Commissioner prescribes" and "under
#: procedures in part" return **zero** matches. That is structural rather than accidental: 법령
#: delegates downward to 시행령/시행규칙/고시, while a CFR Part *is* the subordinate instrument and
#: has nothing beneath it to defer to.
#:
#: What the corpus does contain is **cross-references** — "in accordance with part 807" (39) and
#: "as specified in § ..." (7). Those are not delegations: a cross-reference says where the detail
#: lives, a delegation says someone else will decide the duty. Admitting them here would exclude 46
#: clauses that do state obligations, which is why this pattern stays Korean.
_DELEGATION: Final[re.Pattern[str]] = re.compile(
    r"(?:대통령령|총리령|부령|고시|정관)(?:으)?로\s*정(?:한다|하는)"
)

#: 부칙 is transitional machinery — 시행일, 경과조치, 적용례. Real obligations do live there, but
#: they attach to an operative clause; ADR-0004 decision 1's second row ("conditions span 조 + 부칙
#: → 1 IR citing both") is that case, handled by citing 부칙 from the operative clause's IR rather
#: than by extracting an IR out of 부칙 on its own.
#: **Also Korean-only, and again structural.** A CFR Part carries no transitional segment: effective
#: dates, compliance dates and grandfathering live in the *Federal Register rule*, which is not
#: codified and which this pipeline models as an announcement rather than as text (ADR-0019).
#: Measured 2026-08-25 — "transitional provision/period/rule" and "compliance date" return zero
#: across the FDA corpus, and a leading "Effective date" appears once, as substantive text in
#: 21 CFR 700.25(e) rather than as a segment. **"No equivalent" is the answer**, recorded here so a
#: later reader does not read the absence as an oversight.
_TRANSITIONAL_SEGMENTS: Final[tuple[str, ...]] = ("부칙",)

#: Below this, a clause has no room for "one bearer + one modal + one required action".
_MIN_SUBSTANTIVE_CHARS: Final[int] = 10


@dataclass(frozen=True, slots=True)
class RuleSet:
    """Everything the domain branch contains. Data, not behaviour."""

    domain: Domain
    language: str
    modals: tuple[str, ...]
    permissive: tuple[str, ...]
    taxonomy: tuple[str, ...]
    rule_version: str = IR_RULE_VERSION
    prompt_version: str = IR_PROMPT_VERSION

    def canonical_modal(self, raw: str | None) -> str | None:
        """Map whatever the model reported back onto the closed inventory.

        Returns ``None`` for anything outside it, which the caller treats as a rejected proposal —
        "one modal" is only a rule if the set of modals is enumerable.
        """
        if not raw:
            return None
        candidate = raw.strip()
        for modal in self.modals:
            if candidate == modal:
                return modal
        # The model often echoes the conjugated form it found in the text. Accept that, but store
        # the citation form.
        for modal, pattern in _MODAL_PATTERNS[self.language].items():
            if modal in self.modals and re.search(pattern, candidate):
                return modal
        return None

    def canonical_taxonomy(self, raw: str | None) -> str | None:
        """Taxonomy code, or ``None`` if the model invented one. Never stored unvalidated."""
        if not raw:
            return None
        candidate = raw.strip().lower().replace("-", "_").replace(" ", "_")
        return candidate if candidate in self.taxonomy else None


def rule_set_for(domain: Domain, language: str) -> RuleSet:
    """The rule set for one ``(domain, language)``.

    Raises on an unknown language rather than falling back to Korean: silently extracting an English
    document with a Korean modal inventory would find nothing and report full coverage.
    """
    if language not in MODAL_INVENTORY:
        raise ValueError(
            f"No modal inventory for language {language!r}; "
            f"ADR-0004 decision 1 fixes it per language and {sorted(MODAL_INVENTORY)} are defined"
        )
    return RuleSet(
        domain=domain,
        language=language,
        modals=MODAL_INVENTORY[language],
        permissive=PERMISSIVE_MODALS[language],
        taxonomy=TAXONOMY_CODES[domain],
    )


def found_modals(text: str, rules: RuleSet) -> tuple[str, ...]:
    """Which inventory modals appear in ``text``, in inventory order.

    Order is the inventory's, not the text's, so the result is stable for the same clause — an input
    to the determinism claim in ADR-0017 decision 1.
    """
    patterns = _MODAL_PATTERNS[rules.language]
    return tuple(
        modal for modal in rules.modals if modal in patterns and re.search(patterns[modal], text)
    )


def has_permissive(text: str, rules: RuleSet) -> bool:
    """Whether a permissive form appears. Permissive alone yields no IR (ADR-0004 decision 1)."""
    return re.search(_PERMISSIVE_PATTERNS[rules.language], text) is not None


@dataclass(frozen=True, slots=True)
class Triage:
    """The deterministic verdict on one clause, before any LLM is involved."""

    kind: ClassificationKind
    reason: ExclusionReason | None = None
    note: str | None = None
    modals: tuple[str, ...] = ()

    @property
    def needs_agent(self) -> bool:
        return self.kind is ClassificationKind.OBLIGATION_BEARING


def triage(
    *,
    clause_kind: ClauseKind,
    clause_path: str,
    path_segments: list[str] | tuple[str, ...],
    heading: str | None,
    text: str,
    rules: RuleSet,
) -> Triage:
    """Classify a clause without an LLM, and say whether the agent should see it.

    **Every clause gets a verdict** — there is no "skip" (ADR-0004 decision 6). A clause the agent
    never sees is still on the record as examined, with the reason it was set aside, so coverage is
    provable rather than assumed.

    Order matters: structure first (a heading is a heading whatever words it contains), then the
    clause's own role (definition, scope, delegation, transitional), then the modal test. Testing
    modals first would classify "제2조(정의) … 하여야 한다" as obligation-bearing on the strength of
    a modal inside a definition of a term.
    """
    body = (text or "").strip()

    if clause_kind is ClauseKind.HEADING:
        return Triage(ClassificationKind.EXCLUDED, ExclusionReason.HEADING)
    if clause_kind is ClauseKind.FORM:
        return Triage(ClassificationKind.EXCLUDED, ExclusionReason.FORM)
    if clause_kind is ClauseKind.TABLE:
        # The container carries the column map; its rows carry the obligations (ADR-0014).
        return Triage(ClassificationKind.EXCLUDED, ExclusionReason.TABLE_CONTAINER)
    if len(body) < _MIN_SUBSTANTIVE_CHARS:
        return Triage(ClassificationKind.EXCLUDED, ExclusionReason.EMPTY)

    if any(segment in _TRANSITIONAL_SEGMENTS for segment in path_segments):
        return Triage(
            ClassificationKind.EXCLUDED,
            ExclusionReason.PROCEDURAL,
            note=f"{clause_path} is transitional; conditions here are cited from the operative IR",
        )

    title = _title(heading, body)
    if _matches(title, _DEFINITION_HEADINGS):
        return Triage(ClassificationKind.EXCLUDED, ExclusionReason.DEFINITION, note=title)
    if _matches(title, _SCOPE_HEADINGS):
        return Triage(ClassificationKind.EXCLUDED, ExclusionReason.SCOPE, note=title)

    modals = found_modals(body, rules)
    if modals:
        return Triage(ClassificationKind.OBLIGATION_BEARING, modals=modals)

    if _DELEGATION.search(body):
        return Triage(ClassificationKind.EXCLUDED, ExclusionReason.DELEGATION)
    if has_permissive(body, rules):
        return Triage(ClassificationKind.EXCLUDED, ExclusionReason.PERMISSIVE)
    return Triage(ClassificationKind.EXCLUDED, ExclusionReason.NO_OBLIGATION)


def _title(heading: str | None, body: str) -> str:
    """The clause's title: its ``heading`` column, else the parenthetical 조문내용 embeds.

    법령 본문조회 gives ``heading`` separately; 고시 bodies do not, and their article text opens
    "제2조(정의) …". Both spellings have to be readable or every 고시 definition clause would be
    sent to the agent.
    """
    if heading:
        return heading.strip()
    match = re.match(r"^\s*제\d+조(?:의\d+)?\s*\(([^)]{1,60})\)", body)
    return match.group(1).strip() if match else ""


def _matches(title: str, needles: tuple[str, ...]) -> bool:
    """Does the title announce one of these roles?

    **Word boundaries where the script has them, substring where it does not.** ``scope`` is a
    substring of ``endoscope`` and ``purpose`` of ``repurpose``, so a plain containment test can
    exclude an obligation-bearing clause as *scope* — and a clause wrongly excluded never reaches
    the agent while coverage still reports it as examined, which is the quietest way to lose an
    obligation. Korean needles take the substring path unchanged: ``\b`` is defined against ASCII
    word characters and matches nothing useful in Hangul, so applying it there would stop the
    Korean headings matching at all.

    No English heading in the FDA corpus trips this today — measured 2026-08-25, zero substring
    false positives across 2,039 clauses. It is guarded because the corpus grows, not because it
    is currently wrong.
    """
    if not title:
        return False
    lowered = title.lower()
    for needle in needles:
        if needle.isascii():
            if re.search(rf"\b{re.escape(needle)}\b", lowered):
                return True
        elif needle in lowered:
            return True
    return False


__all__ = [
    "RuleSet",
    "Triage",
    "found_modals",
    "has_permissive",
    "rule_set_for",
    "triage",
]
