"""Shared constants. No magic literals in service code."""

from enum import StrEnum
from typing import Final


class Authority(StrEnum):
    """The only four regulatory authorities in scope (CLAUDE.md § Architecture rules)."""

    MFDS = "mfds"
    FDA = "fda"
    EU = "eu"
    NMPA = "nmpa"


class Domain(StrEnum):
    """The only two product domains in scope."""

    SAMD = "samd"
    COSMETIC = "cosmetic"


#: Exactly 8 cells. ``Authority`` x ``Domain`` is the complete coverage target; the UNIQUE
#: constraint on (authority, domain) plus these two enums make a 9th row structurally impossible.
CELLS: Final[tuple[tuple[Authority, Domain], ...]] = tuple(
    (authority, domain) for authority in Authority for domain in Domain
)

CELL_COUNT: Final[int] = 8


class Role(StrEnum):
    """Phase 1 RBAC (ADR-0005 decision 5). ``compliance`` arrives in Phase 2."""

    VIEWER = "viewer"
    RA = "ra"
    ADMIN = "admin"


#: Ordered least- to most-privileged; each role subsumes the ones before it.
ROLE_ORDER: Final[tuple[Role, ...]] = (Role.VIEWER, Role.RA, Role.ADMIN)


class SourceTier(StrEnum):
    """Source collectability. Tier D source text is never ingested."""

    A = "a"  # public API
    B = "b"  # static files / RSS
    C = "c"  # scraping
    D = "d"  # copyright-protected — metadata only, never body text


#: Token types. ``access`` is the only one Phase 0 issues.
TOKEN_TYPE_ACCESS: Final[str] = "access"
TOKEN_TYPE_REFRESH: Final[str] = "refresh"

#: Embeddings are pinned regardless of the generation provider (ADR-0005 decision 7).
EMBEDDING_MODEL: Final[str] = "nomic-embed-text"
EMBEDDING_DIM: Final[int] = 768

#: Genesis value for the first audit_log row's ``prev_hash`` (ADR-0011).
AUDIT_CHAIN_GENESIS: Final[str] = "0" * 64
