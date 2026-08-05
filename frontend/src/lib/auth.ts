import { cookies } from 'next/headers';

export type Role = 'viewer' | 'ra' | 'admin';

const ROLE_COOKIE = 'regops_role';
const EMAIL_COOKIE = 'regops_email';

/** Mirror of the backend RBAC ordering (ADR-0005 decision 5). */
const ORDER: Role[] = ['viewer', 'ra', 'admin'];

export async function readUserRole(): Promise<Role | null> {
  const value = (await cookies()).get(ROLE_COOKIE)?.value;
  return ORDER.includes(value as Role) ? (value as Role) : null;
}

export async function readUserEmail(): Promise<string | null> {
  return (await cookies()).get(EMAIL_COOKIE)?.value ?? null;
}

/**
 * Client-side gating only hides what the backend would 403 — it never grants anything. Every
 * restricted action is re-checked server-side on the endpoint.
 */
export function hasAtLeast(role: Role | null, required: Role): boolean {
  if (!role) return false;
  return ORDER.indexOf(role) >= ORDER.indexOf(required);
}

export { ROLE_COOKIE, EMAIL_COOKIE };
