"""An RSS feed is a change signal, not regulation text — and must survive the parse stage.

MFDS publishes each board as RSS. `data0008` 제개정고시등 announces 고시 amendments with a title and
a ``pubDate`` and **no 고시 text**; the text is fetched separately through 행정규칙 본문조회. So a
feed has no clauses, which is not a gap.

The hazard is what "no clauses" collides with: the parse stage answers an unknown document type with
``ParseError(MISSING_ROOT)``, and ``_fail_closed`` answers *that* by **deleting the version**. Left
alone, every board publication would destroy the archived record of what the board said at time T —
the very thing that makes the feed usable as a latency signal — and raise a drift alert for it.
"""

from __future__ import annotations

import pytest

from app.parsing import is_parseable, parse_document, profile_for
from regops_shared.constants import DocType


def test_a_feed_is_not_parseable_and_says_so() -> None:
    assert is_parseable(DocType.FEED) is False
    assert profile_for(DocType.FEED) == ""


@pytest.mark.parametrize(
    "doc_type",
    [DocType.LAW, DocType.DECREE, DocType.ENFORCEMENT_RULE, DocType.NOTICE, DocType.ANNEX],
)
def test_every_regulation_type_is_parseable(doc_type: DocType) -> None:
    """The guard must not quietly exclude a type that *does* carry clauses."""
    assert is_parseable(doc_type) is True
    assert profile_for(doc_type)


def test_parsing_a_feed_directly_still_raises() -> None:
    """`is_parseable` is the guard; `parse_document` stays strict.

    Keeping the raise means an unknown *regulation* type — a new `doc_type` someone adds without a
    profile — is still caught loudly rather than silently producing zero clauses.
    """
    from app.parsing import ParseError

    with pytest.raises(ParseError):
        parse_document(
            "<rss><channel><title>제개정고시등</title></channel></rss>".encode(),
            doc_type=DocType.FEED,
            canonical_key="mfds:rss:data0008",
        )


def test_the_guard_covers_every_doc_type_without_a_profile() -> None:
    """Whatever `is_parseable` rejects, `parse_document` must reject too — and vice versa. A type
    that drifts between the two is either silently unparsed or destructively parsed."""
    from app.parsing import ParseError

    for doc_type in DocType:
        if is_parseable(doc_type):
            continue
        with pytest.raises(ParseError):
            parse_document(b"<x/>", doc_type=doc_type, canonical_key="k")
