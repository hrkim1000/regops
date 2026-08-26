export const SCOPE_COOKIE = 'regops_scope_cell';

/**
 * Routes that re-render for the selected cell — the three section roots, plus the subscription
 * manager, which shows every cell on purpose.
 *
 * **This list must match the pages that call `readScope()`**, and it exists because the ScopeBar
 * cannot tell on its own. Every other route is pinned to an entity it resolves by id, and a pinned
 * page ignores scope deliberately: a citation must render identically whichever cell the reader has
 * selected (frontend-page skill). Correct — and it left the ScopeBar looking live on 11 of 14
 * pages while changing nothing the reader could see.
 */
export const SCOPE_AWARE_PATHS = [
  '/monitoring',
  '/monitoring/subscriptions',
  '/qa',
  '/regulations',
] as const;

/** Where a cell change lands when the current page cannot show it. */
export const SECTION_ROOTS = ['/monitoring', '/qa', '/regulations'] as const;

/** httpOnly — set by /session, read by middleware and Server Components, never by client JS. */
export const ACCESS_TOKEN_COOKIE = 'regops_access_token';

/** Human labels for the document kinds the ingest pipeline produces. */
export const DOC_TYPE_LABEL: Record<string, string> = {
  law: '법률',
  decree: '시행령',
  enforcement_rule: '시행규칙',
  notice: '고시',
  annex: '별표',
  guidance: '가이드',
  feed: '피드',
};

/**
 * 국가법령정보's own top-level taxonomy — the way the authority groups its holdings, and so the
 * way an RA already reads them. Labels mirror the source's wording rather than our `doc_type`.
 *
 * Order matches `DOC_CATEGORY_ORDER` in the API; the server sorts by it, so the client only has to
 * render a header when the category changes.
 */
export const DOC_CATEGORY_LABEL: Record<string, string> = {
  statute: '현행법령',
  admin_rule: '현행 행정규칙',
  statute_annex: '법령 별표·서식',
  admin_rule_annex: '행정규칙 별표·서식',
  feed: '변경 신호 (RSS)',
  other: '기타',
};

/** Categories whose members are annexes — listed under their parent, not as instruments. */
export const ANNEX_CATEGORIES = ['statute_annex', 'admin_rule_annex'] as const;

/**
 * Where a version sits relative to today. 시행예정 is the one that has to be visible: a 법령 with
 * four 공포된 amendments still awaiting 시행 is otherwise indistinguishable from one with none.
 */
export const VERSION_STATUS_LABEL: Record<string, string> = {
  in_force: '시행중',
  pending: '시행예정',
  superseded: '지난 버전',
  unknown: '시행일 미확정',
};

/** Tailwind classes per status. 시행예정 is the only one that draws the eye. */
export const VERSION_STATUS_STYLE: Record<string, string> = {
  in_force: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
  pending: 'border-amber-700 bg-amber-950/50 text-amber-300',
  superseded: 'border-surface-border text-slate-500',
  unknown: 'border-surface-border text-slate-500',
};

/** How many characters of an archived artefact to render inline before truncating. */
export const RAW_PREVIEW_CHARS = 200_000;

/**
 * Clauses per page in the clause view. The 95th-percentile version holds 309 clauses and the
 * largest 2,212, so this renders most instruments whole; the API caps the parameter at 1,000.
 */
export const CLAUSE_PAGE_SIZE = 500;

/** Indent per hierarchy level, and the depth past which further nesting stops indenting. */
export const CLAUSE_INDENT_REM = 1.25;
export const CLAUSE_MAX_INDENT_LEVEL = 5;

/**
 * IR lifecycle labels (ADR-0004 decision 4).
 *
 * `draft` is deliberately worded as a *proposal*, not as a requirement: an unreviewed extraction is
 * a model's suggestion, and copy that calls it an obligation is how unreviewed output gets acted on.
 */
export const IR_STATUS_LABEL: Record<string, string> = {
  draft: '초안 (검토 대기)',
  locked: '확정',
  rejected: '반려',
  stale: '재도출 필요',
  superseded: '대체됨',
};

/**
 * Why an RA refused a draft (ADR-0020 decision 2). The enum is what the counts are made of; the
 * note beside it is where the judgement lives.
 */
export const IR_REJECTION_REASON_LABEL: Record<string, string> = {
  not_an_obligation: '의무 아님 (정의·목적·적용범위)',
  misread_clause: '조문을 잘못 읽음',
  not_atomic: '원자적이지 않음 (의무 여러 개 또는 조각)',
  wrong_citation: '인용 조문이 틀림',
  duplicate: '다른 IR과 중복',
};

