import { NextResponse, type NextRequest } from 'next/server';

import { ACCESS_TOKEN_COOKIE } from '@/types/constants';

/**
 * Attach the JWT to `/api/<svc>/*` on its way through the rewrite.
 *
 * The token is httpOnly on purpose — a token in `localStorage` is readable by any script on the
 * page, and this one carries a role the backend trusts. That makes it unreachable from client JS,
 * so the browser cannot set `Authorization` itself and the rewrite alone forwards an anonymous
 * request. Injecting it here keeps both properties: the client never sees the token, and the
 * service still receives a bearer credential.
 *
 * No token means no header — the service answers 401, which is the correct outcome rather than
 * something for middleware to paper over.
 */
export function middleware(request: NextRequest) {
  const token = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return NextResponse.next();

  const headers = new Headers(request.headers);
  headers.set('Authorization', `Bearer ${token}`);
  return NextResponse.next({ request: { headers } });
}

export const config = { matcher: '/api/:path*' };
