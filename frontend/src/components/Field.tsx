import { clsx } from 'clsx';

/**
 * One labelled fact. `muted` is for values that are legitimately absent — a null `published_at`
 * means the source exposes no publication date, and it must not read like a rendering bug.
 */
export function Field({
  label,
  value,
  mono,
  muted,
  title,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  muted?: boolean;
  title?: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
      <dd
        title={title}
        className={clsx(
          'mt-0.5 truncate text-sm',
          mono && 'font-mono text-xs',
          muted ? 'text-slate-600' : 'text-slate-200',
        )}
      >
        {value}
      </dd>
    </div>
  );
}
