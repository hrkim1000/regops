import { chromium, type FullConfig } from '@playwright/test';

import { BASE_URL, credentials, GATED_CELL, ROLES, storageStatePath, UNINDEXED_CELL } from './helpers/env';

/**
 * Sign in for real, once per role, and refuse to start if the world is not the one these specs
 * describe.
 *
 * **Every precondition is checked here rather than skipped in a spec.** A suite that skips when the
 * stack is empty reports green on a broken stack, which is worse than reporting nothing — so a
 * missing service, a missing user or an empty corpus stops the run with the command that fixes it.
 *
 * Signing in through the login form rather than by minting a token is deliberate twice over: the
 * login page is itself a critical path, and the JWT is httpOnly, so a token the suite invented
 * would exercise a path no browser can take.
 */
async function globalSetup(_config: FullConfig): Promise<void> {
  // Read both credentials before opening anything — a missing password should fail in a sentence,
  // not after a browser launch and a navigation timeout.
  const wanted = ROLES.map((role) => ({ role, ...credentials(role) }));

  const browser = await chromium.launch();
  try {
    for (const { role, email, password } of wanted) {
      const context = await browser.newContext({ baseURL: BASE_URL });
      const page = await context.newPage();

      try {
        await page.goto('/login', { timeout: 30_000 });
      } catch (cause) {
        throw new Error(
          `${BASE_URL} is not answering. Bring the stack up first:\n` +
            `  docker compose --profile app up -d\n` +
            `(cause: ${(cause as Error).message})`,
        );
      }

      await page.getByLabel('이메일').fill(email);
      await page.getByLabel('비밀번호').fill(password);
      await page.getByRole('button', { name: '로그인' }).click();

      try {
        await page.waitForURL('**/regulations', { timeout: 30_000 });
      } catch {
        const message = await page.locator('form p.text-red-400').textContent().catch(() => null);
        throw new Error(
          `Sign-in failed for ${email} (${role})${message ? `: ${message.trim()}` : ''}. ` +
            `Seed the user and export REGOPS_E2E_${role.toUpperCase()}_PASSWORD to match — ` +
            `see frontend/e2e/README.md.`,
        );
      }

      if (role === 'ra') await assertCorpus(page);

      await context.storageState({ path: storageStatePath(role) });
      await context.close();
    }
  } finally {
    await browser.close();
  }
}

/**
 * The data these specs read is the real ingested corpus, so its absence is a setup problem and has
 * to say so. Every check goes through the app's own origin: the browser never reaches a service
 * directly, and neither should the preflight — a check that bypassed the rewrite could pass while
 * the path every page uses is broken.
 */
async function assertCorpus(page: import('@playwright/test').Page): Promise<void> {
  const cells = await json<{ id: string; slug: string; document_count: number }[]>(
    page,
    '/api/regulation/cells',
  );

  const gated = cells.find((cell) => cell.slug === GATED_CELL);
  if (!gated || gated.document_count === 0) {
    throw new Error(
      `Cell ${GATED_CELL} holds no documents. Ingest the gated corpus first, or point the suite ` +
        `at a populated cell with REGOPS_E2E_CELL.`,
    );
  }

  const unindexed = cells.find((cell) => cell.slug === UNINDEXED_CELL);
  if (!unindexed) {
    throw new Error(`Cell ${UNINDEXED_CELL} does not exist. The scope is 8 cells; check the slug.`);
  }
  if (unindexed.document_count > 0) {
    // The refusal spec rests on this cell being empty. If a connector lands for it, the lever has
    // to move rather than quietly stop proving anything.
    throw new Error(
      `Cell ${UNINDEXED_CELL} now holds ${unindexed.document_count} documents, so it can no longer ` +
        `force a no_retrieval refusal. Point REGOPS_E2E_EMPTY_CELL at a cell with no connector.`,
    );
  }

  const alerts = await meta(page, `/api/monitoring/alerts?cell_id=${gated.id}&page_size=1`);
  if (alerts.total === 0) {
    throw new Error(
      `No alerts in ${GATED_CELL}. The change-detection journey needs at least one — subscribe to ` +
        `the cell and run the ingest chain, or point REGOPS_E2E_CELL at a cell that has alerts.`,
    );
  }

  const answered = await meta(
    page,
    `/api/assistant/answers?cell_id=${gated.id}&status=answered&page_size=1`,
  );
  if (answered.total === 0) {
    throw new Error(
      `No answered answers in ${GATED_CELL}. The citation deep link needs one that carries ` +
        `citations; ask a question in that cell first.`,
    );
  }
}

async function json<T>(page: import('@playwright/test').Page, path: string): Promise<T> {
  const response = await page.request.get(path);
  if (!response.ok()) {
    throw new Error(`GET ${path} → HTTP ${response.status()}. Is the service up and migrated?`);
  }
  return (await response.json()).data as T;
}

async function meta(
  page: import('@playwright/test').Page,
  path: string,
): Promise<{ total: number }> {
  const response = await page.request.get(path);
  if (!response.ok()) {
    throw new Error(`GET ${path} → HTTP ${response.status()}. Is the service up and migrated?`);
  }
  const body = (await response.json()) as { meta?: { total?: number } };
  return { total: body.meta?.total ?? 0 };
}

export default globalSetup;
