# eCFR versus Federal Register — measured lag

- **Observations:** 10 over 10 distinct days (2026-08-24 → 2026-09-04)
- **Closes:** ADR-0018 open question 1 — *how far does the eCFR `versions` endpoint lag the Federal Register?*

## The lag that bounds the detection gate

**Blind spot** — days since the oldest rule that is *in force* yet absent from the compilation. Zero means every rule in force is present, which is what ADR-0018 decision 6 needs to be true. This is the verdict input.

| n | min | median | max |
|---:|---:|---:|---:|
| 10 | 0 | 0.0 | 0 |

**Raw freshness** — observation date minus the title's own `up_to_date_as_of`. Context only: it cannot tell a compilation that is *behind* from one that did not advance because **nothing was amended**, and those are opposite findings with the same number.

| n | min | median | max |
|---:|---:|---:|---:|
| 10 | 2 | 2.0 | 4 |

**The eCFR can carry the gate.** Across 10 observations no rule was ever in force while absent from the compilation for more than 0 day(s), so polling `versions/title-21.json` sees an amendment within the window ADR-0018 decision 6 assumes.

Day granularity is the endpoint's, not the measurement's — `up_to_date_as_of` is a date, so this bounds the lag at ≤1 day and cannot *prove* ≤24h. That is the strongest claim this surface supports, and it is the claim the ADR needs.

## Absorption — how long after a rule bites does the text show it

eCFR `issue_date` - the rule's `effective_on` (or `publication_date` where the rule states none). Attribution is by Part plus date proximity, never by citation string: the eCFR sources part 820 to `89 FR 7523` while the Federal Register calls the same rule `89 FR 7496`.

| n | min | median | max |
|---:|---:|---:|---:|
| 5 | 0 | 0 | 0 |

- Distinct section-versions seen: **12**, of which **2** touched a Part the FDA cells claim
- Flagged `removed` by the authority: **0**
- Could not be attributed to any rule: **7**
- Attributed but ambiguous (more than one candidate rule): **2**
- Attribution basis: {'effective_on': 5}

## Announcement lead — how much warning the authority gives

`effective_on` - `publication_date`. Not a lag in our pipeline: ADR-0018 decision 7 says a pending amendment produces no version, so this is the size of that blind spot.

| n | min | median | max |
|---:|---:|---:|---:|
| 7 | 0 | 0 | 163 |

- Rules seen: **8**, of which **1** stated no effective date (ADR-0013 applies — null, with the phrase retained)

## Data health

- Observations carrying a note: **1**
- Observations where a response was truncated: **0**
