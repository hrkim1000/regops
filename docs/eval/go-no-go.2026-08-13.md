# RegOps M4 Go/No-Go report

- **Generated:** 2026-08-13
- **Recommendation:** **INCOMPLETE** (No-Go at 4 shortfalls in any one cell)

## Regime

A score is only meaningful per regime. These are the versions the numbers below were produced at; a change to any of them invalidates them.

| Key | Value |
|---|---|
| `answer_confidence_threshold` | `0.7` |
| `answer_prompt_version` | `1.3.1` |
| `embedding_passage_version` | `1.3.1` |
| `ir_prompt_version` | `1.2.0` |
| `ir_rule_version` | `1.2.0` |
| `retrieval_version` | `1.3.0` |
| `verification_prompt_version` | `1.3.0` |

## The six gates, per cell

### `mfds_cosmetic`

| Gate | Threshold | Measured | Verdict | Method |
|---|---|---|---|---|
| Detection coverage | ≥ 95% | — | 미측정 | Share of actual amendments captured, verified by after-the-fact manual comparison. Scored against scheduled polls, with the uptime shortfall reported beside it |
| Detection latency | ≤ 24h | — | 미측정 | Authority publication → owner alert, worst case rather than mean |
| Citation accuracy | ≥ 90% | — | 미측정 | Share of cited clauses that actually support the answer, blind RA assessment |
| Hallucination rate | ≤ 2% | — | 미측정 | Outputs citing non-existent clauses or contradicting source text |

> **Detection coverage — 미측정.** No RA amendment ledger for this cell. The denominator is what the authority actually published, which only after-the-fact manual comparison can supply — the system's own count of what it saw would score 100% by construction. Author docs/eval/ground_truth/amendment_ledger.json to measure this.
> ⚠️ **Detection coverage.** Poll completion 76.2%: 493 of 647 scheduled polls ran over 30 days across 85 sources (154 missed). Detection coverage measured over observed polls would have divided by the polls that happened rather than the polls that were due, and downtime would have improved it.
> **Detection latency — 미측정.** No alert in the window covers an amendment published while this cell was under observation, so there is nothing the gate can be measured on yet. Latency from our own retrieval clock — worst case 123.731h — bounds our pipeline, not the gate. This resolves itself: the first amendment published after ingestion started is measurable.
> ⚠️ **Detection latency.** 4 alert(s) cover amendments published before this cell came under observation (2026-08-03T06:47:00.137638+00:00) and are excluded: publication → alert on a backfilled corpus measures how long the instrument existed before RegOps arrived, not how fast RegOps noticed.
> **Citation accuracy — 미측정.** No completed blind assessment. Whether a clause *supports* a claim is a reading, and the expected-path match is a lower bound, not the gate. The golden set is not RA-signed, so this run is not gate evidence.
> **Hallucination rate — 미측정.** The contradiction half needs the blind assessment. Reporting the mechanical half alone as the gate would understate it by exactly the failures the verification agent exists to catch. The golden set is not RA-signed, so this run is not gate evidence.

### `mfds_samd`

| Gate | Threshold | Measured | Verdict | Method |
|---|---|---|---|---|
| Detection coverage | ≥ 95% | — | 미측정 | Share of actual amendments captured, verified by after-the-fact manual comparison. Scored against scheduled polls, with the uptime shortfall reported beside it |
| Detection latency | ≤ 24h | — | 미측정 | Authority publication → owner alert, worst case rather than mean |
| Citation accuracy | ≥ 90% | — | 미측정 | Share of cited clauses that actually support the answer, blind RA assessment |
| Hallucination rate | ≤ 2% | — | 미측정 | Outputs citing non-existent clauses or contradicting source text |

> **Detection coverage — 미측정.** No RA amendment ledger for this cell. The denominator is what the authority actually published, which only after-the-fact manual comparison can supply — the system's own count of what it saw would score 100% by construction. Author docs/eval/ground_truth/amendment_ledger.json to measure this.
> ⚠️ **Detection coverage.** Poll completion 76.2%: 493 of 647 scheduled polls ran over 30 days across 85 sources (154 missed). Detection coverage measured over observed polls would have divided by the polls that happened rather than the polls that were due, and downtime would have improved it.
> **Detection latency — 미측정.** No alert in the window covers an amendment published while this cell was under observation, so there is nothing the gate can be measured on yet. Latency from our own retrieval clock — worst case 123.731h — bounds our pipeline, not the gate. This resolves itself: the first amendment published after ingestion started is measurable.
> ⚠️ **Detection latency.** 3 alert(s) cover amendments published before this cell came under observation (2026-08-03T06:47:00.638181+00:00) and are excluded: publication → alert on a backfilled corpus measures how long the instrument existed before RegOps arrived, not how fast RegOps noticed.
> **Citation accuracy — 미측정.** No completed blind assessment. Whether a clause *supports* a claim is a reading, and the expected-path match is a lower bound, not the gate. The golden set is not RA-signed, so this run is not gate evidence.
> **Hallucination rate — 미측정.** The contradiction half needs the blind assessment. Reporting the mechanical half alone as the gate would understate it by exactly the failures the verification agent exists to catch. The golden set is not RA-signed, so this run is not gate evidence.

