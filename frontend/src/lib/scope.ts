import { cookies } from 'next/headers';

import { SCOPE_COOKIE } from '@/types/constants';

/**
 * The scope axis is the **cell** (`authority` x `domain`), read from a header ScopeBar cookie —
 * never from a per-page picker or a `?cell=` query (frontend-page skill).
 *
 * Returns the cell slug, or null when nothing is selected yet; a page with no scope renders an
 * empty state rather than silently showing every cell.
 */
export async function readScope(): Promise<string | null> {
  return (await cookies()).get(SCOPE_COOKIE)?.value ?? null;
}
