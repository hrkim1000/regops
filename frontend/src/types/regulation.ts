/** Mirrors the `regulation` service schema. Keep field names identical to the API. */

export type DocType =
  | 'law'
  | 'decree'
  | 'enforcement_rule'
  | 'notice'
  | 'annex'
  | 'guidance'
  | 'feed';

export interface Cell {
  id: string;
  slug: string;
  authority: string;
  domain: string;
  document_count: number;
  annex_count: number;
}

export interface DocumentSummary {
  id: string;
  canonical_key: string;
  title: string;
  doc_type: DocType;
  annex_no: string | null;
  parent_document_id: string | null;
  annex_count: number;
  version_count: number;
}

export interface DocumentVersion {
  id: string;
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
