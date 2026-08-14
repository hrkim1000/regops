import { expect, test } from '@playwright/test';

import { GATED_CELL, storageStatePath } from './helpers/env';
import { selectCell } from './helpers/scope';
import { fixture } from './helpers/stack';

/**
 * **A superseded citation, and the queue it feeds** — the second half of phase 1.5's E2E acceptance.
 *
 * This is the one journey with a seeded row, and the reason is in `scripts/e2e_fixture.py`: no
 * answer in the corpus happens to cite a clause that a later amendment moved, so the sweep would
 * correctly flag nothing. The fixture creates that intersection and nothing else — the sweep itself
 * is the real `assistant.supersede_answer_citations` task, dispatched by name on the real queue,
 * exactly as `regulation`'s diff stage dispatches it. No model is involved on either side.
 *
 * What has to hold is ADR-0002 decision 4: **the citation is flagged, never rewritten.** Repointing
 * it at the new version would silently change the evidence behind a statement someone has already
 * read and acted on, while the record still showed one answer.
 */

test.use({ storageState: storageStatePath('ra') });

interface Seeded {
  answer_id: string;
  clause_path: string;
  cited_version_id: string;
  amended_version_id: string;
}

let seeded: Seeded;

test.beforeAll(() => {
  seeded = fixture<Seeded>('seed', '--cell', GATED_CELL);
});

test.afterAll(() => {
  fixture('clean');
});

test('an amendment flags the answers that rested on it, and rewrites none of them', async ({
  page,
}) => {
  await page.goto(`/qa/${seeded.answer_id}`);
  await selectCell(page, GATED_CELL);
  await page.goto(`/qa/${seeded.answer_id}`);

  // Before: an ordinary answer. The citation is on the page and carries no 개정됨 badge.
  await expect(page.getByText(seeded.clause_path).first()).toBeVisible();
  await expect(page.getByText('개정됨')).toHaveCount(0);
  await expect(page.getByText('이 답변이 인용한 조문이 이후')).toHaveCount(0);

  const before = await citations(page, seeded.answer_id);
  expect(before).toHaveLength(1);
  expect(before[0].superseded_at).toBeNull();

  // The amendment lands — the same task, on the same queue, by the same name the diff stage uses.
  fixture('supersede', '--version-id', seeded.amended_version_id);

  await expect
    .poll(async () => (await citations(page, seeded.answer_id))[0].superseded_at, {
      timeout: 60_000,
      intervals: [1_000],
      message: 'the supersede task did not flag the citation — is the assistant worker up?',
    })
    .not.toBeNull();

  const after = await citations(page, seeded.answer_id);
  // Flagged, not repointed: same version, same path, same row, plus a flag. This is the assertion
  // the whole citation model exists to make possible — an answer that pointed at the *new* text
  // would have silently changed the evidence behind something a reader already acted on.
  expect(after[0].document_version_id).toBe(before[0].document_version_id);
  expect(after[0].clause_path).toBe(before[0].clause_path);

  // And the reader is told, above the answer text rather than below it.
  await page.reload();
  await expect(page.getByText('이 답변이 인용한 조문이 이후')).toBeVisible();
  await expect(page.getByText('개정됨').first()).toBeVisible();
});

test('the flagged answer lands in the 근거 개정 queue', async ({ page }) => {
  await page.goto('/qa');
  await selectCell(page, GATED_CELL);

  await page.getByRole('link', { name: '근거 개정', exact: true }).click();
  await page.waitForURL(/tab=superseded/);

  const row = page.locator(`a[href="/qa/${seeded.answer_id}"]`);
  await expect(row).toBeVisible();
  // The count is the reason the row is in the list — "2 of 3 citations have moved" is what tells a
  // reader whether the answer is worth re-asking, so a row without it would be a bare link.
  await expect(row).toContainText(/근거 개정됨 \d+\/\d+/);
});

async function citations(
  page: import('@playwright/test').Page,
  answerId: string,
): Promise<
  {
    clause_path: string;
    document_version_id: string;
    superseded_at: string | null;
  }[]
> {
  const response = await page.request.get(`/api/assistant/answers/${answerId}`);
  expect(response.ok(), `GET /answers/${answerId} → HTTP ${response.status()}`).toBeTruthy();
  return (await response.json()).data.citations;
}
