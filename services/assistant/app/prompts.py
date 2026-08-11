"""Prompts for the two agents in this service, and the contract their replies must satisfy.

Both prompts are built around one asymmetry that ADR-0006 decision 6 makes explicit: **the
generator sees the question, and the verifier does not.** A verifier shown the question drifts
toward confirming that the answer addresses it; shown only the claim and the clause text, it can
only judge whether the text says what the claim says it says.

Citation is produced *with* the claim and constrains it — it is a property of generation, not a
downstream annotation step (decision 4). The reply format enforces that shape: there is nowhere in
it to put a sentence that has no citation.
"""

from __future__ import annotations

from collections.abc import Sequence

from regops_shared.constants import MAX_CITABLE_PATHS_PER_PASSAGE, MAX_PROMPT_BLOCK_CHARS

from .store import Hit, VersionRef

ANSWER_SYSTEM_PROMPT = """\
You are a regulatory research assistant. You answer ONLY from the numbered passages you are given.

Your answer IS the list of claims. There is no separate prose field: every sentence a reader will
see is one of these claims, so each one must stand on its own and carry its citation.

Absolute rules:
1. Every claim MUST cite at least one passage. A sentence you cannot cite does not belong in the
   answer, so do not write it.
2. You may cite ONLY the passage numbers provided, and within a passage only the clause paths listed
   under "citable". Never invent a clause number, an article, or a document.
3. If the passages do not answer the question, return an empty "claims" list. That is a correct and
   expected outcome, not a failure.
4. Do not add background, caveats, or general knowledge. Only what the passages state.
5. Write in the language of the question. Be brief: state the duty, the deadline or the limit, and
   stop.

Reply with JSON only, in exactly this shape:

{"claims": [
   {"text": "<one factual statement, a complete sentence>",
    "cites": [{"passage": <number>, "clause_path": "<one of that passage's citable paths>"}]}
 ]}
"""

VERIFY_SYSTEM_PROMPT = """\
You check whether a piece of regulatory text supports a specific claim.

You are given ONE claim and the exact text of the clauses it cites. You are deliberately NOT given
the question that produced the claim: your job is not to decide whether the claim is a good answer,
only whether the cited text says it.

Verdicts:
- "supported"   — the cited text states the claim, or states it so directly that no inference is
                  needed.
- "partial"     — the cited text is about the claim but does not establish all of it (a condition,
                  a scope limit, or a number is missing or different).
- "unsupported" — the cited text does not establish the claim. Use this whenever you would have to
                  rely on knowledge outside the text.

Default to "unsupported" when uncertain. A wrong "supported" is far more damaging than a wrong
"unsupported": it lets an unverifiable statement reach a regulatory professional as fact.

Reply with JSON only:

{"verdict": "supported|partial|unsupported", "reason": "<one short sentence>"}
"""


def build_answer_prompt(
    *,
    question: str,
    hits: Sequence[Hit],
    versions: Sequence[VersionRef],
    effective_date_scope: object | None,
    straddles: bool,
) -> str:
    """The question, the passages, and nothing else.

    Passages are numbered because a clause path alone is ambiguous across documents: 제8조 is in
    all nine 법령 — and the number is what pins a citation to a version without asking a model to
    reproduce a UUID.
    """
    titles = {version.version_id: version.document_title for version in versions}
    blocks: list[str] = []
    for index, hit in enumerate(hits, start=1):
        citable = ", ".join(_citable(hit))
        heading = f" ({hit.heading})" if hit.heading else ""
        blocks.append(
            f"[{index}] {titles.get(hit.document_version_id, '')} {hit.clause_path}{heading}\n"
            f"citable: {citable}\n"
            f"{passage_text(hit)}"
        )

    notes = []
    if effective_date_scope is not None:
        notes.append(f"These passages are as of 시행일 {effective_date_scope}.")
    if straddles:
        notes.append(
            "WARNING: these passages do not all share one effective date. Some are in force and "
            "some are amended but not yet effective. Say so in your answer; do not choose one."
        )

    return "\n\n".join(
        [
            f"Question:\n{question}",
            "Passages:\n\n" + "\n\n".join(blocks),
            *(["Notes:\n" + "\n".join(notes)] if notes else []),
            "Reply with the JSON object described in the system prompt, and nothing else.",
        ]
    )


def build_verification_prompt(*, claim: str, evidence: Sequence[tuple[str, str]]) -> str:
    """One claim, and the verbatim text of every clause it cites. No question, by design."""
    blocks = [f"{path}\n{body}" for path, body in evidence]
    return "\n\n".join(
        [
            f"Claim:\n{claim}",
            "Cited text:\n\n" + "\n\n".join(blocks),
            "Reply with the JSON object described in the system prompt, and nothing else.",
        ]
    )


def passage_text(hit: Hit) -> str:
    """The text of one retrieved unit, bounded.

    **A retrieval hit carries the raw clause text, which has no bound.** ``MAX_PASSAGE_CHARS`` caps
    what gets *embedded*, and conflating the two cost a working query: one live question in
    `mfds_samd` produced eight hits totalling 185,161 characters — a single 별표 clause contributing
    130,603 — which is ≈58,000 tokens into a 32,768 window. Ollama truncates that silently, so the
    visible symptom was a three-minute timeout and the invisible one was a model citing passages
    whose text had been cut away before it ever saw them.

    The stored passage is preferred where the vector arm supplied one: it is the 조-level unit the
    embedding actually matched, already assembled and already bounded. Truncation is marked, because
    a model that cannot see the rest of a clause should be able to tell that there is a rest.
    """
    body = (hit.passage or hit.text or "").strip()
    if len(body) <= MAX_PROMPT_BLOCK_CHARS:
        return body
    return body[:MAX_PROMPT_BLOCK_CHARS].rstrip() + "\n… (이하 생략 / truncated)"


def _citable(hit: Hit) -> list[str]:
    paths = [hit.clause_path, *hit.child_clause_paths]
    return list(dict.fromkeys(paths))[:MAX_CITABLE_PATHS_PER_PASSAGE]


__all__ = [
    "ANSWER_SYSTEM_PROMPT",
    "VERIFY_SYSTEM_PROMPT",
    "build_answer_prompt",
    "build_verification_prompt",
]
