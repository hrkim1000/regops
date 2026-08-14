# E2E — the two critical journeys, end to end

Playwright against the **running stack**: four services, Postgres with pgvector, MinIO, two Celery
workers, the real ingested corpus and the real model. Nothing is stubbed. One fixture row is seeded,
for the one journey the corpus cannot supply — see `superseded-citation.spec.ts`.

## Running it

```bash
docker compose --profile app up -d          # the app under test

cd frontend
npm install
npx playwright install chromium             # once per machine

export REGOPS_E2E_RA_PASSWORD=...           # the seeded ra's password
export REGOPS_E2E_VIEWER_PASSWORD=...       # the seeded viewer's password
npm run e2e                                 # or npm run e2e:ui for the interactive runner
```

Users are seeded with the same script the rest of the stack uses; **there is no password in this
repository and there must never be one** — the value you seed with is the value you export:

```bash
REGOPS_SEED_EMAIL=e2e-ra@example.com REGOPS_SEED_PASSWORD=... REGOPS_SEED_ROLE=ra \
    docker compose exec -T platform-core python /scripts/seed_user.py
```

The `ra` is the suite's own principal rather than a person's account, because assigning an alert
owner is written to the audit hash chain: the chain should record that an automated run did it. The
`viewer` writes nothing and reuses the account phase 0's acceptance suite already signs in as.

| Variable | Default | What it selects |
| --- | --- | --- |
| `REGOPS_E2E_BASE_URL` | `http://localhost:23000` | the frontend origin |
| `REGOPS_E2E_RA_EMAIL` / `_PASSWORD` | `e2e-ra@example.com` / — | the principal that assigns and asks |
| `REGOPS_E2E_VIEWER_EMAIL` / `_PASSWORD` | `viewer@example.com` / — | the principal that must be refused |
| `REGOPS_E2E_CELL` | `mfds_cosmetic` | the gated cell the journeys read |
| `REGOPS_E2E_EMPTY_CELL` | `fda_samd` | a cell with no connector — the refusal lever |
| `REGOPS_E2E_ASK_TIMEOUT_MS` | `360000` | how long one live answer may take |

## Why it is not in CI

A live `gemma3:4b` takes minutes per answer and words it differently every run, so a red build here
would as often mean *the model was slow* as *the product broke* — and a gate that cries wolf is a
gate people learn to ignore. This runs where the integration suites run: locally and against a stage
stack, before a phase is called done. CI keeps `typecheck` and `lint`, which are deterministic.

## What each spec pins

| Spec | Journey | The invariant, not the wording |
| --- | --- | --- |
| `change-detection.spec.ts` | amendment → alert → owner | one row per amendment; both gates with their denominators; a renumber renders as a move; `ra` assigns, `viewer` is 403'd |
| `cited-answer.spec.ts` | question → retrieval → cited answer | no prose without evidence; a refusal must not be a defect signal; a citation opens the clause it pins and does not move with the ScopeBar |
| `needs-verification.spec.ts` | a question with no evidence in scope | `no_retrieval`, no citations, empty text; rendered as a result in the expected tone, not as an error |
| `superseded-citation.spec.ts` | an amendment moves an answer's evidence | the citation is flagged, never rewritten; the answer lands in the 근거 개정 queue |

Model **quality** — whether an answer is right — is not measured here. That is the phase 1.6 golden
sets, scored per domain and per gated cell. One ad-hoc question would answer it badly.

## The determinism problem, and how each spec handles it

A live model is not reproducible, so no assertion depends on what it says:

- The refusal spec forces its outcome through an **empty cell** — retrieval over a cell with no
  connector returns nothing every time. Deterministic because of how the product behaves, not
  because something was faked.
- The cited-answer spec accepts either an evidence-bearing answer or an honest refusal, and fails on
  `model_unavailable` / `fabricated_citation` — so a run with Ollama switched off goes red rather
  than green.
- The deep-link and superseded specs read rows the model did not write, so they are exact.

`retries: 0`, deliberately. A retried live-model run turns a flaky product into a green report.
