"""Baseline — cells, users, sessions, audit_log.

What this migration does that ``create_all`` cannot:

1. **Seeds the 8 cells.** With ``authority`` (4 values) x ``domain`` (2 values) as native enums and
   ``UNIQUE(authority, domain)``, a 9th cell is not a policy violation to catch in review — it
   cannot be inserted.
2. **Makes the audit trail append-only at the database level** (ADR-0011): the application role
   holds no UPDATE or DELETE grant on ``audit_log``, and the hash-chain columns are present from
   the first row. Adding them later would mean rewriting a table that by policy cannot be
   rewritten.

Fresh-DB note: every statement uses IF NOT EXISTS / IF EXISTS, so this no-ops on a database already
built from the models and applies cleanly to a live one.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "regops_app"

CELLS = [
    (authority, domain)
    for authority in ("mfds", "fda", "eu", "nmpa")
    for domain in ("samd", "cosmetic")
]


def upgrade() -> None:
    bind = op.get_bind()

    # --- enums ---------------------------------------------------------------
    op.execute(
        "DO $$ BEGIN CREATE TYPE authority AS ENUM ('mfds','fda','eu','nmpa'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE domain AS ENUM ('samd','cosmetic'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE userrole AS ENUM ('viewer','ra','admin'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )

    # --- cells ---------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cells (
            id          uuid PRIMARY KEY,
            authority   authority   NOT NULL,
            domain      domain      NOT NULL,
            slug        varchar(32) NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_cells_authority_domain UNIQUE (authority, domain),
            CONSTRAINT uq_cells_slug UNIQUE (slug)
        );
        """
    )

    # --- users / sessions ----------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id              uuid PRIMARY KEY,
            email           varchar(320) NOT NULL,
            hashed_password varchar(255) NOT NULL,
            full_name       varchar(255),
            role            userrole     NOT NULL DEFAULT 'viewer',
            is_active       boolean      NOT NULL DEFAULT true,
            created_at      timestamptz  NOT NULL DEFAULT now(),
            updated_at      timestamptz  NOT NULL DEFAULT now(),
            CONSTRAINT uq_users_email UNIQUE (email)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id         uuid PRIMARY KEY,
            user_id    uuid        NOT NULL,
            jti        varchar(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_sessions_jti UNIQUE (jti)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sessions_user_id_expires_at "
        "ON sessions (user_id, expires_at);"
    )

    # --- audit_log (ADR-0011) -----------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            seq         bigserial PRIMARY KEY,
            actor_id    uuid,
            service     varchar(64)  NOT NULL,
            action      varchar(128) NOT NULL,
            entity_type varchar(64),
            entity_id   uuid,
            payload     jsonb        NOT NULL DEFAULT '{}'::jsonb,
            created_at  timestamptz  NOT NULL DEFAULT now(),
            prev_hash   varchar(64)  NOT NULL,
            entry_hash  varchar(64)  NOT NULL,
            CONSTRAINT uq_audit_log_entry_hash UNIQUE (entry_hash)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_log_entity ON audit_log (entity_type, entity_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_log_actor_id_created_at "
        "ON audit_log (actor_id, created_at);"
    )

    # Append-only at the database level.
    #
    # This only binds because the app role is NOT the table owner: an owner bypasses its own
    # grants, so a service connecting as the owner would silently retain UPDATE and DELETE. The
    # role is created by infra/postgres/init/01-app-role.sh; migrations run as the owner, services
    # run as APP_ROLE.
    #
    # A superuser can still edit. That is not a gap this can close — it is the case the hash chain
    # exists to make *detectable* (ADR-0011).
    op.execute(
        f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                GRANT SELECT, INSERT ON audit_log TO {APP_ROLE};
                REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM {APP_ROLE};
                GRANT USAGE, SELECT ON SEQUENCE audit_log_seq_seq TO {APP_ROLE};
            END IF;
        END $$;
        """
    )

    # Everything else stays fully writable by the app role.
    op.execute(
        f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON cells, users, sessions TO {APP_ROLE};
            END IF;
        END $$;
        """
    )

    # --- seed the 8 cells ----------------------------------------------------
    for authority, dom in CELLS:
        bind.execute(
            sa.text(
                """
                INSERT INTO cells (id, authority, domain, slug)
                VALUES (
                    gen_random_uuid(),
                    CAST(:authority AS authority),
                    CAST(:domain AS domain),
                    :slug
                )
                ON CONFLICT (authority, domain) DO NOTHING;
                """
            ).bindparams(
                sa.bindparam("authority", authority, type_=sa.Text()),
                sa.bindparam("domain", dom, type_=sa.Text()),
                sa.bindparam("slug", f"{authority}_{dom}", type_=sa.Text()),
            )
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log;")
    op.execute("DROP TABLE IF EXISTS sessions;")
    op.execute("DROP TABLE IF EXISTS users;")
    op.execute("DROP TABLE IF EXISTS cells;")
    op.execute("DROP TYPE IF EXISTS userrole;")
    op.execute("DROP TYPE IF EXISTS domain;")
    op.execute("DROP TYPE IF EXISTS authority;")
