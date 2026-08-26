--
-- RegOps authoritative schema dump.
--
-- Generated from the live database after `alembic upgrade head`. Update this file in the same
-- change as any migration (`.claude/skills/db-migration` rule 4) — it is what a reviewer reads
-- instead of replaying the migration history.
--
-- NOTE: dumped with --no-privileges, so the audit_log GRANT/REVOKE from migration 0001 and the
-- regulation-table grants from 0002/0003/0004/0005 are NOT represented here. Append-only
-- enforcement lives in the migration and in infra/postgres/init/01-app-role.sh (ADR-0011).
--
-- Two *presences* are load-bearing:
--   * `assert_ir_has_citation()` and its two DEFERRABLE constraint triggers. "An IR without a
--     citation does not exist" (ADR-0004 decision 2) is a schema guarantee, not a convention the
--     extractor happens to follow — a FK cannot express "at least one" in that direction, so the
--     check runs at commit from both sides (inserting an uncited IR, and deleting the last
--     citation off an existing one).
--   * the `vector` extension, and clause_embeddings.embedding as vector(768) with an HNSW
--     cosine index. This is why docker-compose's `db` is pgvector/pgvector:pg16 rather than stock
--     postgres — see migration 0005.
--   * `UNIQUE NULLS NOT DISTINCT` on alerts and alert_subscriptions. tenant_id is null until
--     Phase 3 and PostgreSQL's default treats two nulls as distinct, so a plain UNIQUE would
--     enforce nothing at all today — which is exactly when phase1.4's "one amendment is one
--     alert, not forty" is being built. PostgreSQL 15+; the stack is 16.
--
-- Five absences in this file are load-bearing and deliberate:
--   * fetch_observations has no request-URL column   -- ADR-0003 decision 13
--   * standard_references has no text column and no varchar over 512  -- ADR-0002 decision 2
--   * clauses has no domain-specific column          -- ADR-0002 decision 3; a SaMD-only or
--     Cosmetic-only column here is the phase 1.1 falsifier firing, not a schema detail
--   * there is no annex_rows table                   -- ADR-0014; an annex table row is a Clause,
--     so the citation contract needs no branch and there is no second store to keep in sync
--   * answer_citations is NOT ir_citations           -- ADR-0006 decision 10; they share a shape
--     and nothing else, because an amendment stales an IR and supersedes an answer
--

--
-- PostgreSQL database dump
--

\restrict ekPeHJ9gc3MBeswEtUjt7ioVm0fFNF6iQk5YbGbvsIoDMHyXJejZdFTY8qxLava

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg12+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: alert_channel; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.alert_channel AS ENUM (
    'in_app',
    'webhook',
    'email'
);


--
-- Name: alert_severity; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.alert_severity AS ENUM (
    'high',
    'medium',
    'low'
);


--
-- Name: alert_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.alert_status AS ENUM (
    'pending',
    'delivered',
    'failed'
);


--
-- Name: answer_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.answer_status AS ENUM (
    'answered',
    'needs_verification',
    'needs_review'
);


--
-- Name: attachment_kind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.attachment_kind AS ENUM (
    'annex_file',
    'form',
    'other'
);


--
-- Name: authority; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.authority AS ENUM (
    'mfds',
    'fda',
    'eu',
    'nmpa'
);


--
-- Name: change_kind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.change_kind AS ENUM (
    'added',
    'removed',
    'modified',
    'renumbered',
    'moved'
);


--
-- Name: classification_kind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.classification_kind AS ENUM (
    'obligation_bearing',
    'excluded'
);


--
-- Name: clause_kind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.clause_kind AS ENUM (
    'prose',
    'heading',
    'table',
    'table_row',
    'form'
);


--
-- Name: delivery_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.delivery_status AS ENUM (
    'pending',
    'sent',
    'failed'
);


--
-- Name: doc_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.doc_type AS ENUM (
    'law',
    'decree',
    'enforcement_rule',
    'notice',
    'annex',
    'guidance',
    'feed',
    'regulation',
    'codified_statute'
);


--
-- Name: domain; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.domain AS ENUM (
    'samd',
    'cosmetic'
);


--
-- Name: drift_signal; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.drift_signal AS ENUM (
    'zero_records',
    'record_count_delta',
    'missing_root',
    'auth_failure',
    'empty_annex_body',
    'zero_clauses',
    'clause_count_delta'
);


--
-- Name: embedding_scope; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.embedding_scope AS ENUM (
    'article',
    'article_fragment',
    'table_header',
    'form'
);


--
-- Name: exclusion_reason; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.exclusion_reason AS ENUM (
    'definition',
    'scope',
    'heading',
    'permissive',
    'procedural',
    'delegation',
    'table_container',
    'form',
    'empty',
    'no_obligation',
    'unparseable',
    'non_binding'
);


--
-- Name: extraction_run_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.extraction_run_status AS ENUM (
    'running',
    'completed',
    'failed'
);


--
-- Name: fetch_outcome; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.fetch_outcome AS ENUM (
    'changed',
    'unchanged',
    'not_modified',
    'skipped',
    'error'
);


--
-- Name: ir_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.rejection_reason AS ENUM (
    'not_an_obligation',
    'misread_clause',
    'not_atomic',
    'wrong_citation',
    'duplicate'
);


--
-- Name: ir_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.ir_status AS ENUM (
    'draft',
    'locked',
    'rejected',
    'stale',
    'superseded'
);


