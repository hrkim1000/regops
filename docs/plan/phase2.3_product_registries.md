# Phase 2.3 — Product registries and safety surfaces, and the channel they travel

- **Roadmap:** Phase 2 (M5–12) · **Status:** ⬜ planned
- **Governed by:** [ADR-0018](../design/ADR-0018-fda-source-model.md) *Alternatives rejected*
  (openFDA is not a regulation source), [ADR-0021](../design/ADR-0021-guidance-leaves-the-regulation-library.md)
  (the regulation library holds binding text only), [ADR-0007](../design/ADR-0007-context-map-and-applicability.md)
  (Product is tenant-scoped)
- **Decides here:** **who owns this data** — an ADR, not a checkbox. Candidates in *The channel*
- **Depends on:** nothing built. It depends on a decision, which is the point of writing this now
- **Service:** **undecided.** Recording it as undecided rather than defaulting to `regulation`
  because it arrived through `regulation`'s reconnaissance

---

## Goal

FDA publishes registries of *products*: what was cleared, what was approved, who registered, which
identifiers exist, what was recalled, what went wrong in the field. None of it is regulation text and
all of it is regulatory fact.

[ADR-0018](../design/ADR-0018-fda-source-model.md) already rejected openFDA **as a regulation
source**, for the right reason — it carries no regulation text. That rejection said nothing about
whether the data is useful elsewhere, and it is:

> `classification` maps a **product code → device class → 21 CFR part and section**. That is a
> direct edge from a product to the clause store, and it is the only one FDA publishes as data.

This slice exists to route that data somewhere other than the regulation library, and to decide
where before anyone writes a connector.

## Scope

**In:** the nine `device` endpoints openFDA publishes, **plus the two FDA safety surfaces that are
not on openFDA at all** — Warning Letters and Import Alerts — split by what each is *for*; the
acquisition route; and the ownership decision.

The scope is **product- and firm-level regulatory fact, wherever published**, not "whatever openFDA
serves". A warning letter is enforcement against a named firm and an import alert is a detention
list: neither is regulation text, both are exactly the kind of thing this slice exists to route.
They arrived here from [phase2.0a](phase2.0a_fda.md), which had been carrying them since W0 on the
assumption that a change signal about a product belongs beside the regulations it concerns.

**Out:** the regulation corpus (that is [phase2.0a](phase2.0a_fda.md)), tenant product profiles (that
is [phase2.2](phase2.2_compliance.md)), and guidance
([ADR-0021](../design/ADR-0021-guidance-leaves-the-regulation-library.md), still unrouted).

**Not FDA-only in principle.** MFDS publishes equivalents (의료기기 품목허가 정보, 회수·판매중지),
and the same channel question applies. This slice is written against FDA because that is where the
data was measured; the answer should not be FDA-shaped.

## What is actually there

Measured against `api.fda.gov/download.json` on **2026-08-26**. openFDA publishes **daily bulk
exports** as partitioned ZIP, so this needs no crawling and no scraping — which is the opposite of
the guidance problem.

| Endpoint | Records | Partitions | Size | What it is |
| --- | ---: | ---: | ---: | --- |
| `classification` | 7,088 | 1 | **3 MB** | product code → class → **21 CFR section** |
| `pma` | 56,995 | 1 | 21 MB | premarket approvals |
| `registrationlisting` | 334,091 | 2 | 82 MB | establishments and their listed devices |
| `enforcement` | 39,794 | 1 | 90 MB | recall enforcement reports |
| `510k` | 175,879 | 1 | 236 MB | premarket notifications |
| `recall` | 59,025 | 1 | 273 MB | recall records |
| `udi` | 5,083,948 | 51 | **1.8 GB** | device identifiers |
| `event` | 25,711,469 | 365 | **18 GB** | MDR adverse-event reports |
| `covid19serology` | 13,420 | 1 | 0.3 MB | out of scope |

**~20.7 GB in total, and the distribution is the plan.** The four small registries are 342 MB
together; `event` alone is 53× all of them. Anything that treats these nine as one ingestion job is
wrong before it starts.

