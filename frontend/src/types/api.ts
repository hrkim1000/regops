/** The envelope every RegOps endpoint wears: `{code, status, message, data, meta}`. */
export interface Meta {
  page: number | null;
  page_size: number | null;
  total: number | null;
}

export interface Envelope<T> {
  code: number;
  status: 'success' | 'error';
  message: string;
  data: T | null;
  meta: Meta | null;
}
