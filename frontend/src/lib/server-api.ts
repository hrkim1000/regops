import { cookies } from 'next/headers';

import type { Envelope } from '@/types/api';
import { ACCESS_TOKEN_COOKIE } from '@/types/constants';

/**
 * Server-side reads. Server Components run inside the compose network, so they call the service
 * directly rather than looping back through the `/api/<svc>/*` rewrite — that rewrite exists for
 * the browser, which cannot resolve `regulation:8000`.
 */
const ORIGINS = {
  'platform-core': process.env.PLATFORM_CORE_URL ?? 'http://platform-core:8000',
  regulation: process.env.REGULATION_URL ?? 'http://regulation:8000',
  monitoring: process.env.MONITORING_URL ?? 'http://monitoring:8000',
  assistant: process.env.ASSISTANT_URL ?? 'http://assistant:8000',
} as const;

export type ServiceName = keyof typeof ORIGINS;

export { ACCESS_TOKEN_COOKIE };

export async function accessToken(): Promise<string | null> {
  return (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value ?? null;
}

/**
 * Fetch and unwrap the response envelope.
 *
 * Returns `null` on any failure rather than throwing, so one dead resource renders an
 * `<EmptyState>` instead of blanking a page that also shows unrelated data (frontend-page skill).
 * The reason is logged server-side — a silent null is a debugging trap.
 */
/**
 * Query parameters. An **array becomes repeated keys** (`?status=draft&status=locked`), which is how
 * FastAPI spells a multi-value filter — joining them with a comma would arrive as one bogus value
 * and the endpoint would 422 rather than filter.
 */
export type QueryParams = Record<
  string,
  string | number | boolean | readonly string[] | undefined
>;

function buildUrl(service: ServiceName, path: string, params?: QueryParams): URL {
  const url = new URL(`${ORIGINS[service]}/api/v1${path}`);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === '') continue;
    if (Array.isArray(value)) {
      for (const item of value) url.searchParams.append(key, String(item));
    } else {
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

export async function serverGet<T>(
  service: ServiceName,
  path: string,
  params?: QueryParams,
): Promise<T | null> {
  const token = await accessToken();
  if (!token) return null;

  const url = buildUrl(service, path, params);

  try {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      // Ingested data changes on the poll cadence, not per request, but a stale read here would
      // show a document that no longer matches its detail page. Correctness over cache.
      cache: 'no-store',
    });
    if (!response.ok) {
      console.error(`serverGet ${service}${path} -> HTTP ${response.status}`);
      return null;
    }
    const body = (await response.json()) as Envelope<T>;
    return body.data ?? null;
  } catch (error) {
    console.error(`serverGet ${service}${path} failed`, error);
    return null;
  }
}

/** Envelope plus `meta`, for paginated lists that need the total. */
export async function serverGetPage<T>(
  service: ServiceName,
  path: string,
  params?: QueryParams,
): Promise<Envelope<T> | null> {
  const token = await accessToken();
  if (!token) return null;

  const url = buildUrl(service, path, params);

  try {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    if (!response.ok) {
      console.error(`serverGetPage ${service}${path} -> HTTP ${response.status}`);
      return null;
    }
    return (await response.json()) as Envelope<T>;
  } catch (error) {
    console.error(`serverGetPage ${service}${path} failed`, error);
    return null;
  }
}

/**
 * The archived artefact itself. Not enveloped — it is a byte stream, and it is the one place the
 * WORM archive is exposed to a reader.
 */
export async function serverGetRaw(
  versionId: string,
): Promise<{ text: string; bytes: number } | null> {
  const token = await accessToken();
  if (!token) return null;

  try {
    const response = await fetch(
      `${ORIGINS.regulation}/api/v1/document-versions/${versionId}/raw`,
      { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' },
    );
    if (!response.ok) return null;
    const buffer = await response.arrayBuffer();
    return { text: new TextDecoder('utf-8').decode(buffer), bytes: buffer.byteLength };
  } catch (error) {
    console.error(`serverGetRaw ${versionId} failed`, error);
    return null;
  }
}
