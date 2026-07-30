# CLAUDE.md — RegOps

**RegOps** — AI-powered Regulatory platform for SaMD and Cosmetic Product.  
A citation-traceable knowledge layer that turns fragmented SaMD and cosmetic regulations into monitored change alerts, sourced answers, and mapped compliance gaps.

**Scope (invariant):** 2 product domains × 4 regulatory regions — SaMD and Cosmetic × MFDS, FDA, EU, NMPA (China).
Nothing outside these 8 cells: no pharma/biologics, no hardware-only devices, no other authorities
(PMDA, Health Canada, MHRA, TGA, ASEAN). See [docs/RegOps.md](docs/RegOps.md) § Scope.

This file is the **constitution**:
always-loaded, invariant rules only. Task-specific knowledge lives in `.claude/skills/`
(auto-invoked on demand); guardrails in `.claude/settings.json` hooks; delegation in
`.claude/agents/`.

## Repo map

```text
docs/                     # product/strategy docs — the working set
  RegOps.md               # architecture overview — Scope, Data Strategy tiers, 5 layers, roadmap
  import-source-map.md    # SINGLE SOURCE OF TRUTH for per-cell regulation sources (8 cells)
  import-agent.md         # Import Agent spec — how sources are fetched/normalized/parsed
  development-plan.md     # delivery plan, workstreams, stage gates
  executive-summary.md    # 1-page exec summary
  regulation-library-structure.md   # per-cell library layout example
  design/                 # ADRs — ADR-000N-<slug>.md, numbered from 0001
  data/<region>/          # READ-ONLY raw source research (mfds, fda, eu, china, other)
  memo/                   # superseded drafts — never authoritative, may contradict the rules
  reference/              # READ-ONLY, DO NOT CONSULT — parked material
```

### Read-only directories

- **`docs/data/`** — raw source research. Consult it for facts; **never edit it.** Corrections
  belong in `import-source-map.md`, which is what connectors are built against. Do not treat
  anything in here as a scope or roadmap statement.
- **`docs/memo/`** — superseded drafts, kept for provenance. **Never cite as authoritative.**
  Contents predate or contradict the current rules; the live statement is in `RegOps.md`,
  `import-source-map.md`, or an ADR. Do not "fix" a memo — supersede it.
- **`docs/reference/`** — parked material. **Do not read it and do not cite it** when answering
  questions or making changes. It is retained for provenance only.

## Architecture rules (non-negotiable)

- **Scope is 8 cells.** Every source, connector, parser profile, and IR belongs to exactly one
  `{authority}_{domain}` cell. `authority` ∈ mfds|fda|eu|nmpa, `domain` ∈ samd|cosmetic.
  No other spellings ("Medical Device", "Device", "MDR"). Nothing outside the 8 cells.
- **`docs/import-source-map.md` is the only source catalog.** Never create a second list of
  sources in another doc — copy it and one copy silently goes stale. Reference it instead.
- **Tier D is never ingested.** ISO/IEC standards and pharmacopoeias (ISO 13485, ISO 14971,
  IEC 62304, IEC 62366, ISO 27001, USP-NF, Ph.Eur.) prohibit source-text storage and AI
  training. Store only the recognition record — number, edition, recognition number, effective
  and withdrawal dates, harmonized status — and deep-link the official copy. This holds even
  when a regulation makes the standard legally binding (QMSR incorporates ISO 13485:2016 by
  reference): cite the requirement, link the standard, store neither.
- **No answer without evidence.** Generation is citation-enforced: clause-level citation plus
  document version and effective date, or the answer is returned as "needs verification."
  Every generated result passes a separate evidence-verification agent; every answer carries a
  confidence score, and below threshold it routes to human review.
- **Source and version metadata are preserved end to end**, with an immutable (WORM) archive of
  the fetched original and a full audit trail of every retrieval and generation.
- **Login-gated notification portals are not ingestion sources** (EU CPNP, EUDAMED, and the
  like). They are reference-only; do not attach connectors.
- **The knowledge graph is the asset.** LLMs are replaceable and must stay behind a pluggable
  seam; regulation–product–control mapping data is what accumulates value. Pin model versions
  and regression-test against the golden query set before changing them.

## Doc sync to `startup`

Two remotes: `origin` (github.com/hrkim1000/regops — the real repo) and `startup`
(github.com/kimhwangdata/startup-doc — a shared doc repo owned by another account).

- **`startup` pushes go to the `hrkim` branch only. Never to `startup/main`.**
- Only `README.md` and `docs/**` are published, **excluding `docs/data/`** (raw source research)
  and **`docs/memo/`** (superseded drafts — they contradict the current rules, so they must not
  reach a shared repo).
- `.claude/`, `CLAUDE.md`, `.gitignore` and any future code stay out of `startup` entirely.
- `git subtree` is wrong here — `startup` keeps docs under `docs/`, and a subtree split would
  hoist them to the repo root. Publish a filtered snapshot at the same paths instead:

```bash
git fetch startup hrkim
GIT_INDEX_FILE=.git/publish-index git read-tree --empty &&
GIT_INDEX_FILE=.git/publish-index git add README.md docs ':!docs/data' ':!docs/memo' &&
tree=$(GIT_INDEX_FILE=.git/publish-index git write-tree) &&
commit=$(git commit-tree $tree -p FETCH_HEAD -m "docs: sync RegOps documentation") &&
git push startup $commit:hrkim && rm -f .git/publish-index
```

This publishes the **working tree**, not committed state — commit to `origin` first so the two
never diverge. Parenting on `FETCH_HEAD` keeps the push a fast-forward; never `--force` a repo
owned by another account.

## Security must-follows

- **Never** commit or print `.env*` contents (real keys live there; `.env.example` is the template).
- No real emails/passwords/tokens in code, tests, fixtures, or docs — placeholders only.
- JWT issued/signed by platform-core / Identity & Access; verified statelessly per service
  via the shared `get_current_principal()` → `decode_token()`.
- PHI/PII: encrypted at rest + transit, anonymized in logs; RBAC re-checked server-side on
  every endpoint.

## Working agreement

1. Think first: read the relevant code and the matching doc in `docs/`, then write a
   plan (TodoWrite) and confirm it before building.
2. Smallest change that solves the problem — minimize blast radius; simplicity over cleverness.
3. Follow existing patterns; no new abstractions without discussion.
4. Narrate changes at a high level as you go; finish with a summary.
5. Commit/push only when explicitly asked.
