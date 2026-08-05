export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toISOString().replace('T', ' ').slice(0, 19) + 'Z';
}

export function formatDate(iso: string | null): string {
  return iso ? iso.slice(0, 10) : '—';
}

export function shortHash(hash: string): string {
  return hash.slice(0, 12);
}
