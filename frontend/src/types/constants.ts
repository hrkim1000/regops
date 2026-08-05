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

/** How many characters of an archived artefact to render inline before truncating. */
export const RAW_PREVIEW_CHARS = 200_000;
