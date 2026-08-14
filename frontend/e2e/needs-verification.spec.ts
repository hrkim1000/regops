import { expect, test } from '@playwright/test';

import { NO_ANSWER_REASON_LABEL, NO_ANSWER_REASON_TONE } from '@/types/constants';

import { answerRecord, ask } from './helpers/ask';
import { ASK_TIMEOUT_MS, storageStatePath, UNINDEXED_CELL } from './helpers/env';
import { selectCell } from './helpers/scope';

/**
 * **"확인 필요" is a result, not an error** — the acceptance row phase 1.5 carries for the refusal
 * path.
 *
 * The refusal is forced without stubbing anything: `fda_samd` is one of the six cells with no
 * connector, so it holds no clauses and therefore no embeddings, and retrieval over it returns
 * nothing on every run. `ask` refuses with `no_retrieval` before the model is ever asked to
 * generate. That makes this the one live-model spec that is fully deterministic — and it is
 * deterministic *because of* how the product behaves, not because a fake was put in its way.
 *
 * The refusal is also the cheapest thing in the world to fake, which is why the last assertion here
 * is about the three tones: a model that has fallen over produces `model_unavailable`, and a UI that
 * rendered that identically to "there is no evidence" would let a broken model hide inside an
 * honest-looking refusal rate.
 */

test.use({ storageState: storageStatePath('ra') });

test('a question with no evidence in scope is refused, and says why', async ({ page }) => {
  test.setTimeout(ASK_TIMEOUT_MS + 90_000);

  await page.goto('/qa');
  await selectCell(page, UNINDEXED_CELL);

  const answerId = await ask(page, '이 셀에서 안전성 정보 보고 기한은 어떻게 됩니까?');
  const answer = await answerRecord(page, answerId);

  expect(answer.status).toBe('needs_verification');
  expect(answer.no_answer_reason).toBe('no_retrieval');
  expect(answer.citations).toHaveLength(0);
  // Nothing was invented to fill the gap. This is the promise in one assertion.
  expect(answer.text).toEqual('');

  // Rendered as a result: a banner that states the reason, not a toast that reports a failure.
  await expect(page.getByText('확인 필요').first()).toBeVisible();
  await expect(page.getByText(NO_ANSWER_REASON_LABEL.no_retrieval)).toBeVisible();
  await expect(page.getByText('근거 조문이 없습니다')).toBeVisible();

  // An expected refusal is toned apart from a defect signal — sky, not red. The tone map is the
  // app's own, so this asserts the classification rather than restating it.
  expect(NO_ANSWER_REASON_TONE.no_retrieval).toBe('expected');
  const banner = page.locator('p', { hasText: '확인 필요' }).first();
  await expect(banner).toHaveClass(/border-sky-800/);
  await expect(banner).not.toHaveClass(/border-red-800/);
});

test('the refusal is a first-class tab in the workbench, with the rate in front of the asker', async ({
  page,
}) => {
  await page.goto('/qa');
  await selectCell(page, UNINDEXED_CELL);

  // The "확인 필요" rate sits above the list rather than in an admin corner: a system that refused
  // everything would pass both Go/No-Go gates cleanly, so the number that catches it belongs in
  // front of the people asking the questions.
  const metrics = page.locator('section', { hasText: '답변 결과 비율' }).first();
  await expect(metrics).toContainText('확인 필요');

  await page.getByRole('link', { name: '확인 필요', exact: true }).click();
  await page.waitForURL(/tab=needs_verification/);

  const rows = page.locator('a[href^="/qa/"]');
  await expect(rows.first()).toBeVisible();
  await expect(rows.first()).toContainText('확인 필요');
});
