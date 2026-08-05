'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch('/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const body = (await response.json()) as { message?: string };
        setError(body.message ?? '로그인에 실패했습니다');
        return;
      }
      router.replace('/regulations');
      router.refresh();
    } catch {
      setError('요청을 보낼 수 없습니다');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-surface-border bg-surface-raised p-8"
      >
        <h1 className="text-lg font-semibold text-slate-100">RegOps</h1>
        <p className="mt-1 text-xs text-slate-500">수집된 규제 원문 열람</p>

        <label className="mt-6 block text-xs text-slate-400" htmlFor="email">
          이메일
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
        />

        <label className="mt-4 block text-xs text-slate-400" htmlFor="password">
          비밀번호
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
        />

        {error ? <p className="mt-4 text-xs text-red-400">{error}</p> : null}

        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-slate-950 disabled:opacity-50"
        >
          {busy ? '확인 중…' : '로그인'}
        </button>
      </form>
    </main>
  );
}
