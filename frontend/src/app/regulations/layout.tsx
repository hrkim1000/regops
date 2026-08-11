import { redirect } from 'next/navigation';

import { AppShell } from '@/components/AppShell';
import { accessToken } from '@/lib/server-api';

/** Auth gate, then the shared chrome. Everything else lives in {@link AppShell}. */
export default async function RegulationsLayout({ children }: { children: React.ReactNode }) {
  if (!(await accessToken())) redirect('/login');
  return <AppShell active="regulations">{children}</AppShell>;
}
