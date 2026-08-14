import { defineConfig, devices } from '@playwright/test';

import { BASE_URL } from './e2e/helpers/env';

/**
 * E2E against the **running compose stack**, with the real corpus and the real model.
 *
 * There is no `webServer` block on purpose. The app under test is not `next dev` with a mock behind
 * it — it is `docker compose --profile app up -d`: four services, Postgres with pgvector, MinIO,
 * two Celery workers and Ollama. Letting Playwright start a bare Next process would produce a suite
 * that passes with every service down, which is the one outcome an E2E suite must not have.
 * `global-setup.ts` checks the stack instead, and fails with what is missing rather than with a
 * timeout.
 *
 * **This suite is not a CI gate**, and that is a deliberate limit rather than an omission. A live
 * model answers in minutes and words its answer differently every time, so a red run here would as
 * often mean "the model was slow" as "the product broke". It runs where the integration suites run:
 * locally and against a stage stack, before a phase is called done. What CI keeps is `typecheck`
 * and `lint`, which are deterministic.
 *
 * Serial, single worker. Two of these specs write — an owner assignment and a superseded-citation
 * sweep — and they write to the same rows a parallel worker would be reading.
 */

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/.artifacts',
  fullyParallel: false,
  workers: 1,
  // No retries. A retried live-model run turns a flaky product into a green report, and the whole
  // reason this suite exists is to see the failures.
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  globalSetup: './e2e/global-setup.ts',
  reporter: [['list'], ['html', { open: 'never', outputFolder: './e2e/.report' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',
  },
  projects: [
    // Chromium only. Cross-browser rendering is not what these four journeys are checking, and a
    // three-browser matrix would triple a suite whose cost is already the model's.
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