export const IR_REJECTION_REASONS = [
  'not_an_obligation',
  'misread_clause',
  'not_atomic',
  'wrong_citation',
  'duplicate',
] as const;

/**
 * Tailwind classes per status. Only `locked` reads as settled; `draft` and `stale` both draw the
 * eye because both are work, and `superseded` recedes because it is history, not a queue.
 */
export const IR_STATUS_STYLE: Record<string, string> = {
  draft: 'border-sky-800 bg-sky-950/50 text-sky-300',
  locked: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
  rejected: 'border-rose-900 bg-rose-950/40 text-rose-300',
  stale: 'border-amber-700 bg-amber-950/50 text-amber-300',
  superseded: 'border-surface-border text-slate-500',
};

/**
 * Tab order. `locked` first because it is the default and the only status that flows downstream.
 *
 * `rejected` sits after `draft` and before the two history states: it is not a queue — nobody has
 * to act on it — but it is the count that says how often extraction proposed something an RA threw
 * out, which is the number to look at when `draft` keeps filling up (ADR-0020).
 */
export const IR_STATUS_ORDER = ['locked', 'draft', 'rejected', 'stale', 'superseded'] as const;

/**
 * Obligation taxonomy per domain — the entire content of the domain branch alongside the modal
 * inventory and the prompt (ADR-0004 decision 3). One flat map: the codes do not collide, and
 * keying by domain would make the lookup need a domain the IR row already states.
 */
export const IR_TAXONOMY_LABEL: Record<string, string> = {
  design_control: '설계관리',
  risk: '위험관리',
  vnv: '검증·유효성확인',
  postmarket: '시판후관리',
  ingredient: '원료',
  labelling: '표시·기재',
  claims: '표시·광고',
  gmp: 'GMP',
  notification: '보고·신고',
};

/**
 * Why an examined clause yielded no IR. Every one of these is a clause that **was** read — that is
 * the claim ADR-0004 decision 6 exists to make, and the reason breakdown is what makes it auditable
 * rather than a single opaque "excluded" count.
 */
export const EXCLUSION_REASON_LABEL: Record<string, string> = {
  definition: '정의 조항',
  scope: '목적·적용범위',
  heading: '편장절관 제목',
  permissive: '임의규정 (할 수 있다)',
  procedural: '부칙·경과조치',
  delegation: '하위법령 위임',
  table_container: '표 컨테이너 (행이 의무를 가짐)',
  form: '서식·별지',
  empty: '본문 없음',
  no_obligation: '의무 없음',
  unparseable: '에이전트 응답 불가',
};

/**
 * The one exclusion reason that is a *defect signal* rather than a verdict. A run whose
 * `unparseable` count climbs is a prompt or model regression, and it is invisible if it renders the
 * same as the ten legitimate reasons beside it.
 */
export const EXCLUSION_REASON_DEFECT = 'unparseable';

/** IRs per page. The API defaults to 100 and caps the parameter at 500. */
export const IR_PAGE_SIZE = 100;

/**
 * Why a submission-document list must not be read as a settled checklist.
 *
 * These are rendered as a **banner, not a footnote**. 94% of the procedures in the gated corpus
 * carry at least one, so a caveat the reader can scroll past is one that will be scrolled past —
 * and a conditional list shown as definitive manufactures exactly the compliance error the gap
 * analysis pillar exists to catch.
 */
export const CAVEAT_LABEL: Record<string, string> = {
  conditional_procedure: '이 절차 자체가 조건부입니다 — 적용되지 않을 수 있습니다',
  conditional_items: '일부 항목은 특정 경우에만 요구됩니다 — 각 조건을 읽으세요',
  delegated_items: '일부 항목은 하위법령에 위임되어 있어 이 목록만으로 완전하지 않습니다',
  nested_items: '일부 항목은 목으로 더 분기합니다 — 하위 항목에 실제 내용이 있습니다',
  cross_instrument: '근거 조문이 다른 법령에 있어 이 버전이 전부를 진술하지 않을 수 있습니다',
  no_items_parsed: '항목이 자식 조문이 아니라 본문에 인라인으로 있습니다',
};

/**
 * Answer status (ADR-0006). **Two of these three are successes**, and the labels have to say so:
 * "확인 필요" is the promise that no unsourced answer is ever emitted being kept, not an error.
 */
export const ANSWER_STATUS_LABEL: Record<string, string> = {
  answered: '답변 완료',
  needs_review: '검토 대기',
  needs_verification: '확인 필요',
};

/**
 * Only `answered` reads as settled. `needs_review` and `needs_verification` both draw the eye,
 * because an answer presented as final when it is not is the failure this layer exists to prevent.
 */
