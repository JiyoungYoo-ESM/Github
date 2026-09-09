import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type LoadingStateProps = {
  /** Number of metric-card skeletons to render across the top row. 0 to hide. */
  cards?: number;
  /** Render a table/panel skeleton body. */
  panel?: boolean;
  className?: string;
};

/** Consistent loading placeholder for internal data screens. */
export function LoadingState({ cards = 0, panel = true, className }: LoadingStateProps) {
  return (
    <div className={cn("space-y-6", className)} aria-busy="true" aria-live="polite">
      {cards > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: cards }).map((_, index) => (
            <Skeleton key={index} className="h-28" />
          ))}
        </div>
      ) : null}
      {panel ? (
        <div className="space-y-4 rounded-2xl border border-line bg-white p-6 shadow-sm">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-full max-w-md" />
          <div className="space-y-3 pt-2">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-10 w-full rounded-xl" />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
