"""Annex identity — the regression suite for the collision found live on 2026-08-05.

별표번호 alone does not identify an annex. The authority reuses it across ``별표구분`` (별표 vs
서식) and across ``별표가지번호`` (42, 42의2, 42의3). Keyed on the number alone, 105 annex units
corpus-wide were silently merged into other annexes' documents — and each merge landed as a
spurious *version*, so a real annex's amendment history ended up holding unrelated content. In
phase 1.1 the diff stage would have emitted every one of those as an amendment.

The original fixtures never caught it because their 별표번호 were unique, which is the lesson:
a fixture that only contains the easy shape proves the easy shape.
"""

from __future__ import annotations

import pytest
from defusedxml.ElementTree import fromstring as parse_xml
from helpers import StubFetcher, fixture_bytes

from app.connectors.base import AuthorityError, SourceSpec
from app.connectors.law_go_kr import LawConnector, annex_identity
from regops_shared.constants import DriftSignal, SourceTier
from regops_shared.models import Document

SPEC = SourceSpec(
    slug="mfds_samd.primary_laws.digital_medical_products_act_rule",
    title="디지털의료제품법 시행규칙",
    tier=SourceTier.A,
    ingestible=True,
    url_template="https://example.invalid/law",
)


def _unit(kind: str, number: str, branch: str) -> object:
    return parse_xml(
        f"<별표단위><별표번호>{number}</별표번호>"
        f"<별표가지번호>{branch}</별표가지번호>"
        f"<별표구분>{kind}</별표구분></별표단위>"
    )


@pytest.mark.parametrize(
    ("kind", "number", "branch", "expected"),
    [
        ("별표", "0001", "00", ("별표", "1")),
        ("서식", "0001", "00", ("서식", "1")),  # same number, different kind
        ("서식", "0042", "00", ("서식", "42")),
        ("서식", "0042", "02", ("서식", "42의2")),  # 가지번호 branch
        ("서식", "0042", "03", ("서식", "42의3")),
        ("별표", "0001", "", ("별표", "1")),  # missing 가지번호 is not a branch
    ],
)
def test_identity_is_kind_number_and_branch(
    kind: str, number: str, branch: str, expected: tuple[str, str]
) -> None:
    assert annex_identity(_unit(kind, number, branch)) == expected


def test_kind_defaults_to_byeolpyo_when_absent() -> None:
    """Older responses may omit 별표구분; defaulting preserves the keys already issued."""
    unit = parse_xml("<별표단위><별표번호>0003</별표번호></별표단위>")
    assert annex_identity(unit) == ("별표", "3")


# --- the collision, end to end -------------------------------------------------


def test_colliding_numbers_produce_distinct_documents() -> None:
    """Five annex units under two 별표번호 must yield five documents, not two."""
    artifacts = LawConnector(fetcher=StubFetcher()).parse(
        fixture_bytes("law_annex_number_collision.xml"), spec=SPEC
    )
    annexes = [a for a in artifacts if a.ref.parent_canonical_key]
    assert len(annexes) == 5

    keys = [a.ref.canonical_key for a in annexes]
    assert len(set(keys)) == 5, f"identities collided: {keys}"
    assert keys == [
        "mfds:law:014846#별표1",
        "mfds:law:014846#서식1",
        "mfds:law:014846#서식42",
        "mfds:law:014846#서식42의2",
        "mfds:law:014846#서식42의3",
    ]


def test_each_colliding_annex_keeps_its_own_content() -> None:
    """The failure mode was not just a missing document — the merged annex's text was filed as a
    version of a different annex. Distinct content per identity is what makes that impossible."""
    artifacts = LawConnector(fetcher=StubFetcher()).parse(
        fixture_bytes("law_annex_number_collision.xml"), spec=SPEC
    )
    annexes = [a for a in artifacts if a.ref.parent_canonical_key]
    assert len({a.content_hash for a in annexes}) == 5


def test_annex_no_is_the_cited_label() -> None:
    artifacts = LawConnector(fetcher=StubFetcher()).parse(
        fixture_bytes("law_annex_number_collision.xml"), spec=SPEC
    )
    by_key = {a.ref.canonical_key: a.ref for a in artifacts if a.ref.parent_canonical_key}
    assert by_key["mfds:law:014846#서식42의2"].annex_no == "42의2"


# --- fail closed ---------------------------------------------------------------


def test_a_remaining_duplicate_fails_closed_rather_than_merging() -> None:
    """If the authority's numbering gains a dimension this connector does not model, refusing is
    the only safe answer — merging writes one annex's text into another's history."""
    body = fixture_bytes("law_annex_number_collision.xml").decode("utf-8")
    duplicate = body.replace(
        '<별표단위 별표키="004203F">\n      <별표번호>0042</별표번호>\n'
        "      <별표가지번호>03</별표가지번호>",
        '<별표단위 별표키="004203F">\n      <별표번호>0042</별표번호>\n'
        "      <별표가지번호>02</별표가지번호>",
    )
    assert duplicate != body, "the fixture edit must actually collide"

    with pytest.raises(AuthorityError) as exc:
        LawConnector(fetcher=StubFetcher()).parse(duplicate.encode("utf-8"), spec=SPEC)
    assert exc.value.signal is DriftSignal.RECORD_COUNT_DELTA


# --- the model agrees with the connector ---------------------------------------


def test_model_key_builder_matches_the_connector() -> None:
    assert Document.annex_canonical_key("mfds:law:014846", "서식", "42의2") == (
        "mfds:law:014846#서식42의2"
    )
