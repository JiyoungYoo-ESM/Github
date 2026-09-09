"use client";

import { Loader2 } from "lucide-react";

type AnalysisProgressProps = {
  loading: boolean;
};

export function AnalysisProgress({ loading }: AnalysisProgressProps) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-4 text-sm leading-6 text-brand">
        <div className="flex items-start gap-3">
          <Loader2 className="mt-1 h-5 w-5 shrink-0 animate-spin" />
          <div>
            <p className="font-bold">잠시 기다려주세요. 분석 결과를 만들고 있습니다.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm leading-6 text-brand">
      <p className="font-bold">분석 시작을 눌러야 다른 탭에 반영됩니다.</p>
    </div>
  );
}
