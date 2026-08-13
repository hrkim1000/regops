import { redirect } from 'next/navigation';

import { AppShell } from '@/components/AppShell';
import { accessToken } from '@/lib/server-api';

/** Auth gate, then the shared chrome — the same ScopeBar the other two pillars use. */
export default async function MonitoringLayout({ children }: { children: React.ReactNode }) {
  if (!(await accessToken())) redirect('/login');
  return <AppShell active="monitoring">{children}</AppShell>;
}
