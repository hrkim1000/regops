"""국가법령정보 OPEN API — 법령 본문조회 and 행정규칙 본문조회.

This is the largest Phase 1 source and the only viable path to it: `law.go.kr` HTML is JS-rendered
and returns only the page title to a plain fetch, so scraping is not an option. The API returns
조문/항/호/목 as separate structured fields, which is why ADR-0002 decision 3's clause hierarchy is
*given* rather than inferred, and why canonicalization here is a stable serialization rather than a
chrome-stripping exercise.

Two behaviours here exist because of the live API test (spike 2026-07-29), not on principle:

1. **Every failure signature is HTTP 200.** An unregistered egress IP, an ungranted API scope and
   a malformed query all come back 200 — the last as ``success`` with ``totalCnt 0``,
   indistinguishable from "this law does not exist". A connector checking only transport status
   records a healthy observation for a fetch that retrieved nothing, so each is detected here.
2. **행정규칙 본문조회 returns ``<별표단위>`` with ``<별표내용>`` inline.** Annex text arrives
   with the body, so HWP/PDF extraction is off the Phase 1 critical path. Each 별표 becomes its
   own artefact — and its own child Document (ADR-0012) — so amending 별표 2 alone versions the
   annex and leaves the body untouched.

**Not verified against a live key.** The tag names below follow the spike's recorded structure and
are matched anywhere in the tree rather than by fixed path, so an envelope difference degrades to
"nothing found" (a drift alert) rather than a silent mis-parse. Re-verify on first live fetch.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import ClassVar
from xml.etree.ElementTree import Element

import structlog
from defusedxml.ElementTree import fromstring as parse_xml

from regops_shared.constants import AttachmentKind, DocType, DriftSignal
from regops_shared.settings import get_settings

from ..canonicalize import canonical_xml, normalize_text
from .base import (
    ArtifactRef,
    AttachmentLink,
    AuthorityError,
    FetchedArtifact,
    FetchResult,
    SourceSpec,
    assert_ingestible,
)
from .http import PoliteFetcher, resolve_url

log = structlog.get_logger(__name__)

#: Error bodies the authority returns behind HTTP 200. Ordered most specific first.
AUTH_FAILURE_MARKERS: tuple[str, ...] = (
    "사용자 정보 검증에 실패",
    "IP주소 및 도메인주소를 등록",
    "미신청된",
)

#: Tags whose value rotates without the content changing — download links carry sequence numbers
#: that are reissued when the authority re-publishes an identical file.
_LINK_TAGS = frozenset({"별표서식파일링크", "별표서식PDF파일링크"})

_DATE8 = re.compile(r"^\s*(\d{4})[-.]?(\d{2})[-.]?(\d{2})\s*$")


def parse_authority_date(value: str | None) -> datetime | None:
    """``20240701`` / ``2024-07-01`` → an aware datetime. Anything else is None, not a guess."""
    if not value:
        return None
    match = _DATE8.match(value)
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    try:
        return datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return None


def normalize_annex_no(raw: str) -> str:
    """``0001`` → ``1``. The API zero-pads 별표번호; citations do not.

    Confirmed on the first live fetch (2026-08-03): every 별표번호 came back four-digit padded.
    Left as delivered, ``canonical_key`` would read ``…#별표0001`` while every human citation and
    every cross-reference in the text says 별표 1 — a mismatch that would surface as a broken
    citation later rather than as a bug now. Only pure-digit values are stripped, so compound
    numbering such as ``1의2`` is preserved verbatim.
    """
    stripped = raw.strip()
    return stripped.lstrip("0") or "0" if stripped.isdigit() else stripped


#: 법종구분 → ``DocType``. The 법령 본문조회 envelope states the instrument kind outright, so
#: filing 화장품법 시행규칙 as a 법률 is a fidelity loss with no excuse — and it is what leaves
#: ``DocType.DECREE`` and ``ENFORCEMENT_RULE`` defined but unreachable.
LAW_KIND_TO_DOC_TYPE: Mapping[str, DocType] = {
    "법률": DocType.LAW,
    "대통령령": DocType.DECREE,
    "총리령": DocType.ENFORCEMENT_RULE,
    "부령": DocType.ENFORCEMENT_RULE,
}


def annex_identity(unit: Element) -> tuple[str, str]:
    """``<별표단위>`` → ``(kind, label)``, e.g. ``("서식", "42의2")``.

    **별표번호 alone does not identify an annex.** Discovered 2026-08-05: 디지털의료제품법 시행규칙
    returns 76 annex units under only 56 distinct 별표번호, because the authority reuses the number
    across ``별표구분`` (별표 vs 서식) and across ``별표가지번호`` — the 가지번호 branch that Korean
    drafting uses for 제42호의2, 제42호의3 and so on. Keying identity on the number alone silently
    merged 105 units corpus-wide into other annexes' documents, and each merge landed as a spurious
    *version* on the annex that got there first.

    ``(별표구분, 별표번호, 별표가지번호)`` is exactly what the authority's own ``별표키`` attribute
    encodes, so this triple is unique by construction. The readable composite is preferred over the
    opaque key because it is how these are cited — 서식 제42호의2, not ``004202F``.
    """
    kind = _first_text(unit, "별표구분") or "별표"
    number = normalize_annex_no(_first_text(unit, "별표번호") or "")
    branch = normalize_annex_no(_first_text(unit, "별표가지번호") or "0")
    label = number if branch in {"0", ""} else f"{number}의{branch}"
    return kind, label


def _first_text(root: Element, *tags: str) -> str | None:
    """First non-empty text for any of ``tags``, found anywhere in the tree.

    Matching by tag name rather than by path is deliberate: the envelope differs between 법령 and
    행정규칙 responses and between API versions, and a fixed path would break silently.
    """
    for tag in tags:
        for element in root.iter(tag):
            text = normalize_text(element.text or "")
            if text:
                return text
    return None


def check_authority_error(body: bytes, *, slug: str) -> None:
    """Detect the HTTP-200 failure signatures before anything is archived."""
    text = body.decode("utf-8", errors="ignore")
    for marker in AUTH_FAILURE_MARKERS:
        if marker in text:
            raise AuthorityError(
                f"{slug}: authority returned HTTP 200 with an error body ({marker!r}) — "
                "check the registered egress IP and the granted API scopes",
                signal=DriftSignal.AUTH_FAILURE,
            )


def build_url(spec: SourceSpec) -> str:
    """Resolve the URL template. The result is used immediately and never persisted or logged."""
    if not spec.url_template:
        raise AuthorityError(
            f"{spec.slug}: source has no url_template", signal=DriftSignal.MISSING_ROOT
        )
    url = resolve_url(spec.url_template, credential=get_settings().law_go_kr_oc)
    for key, value in spec.params.items():
        url = url.replace(f"{{{key}}}", str(value))
    return url


class _LawGoKrConnector:
    """Shared fetch/parse for both targets. Subclasses supply the tag vocabulary."""

    key: ClassVar[str] = ""
    version: ClassVar[str] = "1.1.0"

    doc_type: ClassVar[DocType] = DocType.LAW
    key_prefix: ClassVar[str] = "mfds:law"
    id_tags: ClassVar[tuple[str, ...]] = ()
    title_tags: ClassVar[tuple[str, ...]] = ()
    published_tags: ClassVar[tuple[str, ...]] = ()
    version_tags: ClassVar[tuple[str, ...]] = ()
    effective_tags: ClassVar[tuple[str, ...]] = ()
    #: Tags that carry actual regulation text. Their absence is how the quietest HTTP-200 failure
    #: is caught: an envelope with ``resultMsg success`` and nothing in it still serializes to
    #: non-empty canonical bytes, so emptiness has to be judged on content, not on length.
    content_tags: ClassVar[tuple[str, ...]] = ("조문내용", "별표내용")

    def __init__(self, fetcher: PoliteFetcher | None = None) -> None:
        self._fetcher = fetcher

    def fetch(self, spec: SourceSpec) -> FetchResult:
        assert_ingestible(spec)
        url = build_url(spec)

        fetcher = self._fetcher or PoliteFetcher()
        try:
            response = fetcher.get(url, etag=spec.http_etag, last_modified=spec.http_last_modified)
        finally:
            if self._fetcher is None:
                fetcher.close()

        if response.not_modified:
            return FetchResult(http_status=response.status, not_modified=True)
        if response.status != 200:
            raise AuthorityError(
                f"{spec.slug}: HTTP {response.status}", signal=DriftSignal.MISSING_ROOT
            )

        check_authority_error(response.body, slug=spec.slug)
        artifacts = self.parse(response.body, spec=spec)
        return FetchResult(
            http_status=response.status,
            artifacts=artifacts,
            etag=response.etag,
            last_modified=response.last_modified,
            published_at=artifacts[0].published_at if artifacts else None,
        )

    # --- parsing (of the API envelope only; clause parsing is phase 1.1) -----------------
    def parse(self, body: bytes, *, spec: SourceSpec) -> tuple[FetchedArtifact, ...]:
        root = parse_xml(body)

        doc_id = _first_text(root, *self.id_tags) or str(spec.params.get("id", "")) or spec.slug
        title = _first_text(root, *self.title_tags) or spec.title
        canonical_key = f"{self.key_prefix}:{doc_id}"

        published_at = parse_authority_date(_first_text(root, *self.published_tags))
        version_label = _first_text(root, *self.version_tags)
        meta = self._envelope_meta(root)

        if _first_text(root, *self.content_tags) is None:
            # `success` with nothing in it is the third HTTP-200 failure signature: silent, and it
            # would otherwise record a healthy observation for a fetch that retrieved nothing.
            raise AuthorityError(
                f"{spec.slug}: response carried no regulation text — a malformed query returns "
                "success with totalCnt 0, which is indistinguishable from 'this document does "
                "not exist'",
                signal=DriftSignal.ZERO_RECORDS,
            )
        body_canonical = self._body_canonical(root)

        artifacts = [
            FetchedArtifact(
                ref=ArtifactRef(
                    canonical_key=canonical_key, title=title, doc_type=self._doc_type(root)
                ),
                raw=body,
                canonical=body_canonical,
                content_type="application/xml",
                version_label=version_label,
                published_at=published_at,
                meta=meta,
            )
        ]
        artifacts.extend(
            self._annexes(
                root,
                raw=body,
                parent_key=canonical_key,
                published_at=published_at,
                version_label=version_label,
            )
        )
        return tuple(artifacts)

    def _doc_type(self, root: Element) -> DocType:
        """Instrument kind from the response, falling back to the connector's default.

        ``법종구분`` distinguishes 법률 / 대통령령 / 총리령 in the 법령 envelope; 행정규칙 carries
        no equivalent and is always a 고시, which is what the class default encodes.
        """
        kind = _first_text(root, "법종구분")
        return LAW_KIND_TO_DOC_TYPE.get(kind or "", self.doc_type)

    def _envelope_meta(self, root: Element) -> Mapping[str, str]:
        """Dates the API hands over that phase 1.1 will write as ``effective_date``.

        Not written here: ``effective_date`` is a parse output (ADR-0003 decision 5), and 1.0 stops
        at "bytes are archived and a version row exists."
        """
        meta: dict[str, str] = {}
        effective = _first_text(root, *self.effective_tags)
        if effective:
            meta["effective_date_raw"] = effective
        return meta

    def _body_canonical(self, root: Element) -> bytes:
        """Canonicalize the body **excluding 별표**.

        This exclusion is what the phase 1.0 acceptance criterion turns on: if the annex text were
        part of the body's hash, amending 별표 2 would create a new body version too, and annexes
        would not version independently after all.
        """
        return canonical_xml(root, drop_tags=("별표", "별표단위", *_LINK_TAGS))

    def _annexes(
        self,
        root: Element,
        *,
        raw: bytes,
        parent_key: str,
        published_at: datetime | None,
        version_label: str | None,
    ) -> Iterator[FetchedArtifact]:
        """Each ``<별표단위>`` becomes its own artefact, hashed independently of the parent body.

        The prohibited and restricted ingredient lists carrying most `mfds_cosmetic` obligations
        arrive this way, so sharing the body's hash would silently miss every ingredient-list
        amendment.

        This runs for **both** targets. The spike observed ``<별표단위>`` on 행정규칙; the first
        live fetch (2026-08-03) found it on 법령 too — 의료기기법 시행규칙 returned 93 of them
        alongside its body. Annex handling is therefore not a 고시 special case.

        Identity comes from :func:`annex_identity`, never from 별표번호 alone, and a repeat within
        one response **fails closed**. Silently reusing an existing document is the worst available
        outcome: the second annex's text lands as a *version* of the first, so the amendment history
        of a real annex ends up holding an unrelated one.
        """
        seen: dict[str, str] = {}
        for ordinal, unit in enumerate(root.iter("별표단위")):
            kind, label = annex_identity(unit)
            annex_no = label or str(ordinal + 1)
            annex_title = _first_text(unit, "별표제목", "별표명") or f"{kind} {annex_no}"
            content = _first_text(unit, "별표내용")
            canonical_key = f"{parent_key}#{kind}{annex_no}"

            links = tuple(self._annex_links(unit))
            if not content:
                # ADR-0003 decision 10's fallback case. Recorded rather than skipped: an empty
                # 별표내용 is one of the spike's four still-open questions, and a missing annex is
                # worse than a noisy one for the cell whose obligations live in them.
                log.warning(
                    "annex.empty_body", parent=parent_key, annex_no=annex_no, links=len(links)
                )
                continue

            if canonical_key in seen:
                raise AuthorityError(
                    f"{parent_key}: two annexes resolve to {canonical_key!r} "
                    f"({seen[canonical_key]!r} and {annex_title!r}). The authority's numbering has "
                    "a dimension this connector does not model — refusing rather than merging them",
                    signal=DriftSignal.RECORD_COUNT_DELTA,
                )
            seen[canonical_key] = annex_title

            yield FetchedArtifact(
                ref=ArtifactRef(
                    canonical_key=canonical_key,
                    title=annex_title,
                    doc_type=DocType.ANNEX,
                    annex_no=annex_no,
                    parent_canonical_key=parent_key,
                ),
                raw=raw,
                canonical=canonical_xml(unit, drop_tags=_LINK_TAGS),
                content_type="application/xml",
                version_label=version_label,
                published_at=published_at,
                attachments=links,
            )

    @staticmethod
    def _annex_links(unit: Element) -> Iterator[AttachmentLink]:
        """The authority's own file copies — archival fallback, not the ingestion route."""
        for ordinal, tag in enumerate(sorted(_LINK_TAGS)):
            url = _first_text(unit, tag)
            if url:
                yield AttachmentLink(
                    kind=AttachmentKind.ANNEX_FILE,
                    ordinal=ordinal,
                    title=tag,
                    file_format="pdf" if "PDF" in tag else "hwp",
                    source_url=url,
                )


