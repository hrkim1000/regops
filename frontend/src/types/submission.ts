/** Mirrors the `regulation` submission-requirement contract. Derived server-side, never stored. */

/** Why a requirement must not be rendered as a settled checklist. */
export type CaveatCode =
  | 'conditional_procedure'
  | 'conditional_items'
  | 'delegated_items'
  | 'nested_items'
  | 'cross_instrument'
  | 'no_items_parsed';

export interface Caveat {
  code: CaveatCode;
  meaning: string;
}

export interface RequiredDocument {
  clause_id: string;
  /** The citation address for this item. An item *is* a clause — evidence is not bolted on. */
  clause_path: string;
  /** Verbatim clause text. This is the document's name as the regulation states it. */
  text: string;
  /**
   * **The signal to check.** True whenever the item applies only in stated cases — including when
   * the whole item is one conditional sentence, which is most of them.
   */
  conditional: boolean;
  /**
   * The condition phrase, only when it is narrower than the item text itself. `null` here does
   * **not** mean unconditional — `conditional` means that.
   */
  condition_text: string | null;
  /** Defers to another instrument; the real content is not in this list. */
  delegates: boolean;
  /** Expands into 목; the children hold detail this level only gestures at. */
  has_sub_items: boolean;
  sub_item_paths: string[];
}

export interface SubmissionRequirement {
  clause_id: string;
  /** The citation for the obligation itself. Each document below carries its own. */
  clause_path: string;
  heading: string | null;
  text: string;
  /** "별지 제5호서식" verbatim — not resolved to a Document (cross-reference is phase 2.1). */
  form_reference: string | null;
  recipient: string | null;
  /** False for 94% of the corpus. Treat true as the exception, never the default. */
  is_definitive: boolean;
  caveats: Caveat[];
  documents: RequiredDocument[];
}

export interface SubmissionListing {
  version: {
    id: string;
    version_label: string | null;
    effective_date: string | null;
    effective_date_phrase: string | null;
  };
  document: { id: string; title: string; canonical_key: string } | null;
  requirements: SubmissionRequirement[];
}
