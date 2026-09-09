import { AlertTriangle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

type ErrorStateProps = {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
};

export function ErrorState({
  title = "데이터를 불러오지 못했습니다",
  message,
  onRetry,
  className
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex min-h-[200px] flex-col items-center justify-center gap-4 rounded-2xl border border-red-100 bg-red-50/40 px-6 py-10 text-center",
        className
      )}
      role="alert"
      aria-live="assertive"
    >
      <AlertTriangle className="h-8 w-8 text-brand-700" />
      <div className="space-y-1">
        <p className="text-base font-black text-ink">{title}</p>
        {message ? (
          <p className="text-sm font-semibold text-slate-500">{message}</p>
        ) : (
          <p className="text-sm font-semibold text-slate-500">
            잠시 후 다시 시도해 주세요. 문제가 계속되면 데이터 파일을 확인해 주세요.
          </p>
        )}
      </div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-bold text-brand-700 transition hover:bg-red-50"
        >
          <RefreshCw className="h-4 w-4" />
          다시 시도
        </button>
      ) : null}
    </div>
  );
}