## The channel — the decision this slice exists to make

Three candidates. **None is chosen here**; the ADR is the deliverable.

**A. `regulation` owns it as shared reference data.** There is a precedent and it is close:
`standard_references` is a table of metadata about instruments whose text we deliberately do not
store ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 7). A product
registry is the same shape — facts about a thing, no body text, shared across tenants.
*Against:* CLAUDE.md scopes `regulation` to L1–L3, ingest → parse → version → diff → IR. Registries
have no clauses, no versions to diff and no IRs, so they would be a fourth kind of thing in a service
defined by the other three.

**B. `compliance` owns it.** It is where product questions live, and applicability is what the
`classification` edge feeds.
*Against:* [ADR-0007](../design/ADR-0007-context-map-and-applicability.md) decision 2 makes Product
**tenant-scoped** — *"facts about a customer"*. These are public facts about everybody's products.
Putting shared reference data inside a tenant-scoped context is the exact inversion that decision
warns about, and Phase 3 is where it would hurt.

**C. A registry context of its own.** Honest about being a third kind of thing: shared, non-tenant,
non-clause reference data.
*Against:* a service boundary should come from ownership and failure isolation
([ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md)), not from tidiness. Nothing here
fails independently of anything yet, and a service with one table and no consumer is a liability.

**What would settle it:** whether anything other than applicability ever reads these. If only
`compliance` reads them, B's objection is about placement rather than correctness and a shared table
owned by `compliance` may be acceptable. If `monitoring` reads the safety half and `compliance` reads
the product half, they are two different things wearing one name — which is the most likely answer
and is why the table below splits by purpose rather than by endpoint.

## Split by purpose, not by endpoint

- [ ] **The bridge — `classification`.** 3 MB, 7,088 rows, and the only FDA-published edge from a
      product code to a CFR section. Highest value per byte in the whole slice: it is what lets
      *"we make a class II infusion pump"* reach 21 CFR 880.5725 in the clause store. **Do this
      first regardless of how the ownership question lands** — it is small enough that placing it
      wrongly is cheap to correct.
- [ ] **Product identity — `510k`, `pma`, `registrationlisting`.** Evidence a customer's product
      profile can be anchored to rather than typed by hand: a K-number or P-number is checkable.
      Feeds [phase2.2](phase2.2_compliance.md) applicability.
- [ ] **Identifiers — `udi`.** 5.1M rows. Decide **lookup-only versus ingested** before touching it;
      a UDI is queried for one device at a time and almost never scanned.
- [ ] **Safety signals — `recall`, `enforcement`, `event`.** These belong to pillar 01 and to
      `monitoring`, not to the product half. `event` is 25.7M rows and must not be ingested whole.
      Probed 2026-08-26 ([phase2.0a](phase2.0a_fda.md) *Deviations* 36) — all three answer 200.
- [ ] **Safety signals not on openFDA — Warning Letters and Import Alerts.** Same family, different
      acquisition, and they are the reason this slice's scope is "wherever published" rather than
      "whatever openFDA serves".
      - **Warning Letters** — `www.fda.gov`, **HTTP 200 and server-rendered** (11 table rows in the
        HTML), so enumerable without a browser. `robots.txt` permits it and asks
        **`Crawl-Delay: 30`**, which the current fetcher would exceed by 30×. A per-host interval
        override is a prerequisite, not a nicety (*Deviations* 37).
      - **Import Alerts** — `accessdata.fda.gov`, **refused**: Akamai redirects to
        `abuse-detection-apology.html`. The same host blocks the Recognized Consensus Standards
        list, and the access request in [docs/fda-request](../fda-request/README.md) covers both.

## Tasks

### Before any connector

- [ ] **The ownership ADR.** Candidates A/B/C above, and the evidence that settles it. Nothing below
      starts until this lands — a connector written against the wrong owner is a migration later
- [ ] **Ingested versus queried, per surface, with the size table as the input.** 3 MB and 18 GB do
      not get the same answer, and "ingest everything" is not available
