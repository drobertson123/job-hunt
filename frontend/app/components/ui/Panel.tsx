import type { ReactNode } from "react";

export default function Panel({
  title,
  actions,
  children,
  className = "",
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex min-h-0 flex-col rounded-sm border border-line bg-surface ${className}`}>
      {title && (
        <div className="flex items-center justify-between rounded-t-sm border-b border-line-soft bg-surface-alt px-3 py-2">
          <span className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-muted">
            {title}
          </span>
          {actions && <div className="flex gap-1">{actions}</div>}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