export const ANSWER_STATUS_STYLE: Record<string, string> = {
  answered: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
  needs_review: 'border-amber-700 bg-amber-950/50 text-amber-300',
  needs_verification: 'border-sky-800 bg-sky-950/50 text-sky-300',
};

/** Tab order. `answered` first because it is what a reader is usually looking for. */
export const ANSWER_STATUS_ORDER = ['answered', 'needs_review', 'needs_verification'] as const;

/**
 * Why no answer was given, from the closed inventory the backend records. A rate whose causes
 * cannot be read is a number that moved without saying what moved it (ADR-0006 decision 7).
 */
export const NO_ANSWER_REASON_LABEL: Record<string, string> = {
  no_retrieval: '이 셀에서 관련 조문을 찾지 못했습니다',
  no_citation: '모델이 근거 조문을 인용하지 못했습니다',
  fabricated_citation: '검색되지 않은 조문을 인용해 기각되었습니다',
  unsupported_claim: '검증 통과에서 근거 부족으로 기각되었습니다',
  unparseable: '모델 응답을 해석하지 못했습니다',
  model_unavailable: '모델에 연결하지 못했거나 시간 안에 응답하지 않았습니다',
};

/**
 * What kind of thing each refusal is. Three categories, not two, and conflating them produces copy
 * that is simply false — `model_unavailable` was rendered as "모델이 잘못된 응답을 냈다" when the
 * model had not responded at all.
 *
 * - `expected` — the product working. No evidence, or evidence that did not hold up.
 * - `regression` — the model misbehaved: a 조문 번호 from memory, or an unusable reply.
 * - `infrastructure` — the model was never reached. Says nothing about evidence *or* model quality.
 */
export const NO_ANSWER_REASON_TONE: Record<
  string,
  'expected' | 'regression' | 'infrastructure'
> = {
  no_retrieval: 'expected',
  no_citation: 'expected',
  unsupported_claim: 'expected',
  fabricated_citation: 'regression',
  unparseable: 'regression',
  model_unavailable: 'infrastructure',
};

/** What to tell the reader to do about it. One sentence per reason, because they differ. */
export const NO_ANSWER_REASON_HINT: Record<string, string> = {
  no_retrieval:
    '이 셀에 관련 조문이 없거나 아직 색인되지 않았습니다. 셀이 맞는지 확인하고 다른 표현으로 다시 물어보세요.',
  no_citation: '근거를 댈 수 없을 때 답변을 지어내지 않는 것이 이 제품의 약속입니다.',
  unsupported_claim:
    '조문은 찾았지만 그 조문이 주장을 뒷받침하지 않았습니다 — 근거 검증이 걸러낸 경우입니다.',
  fabricated_citation:
    '결함 신호입니다 — 모델이 검색되지 않은 조문 번호를 만들어냈습니다. 근거가 없다는 뜻이 아니라 모델·프롬프트의 회귀입니다.',
  unparseable:
    '결함 신호입니다 — 모델이 형식에 맞지 않는 응답을 냈습니다. 근거가 없다는 뜻이 아니라 모델·프롬프트의 회귀입니다.',
  model_unavailable:
    '모델에 닿지 못했습니다 — 답변 품질이나 근거의 문제가 아니라 인프라 문제입니다. 다시 질문하면 대개 해결되고, 반복된다면 이 프롬프트에 비해 모델이 느린 것입니다.',
};

/** Evidence-verification verdicts (ADR-0006 decision 6). `unsupported` fails the whole answer. */
export const VERIFICATION_VERDICT_LABEL: Record<string, string> = {
  supported: '근거 확인',
  partial: '부분 근거',
  unsupported: '근거 없음',
};

export const VERIFICATION_VERDICT_STYLE: Record<string, string> = {
  supported: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
  partial: 'border-amber-700 bg-amber-950/50 text-amber-300',
  unsupported: 'border-red-800 bg-red-950/50 text-red-300',
};

/** Mirror of `ANSWER_CONFIDENCE_THRESHOLD`. Below this the backend routes to human review. */
export const ANSWER_CONFIDENCE_THRESHOLD = 0.7;

/** Answers per page. The API defaults to 50 and caps the parameter at 200. */
export const ANSWER_PAGE_SIZE = 25;

/**
 * Impact grade (phase 1.4). **Cell-level, and the copy has to keep saying so** — until the Product
 * context exists an IR applies to a cell (ADR-0007), so "높음" means *a lot changed in your cell*,
 * never *your product is affected*. The server states the limitation in every alert body; these
 * labels must not quietly promise more than it does.
 */
export const ALERT_SEVERITY_LABEL: Record<string, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
};

