"""Reproducible aggregate-only data-quality checks for Order Analysis V2.

The module intentionally does not persist CMS payloads or row-level business data.
It returns only aggregate counts and rates suitable for an audit report.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
import json
import math
from statistics import fmean, stdev
from typing import Iterable, Mapping

import pandas as pd

from backend.cms_client import fetch_cms_lead_time
from backend.cms_mapping import build_uploaded_data_from_cms
from backend.services.order_logic_v2_lead_time import (
    aggregate_lead_time_rows,
    lead_time_query_window,
)
from backend.services.order_logic_v2_service import _fetch_fresh_cms_source
from backend.services.order_logic_v2_source import (
    build_order_logic_v2_source,
    completed_week_window,
)
from core.sales import filter_sales_by_biz_type


REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "stock_local": ("prod_cd", "avbl_qty", "stock_ucost"),
    "stock_hq": ("prod_cd", "avbl_qty"),
    "sales_local": ("prod_cd", "qty", "ship_dt", "biz_type"),
    "sales_hq": ("prod_cd", "qty", "ship_dt"),
    "shipping": ("prod_cd", "qty"),
    "open_po": ("prod_cd", "open_qty"),
}


def _blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parsed_date(value: object) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _pct(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator * 100.0, 4) if denominator else None


def _canonical_duplicate_counts(rows: Iterable[Mapping[str, object]]) -> tuple[int, int]:
    canonical = [
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
        for row in rows
    ]
    counts = Counter(canonical)
    affected = sum(count for count in counts.values() if count > 1)
    extras = sum(count - 1 for count in counts.values() if count > 1)
    return affected, extras


def _endpoint_profile(name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    required = REQUIRED_FIELDS[name]
    missing_by_field = {
        field: sum(_blank(row.get(field)) for row in rows)
        for field in required
    }
    if name == "sales_local":
        missing_by_field["amount_or_amount_krw"] = sum(
            _blank(row.get("amount")) and _blank(row.get("amount_krw"))
            for row in rows
        )
    affected_duplicates, extra_duplicates = _canonical_duplicate_counts(rows)
    return {
        "endpoint": name,
        "rows": len(rows),
        "field_count": len({key for row in rows for key in row}),
        "missing_required": missing_by_field,
        "rows_with_any_required_missing": sum(
            any(_blank(row.get(field)) for field in required)
            or (
                name == "sales_local"
                and _blank(row.get("amount"))
                and _blank(row.get("amount_krw"))
            )
            for row in rows
        ),
        "exact_duplicate_affected_rows": affected_duplicates,
        "exact_duplicate_extra_rows": extra_duplicates,
    }


def _numeric_profile(values: pd.Series) -> dict[str, int]:
    numeric = pd.to_numeric(values, errors="coerce")
    return {
        "null_or_invalid": int(numeric.isna().sum()),
        "negative": int(numeric.lt(0).sum()),
        "zero": int(numeric.eq(0).sum()),
        "positive": int(numeric.gt(0).sum()),
    }


def _sales_profile(
    sales: pd.DataFrame,
    *,
    entity_code: str,
    as_of: str,
) -> dict[str, object]:
    work = sales.copy()
    work["_sku"] = work["상품코드"].astype(str).str.strip()
    work["_date"] = pd.to_datetime(work["출고일"], errors="coerce")
    work["_qty"] = pd.to_numeric(work["수량"], errors="coerce")
    amount_col = "환산금액" if "환산금액" in work.columns else "금액"
    work["_amount"] = pd.to_numeric(work[amount_col], errors="coerce")
    work["_biz"] = work.get("Biz Type", pd.Series("", index=work.index)).astype(str).str.strip().str.upper()

    window = completed_week_window(as_of)
    period_mask = work["_date"].dt.date.between(window.period_start, window.period_end)
    period = work.loc[period_mask].copy()
    filtered = filter_sales_by_biz_type(work, {"entity_code": entity_code})
    eligible = period.loc[period.index.isin(filtered.index)].copy()
    excluded = period.loc[~period.index.isin(filtered.index)].copy()
    present_weeks = set(
        period["_date"].dropna().dt.date.map(lambda value: value - pd.Timedelta(days=value.weekday())).tolist()
    )
    expected_weeks = set(window.week_starts)

    negative = eligible.loc[eligible["_amount"] < 0].copy()
    positive = eligible.loc[(eligible["_amount"] > 0) & (eligible["_qty"] > 0)].copy()
    positive_pairs = (
        positive.assign(
            _amount_abs=positive["_amount"].round(6),
            _qty_abs=positive["_qty"].abs().round(6),
        )
        .groupby(["_sku", "_amount_abs", "_qty_abs"])
        .size()
        .rename("positive_count")
    )
    negative_pairs = (
        negative.assign(
            _amount_abs=negative["_amount"].abs().round(6),
            _qty_abs=negative["_qty"].abs().round(6),
        )
        .groupby(["_sku", "_amount_abs", "_qty_abs"])
        .size()
        .rename("negative_count")
    )
    matched = positive_pairs.to_frame().join(negative_pairs, how="inner")
    matched_negative_rows = int(matched[["positive_count", "negative_count"]].min(axis=1).sum())

    excluded_groups = (
        excluded.groupby("_biz", dropna=False)
        .agg(rows=("_biz", "size"), qty=("_qty", "sum"), revenue=("_amount", "sum"))
        .sort_values("rows", ascending=False)
        .head(10)
        .reset_index()
    )
    top_excluded = [
        {
            "biz_type": str(row["_biz"]),
            "rows": int(row["rows"]),
            "qty": round(float(row["qty"]), 2),
            "revenue": round(float(row["revenue"]), 2),
        }
        for _, row in excluded_groups.iterrows()
    ]

    return {
        "period_start": window.period_start.isoformat(),
        "period_end": window.period_end.isoformat(),
        "source_date_min": work["_date"].min().date().isoformat() if work["_date"].notna().any() else None,
        "source_date_max": work["_date"].max().date().isoformat() if work["_date"].notna().any() else None,
        "future_dated_rows": int((work["_date"].dt.date > date.fromisoformat(as_of)).sum()),
        "invalid_date_rows": int(work["_date"].isna().sum()),
        "period_rows": int(len(period)),
        "period_skus": int(period["_sku"].nunique()),
        "missing_completed_weeks": sorted(value.isoformat() for value in expected_weeks - present_weeks),
        "quantity": _numeric_profile(period["_qty"]),
        "revenue": _numeric_profile(period["_amount"]),
        "missing_biz_type_rows": int(period["_biz"].eq("").sum()),
        "distinct_biz_types": int(period["_biz"].nunique()),
        "v1_eligible_rows": int(len(eligible)),
        "v1_excluded_rows": int(len(excluded)),
        "v1_excluded_row_pct": _pct(len(excluded), len(period)),
        "v1_excluded_qty": round(float(excluded["_qty"].sum()), 2),
        "v1_excluded_qty_pct": _pct(float(excluded["_qty"].sum()), float(period["_qty"].sum())),
        "v1_excluded_revenue": round(float(excluded["_amount"].sum()), 2),
        "v1_excluded_revenue_pct": _pct(
            float(excluded["_amount"].sum()), float(period["_amount"].sum())
        ),
        "top_excluded_biz_types": top_excluded,
        "eligible_negative_amount_rows": int(len(negative)),
        "eligible_negative_amount_skus": int(negative["_sku"].nunique()),
        "negative_amount_with_positive_qty_rows": int(
            ((negative["_qty"] > 0) & (negative["_amount"] < 0)).sum()
        ),
        "exact_reversal_candidate_rows": matched_negative_rows,
        "exact_reversal_candidate_pct": _pct(matched_negative_rows, len(negative)),
        "eligible_skus": sorted(set(eligible["_sku"]) - {""}),
    }


def _stock_profile(stock: pd.DataFrame, *, include_price: bool) -> dict[str, object]:
    work = stock.copy()
    work["_sku"] = work["상품코드"].astype(str).str.strip()
    result: dict[str, object] = {
        "rows": int(len(work)),
        "skus": int(work["_sku"].nunique()),
        "blank_sku_rows": int(work["_sku"].eq("").sum()),
        "duplicate_sku_extra_rows": int(work["_sku"].duplicated(keep="first").sum()),
    }
    available_col = "EU 현지 가용수량" if "EU 현지 가용수량" in work.columns else "본사 EU창고 가용수량"
    result["available_qty"] = _numeric_profile(work[available_col])
    if include_price:
        result["unit_cost"] = _numeric_profile(work["현지 입고단가"])
        result["currency_values"] = sorted(
            value for value in work["현지 입고단가 통화"].astype(str).str.strip().unique() if value
        )
    result["sku_set"] = sorted(set(work["_sku"]) - {""})
    return result


def _quantity_source_profile(frame: pd.DataFrame, sku_col: str, qty_col: str) -> dict[str, object]:
    work = frame.copy()
    work["_sku"] = work[sku_col].astype(str).str.strip()
    return {
        "rows": int(len(work)),
        "skus": int(work["_sku"].nunique()),
        "blank_sku_rows": int(work["_sku"].eq("").sum()),
        "quantity": _numeric_profile(work[qty_col]),
        "sku_set": sorted(set(work["_sku"]) - {""}),
    }


def _coverage(child: set[str], parents: set[str]) -> dict[str, object]:
    missing = child - parents
    return {
        "child_skus": len(child),
        "matched_skus": len(child) - len(missing),
        "missing_skus": len(missing),
        "match_pct": _pct(len(child) - len(missing), len(child)),
    }


def _generic_lead_time_stats(
    rows: list[dict[str, object]],
    *,
    as_of: str,
) -> dict[str, object]:
    completion_from, completion_to, api_from = lead_time_query_window(as_of)
    mode_map = {
        "AIR": "AIR",
        "항공": "AIR",
        "SEA": "SEA",
        "해운": "SEA",
        "RAIL": "RAIL",
        "철송": "RAIL",
        "TRUCK": "TRUCK",
        "트럭": "TRUCK",
    }
    grouped: dict[str, set[tuple[str, date, date, int]]] = {}
    completed_rows = 0
    missing_packing = 0
    invalid_rows = 0
    for row in rows:
        completed = _parsed_date(row.get("iw_dt"))
        if completed is None or not completion_from <= completed <= completion_to:
            continue
        completed_rows += 1
        packing = str(row.get("pckg_no") or "").strip()
        if not packing:
            missing_packing += 1
            continue
        shipped = _parsed_date(row.get("ow_dt"))
        mode_raw = str(row.get("transport_mode") or "").strip().upper().replace(" ", "")
        mode = mode_map.get(mode_raw)
        duration = _number(row.get("ow_to_iw_days"))
        if (
            shipped is None
            or mode is None
            or duration is None
            or not duration.is_integer()
            or not 1 <= int(duration) <= 180
        ):
            invalid_rows += 1
            continue
        grouped.setdefault(packing, set()).add((mode, shipped, completed, int(duration)))

    samples: dict[str, list[int]] = {mode: [] for mode in ("AIR", "SEA", "RAIL", "TRUCK")}
    conflicts = 0
    for values in grouped.values():
        if len(values) != 1:
            conflicts += 1
            continue
        mode, _shipped, _completed, duration = next(iter(values))
        samples[mode].append(duration)
    mode_stats = {}
    for mode, values in samples.items():
        mode_stats[mode] = {
            "sample_size": len(values),
            "mean_days": round(fmean(values), 4) if values else None,
            "stdev_days": round(stdev(values), 4) if len(values) >= 2 else None,
            "sigma_weeks": round(stdev(values) / 7.0, 4) if len(values) >= 2 else None,
        }
    return {
        "api_date_from": api_from.isoformat(),
        "api_date_to": completion_to.isoformat(),
        "completion_date_from": completion_from.isoformat(),
        "completion_date_to": completion_to.isoformat(),
        "fetched_rows": len(rows),
        "completed_rows": completed_rows,
        "missing_packing_rows": missing_packing,
        "invalid_rows": invalid_rows,
        "conflicting_packings": conflicts,
        "accepted_packings": sum(len(values) for values in samples.values()),
        "modes": mode_stats,
    }


def _entity_profile(entity_code: str, as_of: str) -> dict[str, object]:
    raw, cache = _fetch_fresh_cms_source(as_of, entity_code=entity_code)
    typed_raw = {key: list(value) for key, value in raw.items() if isinstance(value, list)}
    uploaded = build_uploaded_data_from_cms(typed_raw, entity_code=entity_code)

    endpoint_profiles = [
        _endpoint_profile(name, typed_raw.get(name, []))
        for name in REQUIRED_FIELDS
    ]
    sales = _sales_profile(uploaded["sales_detail"], entity_code=entity_code, as_of=as_of)
    local_stock = _stock_profile(uploaded["eu_stock"], include_price=True)
    hq_stock = _stock_profile(uploaded["hq_eu_stock"], include_price=False)
    shipping = _quantity_source_profile(uploaded["shipping"], "상품코드", "수량")
    open_po = _quantity_source_profile(uploaded["open_po"], "상품코드", "미입고 수량")

    sales_skus = set(sales.pop("eligible_skus"))
    local_skus = set(local_stock.pop("sku_set"))
    hq_skus = set(hq_stock.pop("sku_set"))
    shipping_skus = set(shipping.pop("sku_set"))
    open_po_skus = set(open_po.pop("sku_set"))

    try:
        build_order_logic_v2_source(
            typed_raw,
            as_of=as_of,
            entity_code=entity_code,
        )
        current_v2_status = {"status": "ready", "error": None}
    except Exception as exc:  # noqa: BLE001 - quality report needs normalized evidence
        current_v2_status = {"status": "blocked", "error": str(exc)}

    _completion_from, completion_to, api_from = lead_time_query_window(as_of)
    try:
        lead_rows = fetch_cms_lead_time(
            entity_code,
            date_from=api_from.isoformat(),
            date_to=completion_to.isoformat(),
            include_in_transit=False,
        )
        lead_time = _generic_lead_time_stats(lead_rows, as_of=as_of)
        if entity_code == "USA":
            official = aggregate_lead_time_rows(lead_rows, as_of=as_of).as_dict()
            lead_time["official_v2_aggregation"] = official
        lead_time["api_status"] = "ready"
    except Exception as exc:  # noqa: BLE001
        lead_time = {"api_status": "blocked", "error": str(exc)}

    return {
        "entity_code": entity_code,
        "cache": {
            "created_at": cache.get("created_at"),
            "age_seconds": round(float(cache.get("age_seconds") or 0), 2),
            "within_24h": float(cache.get("age_seconds") or 0) <= 86400,
        },
        "endpoints": endpoint_profiles,
        "sales": sales,
        "local_stock": local_stock,
        "hq_stock": hq_stock,
        "shipping": shipping,
        "open_po": open_po,
        "integrity": {
            "sales_to_local_stock": _coverage(sales_skus, local_skus),
            "sales_to_any_stock": _coverage(sales_skus, local_skus | hq_skus),
            "shipping_to_any_stock": _coverage(shipping_skus, local_skus | hq_skus),
            "open_po_to_any_stock": _coverage(open_po_skus, local_skus | hq_skus),
        },
        "current_v2_source_status": current_v2_status,
        "lead_time": lead_time,
    }


def _issue_rows(results: dict[str, object]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for entity_code, profile in results["entities"].items():
        sales = profile["sales"]
        status = profile["current_v2_source_status"]
        local = profile["local_stock"]
        integrity = profile["integrity"]
        lead = profile["lead_time"]
        endpoints = {row["endpoint"]: row for row in profile["endpoints"]}
        if status["status"] == "blocked":
            issues.append(
                {
                    "entity": entity_code,
                    "severity": "Critical",
                    "check": "V2 source build",
                    "evidence": status["error"],
                    "risk": "해당 법인의 V2 전체 계산이 중단됨",
                    "action": "Biz Type 필터 후 음수 거래 정규화 규칙 적용",
                }
            )
        if sales["v1_excluded_rows"]:
            issues.append(
                {
                    "entity": entity_code,
                    "severity": "High" if (sales["v1_excluded_qty_pct"] or 0) >= 1 else "Medium",
                    "check": "Biz Type consistency",
                    "evidence": (
                        f"V1 제외 {sales['v1_excluded_rows']:,}행, "
                        f"수량 비중 {sales['v1_excluded_qty_pct']:.2f}%"
                    ),
                    "risk": "V1과 V2 수요 모집단 불일치",
                    "action": "V2에서 공통 filter_sales_by_biz_type 재사용",
                }
            )
        sales_duplicates = endpoints["sales_local"]["exact_duplicate_extra_rows"]
        if sales_duplicates:
            issues.append(
                {
                    "entity": entity_code,
                    "severity": "Medium",
                    "check": "Exact duplicate local sales rows",
                    "evidence": f"완전 동일 중복 초과 행 {sales_duplicates:,}건",
                    "risk": "거래 행이 실제 중복이면 주간 수요와 순매출이 이중 집계됨",
                    "action": "Invoice/원전표/라인 식별자로 정상 복수행과 중복 적재를 구분",
                }
            )
        shipping_duplicates = endpoints["shipping"]["exact_duplicate_extra_rows"]
        if shipping_duplicates:
            issues.append(
                {
                    "entity": entity_code,
                    "severity": "Medium",
                    "check": "Exact duplicate shipping rows",
                    "evidence": f"완전 동일 중복 초과 행 {shipping_duplicates:,}건",
                    "risk": "실제 중복이면 운송중수량이 이중 집계됨",
                    "action": "Packing No와 상품 라인 키로 중복 여부 확인",
                }
            )
        unit_cost = local.get("unit_cost", {})
        no_positive_price = int(unit_cost.get("null_or_invalid", 0)) + int(unit_cost.get("zero", 0)) + int(unit_cost.get("negative", 0))
        if no_positive_price:
            issues.append(
                {
                    "entity": entity_code,
                    "severity": "Medium",
                    "check": "Local unit cost completeness",
                    "evidence": f"양수 stock_ucost 미확보 {no_positive_price:,} SKU/행",
                    "risk": "발주수량은 계산돼도 제안금액이 0 또는 미계산될 수 있음",
                    "action": "0·누락 단가를 확인 필요로 표시하고 판매단가 fallback 금지",
                }
            )
        coverage = integrity["sales_to_local_stock"]
        if coverage["missing_skus"]:
            issues.append(
                {
                    "entity": entity_code,
                    "severity": "Medium",
                    "check": "Sales-to-local-stock coverage",
                    "evidence": f"판매 SKU 중 현지재고 미연결 {coverage['missing_skus']:,}개 ({100-(coverage['match_pct'] or 0):.2f}%)",
                    "risk": "재고·입고단가 없이 수요만 존재하는 SKU 발생",
                    "action": "미연결 SKU를 별도 검증 큐로 노출",
                }
            )
        negative_open_po = int(profile["open_po"]["quantity"]["negative"])
        if negative_open_po:
            issues.append(
                {
                    "entity": entity_code,
                    "severity": "High",
                    "check": "Negative open-PO quantity",
                    "evidence": f"음수 미입고수량 {negative_open_po:,}행",
                    "risk": "해당 SKU는 V2 입력 검증에서 계산불가 처리됨",
                    "action": "취소·감액 전표 여부를 구분하고 원천 open_qty 의미를 확정",
                }
            )
        for label, key in (("Shipping-to-stock coverage", "shipping_to_any_stock"), ("Open-PO-to-stock coverage", "open_po_to_any_stock")):
            link = integrity[key]
            missing_pct = 100.0 - float(link["match_pct"] or 0)
            if link["missing_skus"]:
                issues.append(
                    {
                        "entity": entity_code,
                        "severity": "High" if missing_pct >= 5 else "Medium",
                        "check": label,
                        "evidence": f"재고마스터 미연결 {link['missing_skus']:,} SKU ({missing_pct:.2f}%)",
                        "risk": "수량은 존재하지만 재고·상품·단가 정보가 불완전함",
                        "action": "법인 재고마스터와 상품코드 등록 상태를 대조",
                    }
                )
        if lead.get("api_status") != "ready":
            issues.append(
                {
                    "entity": entity_code,
                    "severity": "Critical",
                    "check": "Lead-time API",
                    "evidence": str(lead.get("error") or "조회 실패"),
                    "risk": "법인별 리드타임 및 표준편차 계산 불가",
                    "action": "API 조회·필드·표본 요건 복구 후 계산 재개",
                }
            )
        elif entity_code == "PL":
            issues.append(
                {
                    "entity": entity_code,
                    "severity": "High",
                    "check": "EU lead-time integration",
                    "evidence": "EU 리드타임 API는 조회되지만 현행 V2 서비스는 USA만 동적 반영",
                    "risk": "EU가 최신 API 표본 대신 고정 리드타임·표준편차를 사용",
                    "action": "EU RAIL·SEA 표본 집계를 V2 설정과 감사정보에 연결",
                }
            )
        if lead.get("api_status") == "ready":
            accepted = int(lead.get("accepted_packings") or 0)
            conflicts = int(lead.get("conflicting_packings") or 0)
            conflict_pct = _pct(conflicts, accepted + conflicts) or 0.0
            if conflicts:
                issues.append(
                    {
                        "entity": entity_code,
                        "severity": "Medium" if conflict_pct >= 5 else "Low",
                        "check": "Lead-time packing conflicts",
                        "evidence": f"충돌 Packing {conflicts:,}건 ({conflict_pct:.2f}%)",
                        "risk": "해당 Packing은 표본에서 제외되어 평균·표준편차 표본이 감소함",
                        "action": "Packing별 운송모드·출고일·입고일 충돌 원천을 점검",
                    }
                )
    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return sorted(issues, key=lambda row: (severity_order[row["severity"]], row["entity"], row["check"]))


def run_checks(as_of: str = "2026-08-05") -> dict[str, object]:
    entities = {
        entity: _entity_profile(entity, as_of)
        for entity in ("USA", "PL")
    }
    result: dict[str, object] = {
        "as_of": as_of,
        "scope": "Order Analysis V2 CMS sources and entity lead-time APIs",
        "entities": entities,
    }
    result["issues"] = _issue_rows(result)
    result["summary"] = {
        "critical": sum(row["severity"] == "Critical" for row in result["issues"]),
        "high": sum(row["severity"] == "High" for row in result["issues"]),
        "medium": sum(row["severity"] == "Medium" for row in result["issues"]),
        "low": sum(row["severity"] == "Low" for row in result["issues"]),
        "entities_ready": sum(
            profile["current_v2_source_status"]["status"] == "ready"
            for profile in entities.values()
        ),
        "entities_checked": len(entities),
    }
    return result


if __name__ == "__main__":
    print(json.dumps(run_checks(), ensure_ascii=False, indent=2))
