"""Turning a clause tree into the passages that get embedded — ADR-0006 decisions 1 and 2.

**Embed coarse, cite fine.** The embedding unit is the 조, with its 항/호/목 rolled into one
passage; citation still resolves to whichever child the answer actually used. The two granularities
are deliberately different because they answer different needs: a 호 embedded alone is
unretrievable — ``3. 갈색`` carries no meaning without its parent — while citing at 조 level would
break the clause-level precision the citation contract requires.

**Annex table rows are not embedded at all.** 별표 1 of 화장품 안전기준 규정 is thousands of
near-identical ingredient lines differing in a substance name, a CAS number and a limit; embedded,
they cluster so tightly that similarity is noise. What is embedded is the table's title and column
labels, so *"화장품에 쓸 수 없는 원료 목록이 있나?"* still retrieves the annex — after which the
lookup is relational, against ``clauses.row_columns``.

This module is deliberately pure: clause rows in, passages out. No database, no model. The
falsifiable claims about passage assembly — what is a root, what rolls in, where a long article
splits — are then testable without either.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from regops_shared.constants import MAX_PASSAGE_CHARS, ClauseKind, EmbeddingScope


@dataclass(frozen=True, slots=True)
class ClauseRow:
    """One clause, as read across the service boundary by raw SQL.

    Not the ``Clause`` ORM model on purpose: `assistant` reads the clause store one-way and never
    imports `regulation`'s models (CLAUDE.md § Table ownership).
    """

    id: Any
    clause_path: str
    kind: str
    heading: str | None
    text: str
    ordinal: int
    parent_clause_id: Any | None
    row_columns: dict | list | None = None


@dataclass(slots=True)
class Passage:
    """One unit of the retrieval index, before it has a vector."""

    clause_id: Any
    clause_path: str
    scope: EmbeddingScope
    fragment_index: int
    text: str
    #: Every clause folded into this passage, the root first. This is what lets generation cite
    #: 제8조제2항제3호 from a match that only ever had to find 제8조.
    child_clause_paths: list[str] = field(default_factory=list)
    #: Document title, ancestor headings and the clause address. Kept separately so the cap pass can
    #: re-prepend it to every piece it cuts — a fragment that lost its heading is as unretrievable
    #: as the bare 호 this whole design exists to avoid.
    header: str = ""

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def build_passages(
    clauses: Sequence[ClauseRow], *, document_title: str | None = None
) -> list[Passage]:
    """Assemble every passage for one document version, in document order.

    Passage roots **partition** the tree: a clause belongs to exactly one passage, the nearest root
    at or above it. That is what keeps the index free of duplicated text without needing a
    de-duplication pass — an annex's prose item is a root in its own right, so it is not also folded
    into the table above it.
    """
    by_id = {clause.id: clause for clause in clauses}
    children: dict[Any, list[ClauseRow]] = {}
    for clause in sorted(clauses, key=lambda c: c.ordinal):
        children.setdefault(clause.parent_clause_id, []).append(clause)

    out: list[Passage] = []
    for clause in sorted(clauses, key=lambda c: c.ordinal):
        if not is_passage_root(clause, by_id.get(clause.parent_clause_id)):
            continue
        out.extend(
            _passage_for(
                clause,
                children=children,
                by_id=by_id,
                document_title=document_title,
            )
        )
    return enforce_cap(out)


def enforce_cap(passages: list[Passage]) -> list[Passage]:
    """No passage may exceed :data:`MAX_PASSAGE_CHARS`, whatever kind it is.

    Splitting at 항 boundaries handles the common long article, but three shapes slip past it: a
    whole 서식 with an embedded table, a table whose column labels run long, and a single 항 that is
    itself oversized. Measured on the gated corpus, those produced passages of up to 21,588
    characters — and Ollama answers an over-long embedding request with **HTTP 500** rather than
    truncating, so an unbounded passage is not a quality problem, it is a version that never gets
    indexed at all.

    Cutting on line boundaries keeps clause lines intact where it can, and falls back to a hard
    character cut for a single enormous line (a box-drawing table rendered as one row of text).
    """
    out: list[Passage] = []
    for passage in passages:
        if len(passage.text) <= MAX_PASSAGE_CHARS:
            out.append(passage)
            continue
        out.extend(_cut(passage))

    # Fragment index is UNIQUE per (clause_id, fragment_index), so renumber after cutting rather
    # than trusting the index each producer happened to assign.
    seen: dict[Any, int] = {}
    for passage in out:
        index = seen.get(passage.clause_id, 0)
        passage.fragment_index = index
        seen[passage.clause_id] = index + 1
    return out


def _cut(passage: Passage) -> list[Passage]:
    """Split one over-long passage, re-prepending its header to every piece."""
    header = passage.header
    budget = max(MAX_PASSAGE_CHARS - len(header) - 1, MAX_PASSAGE_CHARS // 4)
    body = (
        passage.text[len(header) :].lstrip("\n")
        if passage.text.startswith(header)
        else passage.text
    )

    pieces: list[str] = []
    current = ""
    for line in body.split("\n"):
        while len(line) > budget:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:budget])
            line = line[budget:]
        if current and len(current) + len(line) + 1 > budget:
            pieces.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        pieces.append(current)

    return [
        Passage(
            clause_id=passage.clause_id,
            clause_path=passage.clause_path,
            scope=passage.scope,
            fragment_index=index,
            text=_join(header, piece),
            child_clause_paths=list(passage.child_clause_paths),
            header=header,
        )
        for index, piece in enumerate(pieces)
    ]


def is_passage_root(clause: ClauseRow, parent: ClauseRow | None) -> bool:
    """Whether this clause starts a passage.

    A 조 is a root; its 항/호/목 are not, because they roll into it. A heading (편/장/절) is never a
    root — it has no content of its own and serves as context for the articles beneath it. A table
    is a root so that its title and column labels are retrievable; a table **row** never is, which
    is decision 2 expressed as one line rather than as a filter somewhere downstream.
    """
    kind = clause.kind
    if kind in (ClauseKind.TABLE_ROW.value, ClauseKind.HEADING.value):
        return False
    if kind in (ClauseKind.TABLE.value, ClauseKind.FORM.value):
        return True
    # PROSE: a root unless it hangs off another prose clause, in which case it is a 항/호/목 that
    # belongs to the article above it.
    return parent is None or parent.kind != ClauseKind.PROSE.value


def _scope_for(clause: ClauseRow) -> EmbeddingScope:
    match clause.kind:
        case ClauseKind.TABLE.value:
            return EmbeddingScope.TABLE_HEADER
        case ClauseKind.FORM.value:
            return EmbeddingScope.FORM
        case _:
            return EmbeddingScope.ARTICLE


def _passage_for(
    root: ClauseRow,
    *,
    children: dict[Any, list[ClauseRow]],
    by_id: dict[Any, ClauseRow],
    document_title: str | None,
) -> list[Passage]:
    scope = _scope_for(root)
    header = _header(root, by_id=by_id, document_title=document_title)

    if scope is EmbeddingScope.TABLE_HEADER:
        # Title and column labels only. The rows behind them are reachable by exact match on
        # `row_columns`, which is what an ingredient question actually needs.
        body = _column_labels(root.row_columns)
        text = _join(header, root.heading or "", root.text, body)
        return [
            Passage(
                clause_id=root.id,
                clause_path=root.clause_path,
                scope=scope,
                fragment_index=0,
                text=text,
                child_clause_paths=[root.clause_path],
                header=header,
            )
        ]

    blocks = _child_blocks(root, children=children, by_id=by_id)
    own = _join(header, _rendered(root, is_root=True))
    whole = _join(own, *(block.text for block in blocks))

    if len(whole) <= MAX_PASSAGE_CHARS or not blocks:
        return [
            Passage(
                clause_id=root.id,
                clause_path=root.clause_path,
                scope=scope,
                fragment_index=0,
                text=whole,
                child_clause_paths=[root.clause_path, *(p for b in blocks for p in b.paths)],
                header=header,
            )
        ]

    # Long 조 are split at 항 boundaries with the heading re-prepended, so every fragment stays
    # self-describing (decision 1). A fragment that lost its heading would be as unretrievable as
    # the bare 호 this whole design exists to avoid.
    return _split(root, scope=scope, own=own, header=header, blocks=blocks)


@dataclass(slots=True)
class _Block:
    """One direct child of a passage root, with everything beneath it already flattened."""

    text: str
    paths: list[str]


def _child_blocks(
    root: ClauseRow, *, children: dict[Any, list[ClauseRow]], by_id: dict[Any, ClauseRow]
) -> list[_Block]:
    blocks: list[_Block] = []
    for child in children.get(root.id, []):
        if _excluded(child, parent=root):
            continue
        lines: list[str] = []
        paths: list[str] = []
        _flatten(child, children=children, by_id=by_id, lines=lines, paths=paths)
        if lines:
            blocks.append(_Block(text=_join(*lines), paths=paths))
    return blocks


def _excluded(clause: ClauseRow, *, parent: ClauseRow) -> bool:
    """Whether a child belongs to someone else's passage, or to nobody's."""
    if clause.kind == ClauseKind.TABLE_ROW.value:
        return True
    return is_passage_root(clause, parent)


def _flatten(
    clause: ClauseRow,
    *,
    children: dict[Any, list[ClauseRow]],
    by_id: dict[Any, ClauseRow],
    lines: list[str],
    paths: list[str],
) -> None:
    rendered = _rendered(clause, is_root=False)
    if rendered:
        lines.append(rendered)
    paths.append(clause.clause_path)
    for child in children.get(clause.id, []):
        if _excluded(child, parent=clause):
            continue
        _flatten(child, children=children, by_id=by_id, lines=lines, paths=paths)


def _split(
    root: ClauseRow, *, scope: EmbeddingScope, own: str, header: str, blocks: list[_Block]
) -> list[Passage]:
    del scope  # a split passage is always ARTICLE_FRAGMENT, whatever the whole would have been
    out: list[Passage] = []
    current: list[_Block] = []
    current_len = len(own)

    def flush() -> None:
        nonlocal current, current_len
        if not current:
            return
        out.append(
            Passage(
                clause_id=root.id,
                clause_path=root.clause_path,
                scope=EmbeddingScope.ARTICLE_FRAGMENT,
                fragment_index=len(out),
                text=_join(own, *(block.text for block in current)),
                child_clause_paths=[
                    root.clause_path,
                    *(path for block in current for path in block.paths),
                ],
                header=header,
            )
        )
        current = []
        current_len = len(own)

    for block in blocks:
        # A single oversized 항 still gets its own fragment rather than being dropped: a truncated
        # obligation is worse than a long one, because it is silently incomplete.
        if current and current_len + len(block.text) > MAX_PASSAGE_CHARS:
            flush()
        current.append(block)
        current_len += len(block.text) + 1
    flush()
    return out


# --- rendering -------------------------------------------------------------------------------


def _header(root: ClauseRow, *, by_id: dict[Any, ClauseRow], document_title: str | None) -> str:
    """Document title, ancestor headings, and the clause's own address.

    Every one of these earns its tokens. Without the document title, *"제8조"* matches as well in
    nine 법령; without the ancestor trail a 조 inside 제3장 안전관리 loses the topic its chapter
    supplies; without the path the passage cannot be pointed at.
    """
    trail: list[str] = []
    seen: set[Any] = set()
    node = by_id.get(root.parent_clause_id)
    while node is not None and node.id not in seen:
        seen.add(node.id)
        label = (node.heading or node.text or "").strip().splitlines()
        if label and label[0]:
            trail.append(label[0][:120])
        node = by_id.get(node.parent_clause_id)
    trail.reverse()

    parts = [part for part in (document_title, *trail) if part]
    return _join(" > ".join(parts), root.clause_path)


def _rendered(clause: ClauseRow, *, is_root: bool) -> str:
    """One clause as a line: its heading, then its text.

    A non-root line is prefixed with its own address so that a reviewer reading the retrieved
    passage can see which child a citation refers to without holding the tree in their head.
    """
    heading = (clause.heading or "").strip()
    text = (clause.text or "").strip()
    if is_root:
        return _join(heading, text)
    tail = clause.clause_path.rsplit("/", 1)[-1]
    body = _join(heading, text)
    return f"{tail} {body}".strip() if body else ""


def _column_labels(row_columns: dict | list | None) -> str:
    """A table's column labels, in order. On a ``TABLE`` clause ``row_columns`` is that list."""
    if isinstance(row_columns, list):
        labels: Iterable[Any] = row_columns
    elif isinstance(row_columns, dict):
        labels = row_columns.keys()
    else:
        return ""
    return " | ".join(str(label).strip() for label in labels if str(label).strip())


def _join(*parts: str) -> str:
    return "\n".join(part for part in (p.strip() for p in parts if p) if part)


__all__ = ["ClauseRow", "Passage", "build_passages", "is_passage_root"]
