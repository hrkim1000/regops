import { expect, test } from '@playwright/test';

import { GATED_CELL, storageStatePath } from './helpers/env';
import { selectCell } from './helpers/scope';

/**
 * **Change detection → alert** — the first of the two journeys phase 1.5 accepts on.
 *
 * Everything here runs against the real ingested corpus. No fixture is seeded and none is needed:
 * the alerts under test were composed by `monitoring` from change events `regulation` emitted, and
 * a journey driven over invented rows would not be the journey.
 *
 * What the assertions pin is the *shape* the ADRs require, never a particular amendment. The corpus
 * is re-ingested, amended and re-diffed; a spec that asserted "제7조 changed" would have to be
 * rewritten every time the world it describes moves, and would then be rewritten to match whatever
 * the code did that day.
 */

test.describe('as an ra', () => {
  test.use({ storageState: storageStatePath('ra') });

  test('the feed is one row per amendment, with both gates above it', async ({ page }) => {
    await page.goto('/monitoring');
    await selectCell(page, GATED_CELL);

    const cells = (await (await page.request.get('/api/regulation/cells')).json()).data as {
      id: string;
      slug: string;
    }[];
    const cellId = cells.find((cell) => cell.slug === GATED_CELL)!.id;
    const listing = (await (
      await page.request.get(`/api/monitoring/alerts?cell_id=${cellId}&page_size=1`)
    ).json()) as { meta: { total: number } };
    const metrics = (await (await page.request.get('/api/monitoring/metrics/alerts')).json())
      .data as { cells: { cell: string; change_events_alerted: number; alerts: number }[] };
    const cellMetrics = metrics.cells.find((row) => row.cell === GATED_CELL)!;

    const rows = page.locator('a[href^="/monitoring/alerts/"]');
    await expect(rows).toHaveCount(listing.meta.total);

    // The dedup, asserted rather than described: more change events reached alerts than there are
    // alerts, so the feed is aggregating amendments instead of listing events. 109 events compose 7
    // alerts over the gated corpus, and rendering the events would bury 37 real edits under a
    // thousand empty ones — ADR-0002 decision 7, reintroduced at the last step.
    expect(cellMetrics.change_events_alerted).toBeGreaterThan(cellMetrics.alerts);
    await expect(rows.first()).toContainText(/조문 \d+건/);

    // Both gates, with their denominators. A coverage figure without "알림 도달 X / 감지 Y" beside it
    // cannot be told apart from a system that alerted on everything.
    const gates = page.locator('section', { hasText: '탐지 지표' }).first();
    await expect(gates).toContainText('탐지 커버리지');
    await expect(gates).toContainText(/알림 도달 [\d,]+ \/ 감지 [\d,]+/);
    await expect(gates).toContainText(/구독자 \d+/);
    await expect(gates).toContainText('탐지 지연 (공포 기준)');
  });

  test('an alert opens on clause-level diffs, old beside new', async ({ page }) => {
    await page.goto('/monitoring');
    await selectCell(page, GATED_CELL);
    await page.locator('a[href^="/monitoring/alerts/"]').first().click();
    await page.waitForURL(/\/monitoring\/alerts\/[0-9a-f-]{36}$/);

    await expect(page.getByRole('heading', { name: '변경 내용' })).toBeVisible();

    const diffs = page.locator('section', { hasText: '변경 내용' }).locator('li');
    await expect(diffs.first()).toBeVisible();

    // Old and new side by side is the whole point of resolving the clause text across the seam:
    // `monitoring` never reads the clause store, so this page joins its alert to `regulation`'s
    // diffs on the reader's behalf.
    const first = diffs.first();
    await expect(first).toContainText('개정 전');
    await expect(first).toContainText('개정 후');
    await expect(first).toContainText(/신설|삭제|개정|조번호 변경|위치 이동/);

    // A renumber is a move, never a delete beside an add: the row carries both paths and says which
    // signal paired them. If this amendment has no move in it there is nothing to check — but when
    // there is one, the old path and the basis must both be on the row.
    const moves = diffs.filter({ hasText: /조번호 변경|위치 이동/ });
    if (await moves.count()) {
      const move = moves.first();
      await expect(move).toContainText(/제.+→|→/);
      await expect(move).toContainText(/기관이 명시한 이동|동일 조번호|본문 동일|유사도 추정/);
    }
  });

  test('assigning an owner sticks, and reassignment is allowed', async ({ page }) => {
    await page.goto('/monitoring');
    await selectCell(page, GATED_CELL);
    await page.locator('a[href^="/monitoring/alerts/"]').first().click();
    await page.waitForURL(/\/monitoring\/alerts\/[0-9a-f-]{36}$/);

    const owner = page.locator('dt:text-is("담당자") + dd');
    const before = (await owner.textContent())?.trim() ?? '';

    // Pick anyone who is not already the owner, so the spec is re-runnable: it asserts that the
    // assignment *moved*, which is true on a fresh alert and on one this suite assigned yesterday.
    const select = page.locator('#alert-owner');
    const candidates = await select.locator('option').evaluateAll((options) =>
      options
        .map((option) => ({
          value: (option as HTMLOptionElement).value,
          label: option.textContent?.trim() ?? '',
        }))
        .filter((option) => option.value !== ''),
    );
    const next = candidates.find((candidate) => !candidate.label.startsWith(before));
    expect(next, 'the stack needs at least two users to reassign between').toBeTruthy();

    await select.selectOption(next!.value);
    await page.getByRole('button', { name: /담당자 (지정|변경)/ }).click();

    const email = next!.label.replace(/\s*\(.*\)$/, '');
    await expect(owner).toHaveText(email);

    // And it survives a reload — the assignment is a row and an audit entry, not component state.
    await page.reload();
    await expect(page.locator('dt:text-is("담당자") + dd')).toHaveText(email);
    await expect(page.locator('dt:text-is("지정 시각") + dd')).not.toHaveText('—');
  });
});

test.describe('as a viewer', () => {
  test.use({ storageState: storageStatePath('viewer') });

  test('the assignment control is absent, and forging the call is refused', async ({ page }) => {
    await page.goto('/monitoring');
    await selectCell(page, GATED_CELL);
    await page.locator('a[href^="/monitoring/alerts/"]').first().click();
    await page.waitForURL(/\/monitoring\/alerts\/[0-9a-f-]{36}$/);

    await expect(page.locator('#alert-owner')).toHaveCount(0);
    await expect(page.getByText('담당자 지정은')).toBeVisible();

    // Hiding the control is cosmetic and known to be. The role is re-checked server-side on every
    // endpoint, so the request a viewer *can* still make has to come back 403 — this is the half
    // that actually holds.
    const alertId = page.url().split('/').pop();
    const users = (await (await page.request.get('/api/platform-core/users?page_size=1')).json())
      .data as { id: string }[];
    const response = await page.request.post(`/api/monitoring/alerts/${alertId}/assign`, {
      data: { owner_id: users[0].id },
    });
    expect(response.status()).toBe(403);
  });
});
