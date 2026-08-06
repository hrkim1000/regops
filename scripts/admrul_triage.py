"""Reconcile the MFDS 행정규칙 catalog against the authority's own list, and write the worklist.

    docker compose exec -T regulation python //scripts/admrul_triage.py \
        > docs/mfds-admrul-coverage.md

Markdown goes to **stdout**, progress to stderr — `docs/` is not mounted into the service container,
and redirecting on the host is cheaper than adding a mount that only this script would use.

**Why this is a script and not a hand-written table.** The gap it reports moves every time MFDS
promulgates a 고시, and `docs/import-source-map.md` is the *only* source catalog (CLAUDE.md) — a
second list maintained by hand is exactly the copy that silently goes stale. So the worklist is
generated: this reads the authority's list live, subtracts what the seed already covers, and
regenerates the table wholesale. Edit the table by hand and the next run discards the edit, which is
the intended pressure.

It reports **three** buckets, and the third is the one a keyword filter cannot produce on its own:

``covered``
    A seeded source already fetches it.

``candidate``
    In scope by :func:`~app.discovery.cells_for` and not covered — the 66-item backlog the
    scheduled sweep already records in ``source_discovery_runs``.

``near-miss``
    Upstream, **not** matched by the cell keywords, but matching a wider net. ADR-0003 decision 11
    requires the production filter to be over-inclusive because "a 고시 missed because the filter
    was clever is a coverage hole"; this bucket measures how well it holds. It is what surfaced
    의약품등의 타르색소 지정과 기준 및 시험방법 — a cosmetic colorant standard whose title names
    neither 화장품 nor 의료기기, and which 화장품의 색소 종류 및 기준 cross-references.

Nothing here changes production behaviour: the scheduled sweep and its filter are untouched. This
is a reading of them.
"""

from __future__ import annotations

import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.discovery import (
    UpstreamRule,
    cells_for,
    excluded_by,
    fetch_admrul_index,
    keyword_cells,
    normalize_title,
)
from regops_shared.constants import DISCOVERY_EXCLUSIONS
from regops_shared.db import sync_session
from regops_shared.models import Source

#: The wider net for the near-miss bucket. Deliberately loose — its output is read by a human once,
#: and its whole purpose is to catch what the production keywords cannot see. Terms that would match
#: most of the 511 (식품, 의약품) are excluded, or the bucket stops being readable.
NEAR_MISS_TERMS: tuple[str, ...] = (
    "색소",
    "타르",
    "원료",
    "의약외품",
    "위해평가",
    "인체적용제품",
    "안전성 정보",
    "표시·광고",
    "표시광고",
)

STATUS_LABEL = {
    "covered": "🟢 커버됨",
    "candidate": "⬜ 후보",
    "excluded": "⛔ 제외(결정)",
    "near_miss": "🟡 필터 밖",
}


@dataclass(frozen=True, slots=True)
class Row:
    rule: UpstreamRule
    cells: tuple[str, ...]
    status: str
    #: For a near-miss, the wider-net term that caught it. Shown so a reader can dismiss a whole
    #: cluster at a glance — 11 of the 18 are 의약외품, which is not one of the 8 cells.
    matched: str = ""

    @property
    def sort_key(self) -> tuple[int, str, str]:
        order = {"covered": 0, "candidate": 1, "excluded": 2, "near_miss": 3}
        return (order[self.status], self.matched or ",".join(self.cells), self.rule.title)


def covered_titles() -> set[str]:
    """Normalized 고시명 the seed already fetches."""
    with sync_session() as session:
        names = session.execute(
            select(Source.params["name"].astext).where(Source.connector == "law_go_kr_admrul")
        )
        return {normalize_title(name) for (name,) in names if name}


def near_miss(title: str) -> str:
    """The wider-net term that catches this title, or ``""``."""
    normalized = unicodedata.normalize("NFC", title)
    return next((term for term in NEAR_MISS_TERMS if term in normalized), "")


def classify(rules: list[UpstreamRule], covered: set[str]) -> list[Row]:
    rows: list[Row] = []
    for rule in rules:
        # Excluded first: `cells_for` already returns empty for these, so without an explicit check
        # a scope decision would be indistinguishable from a title the filter never matched.
        #
        # `keyword_cells`, not `cells_for` — a title has only been *ruled out* if it would otherwise
        # have been in scope. 국가연구개발성과 범부처 이어달리기 프로젝트 matches the 범부처
        # exclusion but names no product domain; listing it would credit a decision nobody made.
        if (term := excluded_by(rule.title)) and keyword_cells(rule.title):
            rows.append(Row(rule, (), "excluded", matched=term))
            continue
        cells = tuple(sorted(cells_for(rule.title)))
        if cells and normalize_title(rule.title) in covered:
            rows.append(Row(rule, cells, "covered"))
        elif cells:
            rows.append(Row(rule, cells, "candidate"))
        elif term := near_miss(rule.title):
            rows.append(Row(rule, (), "near_miss", matched=term))
    return sorted(rows, key=lambda row: row.sort_key)


