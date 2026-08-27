"""The agent's validation boundary — everything a model returns, checked before it can reach a row.

Unit tests never call a real LLM (`.claude/skills/testing`). :func:`parse_completion` takes a
``Completion`` directly, so the whole validation path is exercised against recorded model output
including the shapes real models actually produce: fenced JSON, a bare object, an ``{"irs": [...]}``
wrapper, and prose wrapped around an array.
"""

from __future__ import annotations

import json

import pytest

from app.extraction.agent import MAX_PROPOSALS_PER_CLAUSE, parse_completion
from app.extraction.prompt import build_prompt
from app.extraction.rules import rule_set_for
from regops_shared.constants import Domain
from regops_shared.llm import Completion

SAMD = rule_set_for(Domain.SAMD, "ko")
COSMETIC = rule_set_for(Domain.COSMETIC, "ko")

PATH = "제5조"


def _completion(payload: object | str) -> Completion:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return Completion(text=text, provider="ollama", model="test-model")


def _proposal(**overrides) -> dict:
    base = {
        "bearer": "제조업자",
        "modal": "하여야 한다",
        "statement": "기록을 3년간 보관",
        "condition_text": None,
        "taxonomy_code": "design_control",
        "cites": [PATH],
    }
    return base | overrides


def _parse(payload, rules=SAMD):
    return parse_completion(_completion(payload), rules=rules, clause_path=PATH)


# --- one clause, three obligations -------------------------------------------------------------


def test_three_obligations_in_one_clause_yield_three_proposals() -> None:
    """ADR-0004 decision 1, first row of the table."""
    result = _parse([_proposal(statement=f"의무 {n}") for n in range(3)])
    assert len(result.proposals) == 3
    assert {p.statement for p in result.proposals} == {"의무 0", "의무 1", "의무 2"}
    assert all(p.cites == (PATH,) for p in result.proposals)


def test_an_empty_array_is_a_valid_verdict_not_a_failure() -> None:
    """ "This clause states no obligation" is a correct and common answer."""
    result = _parse([])
    assert result.proposals == []
    assert not result.unparseable


def test_conditions_spanning_two_clauses_produce_one_ir_citing_both() -> None:
    """ADR-0004 decision 1, second row: conditions attach, they do not split."""
    result = _parse(
        [_proposal(cites=[PATH, "부칙/제2조"], condition_text="시행일 이후 제조분부터")]
    )
    assert len(result.proposals) == 1
    assert result.proposals[0].cites == (PATH, "부칙/제2조")
    assert result.proposals[0].condition_text == "시행일 이후 제조분부터"


def test_class_restriction_stays_on_one_ir(caplog) -> None:
    """ADR-0017 decision 2 — parameterised, not one IR per product class."""
    result = _parse([_proposal(condition_text="2등급 이상 의료기기에 한정한다")])
    assert len(result.proposals) == 1
    assert "2등급" in (result.proposals[0].condition_text or "")


# --- validation against the rule set -----------------------------------------------------------


def test_modal_outside_the_inventory_is_discarded() -> None:
    """ "One bearer + one modal + one required action" only holds while the modal set is closed."""
    result = _parse([_proposal(modal="바람직하다"), _proposal()])
    assert len(result.proposals) == 1
    assert any("modal outside the inventory" in reason for reason in result.discarded)


def test_conjugated_modal_is_stored_in_its_citation_form() -> None:
    result = _parse([_proposal(modal="하여야 하며")])
    assert result.proposals[0].modal == "하여야 한다"


def test_taxonomy_from_the_wrong_domain_is_nulled_not_stored() -> None:
    """An invented or cross-domain code is dropped; the IR survives without one."""
    result = _parse([_proposal(taxonomy_code="design_control")], rules=COSMETIC)
    assert len(result.proposals) == 1
    assert result.proposals[0].taxonomy_code is None


def test_a_proposal_with_no_cites_is_rejected() -> None:
    """ADR-0004 decision 2 — there is no draft state for an uncited IR."""
    result = _parse([_proposal(cites=[]), _proposal(cites=None)])
    assert result.proposals == []
    assert len(result.discarded) == 2
    assert all("no cites" in reason for reason in result.discarded)


def test_a_proposal_with_no_statement_is_rejected() -> None:
    assert _parse([_proposal(statement="")]).proposals == []
    assert _parse([_proposal(statement=None)]).proposals == []


def test_string_null_is_treated_as_absent() -> None:
    """Models emit the *string* "null" often enough that storing it would poison the field."""
    result = _parse([_proposal(bearer="null", condition_text="N/A")])
    assert result.proposals[0].bearer is None
    assert result.proposals[0].condition_text is None


# --- tolerating what models actually return ---------------------------------------------------


def test_fenced_and_prose_wrapped_json_is_recovered() -> None:
    """Discarding a correct extraction over formatting shows up as unexplainable recall loss."""
    body = json.dumps([_proposal()], ensure_ascii=False)
    for wrapper in (f"```json\n{body}\n```", f"Here are the obligations:\n{body}\nLet me know."):
        assert len(_parse(wrapper).proposals) == 1