--
-- Name: source_block; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.source_block AS ENUM (
    'primary_laws',
    'regulations',
    'standards',
    'guidance',
    'registration',
    'ingredient',
    'gmp',
    'safety',
    'official_sources'
);


--
-- Name: source_tier; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.source_tier AS ENUM (
    'a',
    'b',
    'c',
    'd'
);


--
-- Name: standard_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.standard_status AS ENUM (
    'recognized',
    'harmonized',
    'withdrawn',
    'superseded',
    'unknown'
);


--
-- Name: userrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.userrole AS ENUM (
    'viewer',
    'ra',
    'admin'
);


--
-- Name: verification_verdict; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.verification_verdict AS ENUM (
    'supported',
    'partial',
    'unsupported'
);


--
-- Name: assert_ir_has_citation(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.assert_ir_has_citation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE
            target uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                target := OLD.ir_id;
            ELSE
                target := NEW.id;
            END IF;

            -- The check is deferred to commit, so the row it was queued for may have been deleted
            -- since — by a CASCADE from `irs`, or by a later statement in the same transaction.
            -- An IR that no longer exists cannot be an uncited IR, and asserting about one turns
            -- ordinary cleanup ("unlink, then delete") into a spurious violation.
            IF NOT EXISTS (SELECT 1 FROM irs WHERE id = target) THEN
                RETURN NULL;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM ir_citations WHERE ir_id = target) THEN
                RAISE EXCEPTION
                    'IR % has no citation; an IR without a citation does not exist '
                    '(ADR-0004 decision 2)', target
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END;
        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: alert_deliveries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_deliveries (
    id uuid NOT NULL,
    tenant_id uuid,
    alert_id uuid NOT NULL,
    subscription_id uuid NOT NULL,
    channel public.alert_channel NOT NULL,
    destination text,
    attempt integer DEFAULT 1 NOT NULL,
    status public.delivery_status DEFAULT 'pending'::public.delivery_status NOT NULL,
    error character varying(512),
    attempted_at timestamp with time zone DEFAULT now() NOT NULL,
    delivered_at timestamp with time zone,
    next_retry_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_alert_deliveries_attempt_positive CHECK ((attempt >= 1))
);


--
-- Name: alert_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_subscriptions (
    id uuid NOT NULL,
    tenant_id uuid,
    subscriber_id uuid NOT NULL,
    cell_id uuid NOT NULL,
    channel public.alert_channel DEFAULT 'in_app'::public.alert_channel NOT NULL,
    destination text,
    min_severity public.alert_severity DEFAULT 'low'::public.alert_severity NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_alert_subscriptions_destination_for_remote_channel CHECK (((channel = 'in_app'::public.alert_channel) OR (destination IS NOT NULL)))
);


--
-- Name: alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts (
    id uuid NOT NULL,
    tenant_id uuid,
    cell_id uuid NOT NULL,
    document_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    from_version_id uuid,
    severity public.alert_severity NOT NULL,
    status public.alert_status DEFAULT 'pending'::public.alert_status NOT NULL,
    title text NOT NULL,
    summary text DEFAULT ''::text NOT NULL,
    clause_count integer DEFAULT 0 NOT NULL,
    change_event_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    clause_references jsonb,
    cited_by_locked_ir boolean DEFAULT false NOT NULL,
    locked_ir_count integer DEFAULT 0 NOT NULL,
    published_at timestamp with time zone,
    retrieved_at timestamp with time zone,
    detected_at timestamp with time zone NOT NULL,
    owner_id uuid,
    assigned_by uuid,
    assigned_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_alerts_clause_count_positive CHECK ((clause_count > 0))
);


--
-- Name: answer_citations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.answer_citations (
    id uuid NOT NULL,
    answer_id uuid NOT NULL,
    claim_index integer DEFAULT 0 NOT NULL,
    document_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    clause_path character varying(512) NOT NULL,
    effective_date date,
    superseded_at timestamp with time zone,
    superseded_by_diff_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: answers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.answers (
    id uuid NOT NULL,
    query_id uuid NOT NULL,
    tenant_id uuid,
    text text DEFAULT ''::text NOT NULL,
    status public.answer_status NOT NULL,
    confidence double precision DEFAULT 0 NOT NULL,
    no_answer_reason character varying(32),
    document_version_scope uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    effective_date_scope date,
    straddles_effective_date boolean DEFAULT false NOT NULL,
    llm_provider character varying(32) NOT NULL,
    llm_model character varying(64) NOT NULL,
    prompt_version character varying(32) NOT NULL,
    retrieval_version character varying(32) NOT NULL,
    superseded_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_answers_confidence_range CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision)))
);


--
-- Name: attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attachments (
    id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    kind public.attachment_kind NOT NULL,
    title text,
    ordinal integer DEFAULT 0 NOT NULL,
    file_format character varying(16),
    source_url text,
    content_hash character varying(64),
    raw_object_key character varying(160),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    seq bigint NOT NULL,
    actor_id uuid,
    service character varying(64) NOT NULL,
    action character varying(128) NOT NULL,
    entity_type character varying(64),
    entity_id uuid,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    prev_hash character varying(64) NOT NULL,
    entry_hash character varying(64) NOT NULL
);


--
-- Name: audit_log_seq_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_log_seq_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_log_seq_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_log_seq_seq OWNED BY public.audit_log.seq;


