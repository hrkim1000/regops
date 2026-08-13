/**
 * The `monitoring` service's read shapes — phase 1.4's alerting surface, as the dashboard reads it.
 *
 * Mirrors `services/monitoring/app/api/v1/`. Three properties are load-bearing rather than cosmetic,
 * and the UI is built around them:
 *
 * - **An alert is per amendment, not per clause.** `clause_references` is the list, `clause_count`
 *   is its length, and one alert covering forty clauses is the design rather than a summary of
 *   forty alerts. A UI that rendered one row per clause would undo the dedup the schema enforces.
 * - **Severity is cell-level and says so.** Until the Product context exists an IR applies to a
 *   *cell* (ADR-0007), so the strongest claim an alert can make is "something in your cell changed".
 *   `summary` carries that sentence from the server; the UI must not dress it up as product impact.
 * - **`delivery` is an attempt log, not a status.** "failed twice, then delivered at 04:12" is the
 *   fact an operator needs, and a single status field cannot hold it.
 */

export type AlertSeverity = 'high' | 'medium' | 'low';
export type AlertStatus = 'pending' | 'delivered' | 'failed';
export type AlertChannel = 'in_app' | 'webhook' | 'email';
export type DeliveryStatus = 'pending' | 'sent' | 'failed';

/** One clause an amendment touched, as the alert records it. */
export interface ClauseReference {
  clause_path: string;
  /** The other side of a renumber; null for every other kind. */
  from_clause_path: string | null;
  change_kind: string;
  clause_diff_id: string;
}

export interface AlertDelivery {
  id: string;
  subscription_id: string;
  channel: AlertChannel;
  attempt: number;
  status: DeliveryStatus;
  error: string | null;
  attempted_at: string;
  delivered_at: string | null;
  next_retry_at: string | null;
}

/** The list shape: counts instead of the clause and delivery arrays. */
export interface AlertSummary {
  id: string;
  cell_id: string;
  cell: string;
  severity: AlertSeverity;
  status: AlertStatus;
  title: string;
  document_id: string;
  document_title: string;
  document_version_id: string;
  from_version_id: string | null;
  clause_count: number;
  /** A human had locked an obligation on text this amendment moved — the top grading input. */
  cited_by_locked_ir: boolean;
  locked_ir_count: number;
  /** Null where the authority publishes no date; latency is then unmeasurable, never zero. */
  published_at: string | null;
  retrieved_at: string | null;
  detected_at: string;
  created_at: string;
  owner_id: string | null;
  assigned_at: string | null;
  delivery: { attempts: number; sent: number; failed: number };
}

export interface AlertDetail extends AlertSummary {
  summary: string;
  clause_references: ClauseReference[];
  change_event_ids: string[];
  /** `detected_at` in the authority's own timezone — the clock the reader actually keeps. */
  detected_at_local: string;
  deliveries: AlertDelivery[];
}

export interface AlertSubscription {
  id: string;
  subscriber_id: string;
  cell_id: string;
  cell: string;
  channel: AlertChannel;
  destination: string | null;
  /** A floor, not an equality: asking for medium still delivers high. */
  min_severity: AlertSeverity;
  enabled: boolean;
}

export interface BriefingEntry {
  alert_id: string;
  cell: string;
  severity: AlertSeverity;
  title: string;
  document_title: string;
  clause_count: number;
  locked_ir_count: number;
  detected_at_local: string;
  owner_id: string | null;
}

export interface Briefing {
  subscriber_id: string;
  window_start: string;
  window_end: string;
  cells: string[];
  severity_counts: Partial<Record<AlertSeverity, number>>;
  unassigned: number;
  entries: BriefingEntry[];
}

/** One clock's view of publication → alert. `null` where nothing was measurable. */
export interface LatencyBlock {
  count: number;
  max: number | null;
  within_target: number | null;
}

export interface CellMetrics {
  cell: string;
  subscribers: number;
  alerts: number;
  change_events_emitted: number;
  change_events_alerted: number;
  /** Alerted over emitted. Null when nothing was emitted — not 0%, which would read as a failure. */
  coverage: number | null;
  severity: Record<AlertSeverity, number>;
  latency_hours: {
    from_published: LatencyBlock;
    from_retrieved: LatencyBlock;
    /** Alerts whose source published no date at all. Reported, never counted as zero latency. */
    unmeasurable: number;
    /**
     * Alerts covering amendments published *before* this cell came under observation, excluded
     * from `from_published`. On a backfilled corpus 공포 → 알림 measures how long the instrument
     * existed before RegOps arrived — it read 5,385h on the gated corpus — so counting it as
     * latency fails a system that has not yet had the chance to be measured, and would later
     * "pass" purely because the backfill aged out of the window.
     */
    backfill: number;
    /** First fetch of any source in this cell. Null before anything has been fetched. */
    watching_since: string | null;
  };
}

export interface AlertMetrics {
  window_days: number;
  target_hours: number;
  cells: CellMetrics[];
}

/**
 * The `regulation` clause-diff read — what turns "제5조 changed" into "here is what it now says".
 * A renumber carries both addresses so it renders as a move rather than a delete beside an add.
 */
export interface ClauseDiffSide {
  clause_id: string;
  clause_path: string;
  heading: string | null;
  text: string;
  /** The clause was longer than the response bound. Never render this as the whole clause. */
  truncated: boolean;
  kind: string;
}

export interface ClauseDiff {
  id: string;
  clause_path: string;
  from_clause_path: string | null;
  change_kind: string;
  /** `authority` · `path` · `content_hash` · `similarity` — a stated move vs. an inferred one. */
  match_basis: string | null;
  similarity: number | null;
  needs_review: boolean;
  from: ClauseDiffSide | null;
  to: ClauseDiffSide | null;
}

export interface DiffListing {
  version: {
    id: string;
    version_label: string | null;
    language: string;
    effective_date: string | null;
    published_at: string | null;
    retrieved_at: string;
  };
  from_version: DiffListing['version'] | null;
  document: { id: string; title: string; doc_type: string } | null;
  /** First ingestion of a document — nothing to compare against, which is not a gap. */
  baseline: boolean;
  diffs: ClauseDiff[];
}

/** `platform-core`'s user shape, used only to render an owner as a person rather than a UUID. */
export interface UserSummary {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
}
