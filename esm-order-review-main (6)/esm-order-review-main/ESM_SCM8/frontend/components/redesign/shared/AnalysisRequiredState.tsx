import { Database } from "lucide-react";
import type { Screen } from "../lib/types";

// 발주(order/gap 등) 쪽 화면에서 "분석 시작"을 아직 안 눌렀을 때 보여주는 빈 상태.
export function AnalysisStartRequiredState({
  title,
  description,
  onNavigate
}: {
  title: string;
  description: string;
  onNavigate: (screen: Screen) => void;
}) {
  return (
    <div className="mx-auto max-w-[1320px] py-[24px]">
      <section className="grid min-h-[460px] place-items-center rounded-[16px] border border-dashed border-border bg-surface px-6 py-16 text-center shadow-soft">
        <div className="max-w-[480px]">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-[14px] bg-brand-50 text-brand">
            <Database className="h-6 w-6" />
          </div>
          <h2 className="mt-5 text-[20px] font-black leading-tight text-ink">{title}</h2>
          <p className="mt-3 text-[13px] font-semibold leading-6 text-muted">{description}</p>
          <button
            type="button"
            onClick={() => onNavigate("prep")}
            className="mt-6 inline-flex h-[42px] items-center justify-center rounded-[10px] bg-sidebar px-5 text-[13px] font-black text-white transition hover:bg-ink"
          >
            데이터 입력에서 분석 시작하기
          </button>
        </div>
      </section>
    </div>
  );
}

// 인사이트(country/brand/sku 등) 쪽 화면에서 "분석 시작"을 아직 안 눌렀을 때 보여주는 빈 상태.
export function InsightAnalysisRequiredState({
  title,
  description,
  onNavigate
}: {
  title: string;
  description: string;
  onNavigate: (screen: Screen) => void;
}) {
  return (
    <div className="mx-auto max-w-[1320px] py-[24px]">
      <section className="grid min-h-[460px] place-items-center rounded-[16px] border border-dashed border-border bg-surface px-6 py-16 text-center shadow-soft">
        <div className="max-w-[520px]">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-[14px] bg-brand-50 text-brand">
            <Database className="h-6 w-6" />
          </div>
          <h2 className="mt-5 text-[20px] font-black leading-tight text-ink">{title}</h2>
          <p className="mt-3 text-[13px] font-semibold leading-6 text-muted">{description}</p>
          <button
            type="button"
            onClick={() => onNavigate("idata")}
            className="mt-6 inline-flex h-[42px] items-center justify-center rounded-[10px] bg-sidebar px-5 text-[13px] font-black text-white transition hover:bg-ink"
          >
            데이터 입력에서 분석 시작하기
          </button>
        </div>
      </section>
    </div>
  );
}