--
-- Name: cells; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cells (
    id uuid NOT NULL,
    authority public.authority NOT NULL,
    domain public.domain NOT NULL,
    slug character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: change_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.change_events (
    id uuid NOT NULL,
    clause_diff_id uuid NOT NULL,
    cell_id uuid NOT NULL,
    document_id uuid NOT NULL,
    detected_at timestamp with time zone NOT NULL,
    severity character varying(16),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: clause_classifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clause_classifications (
    id uuid NOT NULL,
    clause_id uuid NOT NULL,
    domain_profile public.domain NOT NULL,
    kind public.classification_kind NOT NULL,
    exclusion_reason public.exclusion_reason,
    exclusion_note text,
    extraction_run_id uuid,
    classified_by uuid,
    classified_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_clause_classifications_reason CHECK (((kind = 'excluded'::public.classification_kind) = (exclusion_reason IS NOT NULL)))
);


--
-- Name: clause_diffs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clause_diffs (
    id uuid NOT NULL,
    from_version_id uuid,
    to_version_id uuid NOT NULL,
    clause_path character varying(512) NOT NULL,
    from_clause_path character varying(512),
    change_kind public.change_kind NOT NULL,
    from_clause_id uuid,
    to_clause_id uuid,
    similarity double precision,
    match_basis character varying(32),
    needs_review boolean DEFAULT false NOT NULL,
    reviewed_at timestamp with time zone,
    reviewed_by uuid,
    review_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: clause_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clause_embeddings (
    id uuid NOT NULL,
    clause_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    scope public.embedding_scope NOT NULL,
    fragment_index integer DEFAULT 0 NOT NULL,
    passage text NOT NULL,
    child_clause_paths text[] DEFAULT '{}'::text[] NOT NULL,
    content_hash character varying(64) NOT NULL,
    embedding public.vector(768) NOT NULL,
    model character varying(64) NOT NULL,
    dim integer DEFAULT 768 NOT NULL,
    passage_version character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_clause_embeddings_fragment_index_nonneg CHECK ((fragment_index >= 0))
);


--
-- Name: clauses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clauses (
    id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    clause_path character varying(512) NOT NULL,
    path_segments text[] NOT NULL,
    level integer DEFAULT 1 NOT NULL,
    ordinal integer DEFAULT 0 NOT NULL,
    kind public.clause_kind DEFAULT 'prose'::public.clause_kind NOT NULL,
    heading text,
    text text DEFAULT ''::text NOT NULL,
    row_columns jsonb,
    effective_date date,
    effective_date_phrase text,
    parent_clause_id uuid,
    source_ref character varying(64),
    moved_from_ref character varying(64),
    moved_to_ref character varying(64),
    authority_changed boolean,
    content_hash character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: document_cells; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_cells (
    document_id uuid NOT NULL,
    cell_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: document_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_versions (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    version_group_id uuid NOT NULL,
    version_label character varying(64),
    language character varying(8) DEFAULT 'ko'::character varying NOT NULL,
    content_hash character varying(64) NOT NULL,
    raw_object_key character varying(160) NOT NULL,
    raw_bytes integer DEFAULT 0 NOT NULL,
    content_type character varying(128),
    retrieved_at timestamp with time zone NOT NULL,
    published_at timestamp with time zone,
    effective_date date,
    effective_date_phrase text,
    authority_removed_paths jsonb,
    parser_version character varying(32),
    fetch_observation_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id uuid NOT NULL,
    canonical_key character varying(255) NOT NULL,
    title text NOT NULL,
    doc_type public.doc_type NOT NULL,
    issuing_authority character varying(128),
    parent_document_id uuid,
    annex_no character varying(32),
    source_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_documents_annex_parent CHECK (((doc_type = 'annex'::public.doc_type) = (parent_document_id IS NOT NULL)))
);


--
-- Name: extraction_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.extraction_runs (
    id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    domain_profile public.domain NOT NULL,
    rule_version character varying(32) NOT NULL,
    prompt_version character varying(32) NOT NULL,
    llm_provider character varying(32) NOT NULL,
    llm_model character varying(64) NOT NULL,
    temperature double precision,
    status public.extraction_run_status DEFAULT 'running'::public.extraction_run_status NOT NULL,
    clauses_seen integer DEFAULT 0 NOT NULL,
    irs_written integer DEFAULT 0 NOT NULL,
    rejected_uncited integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    error text,
    CONSTRAINT ck_extraction_runs_counts_nonneg CHECK (((clauses_seen >= 0) AND (irs_written >= 0) AND (rejected_uncited >= 0)))
);


--
-- Name: fetch_observations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fetch_observations (
    id uuid NOT NULL,
    source_id uuid NOT NULL,
    fetched_at timestamp with time zone NOT NULL,
    http_status integer,
    content_hash character varying(64),
    connector_version character varying(32) NOT NULL,
    outcome public.fetch_outcome NOT NULL,
    published_at timestamp with time zone,
    artifact_count integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ir_citations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ir_citations (
    id uuid NOT NULL,
    ir_id uuid NOT NULL,
    document_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    clause_path character varying(512) NOT NULL,
    effective_date date,
    superseded_at timestamp with time zone,
    superseded_by_diff_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ir_standard_citations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ir_standard_citations (
    id uuid NOT NULL,
    ir_id uuid NOT NULL,
    standard_reference_id uuid NOT NULL,
    reference_text text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: irs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.irs (
    id uuid NOT NULL,
    domain_profile public.domain NOT NULL,
    bearer text,
    modal character varying(64),
    statement text NOT NULL,
    condition_text text,
    taxonomy_code character varying(64),
    status public.ir_status DEFAULT 'draft'::public.ir_status NOT NULL,
    supersedes_ir_id uuid,
    stale_since timestamp with time zone,
    locked_by uuid,
    locked_at timestamp with time zone,
    rejected_by uuid,
    rejected_at timestamp with time zone,
    rejection_reason public.rejection_reason,
    rejection_note text,
    llm_provider character varying(32),
    llm_model character varying(64),
    prompt_version character varying(32),
    rule_version character varying(32),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    extraction_run_id uuid
);


--
-- Name: queries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.queries (
    id uuid NOT NULL,
    tenant_id uuid,
    cell_id uuid NOT NULL,
    cross_cell boolean DEFAULT false NOT NULL,
    text text NOT NULL,
    asked_by uuid,
    asked_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    jti character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: source_discovery_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_discovery_runs (
    id uuid NOT NULL,
    authority public.authority NOT NULL,
    ran_at timestamp with time zone NOT NULL,
    upstream_count integer DEFAULT 0 NOT NULL,
    matched integer DEFAULT 0 NOT NULL,
    unmatched integer DEFAULT 0 NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: source_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_schedules (
    source_id uuid NOT NULL,
    interval_seconds integer NOT NULL,
    next_due_at timestamp with time zone NOT NULL,
    last_started_at timestamp with time zone,
    last_completed_at timestamp with time zone,
    enabled boolean DEFAULT true NOT NULL,
    consecutive_failures integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sources (
    id uuid NOT NULL,
    slug character varying(160) NOT NULL,
    cell_id uuid NOT NULL,
    block public.source_block NOT NULL,
    ordinal integer DEFAULT 0 NOT NULL,
    title text NOT NULL,
    url_template text,
    tier public.source_tier NOT NULL,
    ingestible boolean DEFAULT true NOT NULL,
    connector character varying(64),
    params jsonb DEFAULT '{}'::jsonb NOT NULL,
    interval_override_seconds integer,
    interval_override_reason text,
    http_etag character varying(255),
    http_last_modified character varying(64),
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sources_override_reason CHECK (((interval_override_seconds IS NULL) = (interval_override_reason IS NULL)))
);


--
-- Name: standard_references; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.amendment_announcements (
    id uuid NOT NULL,
    authority character varying(16) NOT NULL,
    ref character varying(64) NOT NULL,
    citation character varying(64),
    title character varying(512),
    published_on date,
    effective_on date,
    effective_date_phrase text,
    official_url character varying(512),
    source_id uuid,
    last_seen_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


CREATE TABLE public.announcement_documents (
    announcement_id uuid NOT NULL,
    document_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


CREATE TABLE public.standard_references (
    id uuid NOT NULL,
    number character varying(64) NOT NULL,
    edition character varying(32),
    issuing_body character varying(64),
    recognition_number character varying(64),
    title character varying(512),
    effective_date date,
    withdrawal_date date,
    status public.standard_status DEFAULT 'unknown'::public.standard_status NOT NULL,
    official_url character varying(512),
    cell_id uuid,
    source_id uuid,
    last_seen_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: structure_drift_alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.structure_drift_alerts (
    id uuid NOT NULL,
    source_id uuid NOT NULL,
    detected_at timestamp with time zone NOT NULL,
    signal public.drift_signal NOT NULL,
    expected text,
    actual text,
    resolved_at timestamp with time zone,
    resolved_by uuid,
    resolution_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying(320) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    full_name character varying(255),
    role public.userrole DEFAULT 'viewer'::public.userrole NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: verification_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.verification_results (
    id uuid NOT NULL,
    answer_id uuid NOT NULL,
    claim_index integer NOT NULL,
    verdict public.verification_verdict NOT NULL,
    reason text,
    verifier_provider character varying(32) NOT NULL,
    verifier_model character varying(64) NOT NULL,
    prompt_version character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_log seq; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log ALTER COLUMN seq SET DEFAULT nextval('public.audit_log_seq_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: alert_deliveries alert_deliveries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_deliveries
    ADD CONSTRAINT alert_deliveries_pkey PRIMARY KEY (id);


--
-- Name: alert_subscriptions alert_subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_subscriptions
    ADD CONSTRAINT alert_subscriptions_pkey PRIMARY KEY (id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id);


--
-- Name: answer_citations answer_citations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_citations
    ADD CONSTRAINT answer_citations_pkey PRIMARY KEY (id);


--
-- Name: answers answers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_pkey PRIMARY KEY (id);


--
-- Name: attachments attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT attachments_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (seq);


--
-- Name: cells cells_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cells
    ADD CONSTRAINT cells_pkey PRIMARY KEY (id);


--
-- Name: change_events change_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.change_events
    ADD CONSTRAINT change_events_pkey PRIMARY KEY (id);


--
-- Name: clause_classifications clause_classifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_classifications
    ADD CONSTRAINT clause_classifications_pkey PRIMARY KEY (id);


--
-- Name: clause_diffs clause_diffs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_diffs
    ADD CONSTRAINT clause_diffs_pkey PRIMARY KEY (id);


--
-- Name: clause_embeddings clause_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_embeddings
    ADD CONSTRAINT clause_embeddings_pkey PRIMARY KEY (id);


--
-- Name: clauses clauses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clauses
    ADD CONSTRAINT clauses_pkey PRIMARY KEY (id);


--
-- Name: document_cells document_cells_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_cells
    ADD CONSTRAINT document_cells_pkey PRIMARY KEY (document_id, cell_id);


--
-- Name: document_versions document_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT document_versions_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: extraction_runs extraction_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction_runs
    ADD CONSTRAINT extraction_runs_pkey PRIMARY KEY (id);


--
-- Name: fetch_observations fetch_observations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fetch_observations
    ADD CONSTRAINT fetch_observations_pkey PRIMARY KEY (id);


--
-- Name: ir_citations ir_citations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_citations
    ADD CONSTRAINT ir_citations_pkey PRIMARY KEY (id);


--
-- Name: ir_standard_citations ir_standard_citations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_standard_citations
    ADD CONSTRAINT ir_standard_citations_pkey PRIMARY KEY (id);


--
-- Name: irs irs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.irs
    ADD CONSTRAINT irs_pkey PRIMARY KEY (id);


--
-- Name: queries queries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.queries
    ADD CONSTRAINT queries_pkey PRIMARY KEY (id);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: source_discovery_runs source_discovery_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_discovery_runs
    ADD CONSTRAINT source_discovery_runs_pkey PRIMARY KEY (id);


--
-- Name: source_schedules source_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_schedules
    ADD CONSTRAINT source_schedules_pkey PRIMARY KEY (source_id);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (id);


--
-- Name: standard_references standard_references_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.standard_references
    ADD CONSTRAINT standard_references_pkey PRIMARY KEY (id);


--
-- Name: structure_drift_alerts structure_drift_alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.structure_drift_alerts
    ADD CONSTRAINT structure_drift_alerts_pkey PRIMARY KEY (id);


--
-- Name: alert_deliveries uq_alert_deliveries_attempt; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_deliveries
    ADD CONSTRAINT uq_alert_deliveries_attempt UNIQUE (alert_id, subscription_id, attempt);


--
-- Name: alert_subscriptions uq_alert_subscriptions_target; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_subscriptions
    ADD CONSTRAINT uq_alert_subscriptions_target UNIQUE NULLS NOT DISTINCT (tenant_id, subscriber_id, cell_id, channel);


--
-- Name: alerts uq_alerts_target; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT uq_alerts_target UNIQUE NULLS NOT DISTINCT (tenant_id, cell_id, document_version_id);


--
-- Name: answer_citations uq_answer_citations_target; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_citations
    ADD CONSTRAINT uq_answer_citations_target UNIQUE (answer_id, claim_index, document_version_id, clause_path);


--
-- Name: attachments uq_attachments_version_kind_ordinal; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT uq_attachments_version_kind_ordinal UNIQUE (document_version_id, kind, ordinal);


--
-- Name: audit_log uq_audit_log_entry_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT uq_audit_log_entry_hash UNIQUE (entry_hash);


--
-- Name: cells uq_cells_authority_domain; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cells
    ADD CONSTRAINT uq_cells_authority_domain UNIQUE (authority, domain);


--
-- Name: cells uq_cells_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cells
    ADD CONSTRAINT uq_cells_slug UNIQUE (slug);


--
-- Name: change_events uq_change_events_diff_cell; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.change_events
    ADD CONSTRAINT uq_change_events_diff_cell UNIQUE (clause_diff_id, cell_id);


--
-- Name: clause_classifications uq_clause_classifications_target; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_classifications
    ADD CONSTRAINT uq_clause_classifications_target UNIQUE (clause_id, domain_profile);


--
-- Name: clause_diffs uq_clause_diffs_target; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_diffs
    ADD CONSTRAINT uq_clause_diffs_target UNIQUE (to_version_id, clause_path, change_kind);


--
-- Name: clause_embeddings uq_clause_embeddings_fragment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_embeddings
    ADD CONSTRAINT uq_clause_embeddings_fragment UNIQUE (clause_id, fragment_index);


--
-- Name: clauses uq_clauses_version_path; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clauses
    ADD CONSTRAINT uq_clauses_version_path UNIQUE (document_version_id, clause_path);


--
-- Name: document_versions uq_document_versions_content; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT uq_document_versions_content UNIQUE (document_id, language, content_hash);


--
-- Name: documents uq_documents_canonical_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT uq_documents_canonical_key UNIQUE (canonical_key);


--
-- Name: ir_citations uq_ir_citations_target; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_citations
    ADD CONSTRAINT uq_ir_citations_target UNIQUE (ir_id, document_version_id, clause_path);


--
-- Name: ir_standard_citations uq_ir_standard_citations_target; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_standard_citations
    ADD CONSTRAINT uq_ir_standard_citations_target UNIQUE (ir_id, standard_reference_id);


--
-- Name: sessions uq_sessions_jti; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT uq_sessions_jti UNIQUE (jti);


--
-- Name: sources uq_sources_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT uq_sources_slug UNIQUE (slug);


--
-- Name: standard_references uq_standard_references_identity; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.standard_references
    ADD CONSTRAINT uq_standard_references_identity UNIQUE (number, edition, recognition_number);


--
-- Name: users uq_users_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_email UNIQUE (email);


--
-- Name: verification_results uq_verification_results_claim; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_results
    ADD CONSTRAINT uq_verification_results_claim UNIQUE (answer_id, claim_index);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: verification_results verification_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_results
    ADD CONSTRAINT verification_results_pkey PRIMARY KEY (id);


--
-- Name: ix_alert_deliveries_alert_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_deliveries_alert_id ON public.alert_deliveries USING btree (alert_id);


--
-- Name: ix_alert_deliveries_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_deliveries_status ON public.alert_deliveries USING btree (status);


--
-- Name: ix_alert_deliveries_subscription_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_deliveries_subscription_id ON public.alert_deliveries USING btree (subscription_id);


--
-- Name: ix_alert_subscriptions_cell_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_subscriptions_cell_id ON public.alert_subscriptions USING btree (cell_id);


--
-- Name: ix_alert_subscriptions_subscriber_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_subscriptions_subscriber_id ON public.alert_subscriptions USING btree (subscriber_id);


--
-- Name: ix_alert_subscriptions_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_subscriptions_tenant_id ON public.alert_subscriptions USING btree (tenant_id);


--
-- Name: ix_alerts_cell_id_detected_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alerts_cell_id_detected_at ON public.alerts USING btree (cell_id, detected_at);


--
-- Name: ix_alerts_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alerts_owner_id ON public.alerts USING btree (owner_id);


--
-- Name: ix_alerts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alerts_status ON public.alerts USING btree (status);


--
-- Name: ix_alerts_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alerts_tenant_id ON public.alerts USING btree (tenant_id);


--
-- Name: ix_answer_citations_answer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_answer_citations_answer_id ON public.answer_citations USING btree (answer_id);


--
-- Name: ix_answer_citations_version_path; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_answer_citations_version_path ON public.answer_citations USING btree (document_version_id, clause_path);


--
-- Name: ix_answers_query_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_answers_query_id ON public.answers USING btree (query_id);


--
-- Name: ix_answers_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_answers_status ON public.answers USING btree (status);


--
-- Name: ix_answers_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_answers_tenant_id ON public.answers USING btree (tenant_id);


--
-- Name: ix_audit_log_actor_id_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_actor_id_created_at ON public.audit_log USING btree (actor_id, created_at);


--
-- Name: ix_audit_log_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_entity ON public.audit_log USING btree (entity_type, entity_id);


--
-- Name: ix_change_events_cell_id_detected_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_change_events_cell_id_detected_at ON public.change_events USING btree (cell_id, detected_at);


--
-- Name: ix_change_events_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_change_events_document_id ON public.change_events USING btree (document_id);


--
-- Name: ix_clause_classifications_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clause_classifications_kind ON public.clause_classifications USING btree (kind);


--
-- Name: ix_clause_classifications_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clause_classifications_run ON public.clause_classifications USING btree (extraction_run_id);


--
-- Name: ix_clause_diffs_from_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clause_diffs_from_version_id ON public.clause_diffs USING btree (from_version_id);


--
-- Name: ix_clause_diffs_needs_review; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clause_diffs_needs_review ON public.clause_diffs USING btree (needs_review) WHERE needs_review;


--
-- Name: ix_clause_diffs_to_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clause_diffs_to_version_id ON public.clause_diffs USING btree (to_version_id);


--
-- Name: ix_clause_embeddings_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clause_embeddings_hnsw ON public.clause_embeddings USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: ix_clause_embeddings_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clause_embeddings_model ON public.clause_embeddings USING btree (model);


--
-- Name: ix_clause_embeddings_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clause_embeddings_version ON public.clause_embeddings USING btree (document_version_id);


--
-- Name: ix_clauses_clause_path; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clauses_clause_path ON public.clauses USING btree (clause_path);


--
-- Name: ix_clauses_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clauses_content_hash ON public.clauses USING btree (content_hash);


--
-- Name: ix_clauses_document_version_id_ordinal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clauses_document_version_id_ordinal ON public.clauses USING btree (document_version_id, ordinal);


--
-- Name: ix_clauses_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clauses_fts ON public.clauses USING gin (to_tsvector('simple'::regconfig, ((COALESCE(heading, ''::text) || ' '::text) || COALESCE(text, ''::text))));


--
-- Name: ix_clauses_fts_english; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clauses_fts_english ON public.clauses USING gin (to_tsvector('english'::regconfig, ((COALESCE(heading, ''::text) || ' '::text) || COALESCE(text, ''::text))));


--
-- Name: ix_clauses_path_segments; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clauses_path_segments ON public.clauses USING gin (path_segments);


--
-- Name: ix_document_versions_document_id_retrieved_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_versions_document_id_retrieved_at ON public.document_versions USING btree (document_id, retrieved_at);


--
-- Name: ix_document_versions_version_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_versions_version_group_id ON public.document_versions USING btree (version_group_id);


--
-- Name: ix_documents_parent_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_parent_document_id ON public.documents USING btree (parent_document_id);


--
-- Name: ix_extraction_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_extraction_runs_status ON public.extraction_runs USING btree (status);


--
-- Name: ix_extraction_runs_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_extraction_runs_version ON public.extraction_runs USING btree (document_version_id, started_at);


--
-- Name: ix_fetch_observations_source_id_fetched_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fetch_observations_source_id_fetched_at ON public.fetch_observations USING btree (source_id, fetched_at);


--
-- Name: ix_ir_citations_ir_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ir_citations_ir_id ON public.ir_citations USING btree (ir_id);


--
-- Name: ix_ir_citations_version_path; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ir_citations_version_path ON public.ir_citations USING btree (document_version_id, clause_path);


--
-- Name: ix_ir_standard_citations_ir_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ir_standard_citations_ir_id ON public.ir_standard_citations USING btree (ir_id);


--
-- Name: ix_irs_extraction_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_irs_extraction_run_id ON public.irs USING btree (extraction_run_id);


--
-- Name: ix_irs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_irs_status ON public.irs USING btree (status);


--
-- Name: ix_irs_supersedes_ir_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_irs_supersedes_ir_id ON public.irs USING btree (supersedes_ir_id) WHERE (supersedes_ir_id IS NOT NULL);


--
-- Name: ix_queries_cell_asked_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_queries_cell_asked_at ON public.queries USING btree (cell_id, asked_at);


--
-- Name: ix_queries_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_queries_tenant_id ON public.queries USING btree (tenant_id);


--
-- Name: ix_sessions_user_id_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sessions_user_id_expires_at ON public.sessions USING btree (user_id, expires_at);


--
-- Name: ix_source_schedules_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_source_schedules_due ON public.source_schedules USING btree (next_due_at) WHERE enabled;


--
-- Name: ix_sources_cell_id_block; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sources_cell_id_block ON public.sources USING btree (cell_id, block);


--
-- Name: ix_structure_drift_alerts_source_id_resolved_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_structure_drift_alerts_source_id_resolved_at ON public.structure_drift_alerts USING btree (source_id, resolved_at);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_verification_results_verdict; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_verification_results_verdict ON public.verification_results USING btree (verdict);


--
-- Name: ir_citations trg_ir_citations_require_citation; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER trg_ir_citations_require_citation AFTER DELETE ON public.ir_citations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.assert_ir_has_citation();


--
-- Name: irs trg_irs_require_citation; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER trg_irs_require_citation AFTER INSERT OR UPDATE ON public.irs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.assert_ir_has_citation();


--
-- Name: alert_deliveries alert_deliveries_alert_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_deliveries
    ADD CONSTRAINT alert_deliveries_alert_id_fkey FOREIGN KEY (alert_id) REFERENCES public.alerts(id) ON DELETE CASCADE;


--
-- Name: alert_deliveries alert_deliveries_subscription_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_deliveries
    ADD CONSTRAINT alert_deliveries_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.alert_subscriptions(id) ON DELETE CASCADE;


--
-- Name: alert_subscriptions alert_subscriptions_cell_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_subscriptions
    ADD CONSTRAINT alert_subscriptions_cell_id_fkey FOREIGN KEY (cell_id) REFERENCES public.cells(id);


--
-- Name: alerts alerts_cell_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_cell_id_fkey FOREIGN KEY (cell_id) REFERENCES public.cells(id);


--
-- Name: alerts alerts_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: alerts alerts_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id);


--
-- Name: alerts alerts_from_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_from_version_id_fkey FOREIGN KEY (from_version_id) REFERENCES public.document_versions(id);


--
-- Name: answer_citations answer_citations_answer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_citations
    ADD CONSTRAINT answer_citations_answer_id_fkey FOREIGN KEY (answer_id) REFERENCES public.answers(id) ON DELETE CASCADE;


--
-- Name: answer_citations answer_citations_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_citations
    ADD CONSTRAINT answer_citations_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: answer_citations answer_citations_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_citations
    ADD CONSTRAINT answer_citations_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id);


--
-- Name: answer_citations answer_citations_superseded_by_diff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_citations
    ADD CONSTRAINT answer_citations_superseded_by_diff_id_fkey FOREIGN KEY (superseded_by_diff_id) REFERENCES public.clause_diffs(id) ON DELETE SET NULL;


--
-- Name: answers answers_query_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_query_id_fkey FOREIGN KEY (query_id) REFERENCES public.queries(id) ON DELETE CASCADE;


--
-- Name: attachments attachments_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT attachments_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE CASCADE;


--
-- Name: change_events change_events_cell_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.change_events
    ADD CONSTRAINT change_events_cell_id_fkey FOREIGN KEY (cell_id) REFERENCES public.cells(id);


--
-- Name: change_events change_events_clause_diff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.change_events
    ADD CONSTRAINT change_events_clause_diff_id_fkey FOREIGN KEY (clause_diff_id) REFERENCES public.clause_diffs(id) ON DELETE CASCADE;


--
-- Name: change_events change_events_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.change_events
    ADD CONSTRAINT change_events_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: clause_classifications clause_classifications_clause_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_classifications
    ADD CONSTRAINT clause_classifications_clause_id_fkey FOREIGN KEY (clause_id) REFERENCES public.clauses(id) ON DELETE CASCADE;


--
-- Name: clause_classifications clause_classifications_extraction_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_classifications
    ADD CONSTRAINT clause_classifications_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES public.extraction_runs(id) ON DELETE SET NULL;


--
-- Name: clause_diffs clause_diffs_from_clause_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_diffs
    ADD CONSTRAINT clause_diffs_from_clause_id_fkey FOREIGN KEY (from_clause_id) REFERENCES public.clauses(id) ON DELETE SET NULL;


--
-- Name: clause_diffs clause_diffs_from_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_diffs
    ADD CONSTRAINT clause_diffs_from_version_id_fkey FOREIGN KEY (from_version_id) REFERENCES public.document_versions(id);


--
-- Name: clause_diffs clause_diffs_to_clause_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_diffs
    ADD CONSTRAINT clause_diffs_to_clause_id_fkey FOREIGN KEY (to_clause_id) REFERENCES public.clauses(id) ON DELETE SET NULL;


--
-- Name: clause_diffs clause_diffs_to_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_diffs
    ADD CONSTRAINT clause_diffs_to_version_id_fkey FOREIGN KEY (to_version_id) REFERENCES public.document_versions(id);


--
-- Name: clause_embeddings clause_embeddings_clause_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_embeddings
    ADD CONSTRAINT clause_embeddings_clause_id_fkey FOREIGN KEY (clause_id) REFERENCES public.clauses(id) ON DELETE CASCADE;


--
-- Name: clause_embeddings clause_embeddings_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clause_embeddings
    ADD CONSTRAINT clause_embeddings_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE CASCADE;


--
-- Name: clauses clauses_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clauses
    ADD CONSTRAINT clauses_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE CASCADE;


--
-- Name: clauses clauses_parent_clause_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clauses
    ADD CONSTRAINT clauses_parent_clause_id_fkey FOREIGN KEY (parent_clause_id) REFERENCES public.clauses(id) ON DELETE CASCADE;


--
-- Name: document_cells document_cells_cell_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_cells
    ADD CONSTRAINT document_cells_cell_id_fkey FOREIGN KEY (cell_id) REFERENCES public.cells(id);


--
-- Name: document_cells document_cells_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_cells
    ADD CONSTRAINT document_cells_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: document_versions document_versions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT document_versions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: document_versions document_versions_fetch_observation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT document_versions_fetch_observation_id_fkey FOREIGN KEY (fetch_observation_id) REFERENCES public.fetch_observations(id);


--
-- Name: documents documents_parent_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_parent_document_id_fkey FOREIGN KEY (parent_document_id) REFERENCES public.documents(id);


--
-- Name: documents documents_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);


--
-- Name: extraction_runs extraction_runs_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction_runs
    ADD CONSTRAINT extraction_runs_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE CASCADE;


--
-- Name: fetch_observations fetch_observations_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fetch_observations
    ADD CONSTRAINT fetch_observations_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);


--
-- Name: ir_citations ir_citations_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_citations
    ADD CONSTRAINT ir_citations_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: ir_citations ir_citations_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_citations
    ADD CONSTRAINT ir_citations_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id);


--
-- Name: ir_citations ir_citations_ir_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_citations
    ADD CONSTRAINT ir_citations_ir_id_fkey FOREIGN KEY (ir_id) REFERENCES public.irs(id) ON DELETE CASCADE;


--
-- Name: ir_citations ir_citations_superseded_by_diff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_citations
    ADD CONSTRAINT ir_citations_superseded_by_diff_id_fkey FOREIGN KEY (superseded_by_diff_id) REFERENCES public.clause_diffs(id) ON DELETE SET NULL;


--
-- Name: ir_standard_citations ir_standard_citations_ir_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_standard_citations
    ADD CONSTRAINT ir_standard_citations_ir_id_fkey FOREIGN KEY (ir_id) REFERENCES public.irs(id) ON DELETE CASCADE;


--
-- Name: ir_standard_citations ir_standard_citations_standard_reference_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ir_standard_citations
    ADD CONSTRAINT ir_standard_citations_standard_reference_id_fkey FOREIGN KEY (standard_reference_id) REFERENCES public.standard_references(id) ON DELETE RESTRICT;


--
-- Name: irs irs_extraction_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.irs
    ADD CONSTRAINT irs_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES public.extraction_runs(id) ON DELETE SET NULL;


--
-- Name: irs irs_supersedes_ir_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.irs
    ADD CONSTRAINT irs_supersedes_ir_id_fkey FOREIGN KEY (supersedes_ir_id) REFERENCES public.irs(id);


--
-- Name: queries queries_cell_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.queries
    ADD CONSTRAINT queries_cell_id_fkey FOREIGN KEY (cell_id) REFERENCES public.cells(id);


--
-- Name: source_schedules source_schedules_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_schedules
    ADD CONSTRAINT source_schedules_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id) ON DELETE CASCADE;


--
-- Name: sources sources_cell_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_cell_id_fkey FOREIGN KEY (cell_id) REFERENCES public.cells(id);


--
-- Name: standard_references standard_references_cell_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.standard_references
    ADD CONSTRAINT standard_references_cell_id_fkey FOREIGN KEY (cell_id) REFERENCES public.cells(id);


--
-- Name: standard_references standard_references_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.standard_references
    ADD CONSTRAINT standard_references_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);


--
-- Name: structure_drift_alerts structure_drift_alerts_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.structure_drift_alerts
    ADD CONSTRAINT structure_drift_alerts_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);


--
-- Name: verification_results verification_results_answer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_results
    ADD CONSTRAINT verification_results_answer_id_fkey FOREIGN KEY (answer_id) REFERENCES public.answers(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict ekPeHJ9gc3MBeswEtUjt7ioVm0fFNF6iQk5YbGbvsIoDMHyXJejZdFTY8qxLava

