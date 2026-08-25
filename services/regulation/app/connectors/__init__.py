"""Connector registry. ``sources.connector`` holds a key from here and nothing else.

Resolving by key rather than by import path means a seed row cannot name a connector that does not
exist, and a connector cannot be reached except through :func:`get_connector` — which is where the
non-ingestible refusal lives.
"""

from __future__ import annotations

from typing import Final

from .base import (
    ArtifactRef,
    AttachmentLink,
    AuthorityError,
    Connector,
    ConnectorError,
    FetchedArtifact,
    FetchResult,
    MissingCredentialError,
    NonIngestibleSourceError,
    SourceSpec,
    StandardRecord,
    assert_ingestible,
)
from .ecfr import ECFRConnector
from .http import PoliteFetcher, redact_url, resolve_url
from .law_go_kr import AdmRuleConnector, LawConnector, PendingLawConnector
from .mfds import MfdsListingConnector, MfdsRssConnector
from .recognition_list import RecognitionListConnector

_CONNECTORS: Final[dict[str, type]] = {
    cls.key: cls
    for cls in (
        LawConnector,
        AdmRuleConnector,
        PendingLawConnector,
        MfdsRssConnector,
        MfdsListingConnector,
        RecognitionListConnector,
        ECFRConnector,
    )
}

CONNECTOR_KEYS: Final[frozenset[str]] = frozenset(_CONNECTORS)


def get_connector(key: str, *, fetcher: PoliteFetcher | None = None) -> Connector:
    try:
        cls = _CONNECTORS[key]
    except KeyError:
        raise ConnectorError(
            f"unknown connector {key!r} — known: {sorted(CONNECTOR_KEYS)}"
        ) from None
    connector = cls(fetcher=fetcher)
    return connector  # type: ignore[return-value]


__all__ = [
    "CONNECTOR_KEYS",
    "AdmRuleConnector",
    "ArtifactRef",
    "AttachmentLink",
    "AuthorityError",
    "Connector",
    "ConnectorError",
    "ECFRConnector",
    "FetchResult",
    "FetchedArtifact",
    "LawConnector",
    "MfdsListingConnector",
    "MfdsRssConnector",
    "MissingCredentialError",
    "NonIngestibleSourceError",
    "PendingLawConnector",
    "PoliteFetcher",
    "RecognitionListConnector",
    "SourceSpec",
    "StandardRecord",
    "assert_ingestible",
    "get_connector",
    "redact_url",
    "resolve_url",
]
