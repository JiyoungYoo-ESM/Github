"use client";

import Link from "next/link";
import { ArrowRight, Database, PlayCircle } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type AnalysisRequiredStateProps = {
  title: string;
  description?: string;
};

export function AnalysisRequiredState({
  title,
  description = "분석 기준을 설정한 뒤 발주 분석 시작하기를 누르면 이 화면에 결과가 반영됩니다."
}: AnalysisRequiredStateProps) {
  return (
    <EmptyState icon={Database} title={title} description={description}>
      <div className="mx-auto mt-6 grid max-w-md gap-2 rounded-2xl border border-slate-200 bg-slate-25 p-4 text-left text-sm text-slate-700">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white text-xs font-bold text-brand-800">
            1
          </span>
          분석 기준값 확인
        </div>
        <div className="flex items-center gap-2">
          <PlayCircle className="h-5 w-5 text-brand-700" />
          발주 분석 시작하기
        </div>
        <div className="flex items-center gap-2">
          <ArrowRight className="h-5 w-5 text-brand-700" />
          대시보드와 발주 분석 탭에 결과 반영
        </div>
      </div>
      <Link href="/upload" className={cn(buttonVariants({ size: "lg" }), "mt-6")}>
        분석 기준 설정
        <ArrowRight className="h-4 w-4" />
      </Link>
    </EmptyState>
  );
}
