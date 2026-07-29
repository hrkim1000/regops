---
name: release-and-commit
description: Use when committing or cutting a release — commit message conventions, ADR and source-map change rules, and what must never be committed.
---

# Commits & Releases

## Commits

- Conventional style: `type(scope): imperative summary` — `feat|fix|refactor|docs|perf|test|chore`.
- Body explains **why** and the blast radius; wrap ~72 cols.
- Group work into focused commits (one concern each); never sweep unrelated or user-modified
  files into a commit. Commit/push **only when asked**.
- **Never commit**: `.env*` (except `.env.example`), credentials, tokens, generated secrets.
  Placeholders only in tests/docs (`user@example.com`, `<your-token>`).

## Changes that need extra care

- **ADRs** live in `docs/design/ADR-000N-<slug>.md`, numbered sequentially from 0001. Never edit an
  Accepted ADR's decision in place — supersede it with a new ADR and link both ways.
- **`docs/import-source-map.md`** is the single source catalog. A commit that changes a source URL,
  tier, or ingestibility flag says in the body **how the change was verified** (fetched on which
  date, what the old URL returned). Silent URL edits are how a dead connector ships.
- **`docs/data/` and `docs/reference/` are read-only** (CLAUDE.md § Read-only directories) —
  a commit touching them needs an explicit reason.
- Scope-affecting changes (anything touching the 8 cells, Tier D handling, or the citation contract)
  reference the ADR that authorises them.

## Never commit

`.env*` (except `.env.example`), credentials, tokens, generated secrets. Placeholders only in
tests and docs (`user@example.com`, `<your-token>`).

**No Tier D source text, ever** — not as a fixture, not as a test asset, not "temporarily". Standards
and pharmacopoeias appear as metadata plus an official link (ADR-0002).
