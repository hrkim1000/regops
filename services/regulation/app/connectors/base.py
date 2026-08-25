"""The connector contract: ``Source -> [FetchedArtifact]``. Connectors fetch; they do not parse.

Splitting fetch from parse keeps the count linear rather than multiplicative (ADR-0003 decision 1):
fetching MFDS RSS and fetching EUR-Lex are different problems, but parsing 화장품법 and 의료기기법
is the *same* problem. Fusing them would push domain knowledge into the fetch layer and break the
shared pipeline that Phase 2's six-cell build rests on.

Where the line falls, concretely:

- **Connector** — talk to the host, identify which artefacts the response carries (body, each 별표),
  read the dates the API envelope hands over, and produce the canonicalized bytes that change
  detection hashes.
- **Parser profile (phase 1.1)** — clause segmentation, ``effective_date`` from 부칙, everything
  that requires reading the regulation rather than the response.

``effective_date`` is deliberately absent from :class:`FetchedArtifact` for that reason, even where
the API hands us 시행일자 outright: it is a parse output (ADR-0003 decision 5) and the value rides
in :attr:`FetchedArtifact.meta` until phase 1.1 owns writing it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Protocol, runtime_checkable

from regops_shared.constants import AttachmentKind, DocType, DriftSignal, SourceTier


class ConnectorError(RuntimeError):
    """Base for connector failures that should be recorded as a failed observation."""


class NonIngestibleSourceError(ConnectorError):
    """Raised when anything asks a non-ingestible source to be fetched.

    This is the code path that does not exist for Tier D (ADR-0003 decision 7). The scheduler skips
    such sources; if something reaches the connector API anyway — a manual trigger, a bad seed, a
    future caller — it fails here rather than downloading a copyright-protected document.
    """


class MissingCredentialError(ConnectorError):
    """The source's URL template needs a credential that settings do not carry."""


