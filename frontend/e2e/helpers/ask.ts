import { expect, type Page } from '@playwright/test';

import { ASK_TIMEOUT_MS } from './env';

const ANSWER_URL = /\/qa\/[0-9a-f-]{36}$/;

export interface AnswerRecord {
  id: string;
  status: 'answered' | 'needs_review' | 'needs_verification';
  no_answer_reason: string | null;
  confidence: number;
  text: string;
  citations: { clause_path: string; document_version_id: string; effective_date: string | null }[];
  provenance: { llm_provider: string; llm_model: string; prompt_version: string };
}

/**
 * Ask a question in the current scope and end up on its answer, however long the model takes.
 *
 * **Both ways out are the product working.** Under the ask box's 4-minute poll ceiling it redirects
 * to the answer; over it, it stops polling and hands over a link to the pending question — which
 * exists precisely because a question whose worker is still running would otherwise be invisible.
 * Following that hand-off is part of the journey, not a fallback around a flaky one, so the helper
 * takes whichever path the model's speed produces.
 */
export async function ask(page: Page, question: string): Promise<string> {
  await page.getByLabel(/범위에서 질문합니다/).fill(question);
  await page.getByRole('button', { name: '질문하기' }).click();

  const pending = page.getByRole('link', { name: '이 질문' });

  await expect
    .poll(
      async () => {
        if (ANSWER_URL.test(page.url())) return 'answered';
        if ((await pending.count()) > 0) return 'pending';
        return 'waiting';
      },
      {
        timeout: ASK_TIMEOUT_MS,
        intervals: [2_000],
        message: `no answer and no pending hand-off within ${ASK_TIMEOUT_MS / 1000}s`,
      },
    )
    .not.toBe('waiting');

  if (!ANSWER_URL.test(page.url())) {
    // The pending page polls on the reader's behalf and redirects once the answer lands, so the
    // URL the ask box hands out stays valid for the whole life of the question.
    await pending.click();
    await page.waitForURL(ANSWER_URL, { timeout: ASK_TIMEOUT_MS });
  }

  return page.url().split('/').pop()!;
}

/**
 * The answer as the service recorded it.
 *
 * The page renders Korean prose that a live model writes differently every run; the row behind it
 * is what carries the invariants. Reading both — the record for the assertions, the page for what
 * the reader is actually shown — is what keeps this a UI test without making it a wording test.
 */
export async function answerRecord(page: Page, answerId: string): Promise<AnswerRecord> {
  const response = await page.request.get(`/api/assistant/answers/${answerId}`);
  expect(response.ok(), `GET /answers/${answerId} → HTTP ${response.status()}`).toBeTruthy();
  return (await response.json()).data as AnswerRecord;
}
