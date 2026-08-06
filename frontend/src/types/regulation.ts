/** Mirrors the `regulation` service schema. Keep field names identical to the API. */

export type DocType =
  | 'law'
  | 'decree'
  | 'enforcement_rule'
  | 'notice'
  | 'annex'
  | 'guidance'
  | 'feed';

/**
 * 국가법령정보's top-level taxonomy. Derived server-side from `doc_type` plus, for an annex, the
 * *parent's* `doc_type` — 별표 of a 법령 and 별표 of a 고시 are different categories and the annex
 * row cannot tell them apart on its own.
 */
export type DocCategory =
  | 'statute'
  | 'admin_rule'
  | 'statute_annex'
  | 'admin_rule_annex'
  | 'feed'
  | 'other';

export interface Cell {
  id: string;
  slug: string;
  authority: string;
  domain: string;
  document_count: number;
  annex_count: number;
  /** Per-category totals for the whole cell, including annexes the list does not show. */
  categories: Record<DocCategory, number>;
}

export interface DocumentSummary {
  id: string;
  canonical_key: string;
  title: string;
  doc_type: DocType;
  category: DocCategory;
  annex_no: string | null;
  parent_document_id: string | null;
  annex_count: number;
  version_count: number;
  /** 공포되었으나 아직 시행 전인 버전 수. Derived from the dates server-side (ADR-0016). */
  pending_version_count: number;
}

/** Where a version sits relative to today. Derived — there is no status column. */
export type VersionStatus = 'in_force' | 'pending' | 'superseded' | 'unknown';

export interface DocumentVersion {
  id: string;
  /**
   * 시행중 / 시행예정 / 지난 버전. Computed server-side because it depends on the *sibling*
   * versions: which one is in force is the latest whose date has arrived, a property of the set.
   */
  status: VersionStatus | null;
  version_label: string | null;
  language: string;
  content_hash: string;
  raw_object_key: string;
  raw_bytes: number;
  content_type: string | null;
  /** Our clock at fetch — always present. */
  retrieved_at: string;
  /** 공포일자 / 발령일자. Null means the source exposes none, never "same as retrieved_at". */
  published_at: string | null;
  /** Parse-derived (phase 1.1). Null plus a phrase when the text states a condition. */
  effective_date: string | null;
  effective_date_phrase: string | null;
  parser_version: string | null;
}

export interface Attachment {
  kind: string;
  title: string | null;
  file_format: string | null;
  source_url: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  cells: string[];
  parent: { id: string; title: string; canonical_key: string } | null;
  annexes: { id: string; annex_no: string | null; title: string; canonical_key: string }[];
  versions: DocumentVersion[];
}

export interface VersionDetail extends DocumentVersion {
  document: {
    id: string;
    title: string;
    canonical_key: string;
    doc_type: DocType;
    annex_no: string | null;
  } | null;
  attachments: Attachment[];
}
