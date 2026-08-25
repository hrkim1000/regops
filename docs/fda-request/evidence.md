# Evidence behind the request

Every factual claim in [access-request.md](access-request.md), with the command that produced it.
Measured 2026-08-25. Re-run any of these before sending if time has passed — a request describing a
block that has since lifted is worse than no request.

## 1. The block, and its shape

```bash
UA='RegOps-ImportAgent/0.1 (+https://github.com/hrkim1000/regops)'
U='https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/results.cfm?referencenumber=62304&Search=Search'
curl -sSgD- --max-time 60 -A "$UA" -o /dev/null "$U" | grep -iE '^(HTTP|location|server)'
```

```text
HTTP/1.1 302 Moved Temporarily
Server: AkamaiGHost
Location: /apology_objects/abuse-detection-apology.html
```

Following the redirect lands on `HTTP 404` — the apology page itself does not exist, which is why
the connector recorded a bare `404` rather than anything that named abuse detection.

## 2. It is keyed on the User-Agent, not on the address

Same URL, same source address, three agents:

| `User-Agent` | Result |
|---|---|
| `RegOps-ImportAgent/0.1 (+https://github.com/hrkim1000/regops)` | **302** → apology |
| `curl/8.0` | **302** → apology |
| `RegOps-recon/0.1` | **200** |

**This is the finding that must not be acted on.** A working string exists; using it would be
evasion. It is recorded here because the request asks FDA to allow our agent, and that ask only
makes sense if we can say what is being matched.

## 3. It is FDA-wide, not one host

```bash
curl -sSgL --max-time 90 -A "$UA" -o /dev/null -w '%{http_code} %{url_effective}\n' \
  'https://www.fda.gov/medical-devices/standards-and-conformity-assessment-program/standards-and-conformity-assessment-program-contacts'
```

```text
404 https://www.fda.gov/apology_objects/abuse-detection-apology.html
```

So `www.fda.gov` redirects too. This is why the request names the general contact form rather than a
CDRH technical contact: the page that would identify one cannot be read.

## 4. The endpoint works, and our parser reads it correctly

With an agent that is not blocked, the same query returns the table, and the connector's own parser
produces the right records:

```text
StandardRecord(number='62304 Edition 1.1 2015-06 CONSOLIDATED VERSION',
               issuing_body='IEC', recognition_number='13-79',
               title='Medical device software - Software life cycle processes',
               effective_date='01/14/2019')
StandardRecord(number='62304:2006/A1:2016',
               issuing_body='ANSI AAMI IEC', recognition_number='13-79',
               title='Medical device software - Software life cycle processes [Including Amendment 1 (2016)]',
               effective_date='01/14/2019')
```

Two records sharing recognition number `13-79` — one recognition covering two designations, which is
what the table's `rowspan="2"` means. **Nothing is broken on our side**, which is what makes this a
request rather than a bug report.

## 5. The volume claim

Six references, one request each, once a day. From
[`seed.py`](../../services/regulation/app/seed.py), `FDA_RECOGNISED_STANDARDS`:

```text
62304 · 14971 · 62366 · 81001-5-1 · SW96 · CR515
```

Each returns one or two rows on a single page, so the pager is never followed. Measured earlier the
same day: an unfiltered query returns 100 rows per page with `start_search` offsets running to at
least 901 — which is the sweep we are **not** doing.

## 6. The `robots.txt` claim

```bash
curl -sSg -A "$UA" https://www.accessdata.fda.gov/robots.txt | grep -i excel
```

```text
Disallow: /scripts/cdrh/*excel*.cfm
Disallow: /scripts/cdrh/*Excel*.CFM
...
```

`cfStandards` itself is **not** disallowed — checked across all 42 lines, zero mentions — and there
is no `Crawl-delay`. So the page we query is permitted and the Excel export is not, which is why the
request says we read the HTML.

## 7. The Tier D claim

Not a measurement but a property of the schema, and the strongest sentence in the request, so it is
worth being able to show:

- `standard_references` has **no text column**; every field is a bounded `varchar`, a date, an enum
  or a uuid.
- `StandardRecord`, what this connector returns, has no bytes field at all — there is nothing to
  archive on this path and no WORM write happens.
- `scripts/tier_d_scan.py` runs in the build and fails if standard text appears anywhere in the
  repository. It reported **clean over 410 files** on the day this was written.

Sources: [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decision 2,
[ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 7.

## 8. What openFDA does not carry

Worth knowing before anyone suggests it as the alternative: openFDA serves 510(k), PMA, device
classification, registration and listing, recalls, MAUDE and UDI. It does **not** carry the
Recognized Consensus Standards list, and it is not a source of regulation text either
([spike-2026-08-24](../design/spike-2026-08-24-fda-source-recon.md)).
