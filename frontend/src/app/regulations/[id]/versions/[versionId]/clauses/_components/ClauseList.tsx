import { clsx } from 'clsx';

import { CLAUSE_INDENT_REM, CLAUSE_MAX_INDENT_LEVEL } from '@/types/constants';
import type { Clause } from '@/types/regulation';

/**
 * The clause store as a reader sees it: document order, the address in the gutter, the text beside
 * it.
 *
 * Two rules the rest of this file exists to honour:
 *
 * - **The address is shown for every clause**, because `clause_path` is what a Citation pins and a
 *   reader has to be able to see what they would cite — not just the text.
 * - **An annex table row is a `Clause`** (ADR-0014), so rows arrive in the same ordinal stream as
 *   prose. They are re-assembled into a table here for reading, but the row keeps its own path.
 */
export function ClauseList({ clauses }: { clauses: Clause[] }) {
  return (
    <ol className="space-y-1">
      {group(clauses).map((node) =>
        node.kind === 'table-block' ? (
          <TableBlock key={node.table.id} table={node.table} rows={node.rows} />
        ) : (
          <ClauseRow key={node.clause.id} clause={node.clause} />
        ),
      )}
    </ol>
  );
}

type Node =
  | { kind: 'clause'; clause: Clause }
  | { kind: 'table-block'; table: Clause; rows: Clause[] };

/**
 * Re-assemble each `table` clause with the `table_row` clauses that follow it.
 *
 * Rows are contiguous after their table in ordinal order, so one pass is enough. A row whose table
 * fell on the previous page has no header to render against and stays a plain clause — a table
 * drawn with guessed column order would be worse than no table.
 */
function group(clauses: Clause[]): Node[] {
  const nodes: Node[] = [];
  for (const clause of clauses) {
    const open = nodes.at(-1);
    if (
      clause.kind === 'table_row' &&
      open?.kind === 'table-block' &&
      clause.parent_clause_id === open.table.id
    ) {
      open.rows.push(clause);
    } else if (clause.kind === 'table') {
      nodes.push({ kind: 'table-block', table: clause, rows: [] });
    } else {
      nodes.push({ kind: 'clause', clause });
    }
  }
  return nodes;
}

function indent(level: number): { paddingLeft: string } {
  return { paddingLeft: `${Math.min(level, CLAUSE_MAX_INDENT_LEVEL) * CLAUSE_INDENT_REM}rem` };
}

function ClauseRow({ clause }: { clause: Clause }) {
  const isHeading = clause.kind === 'heading';
  return (
    <li id={clause.clause_path} style={indent(clause.level)} className="scroll-mt-24">
      <div className="flex gap-3">
        <ClausePath clause={clause} />
        <div className="min-w-0 flex-1">
          <p
            className={clsx(
              'whitespace-pre-wrap break-words text-sm leading-relaxed',
              isHeading ? 'font-semibold text-slate-100' : 'text-slate-300',
            )}
          >
            {clause.text}
          </p>
          <ClauseDate clause={clause} />
        </div>
      </div>
    </li>
  );
}

/**
 * One table, drawn from the ordered header on the `table` clause.
 *
 * The order has to come from here: a row's `row_columns` is a `jsonb` object and Postgres sorts its
 * keys, so rendering from the row alone would put 등급 before 연번 and silently mis-column the
 * limit table the whole annex exists to state.
 */
function TableBlock({ table, rows }: { table: Clause; rows: Clause[] }) {
  const header = Array.isArray(table.row_columns) ? table.row_columns : [];

  if (header.length === 0) {
    return (
      <li style={indent(table.level)}>
        <div className="flex gap-3">
          <ClausePath clause={table} />
          <p className="flex-1 whitespace-pre-wrap text-sm text-slate-400">{table.text}</p>
        </div>
      </li>
    );
  }

  return (
    <li id={table.clause_path} style={indent(table.level)} className="scroll-mt-24">
      <div className="flex gap-3">
        <ClausePath clause={table} />
        <div className="min-w-0 flex-1 overflow-x-auto rounded-md border border-surface-border">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="bg-surface-raised/60">
                <th className="whitespace-nowrap px-2 py-1.5 text-left text-[10px] font-normal uppercase tracking-wide text-slate-500">
                  clause_path
                </th>
                {header.map((label) => (
                  <th
                    key={label}
                    className="whitespace-nowrap px-2 py-1.5 text-left font-medium text-slate-300"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const cells = (row.row_columns ?? {}) as Record<string, string>;
                return (
                  <tr key={row.id} id={row.clause_path} className="border-t border-surface-border">
                    {/* The row's own address — an annex row is cited exactly like a 조. */}
                    <td className="whitespace-nowrap px-2 py-1.5 font-mono text-[10px] text-slate-500">
                      {row.clause_path}
                    </td>
                    {header.map((label) => (
                      <td key={label} className="px-2 py-1.5 align-top text-slate-300">
                        {cells[label] ?? ''}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length === 0 ? (
            <p className="px-2 py-1.5 text-[11px] text-slate-500">
              이 표의 행은 다음 페이지에 있습니다
            </p>
          ) : null}
        </div>
      </div>
    </li>
  );
}

function ClausePath({ clause }: { clause: Clause }) {
  return (
    <span
      className="w-40 shrink-0 truncate pt-0.5 font-mono text-[11px] text-slate-500"
      title={`${clause.clause_path}${clause.source_ref ? ` · 조문키 ${clause.source_ref}` : ''}`}
    >
      {clause.clause_path}
      {/* The authority's own 조문변경여부, shown only where it is set — the source's claim about
          its own text, kept distinct from the diff we computed. */}
      {clause.authority_changed ? <span className="ml-1 text-amber-400">·개정</span> : null}
    </span>
  );
}

/**
 * A clause-level date is rare and always significant: it overrides its version's. Null with a
 * retained phrase is rendered as the phrase, never as a guessed date (ADR-0013).
 */
function ClauseDate({ clause }: { clause: Clause }) {
  if (!clause.effective_date && !clause.effective_date_phrase) return null;
  return (
    <p className="mt-1 text-[11px] text-amber-300/80">
      조문 시행일 {clause.effective_date ?? clause.effective_date_phrase}
    </p>
  );
}
