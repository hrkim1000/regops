아래는 **RegOps Regulation Library** 구축을 위한 **EU(European Union)** Raw Regulation Source Catalog입니다. 중국 NMPA는 `../china/china-cosmetic-regulation-source.md`로 분리되어 있습니다.

---

# EU Cosmetics Regulation Library

## Raw Regulation Source Links

**Version:** 1.1
**Authority:** European Commission (EC)
**Region:** European Union
**Domain:** Cosmetics
**Purpose:** RegOps Regulation Library Raw Document Collection
**Link check:** 2026-07-29 — every URL below was fetched and confirmed resolving

> **Host note.** EU cosmetics moved from DG SANTE to DG GROW: portal pages live on `single-market-economy.ec.europa.eu`, **not** `health.ec.europa.eu`. The old `health.ec.europa.eu/cosmetics/*` paths now return 404. SCCS is the exception — it remains a DG SANTE committee.

---

## 1. Primary Legislation

| Document                                                     | URL                                                                                                              | Priority |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | -------- |
| Regulation (EC) No 1223/2009 on Cosmetic Products            | [https://eur-lex.europa.eu/eli/reg/2009/1223/oj](https://eur-lex.europa.eu/eli/reg/2009/1223/oj)                  | P1       |
| Regulation (EC) No 1223/2009 — English consolidated text     | [https://eur-lex.europa.eu/eli/reg/2009/1223/oj/eng](https://eur-lex.europa.eu/eli/reg/2009/1223/oj/eng)          | P1       |

The ELI endpoint serves the **current consolidated version** (01/05/2026 as of the link check) and lists every prior consolidation — no separate consolidated-version source is needed.

---

## 2. Annexes & Amending Acts — primary change-detection target

Annexes II–VI carry the substantive ingredient rules and are amended several times a year by Commission Regulations. This is the feed that drives change monitoring for the EU cosmetics cell.

| Resource                                                                     | URL                                                                                                                                    | Priority |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| CosIng annex reference (II prohibited · III restricted · IV colorants · V preservatives · VI UV filters) | [https://ec.europa.eu/growth/tools-databases/cosing/reference/annexes](https://ec.europa.eu/growth/tools-databases/cosing/reference/annexes) | P1       |
| Amending acts per annex (EC legislation page)                                | [https://single-market-economy.ec.europa.eu/sectors/cosmetics/legislation_en](https://single-market-economy.ec.europa.eu/sectors/cosmetics/legislation_en) | P1       |
| Consolidation history / "act has been changed" notices                       | [https://eur-lex.europa.eu/eli/reg/2009/1223/oj](https://eur-lex.europa.eu/eli/reg/2009/1223/oj)                                        | P1       |

---

## 3. European Commission Cosmetics Portal

| Resource             | URL                                                                                                                                              | Priority |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| Cosmetics Home       | [https://single-market-economy.ec.europa.eu/sectors/cosmetics_en](https://single-market-economy.ec.europa.eu/sectors/cosmetics_en)                | P1       |
| Cosmetic Legislation | [https://single-market-economy.ec.europa.eu/sectors/cosmetics/legislation_en](https://single-market-economy.ec.europa.eu/sectors/cosmetics/legislation_en) | P1       |

---

## 4. Named Guidance Acts

| Document                                                                                        | URL                                                                                                        | Priority |
| ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | -------- |
| Commission Implementing Decision 2013/674/EU — guidelines on Annex I (Cosmetic Product Safety Report) | [https://eur-lex.europa.eu/eli/dec_impl/2013/674/oj](https://eur-lex.europa.eu/eli/dec_impl/2013/674/oj)    | P1       |
| Commission Regulation (EU) No 655/2013 — common criteria for cosmetic product claims            | [https://eur-lex.europa.eu/eli/reg/2013/655/oj](https://eur-lex.europa.eu/eli/reg/2013/655/oj)              | P1       |

---

## 5. CPNP (Cosmetic Products Notification Portal)

> **Not an ingestion source.** CPNP is an EU Login-gated notification system, not a published regulation. Its data is released only to competent authorities and poison centres. Treat as reference-only — the EU cosmetics analogue of EUDAMED.

| Resource         | URL                                                                                                                                                    | Priority |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| CPNP (login-gated) | [https://webgate.ec.europa.eu/cpnp](https://webgate.ec.europa.eu/cpnp)                                                                                 | ref      |
| CPNP Information | [https://single-market-economy.ec.europa.eu/sectors/cosmetics/cosmetic-product-notification-portal_en](https://single-market-economy.ec.europa.eu/sectors/cosmetics/cosmetic-product-notification-portal_en) | P2       |

---

## 6. Ingredient Database

| Resource        | URL                                                                                                      | Priority |
| --------------- | -------------------------------------------------------------------------------------------------------- | -------- |
| CosIng Database | [https://ec.europa.eu/growth/tools-databases/cosing](https://ec.europa.eu/growth/tools-databases/cosing) | P1       |

---

## 7. SCCS (Scientific Committee on Consumer Safety)

| Resource      | URL                                                                                                                                                                                              | Priority |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| SCCS Opinions | [https://health.ec.europa.eu/scientific-committees/scientific-committee-consumer-safety-sccs_en](https://health.ec.europa.eu/scientific-committees/scientific-committee-consumer-safety-sccs_en) | P1       |

---

## 8. RAPEX / Safety Gate

| Resource    | URL                                                                  | Priority |
| ----------- | -------------------------------------------------------------------- | -------- |
| Safety Gate | [https://ec.europa.eu/safety-gate](https://ec.europa.eu/safety-gate) | P2       |

---

## 9. Official Journal

| Resource | URL                                                    | Priority |
| -------- | ------------------------------------------------------ | -------- |
| EUR-Lex  | [https://eur-lex.europa.eu](https://eur-lex.europa.eu) | P2       |

---

## 10. Harmonized Standards — metadata only (Tier D)

> **원문 수집 금지.** The harmonized standard for cosmetics GMP is **EN ISO 22716**. ISO prohibits source-text storage and AI training, so ingest only the recognition record — standard number, edition, OJ citation, harmonized status, withdrawal date — and deep-link to the official copy. See `../../RegOps.md` § Data Strategy (Tier D) and `../../import-source-map.md`.

| Resource                          | URL                                                                                                        | Priority |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------ | -------- |
| Harmonized standards OJ citations | [https://single-market-economy.ec.europa.eu/sectors/cosmetics/legislation_en](https://single-market-economy.ec.europa.eu/sectors/cosmetics/legislation_en) | P2       |

---

## Recommended Crawling Frequency

| Category                     | Frequency |
| ---------------------------- | --------- |
| EUR-Lex / Official Journal   | Daily     |
| Annexes & amending acts      | Daily     |
| EC Regulation (1223/2009)    | Weekly    |
| CosIng                       | Weekly    |
| Safety Gate                  | Daily     |
| Guidance                     | Monthly   |
| SCCS Opinions                | Weekly    |

---

## Supported Formats

* HTML
* PDF
* XML
* RSS
* CSV
* JSON (if available)

---

## Language

EU acts publish in 24 official languages. Ingest **EN** as the authoritative text (`/oj/eng` on ELI URLs); retain the source-language URL in metadata for citation.

---

## Metadata

* Document ID
* Regulation Number
* Title
* Authority
* Country/Region
* Version
* Effective Date
* Last Updated
* URL
* Language
* Format
* SHA-256
* Imported Time
* Parser Version
* Original Raw File
* Parsed Text
