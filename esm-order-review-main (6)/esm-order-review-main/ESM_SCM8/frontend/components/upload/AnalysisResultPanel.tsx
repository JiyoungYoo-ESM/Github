"use client";

import { Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { downloadHref } from "@/lib/api";
import type { AnalyzeResponse } from "@/types/api";

type AnalysisResultPanelProps = {
  result: AnalyzeResponse;
};

export function AnalysisResultPanel({ result }: AnalysisResultPanelProps) {
  return (
    <div className="space-y-3 rounded-2xl border border-black/10 bg-white px-4 py-4">
      <Badge variant="success" className="w-fit">
        분석 완료
      </Badge>
      <div className="space-y-1 text-sm text-black">
        <p>환율: {result.settings?.eur_krw_rate ?? "-"} KRW/EUR</p>
        <p>안전재고 목표 {result.settings?.safety_months ?? "-"}개월</p>
      </div>
      <a
        href={downloadHref(result)}
        className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-2xl bg-black px-4 text-sm font-semibold text-white hover:bg-brand"
      >
        <Download className="h-4 w-4" />
        결과 엑셀 다운로드
      </a>
    </div>
  );
}
