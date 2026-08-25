# ADR-0019 — An announced amendment is a row of its own, because it exists before any version does

- **Status:** Accepted
- **Date:** 2026-08-25
- **Amends:** [ADR-0018](ADR-0018-fda-source-model.md) decision 4 — *"a Federal Register rule is
  provenance on the version"*. It is provenance, and **not only** on the version: a rule published
  and not yet in force has no version to be provenance of.
- **Confirms:** [ADR-0002](ADR-0002-canonical-regulation-model.md) decision 2 (a different entity
  earns a table, not a flag on `Document`), [ADR-0013](ADR-0013-unresolvable-effective-dates.md)
- **Forced by:** [phase2.0a](../plan/phase2.0a_fda.md) *Deviations* 10 — the connector computes the
  pending-amendment picture on every fetch and it reaches nothing queryable

---

## Context

The `federal_register` connector works and its evidence is archived. Nothing can *ask* it anything.

`document_versions` carries `version_label`, `language`, `content_hash`, `raw_object_key`,
`published_at`, `effective_date`, `effective_date_phrase`, `parser_version` — and no column for a
connector's `meta`. On the MFDS path that is correct by design: `meta` is **consumed** at parse time
to set `effective_date` and is not meant to survive.

A feed of final rules breaks the assumption in two directions at once.

**Many rules, many dates, one version.** 21 CFR Part 820's feed carries 16 final rules. There is no
single version-level date to fold them into, so `meta` is computed each fetch and dropped.

**And the ones that matter most have no version at all.** ADR-0018 decision 7 records that the eCFR
404s on any future date, so an amendment that is published and not yet in force is invisible there
— while the Federal Register carries FDA rules today effective as far out as **2033-03-07**. Those
are precisely the rows an RA needs, and "provenance on the version" cannot hold them, because the
version will not exist for seven years.

Two questions have no answer today, and both are load-bearing:

1. *Which amendments are announced and not yet in force for this cell?* — ADR-0018 decision 7.
2. *What is the legally stated effective date of this CFR version?* — ADR-0018 decision 5, which
   wants the Federal Register's `effective_on` in preference to the eCFR's `amendment_date`.

## Decision

### 1. `amendment_announcements` — one row per announcing document

Not a `Document`: ADR-0018 decision 4 stands on its reasoning, which is that a rule's body is not
what an RA cites. Not a flag either. This is the same shape as `standard_references`
([ADR-0002](ADR-0002-canonical-regulation-model.md) decision 2) — a different entity, so it earns a
table, upserted from connector records with `source_id` and `last_seen_at`.

```text
amendment_announcements(id, authority, ref, citation, title,
                        published_on, effective_on, effective_date_phrase,
                        official_url, source_id, last_seen_at, created_at, updated_at)
  UNIQUE (authority, ref)
```

`ref` is the authority's own identifier — the Federal Register document number, `2024-01709`. Keyed
with `authority` so the uniqueness claim is one an authority can actually make about its own
numbering, and so a second authority's announcements cannot collide with the first's.

### 2. The name is authority-neutral, and the table is FDA-only today

`federal_register_rules` would bake one authority into the schema. Every table in this model is
neutral — `Clause` carries no domain column, `DocType` gained `REGULATION` rather than reusing a
rung of the Korean ladder — and the concept here is not FDA's: an amendment announced before its
text is readable is 공포-before-시행, an Official Journal publication, an FDA final rule.

**Only FDA populates it now, and that is not a reason to name it after FDA.** MFDS needs no row
because `target=eflaw` serves the pending 본문, so ADR-0016 decision 1 makes those *versions* —
which remains right, and this ADR does not disturb it. The two authorities differ in whether the
text exists yet, not in whether an amendment was announced.

### 3. `announcement_documents` — M:N, because one rule amends several Parts

```text
announcement_documents(announcement_id, document_id, PRIMARY KEY (announcement_id, document_id))
```

The QMSR rule names Parts **4 and 820**. Storing one row per (rule, Part) instead would repeat
`effective_on` per Part and let the copies drift; a `varchar` list would not join. This is
`document_cells` again, for the same reason and with the same shape.

