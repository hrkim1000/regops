# ADR-0017 — Extraction determinism, and conditional obligations stay one IR

- **Status:** Accepted
- **Date:** 2026-08-07
- **Closes:** [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md) open questions **3**
  (conditional obligations by product class) and **5** (extraction determinism)
- **Forced by:** [phase1.2](../plan/phase1.2_ir_extraction.md) — both questions gate code that had
  to be written, and a question left open is answered by whatever gets built first

---

## Context

ADR-0004 left two questions open and phase 1.2 could not be built around either of them. Both are
small in isolation and both are expensive to reverse once IRs exist over the gated corpus: one
decides how many rows an obligation produces, the other decides whether "re-extract and compare" is
a regression test or a coin toss.

## Decisions

### 1. Extraction runs at temperature 0, and any delta is a regression

*(Closes ADR-0004 open question 5.)*

Sampling is pinned to `0.0` and stamped on `extraction_runs.temperature`. Two runs over the same
clause at the same `(rule_version, prompt_version, llm_model)` are expected to produce the same IRs,
and a difference is investigated as a defect rather than absorbed as variance.

The alternative — accept variance and gate only on the golden-set score — was rejected because it
makes "why does this IR exist" unanswerable. Re-derivation after an amendment (ADR-0004 decision 5)
re-extracts a clause and supersedes the old IR; under sampled decoding that churns IRs whose
obligation did not change, and every control mapping carried forward against them has to be
re-confirmed by an RA for no regulatory reason. The audit story is the same point from the other
side: an obligation asserted by a model is defensible if a reviewer can re-run the extraction and
get the row back.

**This is a target with a known limit, not a guarantee.** Temperature 0 is greedy decoding, not
determinism: batching, quantization, GPU non-determinism and a provider-side model update can all
move the output. So it is enforced where it is enforceable — the value used is stored on the run
rather than assumed from a constant, and drift is measured against the golden set per
`(rule_version, prompt_version, llm_model)` in [phase1.6](../plan/phase1.6_evaluation.md). Pinning
the model version is already required by CLAUDE.md § Architecture rules for exactly this reason.

The seam grew one parameter to make this possible: `LLMClient.complete(..., temperature=)`, which
Ollama takes under `options` and Claude at the top level. A stray top-level `temperature` is
*silently ignored* by Ollama, which would have made a pinned run look deterministic while sampling
normally.

### 2. A class-restricted obligation is one parameterised IR, never one per class

*(Closes ADR-0004 open question 3.)*

"의료기기 2등급 이상은 …하여야 한다" produces **one** IR whose `condition_text` carries the
restriction. It does not produce one IR per device class.

The reasoning is a boundary one rather than a storage one. Applicability is Compliance-owned and
tenant-scoped ([ADR-0007](ADR-0007-context-map-and-applicability.md), phase 2.2): *which* products a
duty binds depends on a tenant's own product context, which `regulation` does not have and must not
acquire. Regulation data is shared reference data. Fanning an IR out per class here would mean the
shared layer had already made an applicability decision on every tenant's behalf, and mapping to
controls would then be reading someone else's answer rather than computing its own.

Two practical consequences follow the same way:

- **Amendment cost.** A duty stated once and re-derived once stays one supersession chain. Per-class
  IRs multiply every amendment to the shared obligation by the number of classes, and each new IR is
  a separate lock and a separate mapping carry-forward — all describing one change to one sentence.
- **Class lists move.** A device classification rule can add a class without touching the obligation
  clause. Under the parameterised form nothing is re-derived; under per-class IRs the obligation
  silently under-covers until someone notices.

The cost is real and is accepted: gap analysis cannot join an IR directly to a class and must read
`condition_text`. That is 2.2's problem to solve where the product context lives, and it is the
right place for it — the condition is regulatory text, and interpreting it against a product is an
applicability judgement, not a parse.

The rule is in the extraction prompt as an instruction ("Do not emit one IR per class"), not only
here, because a rule that lives only in an ADR is not one the extractor follows.

## Consequences

- `extraction_runs` carries `temperature`; the acceptance suite asserts it is `0.0` and that the
  client was actually called with it.
- `irs.condition_text` is load-bearing rather than descriptive. It is the only place a class
  restriction is recorded, so an extraction that drops it loses scope information silently.
- Phase 1.6's golden set is scored per `(rule_version, prompt_version, llm_model)`. A prompt reword
  without a version bump invalidates every earlier score with nothing failing, which is why both
  versions are constants stamped on every row.

## What this does not decide

Whether the *same* obligation extracted under both domain profiles should be deduplicated. It
currently is not: a document claimed by both gated cells yields one IR per profile, because the
taxonomies differ and forcing one row would make the domain branch a fiction. If that proves
noisy in review, it is a phase 2.1 question about the semantic layer, not a change here.
