"use client";

import { CheckCircle2, Clock3, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  activateV3SeasonFactor,
  createV3SeasonFactorCandidate,
  getV3SeasonFactor,
  listV3SeasonFactors,
  reviewV3SeasonFactorGroup,
  type V3SeasonFactorArtifact,
  type V3SeasonFactorGroup,
  type V3SeasonFactorSummary
} from "@/lib/api/order-logic-v3-season-factors";

const monthLabels = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];

function todayLocal() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function statusLabel(status: string) {
  if (status === "ACTIVE") return "적용 중";
  if (status === "RETIRED") return "이전 버전";
  if (status === "CONFIRMED") return "계절성 확인";
  if (status === "NOT_CONFIRMED") return "계절성 미확인";
  if (status === "CALC_FAILED") return "계산 실패";
  return "검토 대기";
}

export function V3SeasonFactorManagementScreen() {
  const [items, setItems] = useState<V3SeasonFactorSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<V3SeasonFactorArtifact | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<V3SeasonFactorGroup | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const loadList = useCallback(async () => {
    const next = await listV3SeasonFactors();
    setItems(next);
    setSelectedId((current) => current ?? next[0]?.artifact_id ?? null);
  }, []);

  useEffect(() => {
    loadList().catch((error) => setMessage(error instanceof Error ? error.message : "목록을 불러오지 못했습니다."));
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) { setArtifact(null); return; }
    getV3SeasonFactor(selectedId)
      .then((next) => { setArtifact(next); setSelectedGroup(next.categories[0] ?? null); })
      .catch((error) => setMessage(error instanceof Error ? error.message : "상세를 불러오지 못했습니다."));
  }, [selectedId]);

  const pendingCount = useMemo(
    () => artifact?.categories.filter((group) => group.seasonality_status === "PENDING").length ?? 0,
    [artifact]
  );

  const run = async (action: () => Promise<V3SeasonFactorArtifact>, success: string) => {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      const next = await action();
      setArtifact(next); setSelectedId(next.artifact_id);
      setSelectedGroup((current) => next.categories.find((group) =>
        group.function_class_1_code === current?.function_class_1_code &&
        group.function_class_2_code === current?.function_class_2_code
      ) ?? next.categories[0] ?? null);
      await loadList();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "요청을 처리하지 못했습니다.");
    } finally { setBusy(false); }
  };

  return (
    <main className="mx-auto max-w-[1480px] space-y-4 px-4 py-4 lg:px-6 lg:py-5">
      <section className="rounded-[14px] border border-border bg-white p-5 shadow-card">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[10px] font-black text-brand">관리자 · V3 설정</p>
            <h2 className="mt-1 text-[20px] font-black text-ink">계절지수 관리</h2>
            <p className="mt-2 text-[11px] font-semibold text-muted">24개월 후보를 생성하고 기능구분별 검토를 마친 버전만 V3에 적용합니다.</p>
          </div>
          <button type="button" disabled={busy} onClick={() => run(() => createV3SeasonFactorCandidate(todayLocal()), "새 후보를 생성했습니다.")} className="inline-flex h-10 items-center justify-center gap-2 rounded-[9px] bg-brand px-4 text-[11px] font-black text-white disabled:opacity-50">
            <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> 후보 생성
          </button>
        </div>
        {message ? <p role="status" className="mt-4 rounded-[9px] bg-surface-soft px-3 py-2 text-[10.5px] font-bold text-ink">{message}</p> : null}
      </section>

      <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <section className="overflow-hidden rounded-[14px] border border-border bg-white shadow-card">
          <div className="border-b border-border px-4 py-3"><h3 className="text-[13px] font-black text-ink">후보·승인 버전 목록</h3></div>
          <div className="max-h-[680px] overflow-y-auto p-2">
            {items.length ? items.map((item) => (
              <button key={item.artifact_id} type="button" onClick={() => setSelectedId(item.artifact_id)} className={`mb-2 w-full rounded-[10px] border p-3 text-left ${selectedId === item.artifact_id ? "border-brand bg-brand-50" : "border-border bg-white hover:bg-surface-soft"}`}>
                <div className="flex items-center justify-between gap-2"><strong className="text-[11px] text-ink">{item.window_end.slice(0, 7)} 기준</strong><span className="rounded-full bg-surface-soft px-2 py-1 text-[9px] font-black text-muted">{statusLabel(item.artifact_status)}</span></div>
                <p className="mt-2 text-[9.5px] font-semibold text-muted">{item.window_start}~{item.window_end}</p>
                <p className="mt-1 text-[9.5px] font-semibold text-muted">조합 {item.group_count}개 · 검토대기 {item.pending_count}개</p>
              </button>
            )) : <p className="p-6 text-center text-[11px] font-semibold text-muted">아직 생성된 후보가 없습니다.</p>}
          </div>
        </section>

        <section className="overflow-hidden rounded-[14px] border border-border bg-white shadow-card">
          {!artifact ? <p className="p-10 text-center text-[11px] font-semibold text-muted">왼쪽에서 버전을 선택해 주세요.</p> : (
            <>
              <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div><h3 className="text-[14px] font-black text-ink">{artifact.window_start}~{artifact.window_end}</h3><p className="mt-1 text-[9.5px] font-semibold text-muted">{artifact.artifact_id}</p></div>
                <button type="button" disabled={busy || artifact.artifact_status !== "CANDIDATE" || pendingCount > 0} onClick={() => run(() => activateV3SeasonFactor(artifact.artifact_id), "승인 버전을 V3에 적용했습니다.")} className="inline-flex h-9 items-center gap-2 rounded-[8px] bg-emerald-700 px-3 text-[10px] font-black text-white disabled:cursor-not-allowed disabled:opacity-40"><ShieldCheck className="h-4 w-4" /> 승인하여 V3 적용</button>
              </div>
              <div className="grid min-h-[560px] lg:grid-cols-[360px_minmax(0,1fr)]">
                <div className="border-b border-border lg:border-b-0 lg:border-r">
                  <div className="grid grid-cols-[1fr_auto] gap-2 border-b border-border bg-surface-soft px-3 py-2 text-[9px] font-black text-muted"><span>기능구분</span><span>판정</span></div>
                  <div className="max-h-[610px] overflow-y-auto p-2">
                    {artifact.categories.map((group) => (
                      <button key={`${group.function_class_1_code}\0${group.function_class_2_code}`} type="button" onClick={() => setSelectedGroup(group)} className={`mb-1 grid w-full grid-cols-[1fr_auto] gap-2 rounded-[8px] px-3 py-2.5 text-left ${selectedGroup?.function_class_1_code === group.function_class_1_code && selectedGroup?.function_class_2_code === group.function_class_2_code ? "bg-brand-50" : "hover:bg-surface-soft"}`}>
                        <span><strong className="block text-[10.5px] text-ink">{group.function_class_1_code} · {group.function_class_2_code}</strong><small className="text-[9px] font-semibold text-muted">SKU {group.sku_count}개</small></span>
                        <span className="self-center rounded-full bg-surface-soft px-2 py-1 text-[8.5px] font-black text-muted">{statusLabel(group.seasonality_status)}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="p-4 lg:p-5">
                  {selectedGroup ? (
                    <>
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-[10px] font-black text-brand">월별 상세</p><h4 className="mt-1 text-[16px] font-black text-ink">{selectedGroup.function_class_1_code} · {selectedGroup.function_class_2_code}</h4></div>{artifact.artifact_status === "CANDIDATE" ? <div className="flex gap-2"><button type="button" disabled={busy} onClick={() => run(() => reviewV3SeasonFactorGroup(artifact.artifact_id, selectedGroup, "CONFIRMED"), "계절성 확인으로 저장했습니다.")} className="inline-flex h-9 items-center gap-1.5 rounded-[8px] bg-emerald-50 px-3 text-[9.5px] font-black text-emerald-800"><CheckCircle2 className="h-4 w-4" /> 계절성 확인</button><button type="button" disabled={busy} onClick={() => run(() => reviewV3SeasonFactorGroup(artifact.artifact_id, selectedGroup, "NOT_CONFIRMED"), "계절성 미확인(1.0)으로 저장했습니다.")} className="inline-flex h-9 items-center gap-1.5 rounded-[8px] bg-surface-soft px-3 text-[9.5px] font-black text-muted"><XCircle className="h-4 w-4" /> 미확인</button></div> : null}</div>
                      {selectedGroup.seasonality_status === "CALC_FAILED" ? <div className="mt-5 rounded-[10px] border border-red-200 bg-red-50 px-4 py-4 text-[10.5px] font-bold text-red-800">계절지수 계산에 실패했습니다. 1.0으로 대체 적용하지 않으며 이 조합의 V3 계산은 차단됩니다.</div> : <div className="mt-5 grid grid-cols-3 gap-2 sm:grid-cols-4 xl:grid-cols-6">{monthLabels.map((label, index) => <div key={label} className="rounded-[10px] border border-border bg-surface-soft px-3 py-3 text-center"><span className="text-[9px] font-black text-muted">{label}</span><strong className="mt-1 block text-[14px] font-black tabular-nums text-ink">{Number(selectedGroup.factors_by_month[String(index + 1)] ?? 1).toFixed(3)}</strong></div>)}</div>}
                      <div className="mt-5 flex items-center gap-2 rounded-[10px] border border-border p-3 text-[10px] font-semibold text-muted"><Clock3 className="h-4 w-4" /> 현재 상태: {statusLabel(selectedGroup.seasonality_status)}{selectedGroup.reviewed_by ? ` · ${selectedGroup.reviewed_by}` : ""}</div>
                    </>
                  ) : null}
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