A rule naming a Part we do not ingest simply has no row for it — the announcement still exists,
which is the point, and the coverage question is about Parts, not about rules.

### 4. `effective_on` is nullable, and the phrase is kept whether or not it is

6 of Part 820's 16 rules state no effective date. [ADR-0013](ADR-0013-unresolvable-effective-dates.md)
applies unchanged: the column is null and `effective_date_phrase` holds the `dates` prose verbatim.
A derived date here would be worse than in a version, because this is the column a later step reads
*in preference to* the eCFR's own date.

### 5. What this does **not** do: it does not set `document_versions.effective_date`

The join is available now — `announcement_documents` gives Part, `effective_on` gives the date — but
performing it is a separate change with its own risk, and ADR-0018 decision 4 already warns the join
is **best-effort**: the eCFR sources Part 820 to `89 FR 7523` while the Federal Register calls the
same rule `89 FR 7496`, so it matches on Part and date proximity, never on citation string.

Doing it in this ADR would mean writing a derived date into the column citations resolve through, on
a heuristic, in the same change that first makes the data available. The table lands first; the join
is decided when there is something to measure it against.

## Consequences

**Good.** Both questions become SQL. Pending amendments are `effective_on > current_date`, joined to
cells through `announcement_documents` and `document_cells`. The `effective_on` decision 5 wants is a
column rather than a value recomputed per fetch and discarded.

**The blind spot is now measurable rather than merely acknowledged.** ADR-0018 decision 7 says FDA
announces amendments years ahead and withholds the text; until now that was a sentence. It becomes a
count with dates on it, which is what makes it a gap someone can size.

**Cost — a rule can outlive our interest in it.** Rows accumulate for every final rule touching an
in-scope Part, back through the Federal Register's history: 16 for Part 820, 32 for Part 892. That is
small, and it is history we did not archive ourselves, so it is **evidence about** the corpus rather
than evidence *in* it — it is never cited, and nothing downstream may treat it as a source of
regulation text.

**Cost — `meta` still drops for every other connector.** This fixes the Federal Register's case by
giving those records a home, not by making `FetchedArtifact.meta` durable. If a second connector
needs its envelope to survive, that is the same conversation again and it should be had once.

## Alternatives rejected

- **`document_versions.source_meta jsonb`.** The obvious cheap fix, and it cannot answer the
  question that matters: a pending rule has no version, so the row it would hang on does not exist.
  It would make the *dropped* data durable while leaving the *missing* data missing.
- **A `Document` per rule, `doc_type = FEED` per rule instead of per Part.** Every rule becomes a
  Document with a version and a WORM object, for text nobody cites, and ADR-0018 decision 4 rejected
  exactly this: it doubles every amendment.
- **`federal_register_rules`.** Honest about today and wrong for the schema. See decision 2.
- **One row per (rule, Part), no join table.** Repeats `effective_on` per Part and lets the copies
  disagree — the same reason `document_cells` exists rather than a `cell` column on `documents`.
- **Reusing `change_events`.** Those are emitted from a `ClauseDiff`: a change we *observed in text
  we hold*. An announcement is the opposite — a change we have been told about and cannot yet see.
  Collapsing the two would put "not yet in force, no text" rows into the stream `monitoring` grades
  and alerts on.

## Open questions

1. **Who performs the join, and when?** Decision 5 defers it. The candidates are the version stage
   (at write time, needing the announcement to already exist) and a sweep (after the fact, able to
   correct itself). The second is likelier to be right, because a rule can be published *after* the
   eCFR issues the text it explains.
2. **Does an announcement belong to `monitoring`'s alert stream?** A rule effective in 2033 is not a
   change event, but an RA plausibly wants to hear about it once. Deciding that is
   `monitoring`-side and needs the alerting model, not this table.
3. **What retires a row?** `last_seen_at` records what the feed still returns, and nothing prunes.
   Harmless at this scale; revisit if a Part's history ever runs to thousands.
