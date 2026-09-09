"""Source-level data quality checks for season and brand reports."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from core.season_calendar import (
    _number_series,
    _standard_sales_amount_series,
    filter_season_sales_by_biz_type,
)


DUPLICATE_RECOMMENDATION_BLOCK_THRESHOLD_PCT = 0.5
_DATE_ALIASES = ("출고일", "출고 일자", "일자", "date", "Date", "ship_dt")
_QTY_ALIASES = ("판매수량", "수량", "판매 수량", "qty", "quantity")
_STABLE_ID_ALIASES = (
    "sales_detail_id",
    "sale_detail_id",
    "sales_line_id",
    "sale_line_id",
    "invoice_line_id",
    "invc_line_id",
    "판매상세ID",
    "판매행ID",
)


def _normalized_column_map(frame: pd.DataFrame) -> dict[str, str]:
    return {
        "".join(str(column).casefold().split()).replace("_", ""): str(column)
        for column in frame.columns
    }


def _find_column(frame: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    normalized = _normalized_column_map(frame)
    for alias in aliases:
        key = "".join(str(alias).casefold().split()).replace("_", "")
        if key in normalized:
            return normalized[key]
    return None


def _filter_period(
    frame: pd.DataFrame,
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
) -> pd.DataFrame:
    date_column = _find_column(frame, _DATE_ALIASES)
    if date_column is None:
        return frame.copy()
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    selected = dates.notna()
    if start_date is not None:
        selected &= dates.ge(start_date)
    if end_date is not None:
        selected &= dates.le(end_date)
    return frame.loc[selected].copy()


def _duplicate_profile(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, int]:
    if frame.empty:
        empty = pd.Series(False, index=frame.index, dtype=bool)
        return empty, empty, 0
    comparable = frame.copy()
    for column in comparable.columns:
        comparable[column] = comparable[column].astype("string").fillna("")
    all_duplicates = comparable.duplicated(keep=False)
    excess_duplicates = comparable.duplicated(keep="first")
    group_count = int(comparable.loc[all_duplicates].drop_duplicates().shape[0])
    return all_duplicates, excess_duplicates, group_count


def build_source_data_quality(
    sales_df: pd.DataFrame,
    *,
    start_date: pd.Timestamp | None = None,
    end_date: pd.Timestamp | None = None,
    eu_local: bool = False,
    entity_code: str | None = None,
) -> dict[str, object]:
    """Return deterministic quality metadata without unsafe fuzzy deduplication."""
    source = filter_season_sales_by_biz_type(
        pd.DataFrame(sales_df),
        eu_local=eu_local,
        entity_code=entity_code,
    )
    source = _filter_period(source, start_date, end_date)
    if source.empty:
        return {
            "status": "blocked",
            "sourceRows": 0,
            "stableIdColumn": None,
            "stableIdDuplicateRows": 0,
            "duplicateCandidateGroups": 0,
            "duplicateCandidateRows": 0,
            "duplicateCandidateExcessRows": 0,
            "duplicateCandidateAmountEur": 0.0,
            "duplicateCandidateAmountSharePct": 0.0,
            "freeOfChargeRowsExcluded": 0,
            "freeOfChargeQtyExcluded": 0.0,
            "recommendationBlocked": True,
            "blockThresholdPct": DUPLICATE_RECOMMENDATION_BLOCK_THRESHOLD_PCT,
            "notes": ["선택 기간에 분석 가능한 판매 원천 행이 없습니다."],
        }

    all_duplicates, excess_duplicates, duplicate_groups = _duplicate_profile(source)
    amount = _standard_sales_amount_series(source, entity_code=entity_code)
    qty_column = _find_column(source, _QTY_ALIASES)
    qty = (
        _number_series(source[qty_column])
        if qty_column is not None
        else pd.Series(0.0, index=source.index)
    )
    free_of_charge = qty.gt(0) & amount.eq(0)
    excess_amount = float(amount.loc[excess_duplicates].sum())
    total_amount = float(amount.sum())
    impact_pct = abs(excess_amount) / abs(total_amount) * 100 if total_amount else 0.0

    stable_id_column = _find_column(source, _STABLE_ID_ALIASES)
    stable_id_duplicate_rows = 0
    if stable_id_column is not None:
        stable_ids = source[stable_id_column].astype("string").fillna("").str.strip()
        populated = stable_ids.ne("")
        stable_id_duplicate_rows = int((populated & stable_ids.duplicated(keep=False)).sum())

    recommendation_blocked = impact_pct >= DUPLICATE_RECOMMENDATION_BLOCK_THRESHOLD_PCT
    has_warning = bool(duplicate_groups or stable_id_duplicate_rows)
    status = "blocked" if recommendation_blocked else "warning" if has_warning else "ok"
    notes: list[str] = []
    if duplicate_groups:
        notes.append(
            "판매행 고유 ID가 없어 완전 일치 행은 중복 후보로만 표시하며 자동 제거하지 않습니다."
            if stable_id_column is None
            else f"{stable_id_column} 기준 중복 여부를 함께 점검했습니다."
        )
    if recommendation_blocked:
        notes.append(
            f"중복 후보의 최대 매출 영향이 {DUPLICATE_RECOMMENDATION_BLOCK_THRESHOLD_PCT:.1f}% 이상이라 "
            "자동 발주 추천을 차단했습니다."
        )
    if free_of_charge.any():
        notes.append("매출 €0·수량 양수인 무상증정 행은 판매 KPI에서 제외됩니다.")

    return {
        "status": status,
        "sourceRows": int(len(source)),
        "stableIdColumn": stable_id_column,
        "stableIdDuplicateRows": stable_id_duplicate_rows,
        "duplicateCandidateGroups": duplicate_groups,
        "duplicateCandidateRows": int(all_duplicates.sum()),
        "duplicateCandidateExcessRows": int(excess_duplicates.sum()),
        "duplicateCandidateAmountEur": round(excess_amount, 6),
        "duplicateCandidateAmountSharePct": round(impact_pct, 6),
        "freeOfChargeRowsExcluded": int(free_of_charge.sum()),
        "freeOfChargeQtyExcluded": float(qty.loc[free_of_charge].sum()),
        "recommendationBlocked": recommendation_blocked,
        "blockThresholdPct": DUPLICATE_RECOMMENDATION_BLOCK_THRESHOLD_PCT,
        "notes": notes,
    }


__all__ = [
    "DUPLICATE_RECOMMENDATION_BLOCK_THRESHOLD_PCT",
    "build_source_data_quality",
]
