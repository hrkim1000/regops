"""What a parser profile returns. No database, no I/O — profiles are pure functions over bytes.

Keeping the result a plain dataclass is what lets every profile be unit-tested against a recorded
fixture without a session, and what lets the parse stage own persistence in one place.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date

from regops_shared.constants import ClauseKind, DriftSignal

from ..canonicalize import normalize_text


class ParseError(RuntimeError):
    """The body could not be parsed into clauses, and no version should be built from it.

    Carries a :class:`~regops_shared.constants.DriftSignal` so the parse stage raises the operator
    alert ADR-0003 decision 6 requires — never a change event. A site redesign, a truncated
    response and an envelope change are all *structure drift*, and treating any of them as
    regulatory change would generate false alerts and destroy trust in the monitoring pillar.
    """

    def __init__(self, message: str, *, signal: DriftSignal, expected: str = "") -> None:
        super().__init__(message)
        self.signal = signal
        self.expected = expected


@dataclass(slots=True)
class ParsedClause:
    """One addressable unit, before it has an id or a version to belong to.

    ``path_segments`` is the ordered address. ``clause_path`` and ``level`` are derived from it
    rather than stored twice, so the two views cannot disagree.
    """

    path_segments: tuple[str, ...]
    text: str
    kind: ClauseKind = ClauseKind.PROSE
    heading: str | None = None
    row_columns: dict[str, str] | list[str] | None = None
    effective_date: date | None = None
    effective_date_phrase: str | None = None

    #: The authority's own identifier (조문키) and move fields, where the source publishes them.
    #: These are the *primary* renumber signal — a move the authority states beats one we infer.
    source_ref: str | None = None
    moved_from_ref: str | None = None
    moved_to_ref: str | None = None
    authority_changed: bool | None = None

    #: Index into the enclosing list, resolved to ``parent_clause_id`` at persistence time.
    parent_index: int | None = None

    @property
    def clause_path(self) -> str:
        return "/".join(self.path_segments)

    @property
    def level(self) -> int:
        return len(self.path_segments)

    @property
    def content_hash(self) -> str:
        """``sha256`` of the normalized text.

        The diff stage compares hashes before it compares text, so an unchanged clause costs one
        equality test rather than a similarity computation over a 340 KB annex.
        """
        return hashlib.sha256(normalize_text(self.text).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class ParsedDocument:
    """A whole version's parse result.

    ``effective_date`` and ``effective_date_phrase`` are version-level (ADR-0013): the date where
    the authority states one, the raw 부칙 phrase whenever it was non-trivial. They are always
    written as a pair, never one without considering the other.
    """

    profile: str
    clauses: list[ParsedClause] = field(default_factory=list)
    effective_date: date | None = None
    effective_date_phrase: str | None = None


__all__ = ["ParseError", "ParsedClause", "ParsedDocument"]
