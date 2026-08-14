/**
 * What the suite needs from the outside world: an address, two principals, and two cells.
 *
 * **No password has a default and no password is written here.** Placeholders only, in code and in
 * fixtures (CLAUDE.md § Security) — the emails default to the seeded example.com placeholders
 * because they name a row rather than grant anything, and the passwords must come from the
 * environment or the run stops before it opens a browser.
 */

export const BASE_URL = process.env.REGOPS_E2E_BASE_URL ?? 'http://localhost:23000';

/**
 * How long one question may take, end to end.
 *
 * The model is real and local, so this is minutes rather than seconds: one generation plus one
 * verification per claim. The ask box gives up polling at 4 minutes and hands over a link to the
 * pending question, which is itself part of the journey — this ceiling has to sit above that one so
 * the spec can follow the hand-off rather than time out inside it.
 */
export const ASK_TIMEOUT_MS = Number(process.env.REGOPS_E2E_ASK_TIMEOUT_MS ?? 6 * 60_000);

export type RoleName = 'ra' | 'viewer';

export const ROLES: readonly RoleName[] = ['ra', 'viewer'] as const;

export interface Credentials {
  email: string;
  password: string;
}

/**
 * The cell the gated corpus lives in. Both gated cells carry alerts and answers; cosmetic is the
 * default because its 4 alerts are all unassigned, so the assignment journey has somewhere to start.
 */
export const GATED_CELL = process.env.REGOPS_E2E_CELL ?? 'mfds_cosmetic';

/**
 * A cell with no connector, and therefore no clause index.
 *
 * This is the lever that makes the refusal path deterministic **without stubbing anything**:
 * retrieval over a cell with zero embeddings returns nothing, so `ask` refuses with `no_retrieval`
 * every time. A refusal forced this way is the product working, not a mock standing in for it.
 */
export const UNINDEXED_CELL = process.env.REGOPS_E2E_EMPTY_CELL ?? 'fda_samd';

export function storageStatePath(role: RoleName): string {
  return `e2e/.auth/${role}.json`;
}

/**
 * Who each role signs in as by default.
 *
 * The `ra` is the suite's **own** principal, not a person's account. It assigns alert owners, and
 * that is written to the audit hash chain — so the chain has to be able to say "the E2E suite did
 * this" rather than attributing an automated run to whoever `ra@example.com` is. The `viewer` only
 * reads and gets refused, writes nothing, and reuses the account phase 0's acceptance suite already
 * signs in as.
 */
const DEFAULT_EMAIL: Record<RoleName, string> = {
  ra: 'e2e-ra@example.com',
  viewer: 'viewer@example.com',
};

export function credentials(role: RoleName): Credentials {
  const prefix = `REGOPS_E2E_${role.toUpperCase()}`;
  const email = process.env[`${prefix}_EMAIL`] ?? DEFAULT_EMAIL[role];
  const password = process.env[`${prefix}_PASSWORD`];
  if (!password) {
    throw new Error(
      `${prefix}_PASSWORD is not set. The suite signs in as a real ${role}; seed one first:\n` +
        `  REGOPS_SEED_EMAIL=${email} REGOPS_SEED_PASSWORD=<password> REGOPS_SEED_ROLE=${role} \\\n` +
        `      docker compose exec -T platform-core python /scripts/seed_user.py\n` +
        `then export ${prefix}_PASSWORD with the same value.`,
    );
  }
  return { email, password };
}
