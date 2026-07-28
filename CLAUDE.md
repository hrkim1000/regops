# CLAUDE.md — RegOps

**RegOps** — AI-powered Regulatory platform for Medical Device, Cosmetic Product.  
A citation-traceable knowledge layer that turns fragmented medical device, and cosmetic regulations into monitored change alerts, sourced answers, and mapped compliance gaps. 
This file is the **constitution**:
always-loaded, invariant rules only. Task-specific knowledge lives in `.claude/skills/`
(auto-invoked on demand); guardrails in `.claude/settings.json` hooks; delegation in
`.claude/agents/`.

## Repo map

```text
docs/                     # product/strategy docs (architecture overview, plans, summaries)
```

## Architecture rules (non-negotiable)


## Security must-follows

- **Never** commit or print `.env*` contents (real keys live there; `.env.example` is the template).
- No real emails/passwords/tokens in code, tests, fixtures, or docs — placeholders only.
- JWT issued/signed by platform-core / Identity & Access; verified statelessly per service
  via the shared `get_current_principal()` → `decode_token()`.
- PHI/PII: encrypted at rest + transit, anonymized in logs; RBAC re-checked server-side on
  every endpoint.

## Working agreement

1. Think first: read the relevant code (and the matching `docs/design/` doc), then write a
   plan (TodoWrite) and confirm it before building.
2. Smallest change that solves the problem — minimize blast radius; simplicity over cleverness.
3. Follow existing patterns; no new abstractions without discussion.
4. Narrate changes at a high level as you go; finish with a summary.
5. Commit/push only when explicitly asked.
