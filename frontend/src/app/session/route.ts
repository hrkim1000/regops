import { NextResponse } from 'next/server';

import { EMAIL_COOKIE, ROLE_COOKIE } from '@/lib/auth';
import { ACCESS_TOKEN_COOKIE } from '@/lib/server-api';

/**
 * Session exchange. The browser posts credentials here, this route calls `platform-core`, and the
 * JWT comes back as an **httpOnly** cookie.
 *
 * The token deliberately never reaches client JavaScript: a token in `localStorage` is readable by
 * any script on the page, and this one carries a role the backend trusts.
 *
 * Deliberately not under `/api/` — that prefix is reserved for the `/api/<svc>/*` rewrites, and a
 * route handler squatting there would shadow a service path.
 */
const PLATFORM_CORE = process.env.PLATFORM_CORE_URL ?? 'http://platform-core:8000';

export async function POST(request: Request) {
  const { email, password } = (await request.json()) as { email?: string; password?: string };
  if (!email || !password) {
    return NextResponse.json({ message: '이메일과 비밀번호를 입력하세요' }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${PLATFORM_CORE}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ message: '인증 서비스에 연결할 수 없습니다' }, { status: 502 });
  }

  if (!upstream.ok) {
    // Do not echo the upstream message — it distinguishes "no such user" from "wrong password".
    return NextResponse.json({ message: '이메일 또는 비밀번호가 올바르지 않습니다' }, { status: 401 });
  }

  const body = (await upstream.json()) as {
    data?: { access_token?: string; role?: string };
  };
  const token = body.data?.access_token;
  if (!token) {
    return NextResponse.json({ message: '인증 응답에 토큰이 없습니다' }, { status: 502 });
  }

  const response = NextResponse.json({ ok: true });
  const secure = process.env.NODE_ENV === 'production';
  response.cookies.set(ACCESS_TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    secure,
    path: '/',
  });
  // Role and email are display-only mirrors. They gate nothing: the backend re-checks every
  // restricted call, so tampering with these changes what a button looks like, not what it can do.
  response.cookies.set(ROLE_COOKIE, body.data?.role ?? 'viewer', {
    sameSite: 'lax',
    secure,
    path: '/',
  });
  response.cookies.set(EMAIL_COOKIE, email, { sameSite: 'lax', secure, path: '/' });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  for (const name of [ACCESS_TOKEN_COOKIE, ROLE_COOKIE, EMAIL_COOKIE]) {
    response.cookies.delete(name);
  }
  return response;
}
