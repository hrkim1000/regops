"""Risk 1a — the two costs ADR-0018 accepts, tested before either FDA cell is gated.

    STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm regulation \
        python -m pytest tests/integration/test_risk_1a.py -q

[phase2.0a](../../../../docs/plan/phase2.0a_fda.md) *Risks* 1a names two things that need tests
**before either FDA cell is gated**, and they are here together because they are one admission seen
from two sides: FDA states less about its own amendments than MFDS does.

**There is no pending text.** The eCFR 404s on any date past its ceiling, so a rule published today
and effective in 2033 has no text to version. ADR-0018 decision 7 accepts that and forbids the
obvious workaround — synthesising the pending text by applying the rule's body to the current
compilation would put generated regulation into the clause store, indistinguishable from fetched
text, which is the failure the whole citation contract exists to prevent.

**Redesignation lost its stated signal.** MFDS supplies 조문이동이전 / 조문이동이후, so a move is
*stated*; FDA supplies ``removed`` and nothing about movement. CFR redesignation therefore runs on
ADR-0002 decision 7's content-similarity fallback, which had never carried a gated cell.

These use the real parse and diff stages against Postgres. Only the network is stubbed, and the CFR
fixtures follow ``test_parsing_cfr.py``: shapes observed live in title 21, not invented ones.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.connectors.http import HttpResponse
from app.diff import diff_version
from app.ingest import ingest_source
from app.models import (
    AmendmentAnnouncement,
    AnnouncementDocument,
    Cell,
    ChangeEvent,
    Clause,
    ClauseDiff,
    Document,
    DocumentCell,
    DocumentVersion,
    FetchObservation,
    Source,
)
from app.parse import parse_version
from regops_shared.constants import ChangeKind, SourceBlock, SourceTier
from regops_shared.db import sync_session

pytestmark = pytest.mark.integration

CFR_KEY = "fda:cfr:21-820"
#: The Federal Register feed is its own Document (a FEED, never cited) and must be purged with the
#: Part, or its versions keep a foreign key onto the observations this teardown deletes.
FR_KEY = "fda:fr:21-820"
CFR_SLUG = "test.integration.risk1a.cfr_820"
FR_SLUG = "test.integration.risk1a.fr_820"

V1_ISSUE = "2026-02-04"
V2_ISSUE = "2026-06-15"

#: Far enough out that no clock drift makes it current, and it is a real one: FDA has a rule on the
#: books effective 2033-03-07 (ADR-0018 decision 7).
PENDING_ON = "2033-03-07"


# --- CFR fixtures ------------------------------------------------------------------------------


def _versions(rows: list[dict[str, object]]) -> bytes:
    return json.dumps({"content_versions": rows}).encode()


def _row(identifier: str, issue: str, *, removed: bool = False) -> dict[str, object]:
    return {
        "identifier": identifier,
        "issue_date": issue,
        "removed": removed,
        "substantive": True,
    }


#: The provision that gets redesignated. Long enough that SequenceMatcher measures prose rather than
#: two short strings resembling each other by accident.
RECORDS_TEXT = (
    "Each manufacturer shall maintain records of the review and evaluation of each complaint "
    "received, including the name of the device, the date the complaint was received, and any "
    "unique device identifier used."
)
EDITED_RECORDS_TEXT = (
    "Each manufacturer shall maintain records of the review and evaluation of each complaint "
    "received, including the name of the device, the date the complaint was received, the "
    "responsible individual, and any unique device identifier used."
)
#: A genuinely different provision, and the fixture is **measured rather than invented**: against
#: ``RECORDS_TEXT`` it scores 0.69, which is the band the whole case lives in. Above 0.90 the old
#: code and the new code agree, and below 0.60 the old code refused the pairing anyway — either way
#: the test would pass without the mitigation and prove nothing. At 0.69 the old code pairs it (the
#: bug) and the raised bar refuses it (the fix).
#:
#: It shares the boilerplate every CFR section is built from — "Each manufacturer shall maintain
#: records of … including the name of the device, the date …" — which is how a deletion gets
#: absorbed as a renumber in the first place.
SERVICING_TEXT = (
    "Each manufacturer shall maintain records of each servicing report received, including the "
    "name of the device, the date the report was received, and the name of the individual "
    "performing the service."
)


def _part(sections: str) -> bytes:
    return (
        '<?xml version="1.0"?>'
        '<DIV5 N="820" TYPE="PART">'
        "<HEAD>PART 820&#x2014;QUALITY MANAGEMENT SYSTEM REGULATION</HEAD>"
        f"{sections}"
        "</DIV5>"
    ).encode()


def _subpart(letter: str, name: str, sections: str) -> str:
    return (
        f'<DIV6 N="{letter}" TYPE="SUBPART"><HEAD>Subpart {letter}&#x2014;{name}</HEAD>'
        f"{sections}</DIV6>"
    )


def _section(number: str, heading: str, text: str) -> str:
    return (
        f'<DIV8 N="{number}" TYPE="SECTION">'
        f"<HEAD>&#xA7; {number} {heading}</HEAD>"
        f"<P>{text}</P>"
        "</DIV8>"
    )


class _ECFRFetcher:
    """Serves the versions endpoint and the body, as ecfr.gov does."""

    def __init__(self, versions: bytes, body: bytes) -> None:
        self._versions = versions
        self._body = body
        self.urls: list[str] = []

    def get(self, url, *, etag=None, last_modified=None, extra_headers=None) -> HttpResponse:
        self.urls.append(url)
        if "/versions/" in url:
            return HttpResponse(status=200, body=self._versions, content_type="application/json")
        return HttpResponse(status=200, body=self._body, content_type="application/xml")

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


class _FRFetcher:
    def __init__(self, results: list[dict[str, object]]) -> None:
        self._body = json.dumps({"count": len(results), "results": results}).encode()

    def get(self, url, *, etag=None, last_modified=None, extra_headers=None) -> HttpResponse:
        return HttpResponse(status=200, body=self._body, content_type="application/json")

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


# --- harness -----------------------------------------------------------------------------------


def _purge(session) -> None:
    documents = list(
        session.scalars(select(Document).where(Document.canonical_key.in_((CFR_KEY, FR_KEY))))
    )
    ids = [d.id for d in documents]
    if ids:
        session.execute(
            delete(AnnouncementDocument).where(AnnouncementDocument.document_id.in_(ids))
        )
        versions = list(
            session.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(ids)))
        )
        if versions:
            diffs = select(ClauseDiff.id).where(ClauseDiff.to_version_id.in_(versions))
            session.execute(delete(ChangeEvent).where(ChangeEvent.clause_diff_id.in_(diffs)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.to_version_id.in_(versions)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.from_version_id.in_(versions)))
            session.execute(delete(Clause).where(Clause.document_version_id.in_(versions)))
        session.execute(delete(DocumentCell).where(DocumentCell.document_id.in_(ids)))
        session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(ids)))
        session.execute(delete(Document).where(Document.id.in_(ids)))

    sources = list(session.scalars(select(Source).where(Source.slug.in_((CFR_SLUG, FR_SLUG)))))
    for source in sources:
        session.execute(
            delete(AmendmentAnnouncement).where(AmendmentAnnouncement.source_id == source.id)
        )
        session.execute(delete(FetchObservation).where(FetchObservation.source_id == source.id))
        session.execute(delete(Source).where(Source.id == source.id))
    session.commit()


@pytest.fixture
def session():
    with sync_session() as db:
        _purge(db)
        yield db
        _purge(db)


@pytest.fixture
def cells(session) -> dict[str, uuid.UUID]:
    return {cell.slug: cell.id for cell in session.scalars(select(Cell)).all()}


@pytest.fixture
def cfr_source(session, cells) -> Source:
    row = Source(
        slug=CFR_SLUG,
        cell_id=cells["fda_samd"],
        block=SourceBlock.REGULATIONS,
        ordinal=10,
        title="21 CFR Part 820",
        url_template=None,
        tier=SourceTier.A,
        ingestible=True,
        connector="ecfr_part",
        params={"title": "21", "part": "820"},
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def fr_source(session, cells) -> Source:
    row = Source(
        slug=FR_SLUG,
        cell_id=cells["fda_samd"],
        block=SourceBlock.REGULATIONS,
        ordinal=11,
        title="Federal Register — 21 CFR Part 820",
        url_template=None,
        tier=SourceTier.A,
        ingestible=True,
        connector="federal_register",
        params={"title": "21", "part": "820"},
    )
    session.add(row)
    session.commit()
    return row


def _land(session, source: Source, versions: bytes, body: bytes) -> DocumentVersion:
    """Ingest one eCFR snapshot and parse it, returning the version it created."""
    summary = ingest_source(session, source, connector_fetcher=_ECFRFetcher(versions, body))
    assert summary.new_version_ids, "fixture produced no new version"
    version = session.get(DocumentVersion, summary.new_version_ids[-1])
    parse_version(session, version)
    session.commit()
    return version


def _kinds(session, version: DocumentVersion) -> dict[ChangeKind, list[ClauseDiff]]:
    rows = session.scalars(select(ClauseDiff).where(ClauseDiff.to_version_id == version.id)).all()
    out: dict[ChangeKind, list[ClauseDiff]] = {}
    for row in rows:
        out.setdefault(row.change_kind, []).append(row)
    return out


def _clauses(session, version: DocumentVersion) -> list[Clause]:
    return list(
        session.scalars(select(Clause).where(Clause.document_version_id == version.id)).all()
    )


def _baseline(session, source: Source) -> DocumentVersion:
    """One Part carrying one section, diffed so the next version has something to diff against."""
    version = _land(
        session,
        source,
        _versions([_row("820.35", V1_ISSUE)]),
        _part(_subpart("A", "General Provisions", _section("820.35", "Records.", RECORDS_TEXT))),
    )
    diff_version(session, version)
    session.commit()
    return version


# --- redesignation: the similarity fallback carrying a gated cell -------------------------------


def test_a_stated_removal_that_is_really_a_redesignation_is_not_delete_plus_add(
    session, cfr_source
) -> None:
    """*Renumbering must never be delete+add* — including when the authority said "removed".

    FDA writes a redesignation as *"§ 820.35 removed"* plus *"§ 820.45 added"*, so the sections
    carrying a stated removal are exactly the ones most likely to be renumbers. A veto on pairing
    them would manufacture the failure ADR-0002 decision 7 exists to prevent.
    """
    _baseline(session, cfr_source)

    v2 = _land(
        session,
        cfr_source,
        _versions([_row("820.35", V2_ISSUE, removed=True), _row("820.45", V2_ISSUE)]),
        _part(_subpart("A", "General Provisions", _section("820.45", "Records.", RECORDS_TEXT))),
    )
    result = diff_version(session, v2)
    session.commit()

    kinds = _kinds(session, v2)
    assert ChangeKind.REMOVED not in kinds, "a redesignation was reported as a deletion"
    assert ChangeKind.ADDED not in kinds, "a redesignation was reported as an addition"

    (renumber,) = kinds[ChangeKind.RENUMBERED]
    assert renumber.from_clause_path.endswith("820.35")
    assert renumber.clause_path.endswith("820.45")
    assert result.counts.get("renumbered") == 1

    # **Not `content_hash`, and that is a finding rather than a detail.** The body is
    # byte-identical, but a CFR section clause's text *embeds its own number* — it opens
    # "§ 820.35 Records." — so the hash moves with the redesignation and the free exact-match
    # arm never fires.
    #
    # That is the 조문내용 phenomenon exactly. `_same_but_for_its_number` already solves it for
    # MFDS, but with a Korean-only regex and on `_authority_renumbers`, a path FDA never reaches.
    #
    # So every CFR redesignation lands on similarity and, over a stated removal, in the review
    # queue. Correct but not free: the QMSR issue flagged 27 removed sections in Part 820 alone.
    # Recorded in phase2.0a *Deviations* rather than fixed in passing — generalising that helper
    # changes what the **gated** MFDS pair diffs, which needs a before-and-after over the golden
    # sets, not a change made while writing a test for something else.
    assert renumber.match_basis == "similarity_contested"
    assert renumber.similarity is not None and renumber.similarity > 0.99
    assert renumber.needs_review is True


def test_a_stated_removal_is_a_removal_and_not_absorbed_into_a_lookalike(
    session, cfr_source
) -> None:
    """**The case the mitigation exists for.** ``RENUMBER_MATCH_RATIO`` is 0.60 and CFR prose is
    boilerplate-heavy — *"Each manufacturer shall maintain records of the review and evaluation of
    each …"* opens both a complaint-records section and a servicing-records one. Without the
    authority's own statement a section it deleted pairs to whatever survived, and a deletion
    reported as a renumber is an alert the subscriber never receives.

    ADR-0018 decision 8 is what closes it: *"the `removed` flag helps: it distinguishes 'the
    authority deleted this' from 'our differ lost it'."*
    """
    _baseline(session, cfr_source)

    v2 = _land(
        session,
        cfr_source,
        _versions([_row("820.35", V2_ISSUE, removed=True), _row("820.50", V2_ISSUE)]),
        _part(
            _subpart("A", "General Provisions", _section("820.50", "Servicing.", SERVICING_TEXT))
        ),
    )
    diff_version(session, v2)
    session.commit()

    kinds = _kinds(session, v2)
    assert ChangeKind.RENUMBERED not in kinds, (
        "a deletion the authority stated was absorbed as a renumber"
    )
    (removed,) = kinds[ChangeKind.REMOVED]
    assert removed.clause_path.endswith("820.35")
    (added,) = kinds[ChangeKind.ADDED]
    assert added.clause_path.endswith("820.50")


def test_a_redesignation_with_an_edit_survives_the_raised_bar_and_is_flagged(
    session, cfr_source
) -> None:
    """Between the two cases above: renumbered *and* amended, over a stated removal.

    It must still pair — losing it would be delete+add again — and it must carry ``needs_review``
    however high the score, because the pairing contradicts what the authority said. That is
    ADR-0002 decision 7's own remedy, *"reviewed by RA when confidence is low"*, applied where
    confidence is contested rather than merely low.
    """
    _baseline(session, cfr_source)

    v2 = _land(
        session,
        cfr_source,
        _versions([_row("820.35", V2_ISSUE, removed=True), _row("820.45", V2_ISSUE)]),
        _part(
            _subpart("A", "General Provisions", _section("820.45", "Records.", EDITED_RECORDS_TEXT))
        ),
    )
    diff_version(session, v2)
    session.commit()

    kinds = _kinds(session, v2)
    assert ChangeKind.REMOVED not in kinds
    assert ChangeKind.ADDED not in kinds
    (renumber,) = kinds[ChangeKind.RENUMBERED]
    assert renumber.match_basis == "similarity_contested"
    assert renumber.needs_review is True
    assert renumber.similarity is not None and renumber.similarity >= 0.90


def test_a_section_that_keeps_its_number_across_subparts_is_moved_not_renumbered(
    session, cfr_source
) -> None:
    """``MOVED`` keeps its phase-1.1 meaning — same identifier, different parent — and a CFR section
    relocated between subparts fits it exactly (ADR-0018 decision 8)."""
    # Both subparts exist in both versions, because a subpart is itself a clause: introducing one
    # would be a real addition and would drown the case under test.
    v1 = _land(
        session,
        cfr_source,
        _versions([_row("820.35", V1_ISSUE), _row("820.60", V1_ISSUE), _row("820.90", V1_ISSUE)]),
        _part(
            _subpart(
                "A",
                "General Provisions",
                _section("820.35", "Records.", RECORDS_TEXT)
                + _section("820.60", "Servicing.", SERVICING_TEXT),
            )
            + _subpart("B", "Records", _section("820.90", "Nonconforming product.", "Reserved."))
        ),
    )
    diff_version(session, v1)
    session.commit()

    v2 = _land(
        session,
        cfr_source,
        _versions([_row("820.35", V2_ISSUE)]),
        _part(
            _subpart("A", "General Provisions", _section("820.60", "Servicing.", SERVICING_TEXT))
            + _subpart(
                "B",
                "Records",
                _section("820.35", "Records.", RECORDS_TEXT)
                + _section("820.90", "Nonconforming product.", "Reserved."),
            )
        ),
    )
    diff_version(session, v2)
    session.commit()

    kinds = _kinds(session, v2)
    assert ChangeKind.REMOVED not in kinds, "a relocation was reported as a deletion"
    assert ChangeKind.ADDED not in kinds, "a relocation was reported as an addition"
    (moved,) = kinds[ChangeKind.MOVED]
    assert moved.from_clause_path == "Subpart A/820.35"
    assert moved.clause_path == "Subpart B/820.35"


def test_a_source_that_states_no_removal_keeps_the_floor_it_had(session, cfr_source) -> None:
    """The other half: silence must not read as a report.

    law.go.kr states 조문이동이전 / 조문이동이후, so an MFDS renumber never reaches this fallback at
    all — but the floor it *would* meet has to be the one it always met, or the gated MFDS pair
    moves. An eCFR issue reporting no removals is the same input shape, and it keeps 0.60 and stays
    unflagged.
    """
    _baseline(session, cfr_source)

    v2 = _land(
        session,
        cfr_source,
        _versions([_row("820.45", V2_ISSUE)]),
        _part(
            _subpart("A", "General Provisions", _section("820.45", "Records.", EDITED_RECORDS_TEXT))
        ),
    )
    assert v2.authority_removed_paths == [], (
        "an issue reporting no removals must record an empty list, not null"
    )
    diff_version(session, v2)
    session.commit()

    kinds = _kinds(session, v2)
    (renumber,) = kinds[ChangeKind.RENUMBERED]
    assert renumber.match_basis == "similarity"
    assert renumber.needs_review is False


# --- pending text: a signal without a version ---------------------------------------------------


def _pending_rule() -> dict[str, object]:
    return {
        "document_number": "2026-99001",
        "citation": "91 FR 60000",
        "type": "Rule",
        "publication_date": date.today().isoformat(),
        "effective_on": PENDING_ON,
        "cfr_references": [{"title": 21, "part": "820"}],
        "dates": f"This rule is effective {PENDING_ON}.",
        "html_url": "https://www.federalregister.gov/documents/2026-99001",
    }


def test_a_pending_amendment_is_an_announcement_and_never_a_version(
    session, cfr_source, fr_source
) -> None:
    """*ADR-0018 decision 7* — a future-effective rule produces a change signal and no text.

    The honest floor is *"a rule effective 2033-03-07 was published, here it is, and it amends Part
    820"*. What it must never produce is a ``DocumentVersion``: there is no fetched text behind one,
    and the only way to make it would be to generate the amended provision ourselves.
    """
    v1 = _baseline(session, cfr_source)
    before = {c.clause_path: c.content_hash for c in _clauses(session, v1)}

    ingest_source(session, fr_source, connector_fetcher=_FRFetcher([_pending_rule()]))
    session.commit()

    announcement = session.scalar(
        select(AmendmentAnnouncement).where(AmendmentAnnouncement.ref == "2026-99001")
    )
    assert announcement is not None, "the pending rule left no signal at all"
    assert announcement.effective_on == date.fromisoformat(PENDING_ON)

    document = session.scalar(select(Document).where(Document.canonical_key == CFR_KEY))
    assert session.get(AnnouncementDocument, (announcement.id, document.id)) is not None, (
        "the announcement did not reach the Part it amends"
    )

    versions = session.scalars(
        select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    ).all()
    assert [v.id for v in versions] == [v1.id], "a pending rule created a DocumentVersion"

    after = {c.clause_path: c.content_hash for c in _clauses(session, v1)}
    assert after == before, "the in-force text moved when only an announcement had arrived"


def test_no_fda_version_carries_a_future_effective_date(session, cfr_source, fr_source) -> None:
    """*ADR-0018 decision 7* says ADR-0016's in-force rule holds **vacuously** for FDA: no version
    ever has a future ``effective_date``, because the text is unavailable until it is in force.

    Asserted over the store rather than over one fixture — a synthesised pending version shows up
    here whatever produced it.
    """
    _baseline(session, cfr_source)
    ingest_source(session, fr_source, connector_fetcher=_FRFetcher([_pending_rule()]))
    session.commit()

    today = datetime.now(tz=UTC).date()
    future = session.scalars(
        select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Document.canonical_key.like("fda:%"),
            DocumentVersion.effective_date > today + timedelta(days=1),
        )
    ).all()
    assert future == [], (
        "an FDA version claims a future effective date — the eCFR cannot supply text for one, "
        f"so it was synthesised: {[(v.id, v.effective_date) for v in future]}"
    )
