/** Mirrors the `regulation` service IR schema (phase 1.2). Field names identical to the API. */

/**
 * IR lifecycle (ADR-0004 decision 4). **Only `locked` flows downstream** — a `draft` is unreviewed
 * model output and a `stale` one has had its evidence amended out from under it.
 */
export type IRStatus = 'draft' | 'locked' | 'rejected' | 'stale' | 'superseded';

export type IRRejectionReason =
  | 'not_an_obligation'
  | 'misread_clause'
  | 'not_atomic'
  | 'wrong_citation'
  | 'duplicate';

export type Domain = 'samd' | 'cosmetic';

/**
 * A citation is pinned to an immutable version, never to "current" (ADR-0002 decision 4).
 *
 * `document_id` and `document_version_id` travel with the citation because a link to the cited
 * clause must resolve from the citation's own binding — not from the page it happens to be rendered
 * on. A superseded citation points at an *older* version, and following it must land on the text
 * that was actually cited.
 */
export interface IRCitation {
  document_id: string;
  document_version_id: string;
  clause_path: string;
  effective_date: string | null;
  /** Set by the diff stage when an amendment touched the cited path. The row is never rewritten. */
  superseded_at: string | null;
}

/** What produced this row. Mandatory reading, not diagnostics (ADR-0004 decision 4). */
export interface IRProvenance {
  llm_provider: string | null;
  llm_model: string | null;
  prompt_version: string | null;
  rule_version: string | null;
  extraction_run_id: string | null;
}

export interface ExtractionRun {
  id: string;
  document_version_id: string;
  domain_profile: Domain;
  rule_version: string;
  prompt_version: string;
  llm_provider: string;
  llm_model: string;
  /** Pinned to 0 (ADR-0017 decision 1). Stored rather than assumed, so the claim is checkable. */
  temperature: number | null;
  status: 'running' | 'completed' | 'failed';
  clauses_seen: number;
  irs_written: number;
  /** Proposals discarded for having no resolvable citation. A climbing rate is a prompt regression. */
  rejected_uncited: number;
  started_at: string;
  completed_at: string | null;
  error: string | null;
}

export interface IR {
  id: string;
  /** Selects the extraction *rule set*, not a code path (ADR-0004 decision 3). */
  domain_profile: Domain;
  bearer: string | null;
  modal: string | null;
  statement: string;
  /**
   * Where a class or category restriction lives. One parameterised IR, never one per class
   * (ADR-0017 decision 2) — so this field is scope information, not a footnote.
   */
  condition_text: string | null;
  taxonomy_code: string | null;
  status: IRStatus;
  /** Server-derived from `status`. There is no second stored flag to drift out of step. */
  visible_downstream: boolean;
  supersedes_ir_id: string | null;
  stale_since: string | null;
  locked_by: string | null;
  locked_at: string | null;
  citations: IRCitation[];
  provenance: IRProvenance;
  extraction_run?: ExtractionRun;
}

/** One domain's classification ledger over a version — ADR-0004 decision 6, as a number. */
export interface DomainCoverage {
  domain: Domain;
  clauses: number;
  classified: number;
  /**
   * The whole point. "N IRs from M clauses" cannot be told apart from missed obligations unless the
   * remainder is on record as examined, so a non-zero value here is a finding.
   */
  unclassified: number;
  obligation_bearing: number;
  excluded: number;
  exclusion_reasons: Record<string, number>;
  complete: boolean;
}

export interface ExtractionRunSummary {
  id: string;
  status: 'running' | 'completed' | 'failed';
  clauses_seen: number;
  irs_written: number;
  started_at: string;
  heartbeat_at: string | null;
  completed_at: string | null;
  error: string | null;
  /**
   * Whether work is actually in flight — **read this, not `status`.**
   *
   * `status` is what the row says; `live` is whether anything is still saying it. They differ
   * exactly when a worker died without closing its run, and that is the case a reader most needs
   * told apart: a stuck `running` row would otherwise show "추출 중" forever. Derived server-side
   * from the checkpoint heartbeat so the client never has to agree two fields.
   */
  live: boolean;
}

export interface CoverageReport {
  version_id: string;
  clauses: number;
  domains: DomainCoverage[];
  /**
   * The most recent run, or null if this version has never been extracted.
   *
   * Coverage means a different thing while one is in flight: an `unclassified` remainder mid-run is
   * a snapshot, not a finding. The page needs the run to tell those apart.
   */
  latest_run: ExtractionRunSummary | null;
}
