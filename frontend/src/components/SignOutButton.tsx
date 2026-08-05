'use client';

import { LogOut } from 'lucide-react';
import { useRouter } from 'next/navigation';

export function SignOutButton() {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={async () => {
        await fetch('/session', { method: 'DELETE' });
        router.replace('/login');
        router.refresh();
      }}
      className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300"
    >
      <LogOut size={13} /> 로그아웃
    </button>
  );
}