- [ ] **What a registry row's identity is.** `Document`/`DocumentVersion` do not fit: there is no
      text, no clause path and nothing to diff at clause level. A K-number is the identity of a
      510(k) record; what is the identity of a *change* to one?
- [ ] **Whether a registry record is citable.** [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md)
      requires clause-level evidence with an effective date. A 510(k) record has neither. Either it
      is out of the citation contract (like guidance under ADR-0021) or the contract needs a second
      shape — and **that is an ADR, not an implementation detail**

### Acquisition — cheap, and the only easy part

- [ ] Bulk ZIP from `download.open.fda.gov`, not the query API. Daily export, partitioned, and the
      manifest at `api.fda.gov/download.json` states record counts and sizes per partition
- [ ] Freshness comes from the manifest's `export_date`, so "has this changed" needs no diffing of
      20 GB
- [ ] **`api.fda.gov` is a different host from the two that refuse us** — it answered 200 on every
      endpoint probed (*Deviations* 36). No credential was needed at the sizes tested. Politeness
      still applies; the sibling host has us behind Akamai abuse detection
- [ ] WORM archive and provenance as for any source — a registry fact quoted to a customer needs to
      be as traceable as a clause

### Not in this slice

- [ ] MFDS equivalents. Named so the channel decision is not made FDA-shaped, and deliberately not
      scoped here

## Acceptance criteria

- [ ] The ownership ADR is written and links back to [ADR-0007](../design/ADR-0007-context-map-and-applicability.md)
      decision 2 and [ADR-0018](../design/ADR-0018-fda-source-model.md)
- [ ] `classification` is ingested and a product code resolves to a CFR section **that exists in the
      clause store** — the bridge is verified end to end, not asserted
- [ ] No registry row is reachable from an answer's citation list unless the citation question above
      was answered in the affirmative and the contract says how
- [ ] Nothing over 1 GB was ingested without a written reason

## Risks & open questions

- **Risk — this is a data pipeline wearing a regulation platform's clothes.** 20 GB of product
  records has different failure modes from 526 documents: partial loads, schema drift with no
  version to pin, and a size that makes "just re-ingest" stop being an answer. The regulation
  pipeline's habits do not transfer unexamined.
- **Risk — the citation contract is the load-bearing promise and this data cannot meet it.** The
  temptation is to let an answer cite a 510(k) record because it is a fact. It has no clause and no
  effective date, and ADR-0006's whole point is that an answer's evidence is checkable at clause
  level. Decide deliberately; do not let it happen through retrieval scope, which is exactly how
  guidance nearly got in ([ADR-0021](../design/ADR-0021-guidance-leaves-the-regulation-library.md)).
- **Open question — is `classification` reference data or regulation data?** It maps to a CFR
  section, so it is *about* the corpus. If it lands in `regulation` the other eight probably should
  not, and the split would need a reason better than size.
- **Open question — does UDI belong in this product at all?** 5.1M identifiers serve device
  traceability, which is a different job from regulatory-change monitoring. It may be listed here
  only because openFDA publishes it.

## Deviations & decisions

1. **Warning Letters and Import Alerts moved here from [phase2.0a](phase2.0a_fda.md) on the day this
   file was written (2026-08-26).** Its *Safety surfaces* row had carried all four since W0.
   Once the openFDA half moved here, splitting the row would have left two plans claiming the same
   work — and the split would have been by *publisher* rather than by *what the thing is*. All four
   are product- or firm-level fact, so all four travel together.

2. **Written before anything was built, and before the owner was decided (2026-08-26).** Prompted by
   the observation that 510(k), PMA, MDR and UDI do not belong in the regulation library — the same
   reasoning [ADR-0021](../design/ADR-0021-guidance-leaves-the-regulation-library.md) applied to
   guidance, arriving one surface later.

   The sizes and record counts here are **measured**, from `api.fda.gov/download.json` on
   2026-08-26, not estimated. That is deliberate: the last two deferrals in
   [phase2.0a](phase2.0a_fda.md) were made without knowing acquisition cost and both had to be
   revisited (*Deviations* 20, 36, 37). The cost is on the page this time, before the decision.