def test_bare_object_and_wrapped_list_are_both_accepted() -> None:
    assert len(_parse(_proposal()).proposals) == 1
    assert len(_parse({"irs": [_proposal(), _proposal()]}).proposals) == 2


def test_unparseable_output_is_recorded_never_silently_empty() -> None:
    """ "The model answered nothing usable" and "the clause has no duty" are different findings.

    Collapsing them hides a prompt regression inside a legitimate verdict, and the coverage report
    would show full classification while recall quietly fell.
    """
    result = _parse("I'm sorry, I cannot help with that request.")
    assert result.unparseable
    assert result.proposals == []


def test_runaway_output_is_truncated_and_says_so() -> None:
    result = _parse([_proposal() for _ in range(MAX_PROPOSALS_PER_CLAUSE + 5)])
    assert len(result.proposals) == MAX_PROPOSALS_PER_CLAUSE
    assert any("truncated" in reason for reason in result.discarded)


def test_provenance_travels_with_the_result() -> None:
    """Every row this produces must be able to say what produced it (ADR-0004 decision 4)."""
    result = _parse([_proposal()])
    assert (result.provider, result.model) == ("ollama", "test-model")


# --- the prompt ---------------------------------------------------------------------------------


@pytest.mark.parametrize("rules", [SAMD, COSMETIC])
def test_prompt_carries_its_domain_taxonomy_and_the_closed_modal_set(rules) -> None:
    prompt = build_prompt(
        rules=rules,
        clause_path=PATH,
        heading="기록의 보관",
        text="제조업자는 기록을 보관하여야 한다.",
        detected_modals=("하여야 한다",),
    )
    for code in rules.taxonomy:
        assert code in prompt
    for modal in rules.modals:
        assert modal in prompt
    # The class-restriction rule has to be *in* the prompt, not only in the ADR.
    assert "Do not emit one IR per class" in prompt


def test_prompt_differs_between_domains() -> None:
    """If it did not, `domain_profile` would select nothing and the branch would be a fiction."""
    kwargs = {
        "clause_path": PATH,
        "heading": None,
        "text": "…하여야 한다.",
        "detected_modals": ("하여야 한다",),
    }
    assert build_prompt(rules=SAMD, **kwargs) != build_prompt(rules=COSMETIC, **kwargs)


# --- composed fields are written in the clause's language --------------------------------------

SAMD_EN = rule_set_for(Domain.SAMD, "en")


def test_a_statement_composed_in_the_wrong_language_is_discarded() -> None:
    """An IR is checked by holding it beside the clause it cites, which needs one language.

    Observed 2026-08-27 on 의료기기법: three of 133 IRs carried an English `statement` beside
    `modal: 하여야 한다` — a row disagreeing with itself, and one a reviewer had to translate before
    they could verify it.
    """
    result = _parse(
        [
            _proposal(statement="shall report to the relevant government officials."),
            _proposal(),
        ]
    )
    assert len(result.proposals) == 1
    assert any("statement is not written in ko" in reason for reason in result.discarded)


def test_a_condition_composed_in_the_wrong_language_is_discarded_too() -> None:
    """`condition_text` carries the class restriction, so a reviewer reads it as closely."""
    result = _parse(
        [_proposal(condition_text="according to the standards set by the Minister of Health")]
    )
    assert not result.proposals
    assert any("condition_text is not written in ko" in reason for reason in result.discarded)


def test_latin_inside_a_korean_statement_is_not_a_foreign_language() -> None:
    """The rule is deliberately asymmetric: Korean statutes are full of Latin.

    GMP, IEC 62304, RFID. A mirror-image rule would refuse a correct Korean statement for naming a
    standard, which is why `LANGUAGE_SCRIPT_FOREIGN["ko"]` is empty rather than `[A-Za-z]`.
    """
    result = _parse([_proposal(statement="GMP 적합인정을 받아야 하며 IEC 62304를 따라야 한다")])
    assert len(result.proposals) == 1
    assert not result.discarded


def test_hangul_inside_an_english_statement_is_a_foreign_language() -> None:
    """The other direction *is* evidence — an English rule set has no reason to compose Hangul."""
    result = _parse(
        [
            {
                "bearer": "the manufacturer",
                "modal": "shall",
                "statement": "기록을 3년간 보관하여야 한다",
                "condition_text": None,
                "taxonomy_code": None,
                "cites": [PATH],
            }
        ],
        rules=SAMD_EN,
    )
    assert not result.proposals
    assert any("statement is not written in en" in reason for reason in result.discarded)


def test_an_absent_condition_is_not_a_language_failure() -> None:
    """`condition_text` is optional; a null must not be reported as the wrong language."""
    result = _parse([_proposal(condition_text=None)])
    assert len(result.proposals) == 1
    assert not result.discarded


def test_the_prompt_names_the_language_it_expects() -> None:
    """The check is the guarantee; the instruction is what keeps the model from needing it."""
    prompt = build_prompt(
        rules=SAMD, clause_path=PATH, heading=None, text="…", detected_modals=("하여야 한다",)
    )
    assert "Korean (한국어)" in prompt
    assert "English" in build_prompt(
        rules=SAMD_EN, clause_path=PATH, heading=None, text="…", detected_modals=("shall",)
    )
