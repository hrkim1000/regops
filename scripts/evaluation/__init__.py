"""The phase 1.6 evaluation harness — the numbers the M4 Go/No-Go decision is made from.

The purpose of the PoC is measurement, not a demo, and No-Go is called if four or more of the six
gates fall short. Everything here exists to make that judgement defensible rather than arguable, so
two rules run through the whole package:

**A measurement states its own method.** Every number this harness emits carries the triple that
produced it — ``(rule_version, prompt_version, llm_model)`` for anything model-bound — plus the
denominator it was divided by. A score without its regime is not reproducible, and a rate without
its denominator is not checkable.

**A number nobody could have measured is not reported as if somebody had.** Three of the six gates
are human judgements: citation accuracy and hallucination rate rest on blind RA assessment, and
research-time savings on a baseline captured before the pilot. The harness computes their
*mechanical* halves — a cited clause either resolves at its version or it does not — and emits a
blind worksheet for the rest. It never fills the human half in with a proxy and calls it the gate.
"""

from __future__ import annotations

__all__: list[str] = []