export const ALERT_SEVERITY_STYLE: Record<string, string> = {
  high: 'border-red-800 bg-red-950/50 text-red-300',
  medium: 'border-amber-700 bg-amber-950/50 text-amber-300',
  low: 'border-surface-border text-slate-500',
};

/** Worst first. A feed ordered only by time buries the one high alert under a morning's routine. */
export const ALERT_SEVERITY_ORDER = ['high', 'medium', 'low'] as const;

/**
 * Why an alert got the grade it did — mirrors the closed inventory in `app/grade.py`.
 * Rendered as a hint rather than a badge: the grade is the headline, the basis is the reason.
 */
export const ALERT_SEVERITY_HINT: Record<string, string> = {
  high: '확정(lock)된 요구사항이 근거로 삼던 조문이 변경되었습니다 — 사람이 승인한 의무의 근거가 움직였다는 뜻입니다.',
  medium: '삭제된 조문이 있거나 변경 조문 수가 많습니다.',
  low: '일반 개정입니다.',
};

/**
 * Delivery state of an alert, derived from its attempt log. `pending` means *delivery work is
 * outstanding* — an alert with no eligible subscriber is `delivered` with zero attempts, and the
 * attempt count beside it is what keeps "전달 대상 없음" legible.
 */
export const ALERT_STATUS_LABEL: Record<string, string> = {
  pending: '전달 대기',
  delivered: '전달됨',
  failed: '전달 실패',
};

export const ALERT_STATUS_STYLE: Record<string, string> = {
  pending: 'border-sky-800 bg-sky-950/50 text-sky-300',
  delivered: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
  failed: 'border-red-800 bg-red-950/50 text-red-300',
};

export const DELIVERY_STATUS_LABEL: Record<string, string> = {
  pending: '시도 중',
  sent: '전달',
  failed: '실패',
};

export const DELIVERY_STATUS_STYLE: Record<string, string> = {
  pending: 'border-sky-800 bg-sky-950/50 text-sky-300',
  sent: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
  failed: 'border-red-800 bg-red-950/50 text-red-300',
};

/** `email` is declared and unimplemented in Phase 1 — the label says so rather than offering it. */
export const ALERT_CHANNEL_LABEL: Record<string, string> = {
  in_app: '앱 내',
  webhook: '웹훅',
  email: '이메일 (미구현)',
};

/** The channels a subscriber may actually pick today. `email` has no relay behind it. */
export const ALERT_CHANNEL_CHOICES = ['in_app', 'webhook'] as const;

/**
 * How a clause changed (ADR-0002 decision 7). **`renumbered` and `moved` are not edits** — they
 * move an address, not an obligation, and an amendment made only of them raises no alert at all.
 * They appear here because a *mixed* amendment still lists them beside its real edits.
 */
export const CHANGE_KIND_LABEL: Record<string, string> = {
  added: '신설',
  removed: '삭제',
  modified: '개정',
  renumbered: '조번호 변경',
  moved: '위치 이동',
};

export const CHANGE_KIND_STYLE: Record<string, string> = {
  added: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
  removed: 'border-red-800 bg-red-950/50 text-red-300',
  modified: 'border-amber-700 bg-amber-950/50 text-amber-300',
  renumbered: 'border-surface-border text-slate-500',
  moved: 'border-surface-border text-slate-500',
};

/** Change kinds that move an address rather than an obligation — rendered muted, never as an edit. */
export const NON_SUBSTANTIVE_CHANGE_KINDS = ['renumbered', 'moved'] as const;

/**
 * How the diff stage paired the two sides. A move the authority *stated* in 조문이동이전/이후 and
 * one we inferred from text similarity carry very different confidence, and showing them alike
 * would present a guess as a fact.
 */
export const MATCH_BASIS_LABEL: Record<string, string> = {
  authority: '기관이 명시한 이동',
  path: '동일 조번호',
  content_hash: '본문 동일',
  similarity: '유사도 추정',
};

/** Mirror of `DETECTION_LATENCY_TARGET_HOURS`. The Go/No-Go ceiling, publication → alert. */
export const DETECTION_LATENCY_TARGET_HOURS = 24;

/** Mirror of the Go/No-Go detection-coverage floor. */
export const DETECTION_COVERAGE_TARGET = 0.95;

/** Alerts per page. The API defaults to 50 and caps the parameter at 200. */
export const ALERT_PAGE_SIZE = 25;

/** Clause diffs fetched per alert. The API caps the parameter at 500. */
export const DIFF_PAGE_SIZE = 200;

/** Window the briefing covers, in hours. Rolling, not a calendar day — see phase1.4 deviation 8. */
export const BRIEFING_WINDOW_HOURS = 24;
