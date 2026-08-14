import { expect, test } from '@playwright/test';

import { NO_ANSWER_REASON_TONE } from '@/types/constants';

import { answerRecord, ask } from './helpers/ask';
import { ASK_TIMEOUT_MS, GATED_CELL, storageStatePath } from './helpers/env';
import { selectCell } from './helpers/scope';

/**
 * **Question → retrieval → cited answer** — the second journey, against the real model.
 *
 * The assertions here are invariants, not answers. A live `gemma3:4b` phrases the same question
 * differently every run and may legitimately decline it, so pinning the prose would pin nothing and
 * would go red for the wrong reason. What must hold on every run is the promise the product is
 * built on: **no answer without evidence**, and every citation pinned to an immutable version.
 *
 * Model *quality* — is the answer right, is the citation the right one — is measured against the
 * golden sets in phase 1.6, per domain and per gated cell. That is a different question from the one
 * this file asks, and answering it here with one ad-hoc question would answer it badly.
 */

test.describe('as an ra', () => {
  test.use({ storageState: storageStatePath('ra') });

  test('an answer either carries its evidence or refuses for a stated reason', async ({ page }) => {
    test.setTimeout(ASK_TIMEOUT_MS + 90_000);

    await page.goto('/qa');
    await selectCell(page, GATED_CELL);

    const answerId = await ask(
      page,
      '화장품책임판매업자는 안전성 정보를 언제까지 보고해야 하나요?',
    );
    const answer = await answerRecord(page, answerId);

    // The invariant, in one line: prose without evidence must not exist. Everything else on this
    // page is a rendering of that rule or a caveat about it.
    if (answer.status !== 'needs_verification') {
      expect(
        answer.citations.length,
        'an answer that was not refused must carry at least one citation',
      ).toBeGreaterThan(0);
      for (const citation of answer.citations) {
        expect(citation.clause_path).not.toEqual('');
        expect(citation.document_version_id).toMatch(/^[0-9a-f-]{36}$/);
      }
    } else {
      // A refusal is the product working, and that includes the unflattering reasons. Observed on
      // this stack: `gemma3:4b` cited a 조문 number that was never retrieved, and the pipeline threw
      // the answer away — `fabricated_citation` is the guardrail firing, not the guardrail failing.
      // *How often* a model does that is model quality, measured against the phase 1.6 golden sets
      // per domain; asserting a rate here off one ad-hoc question would be measuring nothing.
      //
      // What must hold whatever the reason: nothing unsourced reached the reader.
      expect(answer.text, 'a refused answer must carry no prose').toEqual('');
      expect(answer.citations, 'a refused answer must carry no citations').toHaveLength(0);

      // One reason is not a product outcome at all. `model_unavailable` means the model was never
      // reached, so the run proved nothing — and a suite that accepted it would go green with
      // Ollama switched off, which is exactly the failure this line exists to catch.
      expect(
        NO_ANSWER_REASON_TONE[answer.no_answer_reason ?? ''],
        `refused as ${answer.no_answer_reason} — the model was never reached, so this run tested nothing`,
      ).not.toBe('infrastructure');
    }

    // What the reader is actually shown: the status, the confidence against its threshold, and the
    // provenance of the model that produced it.
    await expect(page.getByText(/답변 완료|검토 대기|확인 필요/).first()).toBeVisible();
    await expect(page.getByText(/신뢰도 \d\.\d\d/)).toBeVisible();
    await expect(page.locator('dt:text-is("llm_provider") + dd')).not.toBeEmpty();
    await expect(page.locator('dt:text-is("llm_model") + dd')).not.toBeEmpty();
    expect(answer.provenance.llm_provider).not.toEqual('');

    // The caveats sit above the prose, never below it. An answer whose clauses straddle an
    // effective-date boundary looks identical to a correct one, so a banner a reader meets after
    // they have already acted is a banner that did not work.
    const banner = page.locator('p', { hasText: /확인 필요|시행일이 일치하지 않습니다|개정/ }).first();
    if (await banner.count()) {
      const body = page.locator('section p.whitespace-pre-wrap').first();
      if (await body.count()) {
        const bannerBox = await banner.boundingBox();
        const bodyBox = await body.boundingBox();
        expect(bannerBox!.y).toBeLessThan(bodyBox!.y);
      }
    }
  });

  test('a citation opens the clause it pins, and the ScopeBar cannot move it', async ({ page }) => {
    // Deterministic on purpose: this reads an answer that already carries citations rather than
    // hoping the live model produces one. What is under test is the link, which is ours.
    await page.goto('/qa?tab=answered');
    await selectCell(page, GATED_CELL);

    await page.locator('a[href^="/qa/"]').first().click();
    await page.waitForURL(/\/qa\/[0-9a-f-]{36}$/);
    const answerId = page.url().split('/').pop()!;
    const answer = await answerRecord(page, answerId);
    expect(answer.citations.length).toBeGreaterThan(0);

    const citation = page.locator('a[href*="/clauses?clause_path="]').first();
    const href = await citation.getAttribute('href');

    // A citation renders from its own pinned version, never through the scope cookie. Switching
    // cells must leave the link byte-identical — otherwise a reader in another cell would follow a
    // citation to different text than the one it was written against.
    await selectCell(page, GATED_CELL === 'mfds_cosmetic' ? 'mfds_samd' : 'mfds_cosmetic');
    await expect(page.locator('a[href*="/clauses?clause_path="]').first()).toHaveAttribute(
      'href',
      href!,
    );

    await page.locator('a[href*="/clauses?clause_path="]').first().click();
    await page.waitForURL(/\/clauses\?clause_path=/);

    // The link resolves to whichever page holds the clause, not to page 1 of 5 — the largest
    // version runs to 2,212 clauses, so a link that landed on the instrument rather than on the
    // evidence would be a citation nobody checks.
    const path = decodeURIComponent(new URL(href!, page.url()).searchParams.get('clause_path')!);
    await expect(page.locator(`[id="${path}"]`)).toHaveCount(1);
    await expect(page.getByText('인용은 불변 버전에 고정되며')).toHaveCount(0);
  });
});
