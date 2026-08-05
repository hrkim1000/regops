import type { Metadata } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'RegOps — 규제 원문',
  description: '수집된 규제 원문 열람',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