def render(rows: list[Row], *, upstream_total: int, truncated: bool) -> str:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row.status] += 1
    per_cell: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.status == "candidate":
            for cell in row.cells:
                per_cell[cell] += 1

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out: list[str] = [
        "# MFDS 행정규칙 — coverage against the authority's own list",
        "",
        "> **GENERATED FILE — do not edit.** Regenerate with",
        "> `docker compose exec -T regulation python //scripts/admrul_triage.py`.",
        "> Hand edits are discarded on the next run.",
        "",
        f"Swept `org=1471000` on **{stamp}**: **{upstream_total}** 행정규칙 upstream"
        f"{' (TRUNCATED — the walk hit its page cap)' if truncated else ''}.",
        "",
        "**This is not a source catalog.** [import-source-map.md](import-source-map.md) is the",
        "only one (CLAUDE.md § Architecture rules); this is the *gap* between it and what MFDS",
        "publishes.",
        "A row decided **add** becomes an entry there and a seed row — it is not tracked here.",
        "",
        "| Bucket | Count | Meaning |",
        "|---|---:|---|",
        f"| {STATUS_LABEL['covered']} | {counts['covered']} | a seeded source already fetches it |",
        f"| {STATUS_LABEL['candidate']} | {counts['candidate']} | in scope by keyword, uncovered —"
        " the triage backlog |",
        f"| {STATUS_LABEL['excluded']} | {counts['excluded']} | matched the keywords but ruled"
        " **out of scope by decision** — kept visible on purpose |",
        f"| {STATUS_LABEL['near_miss']} | {counts['near_miss']} | upstream but **outside** the"
        " production keyword filter — read these first |",
        "",
        (
            "Candidates per cell: "
            + " · ".join(f"`{cell}` {n}" for cell, n in sorted(per_cell.items()))
            if per_cell
            else "**No candidates outstanding** — every in-scope 고시 the sweep can see is seeded."
        ),
        "",
        "## ⛔ Scope decisions",
        "",
        'These matched the keywords and were ruled out. They stay listed because **"seen and',
        'rejected" and "never seen" are different states, and only the first can be revisited.**',
        "The rationale lives in [import-source-map.md](import-source-map.md); the enforcement is",
        "`DISCOVERY_EXCLUSIONS`.",
        "",
        "| 제외어 | 사유 |",
        "|---|---|",
        *(f"| `{term}` | {reason} |" for term, reason in DISCOVERY_EXCLUSIONS.items()),
        "",
        "## Why the 🟡 bucket matters",
        "",
        "ADR-0003 decision 11 requires the discovery filter to be **deliberately over-inclusive**",
        '— *"a 고시 missed because the filter was clever is a coverage hole, one wrongly listed',
        'costs a glance."* These rows are upstream but name neither 화장품 nor 의료기기,',
        "so `cells_for()` cannot see them. Each is either a genuine miss (widen the keywords) or",
        "genuinely out of scope (leave it, and the count stays visible). The *매칭어* column names",
        "the term that caught the row, so a whole cluster can be dismissed at a glance —",
        "**의약외품 is not one of the 8 cells** and accounts for most of this bucket.",
        "",
        "## Worklist",
        "",
        "| # | 상태 | cell / 매칭어 | 고시명 | 행정규칙ID | 제개정 | 공포일 |",
        "|---:|---|---|---|---|---|---|",
    ]
    for index, row in enumerate(rows, start=1):
        scope = row.matched and f"*{row.matched}*"
        scope = scope or " · ".join(c.replace("mfds_", "") for c in row.cells) or "—"
        out.append(
            f"| {index} | {STATUS_LABEL[row.status]} | {scope} | {row.rule.title} "
            f"| `{row.rule.admrul_id}` | {row.rule.revision_kind or '—'} "
            f"| {row.rule.promulgated_on or '—'} |"
        )
    out.append("")
    return "\n".join(out)


def main() -> int:
    rules, truncated = fetch_admrul_index()
    rows = classify(rules, covered_titles())
    sys.stdout.write(render(rows, upstream_total=len(rules), truncated=truncated))

    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row.status] += 1
    print(
        f"{len(rules)} upstream → {counts['covered']} covered, "
        f"{counts['candidate']} candidates, {counts['near_miss']} outside the filter",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
