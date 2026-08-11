/**
 * The `assistant` service's read shapes — phase 1.3's answer log, as the workbench reads it.
 *
 * Mirrors `services/assistant/app/api/v1/queries.py`. Two properties are load-bearing rather than
 * cosmetic and the UI is built around them:
 *
 * - **A citation names an immutable version**, so `document_version_id` is what a deep link follows.
 *   It is never resolved through the active cell — a citation must render identically whichever
 *   scope the reader has selected (frontend-page skill).
 * - **`status` has three values and only one of them is final.** `needs_verification` and
 *   `needs_review` are outputs, not errors, and rendering either as an answer would defeat the
 *   whole citation contract.
 */

export type AnswerStatus = 'answered' | 'needs_verification' | 'needs_review';

export type NoAnswerReason =
  | 'no_retrieval'
  | 'no_citation'
  | 'fabricated_citation'
  | 'unsupported_claim'
  | 'unparseable'
  | 'model_unavailable';

export type VerificationVerdict = 'supported' | 'partial' | 'unsupported';

export interface AnswerCitation {
  /** Which claim this supports. Verification judges claims one at a time, so citations are per claim. */
  claim_index: number;
  document_id: string;
  document_version_id: string;
  clause_path: string;
  effective_date: string | null;
  /** Set when an amendment touched this clause. The citation is flagged, never repointed. */
  superseded_at: string | null;
}

export interface VerificationResult {
  claim_index: number;
  verdict: VerificationVerdict;
  reason: string | null;
  verifier_provider: string;
  verifier_model: string;
}

export interface AnswerProvenance {
  llm_provider: string;
  llm_model: string;
  prompt_version: string;
  retrieval_version: string;
}

export interface Answer {
  id: string;
  query_id: string;
  /** Present on the detail endpoint only — the list returns a summary. */
  question?: string | null;
  text: string;
  status: AnswerStatus;
  is_final: boolean;
  confidence: number;
  no_answer_reason: NoAnswerReason | null;
  effective_date_scope: string | null;
  /** Retrieved clauses did not share one effective date. Said out loud, never resolved silently. */
  straddles_effective_date: boolean;
  document_version_scope: string[];
  superseded_at: string | null;
  citations: AnswerCitation[];
  verification: VerificationResult[];
  provenance: AnswerProvenance;
}

/** The list shape: counts instead of the citation and verdict arrays. */
export interface AnswerSummary {
  id: string;
  query_id: string;
  status: AnswerStatus;
  is_final: boolean;
  confidence: number;
  no_answer_reason: NoAnswerReason | null;
  effective_date_scope: string | null;
  straddles_effective_date: boolean;
  superseded_at: string | null;
  citation_count: number;
  superseded_citation_count: number;
  created_at: string;
}

export interface QueryDetail {
  id: string;
  text: string;
  cell_id: string;
  cross_cell: boolean;
  asked_at: string;
  /** Null while the worker is still answering — the question row is written synchronously. */
  answer: Answer | null;
}

export interface AnswerRateBlock {
  total: number;
  answered: number;
  needs_verification: number;
  needs_review: number;
  needs_verification_rate: number | null;
  needs_review_rate: number | null;
}

export interface AnswerMetrics {
  overall: AnswerRateBlock;
  domains: (AnswerRateBlock & { domain: string })[];
  reasons: Partial<Record<NoAnswerReason, number>>;
}
