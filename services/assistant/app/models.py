"""Tables owned by `assistant` (CLAUDE.md § Table ownership).

Re-exported from the canonical models in ``regops_shared.models`` — never redefined here.

Everything this service *answers from* belongs to `regulation`: ``clauses``, ``documents``,
``document_versions``, ``cells``. Those are read one-way, by raw SQL, exactly the way `monitoring`
reads ``change_events``. The one apparent exception is ``clause_embeddings``, which references
``clauses`` but is owned here: coupling the embedding lifecycle to the clause lifecycle would make
a model swap a `regulation` migration, and the model is the replaceable part.
"""

from regops_shared.models import (
    Answer,
    AnswerCitation,
    ClauseEmbedding,
    Query,
    VerificationResult,
)

__all__ = [
    "Answer",
    "AnswerCitation",
    "ClauseEmbedding",
    "Query",
    "VerificationResult",
]
