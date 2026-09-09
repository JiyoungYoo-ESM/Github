"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, CheckCircle2, Globe, Info, PackageCheck } from "lucide-react";
import type { SeasonTrendAnalyzeResponse } from "@/types/api";
import { SeasonTrendUploadPanel } from "./SeasonTrendUploadPanel";

const sectionLinks = [
  { href: "/season-trend/global-demand", label: "수요 분석", icon: Globe },
  { href: "/integrated-order-review", label: "통합 발주", icon: PackageCheck }
];

export function SeasonTrendSetupClient() {
  const [lastResult, setLastResult] = useState<SeasonTrendAnalyzeResponse | null>(null);

  return (
    <div className="space-y-6">
      <SeasonTrendUploadPanel onAnalyzed={setLastResult} />

      {lastResult ? (
        <div className="flex items-start gap-2 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          분석이 완료되었습니다. 수요 분석에서 국가/권역별 시즌 수요까지 확인한 뒤 성분 트렌드와 통합 발주에서 최종 판단할 수 있습니다.
        </div>
      ) : (
        <div className="flex items-start gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
          장기 판매이력과 상품목록 파일을 업로드한 뒤 분석을 시작하면 아래 분석 화면에 결과가 반영됩니다.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {sectionLinks.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className="group flex items-center justify-between gap-3 rounded-2xl border border-line bg-white px-4 py-4 text-sm font-bold text-slate-800 shadow-sm transition hover:border-brand/40 hover:bg-red-50/40 hover:text-brand"
            >
              <span className="flex min-w-0 items-center gap-3">
                <Icon className="h-5 w-5 shrink-0 text-slate-400 transition-colors group-hover:text-brand" />
                <span className="truncate">{item.label}</span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-brand" />
            </Link>
          );
        })}
      </div>
    </div>
  );
}
