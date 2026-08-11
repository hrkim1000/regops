import { redirect } from 'next/navigation';

import { AppShell } from '@/components/AppShell';
import { accessToken } from '@/lib/server-api';

/** Auth gate, then the shared chrome — the same ScopeBar the regulation browser uses. */
export default async function QaLayout({ children }: { children: React.ReactNode }) {
  if (!(await accessToken())) redirect('/login');
  return <AppShell active="qa">{children}</AppShell>;
}
