# FDA access request

**Status: drafted 2026-08-25, not yet sent.**

`accessdata.fda.gov` and `www.fda.gov` sit behind Akamai, which currently classifies this project's
identified client as abuse and answers it with a redirect to an apology page. That closes the only
path we have to FDA's Recognized Consensus Standards list, and with it the Tier D freshness story
for the `fda_samd` cell.

This folder holds the request that asks FDA to let us back in, and the measured evidence behind it.

| File | What it is |
|---|---|
| [access-request.md](access-request.md) | The request itself, in Markdown — for an email |
| [access-request.txt](access-request.txt) | The same request as plain text — **for a web form**, which will not render Markdown. 4,192 characters between its two markers |
| [evidence.md](evidence.md) | What was measured, when, and with what commands — so nothing in the request is asserted from memory |

## How to send it

Open <https://www.fda.gov/about-fda/contact-fda> **in a browser** and take the technical or
website-feedback route. An abuse-detection unblock is handled by the people who run the site rather
than by the standards programme, so website feedback is likelier to reach them than a device-policy
mailbox.

That page could not be checked from here, because `www.fda.gov` returns the same redirect the
request is about. **A person opening it in a browser is not affected** — the block is on automated
access, not on us as people, and using the site as intended is not the workaround ruled out below.

Use the `.txt` for a form and the `.md` for an email. If the form caps the length, the `.txt` says
what to cut and in what order — and what must not be cut.

## Why a request rather than a workaround

The block is triggered by our `User-Agent`, and a different one gets through today. **We are not
going to use one.** Looking for a string that slips past an abuse detector is evasion, it is the
behaviour [ADR-0018](../design/ADR-0018-fda-source-model.md) decision 11 forbids on the other FDA
hosts for exactly this reason, and it would make us the thing the control exists to stop.

There is an irony worth stating in the request itself: the string that trips the detector is the
*polite* one. `RegOps-ImportAgent/0.1 (+https://github.com/hrkim1000/regops)` follows the crawler
self-identification convention, and that convention is itself a bot signal.

## What is blocked, and what is not

| Host | Operator | State |
|---|---|---|
| `accessdata.fda.gov` | FDA | **Blocked** — 302 to `/apology_objects/abuse-detection-apology.html` |
| `www.fda.gov` | FDA | **Blocked** — same redirect |
| `ecfr.gov` | Office of the Federal Register (NARA) | Working. Different organisation, different channel |
| `federalregister.gov` | Office of the Federal Register (NARA) | Working. Same |
| `api.govinfo.gov` | GPO | Working, with an API key |

**The two are not one conversation.** If the OFR hosts ever block us, their unblock page carries a
*Site Help* form that explicitly invites a request for a wider IP range; that is a separate channel
and this request does not cover it.

## Until it is answered

The six `recognition_list` seed rows exist and are **disabled** — the row is there, it just does not
fire ([phase2.0a](../plan/phase2.0a_fda.md) *Deviations* 17). The connector, the column mapping and
the parser are all verified correct against the live page; only the fetch is refused. When access is
granted, re-enabling is a seed change and nothing else.

**Do not re-enable by changing how we identify.**
