--
-- RegOps authoritative schema dump.
--
-- Generated from the live database after `alembic upgrade head`. Update this file in the same
-- change as any migration (`.claude/skills/db-migration` rule 4) — it is what a reviewer reads
-- instead of replaying the migration history.
--
-- NOTE: dumped with --no-privileges, so the audit_log GRANT/REVOKE from migration 0001 is NOT
-- represented here. Append-only enforcement lives in the migration and in
-- infra/postgres/init/01-app-role.sh (ADR-0011).
--

--
-- PostgreSQL database dump
--

\restrict PDMQf6oFRXPxhfviH1KEWSvJTrtluNnpR64nmstIv2RbbWY4gHfabTj4w1SQVip

-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

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
-- Name: authority; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.authority AS ENUM (
    'mfds',
    'fda',
    'eu',
    'nmpa'
);


--
-- Name: domain; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.domain AS ENUM (
    'samd',
    'cosmetic'
);


--
-- Name: userrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.userrole AS ENUM (
    'viewer',
    'ra',
    'admin'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
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
-- Name: audit_log seq; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log ALTER COLUMN seq SET DEFAULT nextval('public.audit_log_seq_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


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
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


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
-- Name: sessions uq_sessions_jti; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT uq_sessions_jti UNIQUE (jti);


--
-- Name: users uq_users_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_email UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_audit_log_actor_id_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_actor_id_created_at ON public.audit_log USING btree (actor_id, created_at);


--
-- Name: ix_audit_log_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_entity ON public.audit_log USING btree (entity_type, entity_id);


--
-- Name: ix_sessions_user_id_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sessions_user_id_expires_at ON public.sessions USING btree (user_id, expires_at);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_email ON public.users USING btree (email);


--
-- PostgreSQL database dump complete
--

\unrestrict PDMQf6oFRXPxhfviH1KEWSvJTrtluNnpR64nmstIv2RbbWY4gHfabTj4w1SQVip

