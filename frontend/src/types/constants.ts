export const SCOPE_COOKIE = 'regops_scope_cell';

/** httpOnly — set by /session, read by middleware and Server Components, never by client JS. */
export const ACCESS_TOKEN_COOKIE = 'regops_access_token';

/** Human labels for the document kinds the ingest pipeline produces. */
export const DOC_TYPE_LABEL: Record<string, string> = {
  law: '법률',
  decree: '시행령',
  enforcement_rule: '시행규칙',
  notice: '고시',
  annex: '별표',
  guidance: '가이드',
  feed: '피드',
};

/**
 * 국가법령정보's own top-level taxonomy — the way the authority groups its holdings, and so the
 * way an RA already reads them. Labels mirror the source's wording rather than our `doc_type`.
 *
 * Order matches `DOC_CATEGORY_ORDER` in the API; the server sorts by it, so the client only has to
 * render a header when the category changes.
 */
export const DOC_CATEGORY_LABEL: Record<string, string> = {
  statute: '현행법령',
  admin_rule: '현행 행정규칙',
  statute_annex: '법령 별표·서식',
  admin_rule_annex: '행정규칙 별표·서식',
  feed: '변경 신호 (RSS)',
  other: '기타',
};

/** Categories whose members are annexes — listed under their parent, not as instruments. */
export const ANNEX_CATEGORIES = ['statute_annex', 'admin_rule_annex'] as const;

/**
 * Where a version sits relative to today. 시행예정 is the one that has to be visible: a 법령 with
 * four 공포된 amendments still awaiting 시행 is otherwise indistinguishable from one with none.
 */
export const VERSION_STATUS_LABEL: Record<string, string> = {
  in_force: '시행중',
  pending: '시행예정',
  superseded: '지난 버전',
  unknown: '시행일 미확정',
};

/** Tailwind classes per status. 시행예정 is the only one that draws the eye. */
export const VERSION_STATUS_STYLE: Record<string, string> = {
  in_force: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
  pending: 'border-amber-700 bg-amber-950/50 text-amber-300',
  superseded: 'border-surface-border text-slate-500',
  unknown: 'border-surface-border text-slate-500',
};

/** How many characters of an archived artefact to render inline before truncating. */
export const RAW_PREVIEW_CHARS = 200_000;

/**
 * Clauses per page in the clause view. The 95th-percentile version holds 309 clauses and the
 * largest 2,212, so this renders most instruments whole; the API caps the parameter at 1,000.
 */
export const CLAUSE_PAGE_SIZE = 500;

/** Indent per hierarchy level, and the depth past which further nesting stops indenting. */
export const CLAUSE_INDENT_REM = 1.25;
export const CLAUSE_MAX_INDENT_LEVEL = 5;
