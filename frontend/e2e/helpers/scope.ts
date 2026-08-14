import { expect, type Page } from '@playwright/test';

import { SCOPE_COOKIE } from '@/types/constants';

/**
 * Choose a cell the way a reader does — by clicking the ScopeBar.
 *
 * Writing the cookie directly would be one line shorter and would skip the control that makes the
 * whole scoping rule true. Scope is an app-level axis (no per-page cell pickers, no `?cell=`), so
 * the bar being one control across the regulation browser, Q&A and the alert feed is a property
 * worth exercising rather than assuming.
 *
 * The wait is on the cookie rather than on a CSS class: the class is styling and may change, while
 * the cookie is what every Server Component reads back through `readScope()`.
 */
export async function selectCell(page: Page, slug: string): Promise<void> {
  // The count sits in a sibling span with no separating whitespace, so the accessible name reads
  // `mfds_cosmetic20`. Anchoring on the prefix alone is safe: no cell slug is a prefix of another.
  await page.getByRole('button', { name: new RegExp(`^${slug}\\d*$`) }).click();

  await expect
    .poll(async () => {
      const cookies = await page.context().cookies();
      return cookies.find((cookie) => cookie.name === SCOPE_COOKIE)?.value;
    }, { message: `ScopeBar did not settle on ${slug}` })
    .toBe(slug);
}
