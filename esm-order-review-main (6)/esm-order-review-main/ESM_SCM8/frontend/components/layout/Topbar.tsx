import type { ReactNode } from "react";

type TopbarProps = {
  title: string;
  description?: string;
  actions?: ReactNode;
};

export function Topbar({ title, description, actions }: TopbarProps) {
  return (
    <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-line bg-white px-5 py-3">
      <div className="min-w-0">
        <h1 className="text-xl font-bold tracking-tight text-ink">{title}</h1>
        {description ? <p className="mt-1 text-sm text-slate-500">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
