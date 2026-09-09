import type { OrderV3Row } from "./types";

export const SEASON_FACTOR_EXPORT_COLUMNS = [
  "계절지수 적용 상태", "계절지수 버전", "계절지수 f1", "계절지수 f2", "계절지수 fLR",
  "계절지수 원래 보류 코드", "계절지수 원래 보류 사유",
  "기능구분1", "기능구분2", "계절지수 연결 상태"
];

export function seasonFactorExportValues(row: OrderV3Row) {
  return [
    row.seasonalApplied
      ? row.seasonFactorDefaulted ? "기본값 1.0 적용" : "계산된 지수 적용"
      : row.seasonFactorAvailable
        ? row.seasonFactorDefaulted ? "기본값 1.0 연결 · 발주 계산 미완료" : "지수 연결 · 발주 계산 미완료"
        : "미적용",
    row.seasonFactorVersion ?? "",
    row.seasonalFactors?.f1 ?? null,
    row.seasonalFactors?.f2 ?? null,
    row.seasonalFactors?.fLR ?? null,
    row.seasonFactorOriginalReasonCode ?? "",
    row.seasonFactorOriginalMessage ?? "",
    row.functionClass1 ?? "",
    row.functionClass2 ?? "",
    row.seasonFactorAvailable === false ? "연결 불가" : row.seasonFactorAvailable || row.seasonalApplied ? "연결 완료" : "미확인"
  ];
}
