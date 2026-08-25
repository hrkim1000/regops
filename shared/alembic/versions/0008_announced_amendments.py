"""``amendment_announcements`` and ``announcement_documents`` — a home for an amendment that has
been announced but whose text does not exist yet.

[ADR-0019](../../../docs/design/ADR-0019-announced-amendments.md), which amends
[ADR-0018](../../../docs/design/ADR-0018-fda-source-model.md) decision 4. A Federal Register final
rule is provenance rather than a Document — its body is not what an RA cites. But "provenance on the
version" cannot hold the rows that matter most: the eCFR 404s on any future date, so a rule
published and not yet in force has **no version to be provenance of**, and FDA carries rules today
effective as far out as 2033-03-07.

Two tables rather than one, for the reason ``document_cells`` exists: the QMSR rule names Parts
**4 and 820**, so a row per (rule, Part) would repeat ``effective_on`` per Part and let the copies
drift.

**No ``text`` column carries regulation.** ``effective_date_phrase`` is the authority's own ``dates``
prose — "This rule is effective February 2, 2026…" — and is retained whether or not the date
resolved, because it is the input a later resolver needs and the only evidence left when resolution
failed (ADR-0013). These rows are evidence *about* the corpus, never evidence *in* it: nothing cites
an announcement.

``authority`` is a plain column and deliberately not an FK to ``cells``: an announcement is about an
authority, not one of its cells, and the QMSR rule reaches both FDA cells at once. Uniqueness is
``(authority, ref)`` so the claim is one an authority can make about its own numbering.

Fresh-DB note: the baseline builds the schema with ``create_all`` from the models, which now include
both tables, so every statement uses IF NOT EXISTS and this no-ops there while applying cleanly to a
live database.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

APP_ROLE = "regops_app"

NEW_TABLES = ("announcement_documents", "amendment_announcements")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS amendment_announcements (
            id                       uuid          PRIMARY KEY,
            authority                varchar(16)   NOT NULL,
            ref                      varchar(64)   NOT NULL,
            citation                 varchar(64),
            title                    varchar(512),
            published_on             date,
            effective_on             date,
            effective_date_phrase    text,
            official_url             varchar(512),
            source_id                uuid          REFERENCES sources(id),
            last_seen_at             timestamptz,
            created_at               timestamptz   NOT NULL DEFAULT now(),
            updated_at               timestamptz   NOT NULL DEFAULT now(),
            CONSTRAINT uq_amendment_announcements_identity UNIQUE (authority, ref)
        );
        """
    )
    # The pending-amendment question is "effective_on in the future", asked per authority — the
    # blind spot ADR-0018 decision 7 names, which this table exists to make countable.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_amendment_announcements_effective "
        "ON amendment_announcements (authority, effective_on);"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS announcement_documents (
            announcement_id  uuid         NOT NULL
                REFERENCES amendment_announcements(id) ON DELETE CASCADE,
            document_id      uuid         NOT NULL
                REFERENCES documents(id) ON DELETE CASCADE,
            created_at       timestamptz  NOT NULL DEFAULT now(),
            PRIMARY KEY (announcement_id, document_id)
        );
        """
    )
    # The join runs from the Document side too: "what has been announced against this Part".
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_announcement_documents_document "
        "ON announcement_documents (document_id);"
    )

    for table in NEW_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {APP_ROLE};")


def downgrade() -> None:
    for table in NEW_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table};")
