# ADR-0011 — Audit-trail immutability

- **Status:** Proposed
- **Date:** 2026-07-30
- **Depends on:** [ADR-0005](ADR-0005-service-architecture.md) decision 4 (audit is a table, not a service)
- **Resolves:** [ADR-0005](ADR-0005-service-architecture.md) open question 3
- **Built in:** [phase0](../plan/phase0_foundation.md), migration `0001`

---

## Context

ADR-0005 decision 4 settled *where* the audit trail lives — an append-only table in `platform-core`,
written through `regops_shared` — and left *how* append-only is enforced open:

> **Audit trail retention and immutability** — append-only by convention, or enforced (no UPDATE
> grant, periodic hash-chaining)? 21 CFR Part 11 expects tamper-evidence; convention alone will not
> survive an audit.

The question had to be answered before migration `0001`. `audit_log` is the one table that cannot
be rewritten later — adding hash columns to a populated append-only table means doing the exact
thing the table forbids.

## Decisions

### 1. Enforce at the database, not in application code

The application role holds `SELECT` and `INSERT` on `audit_log` and nothing else. `UPDATE`,
`DELETE` and `TRUNCATE` are revoked.

### 2. The application must not own the table

This is the part that makes decision 1 real, and it is easy to get wrong. **A table owner bypasses
its own grants.** A service connecting as the owner keeps `UPDATE` and `DELETE` no matter what is
revoked, and the enforcement reads as present while doing nothing.

So there are two roles:

| Role | Used by | Rights on `audit_log` |
|---|---|---|
| `regops` (owner) | migrations only | full — it created the table |
| `regops_app` | every service | `SELECT`, `INSERT` |

`regops_app` is created by `infra/postgres/init/01-app-role.sh` as `NOSUPERUSER NOCREATEDB
NOCREATEROLE`; migration `0001` grants and revokes against it.

> Verified during the phase 0 build: with the app connecting as the owner, `UPDATE audit_log`
> succeeded. With the split, it returns `permission denied for table audit_log`.

### 3. A hash chain makes the residual case detectable

Grants stop the application. They do not stop a superuser or anyone with direct database access —
and that is precisely the actor an auditor asks about.

Each row carries `prev_hash` and `entry_hash`, where `entry_hash = sha256(canonical(row) ||
prev_hash)`. Editing any row breaks every link after it. Re-hashing the edited row does not help:
the next row's `prev_hash` still points at the original.

Serialization is canonical — sorted keys, no whitespace, UTC isoformat — because the hash is only
worth having if a verifier holding nothing but the rows can recompute it identically years later.

`POST /api/v1/audit/verify` recomputes the chain and returns the first bad `seq`.

### 4. Ordering is a sequence, not a timestamp

`seq` is a `bigserial`, not a UUID and not `created_at`. The chain needs a total order that does not
depend on clock skew between services.

### 5. Concurrent writers lose loudly

The writer reads the tail then inserts, so two concurrent writers can select the same predecessor.
`entry_hash` is `UNIQUE`, so the loser gets an integrity error and retries rather than forking the
chain silently.

At PoC volume this is fine. If audit write contention ever shows up as a real error rate, the fix is
an advisory lock around the append, not a weaker constraint.

## Consequences

- Part 11 tamper-*evidence* is demonstrable rather than asserted — the verify endpoint is the
  demonstration, and phase 3's validation package can point at it.
- A broken chain is an incident, not a bug. `docs/plan/phase3.0_saas.md` should carry the runbook.
- Every service now connects as a non-owner role. Any future migration that creates a table must
  grant on it — the `ALTER DEFAULT PRIVILEGES` in the init script covers tables created by the
  owner, but a table created by anyone else will silently lack grants.
- Verification is a single pass over the table. That is correct at PoC volume and wrong eventually;
  when it outgrows memory it becomes a windowed job with checkpointed anchors. Noted, not pre-built.

## Alternatives rejected

**Append-only by convention.** ADR-0005 already anticipated the objection: convention will not
survive an audit. Any service bug or console session rewrites history with no trace.

**Grants only, chain later.** Blocks casual tampering but provides no evidence, and defers the
column addition onto a populated table that by policy cannot be rewritten — the same trap as doing
nothing, just later and more expensive.

**Write-once storage (WORM object per entry).** The archive already uses content-addressed WORM for
fetched sources (ADR-0002 decision 6), so this was tempting for symmetry. Rejected: the audit trail
is queried relationally on every screen, and moving it out of Postgres buys durability RegOps
already has from backups while costing every join.

## Open questions

1. **Chain-break response.** Alert, refuse writes, or refuse reads? Refusing writes on a broken
   chain would let a single corrupt row halt the platform; alerting is probably right, but it is a
   policy question for the Phase 3 quality agreement.
2. **Retention.** Part 11 expects records for the life of the product plus a retention period. No
   deletion path exists — deliberately — so this becomes an archival question before Phase 3.
3. **Periodic anchoring.** Publishing the head hash somewhere external (a signed daily digest) would
   defend against wholesale table replacement, which the chain alone cannot detect. Cheap, but not
   needed until there is an external customer to prove it to.
