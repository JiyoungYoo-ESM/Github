import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type EmptyStateProps = {
  icon?: LucideIcon;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  /** Compact variant for use inside an existing card/table area. */
  compact?: boolean;
  children?: React.ReactNode;
};

export function EmptyState({
  icon: Icon,
  title,
  description,
  actions,
  className,
  compact = false,
  children
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 text-center",
        compact ? "min-h-[180px] py-8" : "min-h-[360px] py-12",
        className
      )}
    >
      <div className="max-w-md">
        {Icon ? (
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-700">
            <Icon className="h-6 w-6" />
          </div>
        ) : null}
        <h3 className={cn("font-semibold text-ink", compact ? "text-base" : "text-lg")}>{title}</h3>
        {description ? <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p> : null}
        {children}
        {actions ? <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{actions}</div> : null}
      </div>
    </div>
  );
}
