"""Canonicalization — the step that decides whether anything actually changed.

``content_hash = sha256(canonical bytes)``, and it is **never** ``sha256(response bytes)``. Nav
chrome, session tokens, rotating banners and view counts change on every request; hashing raw bytes
would make every poll look like an amendment and bury the detection-coverage gate in false
positives on day one (ADR-0003 decision 2).

How much work this is varies sharply by source, and the [source
reconnaissance](../../../docs/design/spike-2026-07-29-mfds-source-recon.md) downgraded the estimate
for Phase 1:

- **국가법령정보 본문조회** returns 조문/항/호/목 as separate structured fields with no page chrome,
  so canonicalization is a stable serialization of the content subtree — there is nothing to strip.
- **MFDS listing rows** carry ``조회수`` (view count), confirmed volatile. Dropping it is the whole
  job, and the test that proves it is the one protecting the coverage gate.

**Scope note.** Parser profiles belong to phase 1.1, but change detection ships in 1.0, so 1.0 owns
a minimal canonicalizer per connector and 1.1 takes them over.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from xml.etree.ElementTree import Element

from regops_shared.constants import VOLATILE_RECORD_FIELDS

_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_RUN = re.compile(r"\n{3,}")


def normalize_text(value: str) -> str:
    """Unicode NFC, LF line endings, no trailing whitespace, no runs of blank lines.

    NFC matters for Korean specifically: the same 한글 syllable can arrive precomposed or
    decomposed depending on the producer, and the two hash differently while rendering identically.
    """
    text = unicodedata.normalize("NFC", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_WS.sub("", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()


def _fold(name: str) -> str:
    """Fold a field label to its comparable form — case, spaces and underscores are labelling."""
    folded = unicodedata.normalize("NFC", name).strip().lower()
    return folded.replace(" ", "").replace("_", "").replace("-", "")


_VOLATILE_FOLDED = frozenset(_fold(v) for v in VOLATILE_RECORD_FIELDS)


def is_volatile_field(name: str) -> bool:
    """Does this record field change without the content changing?"""
    return _fold(name) in _VOLATILE_FOLDED


def canonical_records(records: Sequence[Mapping[str, str]]) -> bytes:
    """Canonicalize a list of extracted rows — RSS items, listing-table rows.

    Volatile fields are dropped before serialization, so two fetches whose only delta is ``조회수``
    produce the same ``content_hash`` and therefore **no** new version. Field order within a record
    is normalized too: the source's column order is presentation, not content.
    """
    lines: list[str] = []
    for record in records:
        for key in sorted(record):
            if is_volatile_field(key):
                continue
            value = normalize_text(str(record[key]))
            lines.append(f"{normalize_text(key)}\t{value}")
        lines.append("")  # record separator, so two records cannot merge into one
    return "\n".join(lines).encode("utf-8")


def canonical_xml(root: Element, *, drop_tags: Iterable[str] = ()) -> bytes:
    """Canonicalize a structured XML response by content, not by serialization.

    Emits ``path\\ttext`` in document order for every element carrying text. Attribute order,
    whitespace between elements, self-closing style and the XML declaration all vary between
    responses without the regulation changing, so none of them are hashed.
    """
    drop = set(drop_tags)
    lines: list[str] = []

    def walk(element: Element, path: str) -> None:
        if element.tag in drop or is_volatile_field(element.tag):
            return
        here = f"{path}/{element.tag}" if path else element.tag
        text = normalize_text(element.text or "")
        if text:
            lines.append(f"{here}\t{text}")
        for child in element:
            walk(child, here)

    walk(root, "")
    return "\n".join(lines).encode("utf-8")


__all__ = ["canonical_records", "canonical_xml", "is_volatile_field", "normalize_text"]
