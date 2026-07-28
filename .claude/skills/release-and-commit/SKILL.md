---
name: release-and-commit
description: Use when committing, tagging, or cutting a release — commit message conventions, CR/Risk trailers, release tagging (vX.Y.Z → change_kind), and what must never be committed.
---

# Commits, Tags & Releases

## Commits (platform repo)

- Conventional style: `type(scope): imperative summary` — `feat|fix|refactor|docs|perf|test|chore`.
- Body explains **why** and the blast radius; wrap ~72 cols.
- Group work into focused commits (one concern each); never sweep unrelated or user-modified
  files into a commit. Commit/push **only when asked**.
- **Never commit**: `.env*` (except `.env.example`), credentials, tokens, generated secrets.
  Placeholders only in tests/docs (`user@example.com`, `<your-token>`).

## Traceability trailers (customer/SaMD repos — IEC 62304 §8)

Commits implementing a Change Request carry trailers the Evidence Agent (②) reads read-only:

```text
Refs: CR-123          # links commit → change request
Risk: RISK-45         # links commit → risk item
```

These build the `CR ↔ implementation ↔ verification` traceability chain.

## Releases (customer/SaMD repos)

- A release = a **GitLab Release object** on tag `vX.Y.Z` (frozen tag → immutable commit,
  ADR-0005). Optional prerelease suffix `vX.Y.Z-rc1` records but suppresses fan-out.
- `change_kind` derives from the **tag digit transition**: X↑ = major, Y↑ = minor, else patch.
  A MAJOR bump triggers the re-apply fan-out (re-derivation + regeneration).
- A Safety Class (A/B/C) change forces MAJOR and escalates to a human — never auto-handled.
- The platform never pushes to the repo; it only records what it observes (ADR-0002).

## Document versioning (platform records)

Generated documents carry MAJOR/MINOR/PATCH + status lifecycle with appended change history
on `generated_documents` / `document_sections` — the platform is the document system of record.