## Reported beside the gates, deliberately not gated

A gate set that can be satisfied by a degenerate system is evidence of nothing. A system that refuses every question passes citation accuracy and hallucination rate cleanly; one that alerts on everything passes detection coverage and latency.

| Number | Value | Why it is here |
|---|---|---|
| '확인 필요' rate — cosmetic | 83.3% | Two-sided. Near 0% means the confidence threshold is too permissive and the hallucination gate is about to be missed; too high means the product is unusable however honest it is (ADR-0006 decision 7). |
| '확인 필요' rate — samd | 85.7% | Two-sided. Near 0% means the confidence threshold is too permissive and the hallucination gate is about to be missed; too high means the product is unusable however honest it is (ADR-0006 decision 7). |
| Alert volume — mfds_cosmetic | 4 | 53 of 53 change events alerted to 1 subscriber(s). Alert *precision* is not gated in Phase 1: a system that alerted on everything would pass detection coverage and latency cleanly. |
| Alert volume — mfds_samd | 3 | 56 of 56 change events alerted to 1 subscriber(s). Alert *precision* is not gated in Phase 1: a system that alerted on everything would pass detection coverage and latency cleanly. |
| Scheduled-poll completion | 76.2% | Not a gate, and the reason the coverage gate is scored against scheduled polls: a day the poller did not run leaves no observation row at all, so an observed-poll denominator makes downtime improve the number. |

## Not measured

Listed rather than defaulted. An unmeasured gate is not a pass and not a failure, and a report that guessed either way would be making the decision rather than informing it.

- **Detection coverage** (`mfds_cosmetic`) — No RA amendment ledger for this cell. The denominator is what the authority actually published, which only after-the-fact manual comparison can supply — the system's own count of what it saw would score 100% by construction. Author docs/eval/ground_truth/amendment_ledger.json to measure this.
- **Detection latency** (`mfds_cosmetic`) — No alert in the window covers an amendment published while this cell was under observation, so there is nothing the gate can be measured on yet. Latency from our own retrieval clock — worst case 123.731h — bounds our pipeline, not the gate. This resolves itself: the first amendment published after ingestion started is measurable.
- **Citation accuracy** (`mfds_cosmetic`) — No completed blind assessment. Whether a clause *supports* a claim is a reading, and the expected-path match is a lower bound, not the gate. The golden set is not RA-signed, so this run is not gate evidence.
- **Hallucination rate** (`mfds_cosmetic`) — The contradiction half needs the blind assessment. Reporting the mechanical half alone as the gate would understate it by exactly the failures the verification agent exists to catch. The golden set is not RA-signed, so this run is not gate evidence.
- **Detection coverage** (`mfds_samd`) — No RA amendment ledger for this cell. The denominator is what the authority actually published, which only after-the-fact manual comparison can supply — the system's own count of what it saw would score 100% by construction. Author docs/eval/ground_truth/amendment_ledger.json to measure this.
- **Detection latency** (`mfds_samd`) — No alert in the window covers an amendment published while this cell was under observation, so there is nothing the gate can be measured on yet. Latency from our own retrieval clock — worst case 123.731h — bounds our pipeline, not the gate. This resolves itself: the first amendment published after ingestion started is measurable.
- **Citation accuracy** (`mfds_samd`) — No completed blind assessment. Whether a clause *supports* a claim is a reading, and the expected-path match is a lower bound, not the gate. The golden set is not RA-signed, so this run is not gate evidence.
- **Hallucination rate** (`mfds_samd`) — The contradiction half needs the blind assessment. Reporting the mechanical half alone as the gate would understate it by exactly the failures the verification agent exists to catch. The golden set is not RA-signed, so this run is not gate evidence.
- **Pilot retention** (`—`) — No pilot cohort recorded. Retention needs 20–30 onboarded users and four uncompressible weeks of real use; a rate computed over an empty cohort is not a small number, it is no number.
- **Research time savings** (`—`) — No pre-pilot baseline. The manual time for matched query types has to be captured before the pilot starts, or the 30% is unfalsifiable.

## Notes

- Three gates are human judgements and the harness does not fill them in: citation accuracy and the contradiction half of hallucination rate come from the blind worksheet, and research-time savings needs a baseline captured before the pilot starts.