class LawConnector(_LawGoKrConnector):
    """법령 본문조회 — 화장품법, 의료기기법 and their 시행령 · 시행규칙."""

    key: ClassVar[str] = "law_go_kr_law"
    version: ClassVar[str] = "1.1.0"

    doc_type: ClassVar[DocType] = DocType.LAW
    key_prefix: ClassVar[str] = "mfds:law"
    id_tags: ClassVar[tuple[str, ...]] = ("법령ID",)
    title_tags: ClassVar[tuple[str, ...]] = ("법령명_한글", "법령명한글", "법령명")
    published_tags: ClassVar[tuple[str, ...]] = ("공포일자",)
    version_tags: ClassVar[tuple[str, ...]] = ("공포번호",)
    effective_tags: ClassVar[tuple[str, ...]] = ("시행일자",)


class AdmRuleConnector(_LawGoKrConnector):
    """행정규칙 본문조회 — 고시, including ``<별표단위>`` / ``<별표내용>``."""

    key: ClassVar[str] = "law_go_kr_admrul"
    version: ClassVar[str] = "1.1.0"

    doc_type: ClassVar[DocType] = DocType.NOTICE
    key_prefix: ClassVar[str] = "mfds:admrul"
    id_tags: ClassVar[tuple[str, ...]] = ("행정규칙ID", "행정규칙일련번호")
    title_tags: ClassVar[tuple[str, ...]] = ("행정규칙명",)
    published_tags: ClassVar[tuple[str, ...]] = ("발령일자",)
    version_tags: ClassVar[tuple[str, ...]] = ("발령번호",)
    effective_tags: ClassVar[tuple[str, ...]] = ("시행일자",)


__all__ = [
    "AUTH_FAILURE_MARKERS",
    "AdmRuleConnector",
    "LawConnector",
    "annex_identity",
    "build_url",
    "check_authority_error",
    "normalize_annex_no",
    "parse_authority_date",
]