class AuthorityError(ConnectorError):
    """The authority answered HTTP 200 with an error body.

    Not a transport failure. 국가법령정보 returns 200 for an unregistered egress IP, for an
    ungranted API scope, and for a malformed query (which comes back ``success`` with
    ``totalCnt 0``). A connector checking only transport status treats all three as success and
    records a healthy observation for a fetch that returned nothing — see the live API test in
    ``docs/design/spike-2026-07-29-mfds-source-recon.md``.

    Carries the drift signal the pipeline should raise, so "the key stopped working" and "the
    response shape changed" stay distinguishable in ``structure_drift_alerts``.
    """

    def __init__(self, message: str, *, signal: DriftSignal = DriftSignal.AUTH_FAILURE) -> None:
        super().__init__(message)
        self.signal = signal


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """The fields of a ``sources`` row a connector is allowed to see.

    An ORM row is deliberately not passed in: connectors stay unit-testable against fixtures, and
    they get no handle on the session with which to write anything.
    """

    slug: str
    title: str
    tier: SourceTier
    ingestible: bool
    url_template: str | None
    params: Mapping[str, object] = field(default_factory=dict)
    http_etag: str | None = None
    http_last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Which Document an artefact belongs to.

    An annex sets ``doc_type=ANNEX`` and ``parent_canonical_key``; it becomes a child Document with
    its own versions rather than a row hanging off the body's version (ADR-0012).
    """

    canonical_key: str
    title: str
    doc_type: DocType
    annex_no: str | None = None
    parent_canonical_key: str | None = None


@dataclass(frozen=True, slots=True)
class AttachmentLink:
    """A file the authority publishes alongside a version — archival copy and fallback only."""

    kind: AttachmentKind
    ordinal: int
    title: str | None = None
    file_format: str | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class FetchedArtifact:
    """One archivable unit: the body, or one 별표.

    ``raw`` is the response archived **unmodified** — it is what gets cited. ``canonical`` is a
    separate, derived view used only to decide whether anything changed. Hashing ``raw`` instead
    would make nav chrome, session tokens and view counts read as amendments, which would bury the
    detection-coverage gate in false positives on day one (ADR-0003 decision 2).

    Artefacts produced by one call **share** ``raw``: 행정규칙 본문조회 returns the body and every
    ``<별표단위>`` in a single response, and "unmodified" means exactly that — the annex's evidence
    is the response it arrived in, not a subtree re-serialized by us. They differ in ``canonical``,
    which is sliced per artefact, and that is what makes 별표 2 version without dragging the body
    with it (ADR-0012).
    """

    ref: ArtifactRef
    raw: bytes
    canonical: bytes
    content_type: str = "application/xml"
    language: str = "ko"
    version_label: str | None = None
    #: From source metadata — 공포일자 / 발령일자 / RSS pubDate. Stays **None** where the source
    #: exposes none; never defaulted to our fetch clock, which would make the ≤24h latency gate
    #: pass by construction and measure nothing.
    published_at: datetime | None = None
    attachments: tuple[AttachmentLink, ...] = ()
    #: Envelope values phase 1.1 will need — 시행일자, 조문시행일자, 제개정구분 and the like.
    meta: Mapping[str, str] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class StandardRecord:
    """Tier D output: the recognition record and nothing else.

    There is no bytes field here, and that is the point — the recognition *list* is an ingestible
    Tier B page, while the standard it names is never fetched (ADR-0003 decision 7).
    """

    number: str
    edition: str | None = None
    issuing_body: str | None = None
    recognition_number: str | None = None
    title: str | None = None
    effective_date: str | None = None
    withdrawal_date: str | None = None
    status: str = "unknown"
    official_url: str | None = None


@dataclass(frozen=True, slots=True)
class AnnouncementRecord:
    """An amendment the authority has announced, whether or not its text exists yet.

    ADR-0019. Sibling of :class:`StandardRecord`: connector output that becomes a row of its own
    rather than a Document, because a rule published and not yet in force has no version to hang on.

    ``affects`` holds **canonical keys** — ``fda:cfr:21-820`` — not raw part numbers. The connector
    knows its own key convention; the ingest stage only resolves keys to Documents it already has,
    so a rule naming a Part outside the corpus keeps its row and gains no link.
    """

    ref: str
    authority: str
    affects: tuple[str, ...] = ()
    citation: str | None = None
    title: str | None = None
    published_on: str | None = None
    #: Nullable on purpose — ADR-0013. Null with the phrase retained, never a derived date.
    effective_on: str | None = None
    effective_date_phrase: str | None = None
    official_url: str | None = None


@dataclass(frozen=True, slots=True)
class FetchResult:
    """What one fetch attempt produced, whether or not it produced anything."""

    http_status: int | None = None
    not_modified: bool = False
    artifacts: tuple[FetchedArtifact, ...] = ()
    #: Populated only by recognition-list connectors.
    standards: tuple[StandardRecord, ...] = ()
    #: Populated only by announcement connectors (ADR-0019).
    announcements: tuple[AnnouncementRecord, ...] = ()
    etag: str | None = None
    last_modified: str | None = None
    #: Feed-level publication timestamp, where the source exposes one at that level.
    published_at: datetime | None = None
    notes: str | None = None
    #: Annexes the response listed but returned no text for — ``("별표1", "서식3")``. They produce
    #: **no artefact**, so nothing downstream would otherwise know they exist: the parse stage can
    #: only raise ``EMPTY_ANNEX_BODY`` against a Document, and no Document is created. The ingest
    #: stage turns this into an operator alert (ADR-0003 decision 10's fallback case).
    empty_annexes: tuple[str, ...] = ()


@runtime_checkable
class Connector(Protocol):
    """Implemented by every connector. ``version`` is recorded on each observation, so a change in
    fetch behaviour is attributable after the fact."""

    key: ClassVar[str]
    version: ClassVar[str]

    def fetch(self, spec: SourceSpec) -> FetchResult: ...


def assert_ingestible(spec: SourceSpec) -> None:
    """Refuse to fetch a Tier D or otherwise non-ingestible source.

    Called at the top of every connector. Together with ``sources.ingestible = false`` on Tier D
    rows and ``standard_references`` having no column body text could occupy, this is what makes
    the Tier D rule structural rather than a policy someone has to remember.
    """
    if spec.tier is SourceTier.D:
        raise NonIngestibleSourceError(
            f"{spec.slug}: Tier D is metadata-only — the standard's text is never fetched. "
            "Track freshness through the recognition list instead."
        )
    if not spec.ingestible:
        raise NonIngestibleSourceError(f"{spec.slug}: source is marked non-ingestible")


__all__ = [
    "ArtifactRef",
    "AttachmentLink",
    "AuthorityError",
    "Connector",
    "ConnectorError",
    "FetchResult",
    "FetchedArtifact",
    "MissingCredentialError",
    "NonIngestibleSourceError",
    "SourceSpec",
    "StandardRecord",
    "assert_ingestible",
]
