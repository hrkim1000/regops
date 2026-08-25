# Request for programmatic access — Recognized Consensus Standards database

**Send to:** FDA via <https://www.fda.gov/about-fda/contact-fda>. If a CDRH Standards Program
contact is reachable, prefer it — that page could not be read from here to find one, because
`www.fda.gov` returns the same abuse-detection redirect described below.

**Before sending, fill in:** `<your role>`, `<your organisation>`, `<your email>`,
`<source IP or CIDR range>`. Leave everything else as written — the specifics are what make this
answerable.

**Fill the email and the IP range in the message you send, not in this file.** It is committed, and
this repository is mirrored to a shared one; `CLAUDE.md` keeps real addresses out of docs, and no
document here carries one today. The name is already the author of every commit, so it is written
in.

---

## Subject

Automated client blocked by abuse detection — request to allow low-volume access to the Recognized
Consensus Standards database

## Message

Dear FDA,

I am Hyeran Kim, `<your role>` at `<your organisation>`. We operate an internal regulatory
compliance system that tracks the medical device and cosmetic regulations our products are subject
to, including the FDA Recognized Consensus Standards list.

Since 25 August 2026 our client has been unable to reach `accessdata.fda.gov`. Requests are answered
with `HTTP 302` to `/apology_objects/abuse-detection-apology.html`, served by `AkamaiGHost`; that
target then returns `404`. The same happens on `www.fda.gov`. The redirect appears to be keyed on our
`User-Agent` string.

We would like to ask for this client to be allowed, and we would rather ask than work around it. We
have deliberately not tried to find a `User-Agent` that is not blocked: identifying ourselves
accurately is the point, and disguising the client would defeat the control.

**What we request.** One thing only: that the client identified below be permitted to make the
described requests.

### The client

| | |
|---|---|
| `User-Agent` | `RegOps-ImportAgent/0.1 (+https://github.com/hrkim1000/regops)` |
| Source address | `<source IP or CIDR range>` |
| Contact | `<your email>` |

We note without complaint that the string above follows the conventional crawler
self-identification format, and we suspect that format is itself what the detector matches. We are
willing to change it to any form you prefer, provided it still identifies us honestly.

### The requests

A single endpoint, queried once per standard:

```
GET https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/results.cfm
        ?referencenumber={reference}&Search=Search
```

`{reference}` takes six values, and only these six:

| Reference | Standard |
|---|---|
| `62304` | IEC 62304 — medical device software life cycle processes |
| `14971` | ISO 14971 — risk management |
| `62366` | IEC 62366-1 — usability engineering |
| `81001-5-1` | IEC 81001-5-1 — health software security |
| `SW96` | ANSI/AAMI SW96 — security risk management |
| `CR515` | AAMI CR515 — software bill of materials |

**Volume: six requests per day, on a daily schedule.** That is the whole of it.

**We do not crawl the database.** The full list runs to more than a thousand records across ten or
more pages; we deliberately do not sweep it, because we need eight records and sweeping would cost
you a thousand to deliver them. Our client fetches one page per query and does not follow the pager.

**We honour `robots.txt`.** In particular we do not use the Excel export
(`/scripts/cdrh/*excel*.cfm`), because your `robots.txt` disallows it. We use conditional requests
where the server offers validators, and we back off on `503` and `429` rather than retrying
immediately.

### What we store, and what we do not

We store the **recognition record only**: recognition number, extent of recognition, standards
developing organisation, standard designation, title, and date of entry — the fields your results
page displays.

**We do not store the text of any standard, and our system has nowhere to put it.** ISO and IEC
prohibit storing standard text and using it for AI training, so we treat the standards themselves as
metadata-plus-link throughout: the database table that holds these records has no text column, every
field in it is a bounded identifier or a date, and an automated check in our build fails if standard
text appears anywhere in the repository. Where a regulation incorporates a standard by reference —
21 CFR 820 and ISO 13485:2016, for instance — we cite the regulation, link to the standard, and
store neither.

The recognition list is how we learn that a recognition has changed. It is the only thing we fetch,
and it is the reason we need to fetch it at all.

### If access cannot be granted

We would still find it useful to know:

1. whether a different `User-Agent` format would pass, so that we can identify ourselves in a way
   your protection accepts;
2. whether the recognition list is published anywhere as bulk or structured data, which would let us
   stop querying the web endpoint entirely;
3. whether there is a more appropriate contact for this request within CDRH.

Thank you for your time, and for maintaining the database — it is the authoritative record of what
FDA recognises, and there is no substitute for it.

Regards,
Hyeran Kim
`<your organisation>`
`<your email>`

---

## Notes for the sender — not part of the message

- **Do not** paste an internal hostname, credential, or anything from `.env*`. The only site-specific
  values are your contact details and the source IP range.
- The IP range matters more than anything else here. If the egress address is dynamic, say so and
  give the range rather than a single address.
- If FDA answers by asking us to change the `User-Agent`, that is an acceptable outcome and **not**
  the evasion this project rules out: it is identifying ourselves in a form the operator asked for,
  agreed with them, in the open. Record the agreed string in
  [phase2.0a](../plan/phase2.0a_fda.md) *Deviations* when it lands.
- Re-enabling the sources afterwards is a `seed.py` change: set the six `recognition_list` rows back
  to `enabled=True` and re-run the seeder.
