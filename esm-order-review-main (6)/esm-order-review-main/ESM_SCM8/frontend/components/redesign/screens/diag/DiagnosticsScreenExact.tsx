"use client";

import { brandOf, ingredientOf, productNameOf, qtyOf, skuCodeOf } from "@/lib/global-demand-view-model";
import { formatNumber } from "@/lib/utils";
import { CategorySelectPill, DiagnosticMetricCard, SelectPill } from "./DiagnosticsScreenParts";
import {
  diagnosticCorrectionDraft,
  diagnosticCorrectionKey,
  diagnosticEditable,
  diagnosticReason
} from "./diagnosticsScreenModel";
import { useDiagnosticsScreenModel } from "./useDiagnosticsScreenModel";

export function DiagnosticsScreenExact() {
  const {
    loading,
    loadFailed,
    options,
    drafts,
    correctionRows,
    regionRows,
    mismatchRows,
    taggedSkuCount,
    completeItems,
    updateDraft,
    handleSave,
    isSaving,
    message,
    error
  } = useDiagnosticsScreenModel();

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[20px]">
        <div className="flex items-center gap-[8px]">
          <h2 className="text-[18px] font-black leading-none text-ink">데이터 진단</h2>
          <span className="rounded-full bg-row px-[9px] py-[3px] text-[11px] font-black text-muted2">데이터 위생</span>
        </div>
        <p className="mt-[11px] text-[13px] font-semibold leading-none text-muted">
          미분류 SKU · 성분 미매칭 · 권역 미연동처럼 확인이 필요한 항목만 점검합니다. 미분류를 줄일수록 분석·발주 정확도가 올라갑니다.
        </p>
      </div>

      <div className="mb-[18px] rounded-[10px] border border-warn-border bg-warn-bg px-[18px] py-[14px]">
        <p className="text-[13px] font-black text-warn">
          {loading
            ? "데이터 진단 결과를 불러오는 중입니다."
            : loadFailed
              ? "데이터 진단 결과를 불러오지 못했습니다. 데이터 입력 탭에서 분석을 다시 실행해 주세요."
              : "CMS 시즌/성분 분석 결과를 기준으로 점검 항목을 자동 집계합니다. 보정값 저장 후 다시 분석하면 결과에 반영됩니다."}
        </p>
      </div>

      <p className="mb-[9px] text-[11px] font-black uppercase tracking-[.16em] text-muted2">DIAGNOSTICS · 진단 요약</p>
      <div className="mb-[18px] grid grid-cols-4 gap-[14px]">
        <DiagnosticMetricCard label="분류 필요 SKU" value={loading ? "-" : formatNumber(correctionRows.length)} sub={correctionRows.length > 0 ? "마스터 확인·분류 누락" : "분류 점검 완료"} positive={!loading && correctionRows.length === 0} />
        <DiagnosticMetricCard label="성분 미매칭 SKU" value={loading ? "-" : formatNumber(mismatchRows.length)} sub={mismatchRows.length > 0 ? "성분/라인 미인식" : "성분 매칭 완료"} positive={!loading && mismatchRows.length === 0} />
        <DiagnosticMetricCard label="권역 확인 국가" value={loading ? "-" : formatNumber(regionRows.length)} sub={regionRows.length > 0 ? "권역 미지정" : "권역 확인 완료"} positive={!loading && regionRows.length === 0} />
        <DiagnosticMetricCard label="성분 태깅 SKU" value={loading ? "-" : formatNumber(taggedSkuCount)} sub="자동 태깅 완료" positive />
      </div>

      <section className="mb-[18px] overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
        <div className="flex items-center justify-between border-b border-divider px-[20px] py-[16px]">
          <div>
            <h3 className="text-[15px] font-black text-ink">분류 필요 SKU</h3>
            <p className="mt-[6px] text-[12px] font-semibold text-muted2">
              상품마스터 미매칭·분류 누락 SKU입니다. 중분류 누락만 보정할 수 있으며, 미매칭 SKU는 상품마스터에서 먼저 확인해야 합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving || completeItems.length === 0}
            className="h-[38px] rounded-[10px] bg-brand px-[18px] text-[13px] font-black text-white transition hover:bg-brand/90 disabled:cursor-not-allowed disabled:opacity-55"
          >
            {isSaving ? "저장 중" : `선택값 저장 (${formatNumber(completeItems.length)})`}
          </button>
        </div>
        {message ? <div className="border-b border-divider bg-pos/10 px-[20px] py-[11px] text-[12px] font-black text-pos">{message}</div> : null}
        {error ? <div className="border-b border-divider bg-warn-bg px-[20px] py-[11px] text-[12px] font-black text-warn">{error}</div> : null}
        <table className="w-full table-fixed border-collapse text-[13px]">
          <thead>
            <tr className="bg-surface-soft text-muted">
              <th className="w-[170px] border-b border-divider px-[16px] py-[12px] text-left font-black">SKU</th>
              <th className="border-b border-divider px-[16px] py-[12px] text-left font-black">제품명</th>
              <th className="w-[90px] border-b border-divider px-[16px] py-[12px] text-right font-black">판매</th>
              <th className="w-[210px] border-b border-divider px-[16px] py-[12px] text-left font-black">진단 사유</th>
              <th className="w-[190px] border-b border-divider px-[16px] py-[12px] text-left font-black">대분류</th>
              <th className="w-[190px] border-b border-divider px-[16px] py-[12px] text-left font-black">중분류</th>
            </tr>
          </thead>
          <tbody>
            {correctionRows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-[16px] py-[34px] text-center text-[13px] font-black text-muted2">
                  {loading ? "분류 필요 SKU를 불러오는 중입니다." : "현재 분류 보정이 필요한 SKU가 없습니다."}
                </td>
              </tr>
            ) : (
              correctionRows.slice(0, 20).map((row) => {
                const sku = diagnosticCorrectionKey(row);
                const draft = diagnosticCorrectionDraft(row, drafts[sku]);
                const editable = diagnosticEditable(row);
                const category2Options = draft.category1 ? options.category2ByCategory1[draft.category1] ?? [] : [];
                return (
                  <tr key={sku}>
                    <td className="border-b border-rowline px-[16px] py-[14px] font-black text-ink3">{sku}</td>
                    <td className="border-b border-rowline px-[16px] py-[14px] font-black text-ink">{productNameOf(row)}</td>
                    <td className="border-b border-rowline px-[16px] py-[14px] text-right font-semibold text-ink3">{formatNumber(qtyOf(row))}</td>
                    <td className="border-b border-rowline px-[16px] py-[14px]">
                      <span className="inline-flex rounded-[7px] border border-warn-border bg-warn-bg px-[9px] py-[5px] text-[11px] font-black text-warn">
                        {diagnosticReason(row)}
                      </span>
                    </td>
                    <td className="border-b border-rowline px-[16px] py-[14px]">
                      <CategorySelectPill
                        value={draft.category1}
                        options={options.category1}
                        placeholder={editable ? "선택" : "마스터 확인 필요"}
                        disabled={!editable}
                        onChange={(value) => updateDraft(sku, { category1: value })}
                      />
                    </td>
                    <td className="border-b border-rowline px-[16px] py-[14px]">
                      <CategorySelectPill
                        value={draft.category2}
                        options={category2Options}
                        placeholder={editable ? "선택" : "마스터 확인 필요"}
                        disabled={!editable || !draft.category1}
                        onChange={(value) => updateDraft(sku, { category2: value })}
                      />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>

      <div className="grid grid-cols-2 gap-[18px]">
        <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
          <div className="flex items-start justify-between gap-4 border-b border-divider px-[20px] py-[16px]">
            <div>
              <h3 className="text-[15px] font-black text-ink">성분 미매칭 SKU</h3>
              <p className="mt-[6px] text-[12px] font-semibold text-muted2">자동 태깅에서 성분/라인을 찾지 못한 SKU 전체입니다.</p>
            </div>
            <span className="shrink-0 rounded-full bg-row px-[10px] py-[5px] text-[11px] font-black text-ink3">
              {formatNumber(mismatchRows.length)}건
            </span>
          </div>
          {mismatchRows.length === 0 ? (
            <div className="px-[20px] py-[34px] text-center text-[13px] font-black text-muted2">
              {loading ? "성분 미매칭 SKU를 불러오는 중입니다." : "현재 성분 미매칭 SKU가 없습니다."}
            </div>
          ) : (
            <div className="max-h-[520px] overflow-y-auto">
              {mismatchRows.map((row) => (
                <div key={`${skuCodeOf(row)}-${productNameOf(row)}`} className="flex items-center justify-between gap-4 border-b border-rowline px-[20px] py-[14px] last:border-b-0">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-black text-ink" title={productNameOf(row)}>{productNameOf(row)}</p>
                    <p className="mt-[4px] truncate text-[12px] font-semibold text-muted2" title={`${skuCodeOf(row)} · ${brandOf(row)} · ${ingredientOf(row)}`}>
                      {skuCodeOf(row)} · {brandOf(row)} · {ingredientOf(row)}
                    </p>
                  </div>
                  <span className="shrink-0 rounded-[8px] border border-border bg-surface px-[13px] py-[8px] text-[12px] font-black text-ink3">
                    확인 필요
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
          <div className="flex items-start justify-between gap-4 border-b border-divider px-[20px] py-[16px]">
            <div>
              <h3 className="text-[15px] font-black text-ink">권역 기준 확인</h3>
              <p className="mt-[6px] text-[12px] font-semibold text-muted2">국가별 데이터를 권역으로 묶기 전 회사 기준 확인이 필요한 국가입니다.</p>
            </div>
            <span className="shrink-0 rounded-full bg-row px-[10px] py-[5px] text-[11px] font-black text-ink3">
              {formatNumber(regionRows.length)}건
            </span>
          </div>
          {regionRows.length === 0 ? (
            <div className="px-[20px] py-[34px] text-center text-[13px] font-black text-muted2">
              {loading ? "권역 확인 국가를 불러오는 중입니다." : "현재 권역 기준 확인이 필요한 국가는 없습니다."}
            </div>
          ) : (
            <div className="max-h-[520px] overflow-y-auto">
              {regionRows.map((row) => (
                <div key={row.country} className="flex items-center justify-between gap-4 border-b border-rowline px-[20px] py-[16px] last:border-b-0">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-black text-ink">{row.country}</p>
                    <p className="mt-[4px] truncate text-[12px] font-semibold text-muted2" title={`${row.regionInfo.region} · ${row.regionInfo.note ?? "회사 권역 기준 확인 필요"} · 판매 ${formatNumber(row.qty)}`}>
                      {row.regionInfo.region} · {row.regionInfo.note ?? "회사 권역 기준 확인 필요"} · 판매 {formatNumber(row.qty)}
                    </p>
                  </div>
                  <SelectPill label={row.regionInfo.region} />
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
