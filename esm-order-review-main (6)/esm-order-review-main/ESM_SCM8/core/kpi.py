from __future__ import annotations

import os
import logging
import re
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from core.session import SessionContext, ensure_session_context
from core.exchange_rate import warn_if_fallback_rate_stale

from core.common import (
    _DEFAULT_EUR_KRW_RATE,
    _EU_STOCK_AMOUNT_CANDIDATES,
    _HQ_STOCK_EUR_VALUE_CANDIDATES,
    _HQ_STOCK_EXPLICIT_EUR_VALUE_CANDIDATES,
    _HQ_STOCK_HOLD_CANDIDATES,
    _HQ_STOCK_PRICE_CANDIDATES,
    _HQ_STOCK_QTY_CANDIDATES,
    _KRW_LIKE_UNIT_PRICE_THRESHOLD,
    _SEA_CONTAINER_EUR_CANDIDATES,
    COLORS,
    EU_LOCAL_STOCK_UNIT_PRICE_CURRENCY,
    HQ_EU_STOCK_UNIT_PRICE_CURRENCY,
    korea_now,
    korea_today,
    KST,
)
import warnings
from core import inventory as inventory_mod, loaders as loaders_mod, order_review as order_review_mod, preprocess as preprocess_mod, sales as sales_mod, validation as validation_mod

logger = logging.getLogger(__name__)
_TRUSTSTORE_INJECTED = False


@dataclass(frozen=True)
class EximKrwRate:
    """One Korea Eximbank quote normalized to KRW per one currency unit."""

    currency_code: str
    quote_unit: str
    quote_krw: Decimal
    krw_per_unit: Decimal
    rate_date: str


def _ensure_system_trust_store() -> None:
    """Use the OS certificate store when available, especially on Windows."""
    global _TRUSTSTORE_INJECTED
    if _TRUSTSTORE_INJECTED:
        return
    _TRUSTSTORE_INJECTED = True
    try:
        import truststore
    except ImportError:
        return
    try:
        truststore.inject_into_ssl()
    except Exception:
        logger.debug("Could not inject system trust store for exchange-rate lookup.")


def _normalize_exim_quote(item: object, requested_currencies: set[str], rate_date: date) -> EximKrwRate | None:
    """Parse one Eximbank quote, including quotations such as ``JPY(100)``.

    Eximbank publishes a few currencies per 100 units.  The returned
    ``krw_per_unit`` is always for a single unit, so callers can use one
    consistent multiplication rule without making a 100x JPY/IDR mistake.
    """

    if not isinstance(item, dict):
        return None
    raw_unit = str(item.get("cur_unit") or "").strip().upper()
    match = re.fullmatch(r"([A-Z]{3})(?:\((\d+)\))?", raw_unit)
    if match is None:
        return None
    currency_code = match.group(1)
    if currency_code not in requested_currencies:
        return None
    unit_count = Decimal(match.group(2) or "1")
    if unit_count <= 0:
        return None
    try:
        quote_krw = Decimal(str(item.get("deal_bas_r") or "").replace(",", ""))
    except InvalidOperation:
        return None
    if not quote_krw.is_finite() or quote_krw <= 0:
        return None
    return EximKrwRate(
        currency_code=currency_code,
        quote_unit=raw_unit,
        quote_krw=quote_krw,
        krw_per_unit=quote_krw / unit_count,
        rate_date=rate_date.isoformat(),
    )


def get_exim_currency_krw_rates(currency_codes: set[str]) -> dict[str, EximKrwRate]:
    """Get the latest available Eximbank KRW quotes for several currencies.

    All requested currencies are read from each Eximbank response together.
    This avoids one network request per destination currency and deliberately
    provides no fallback rate: callers that need a current authoritative
    aggregate can fail safely when a quote is unavailable.
    """

    currencies = {str(code or "").strip().upper() for code in currency_codes}
    currencies.discard("")
    if not currencies:
        return {}
    if any(re.fullmatch(r"[A-Z]{3}", currency) is None for currency in currencies):
        raise ValueError("환율 통화 코드 형식이 올바르지 않습니다.")

    api_key = os.environ.get("KOREAEXIM_API_KEY", "").strip()
    if not api_key:
        return {}

    url = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
    _ensure_system_trust_store()
    remaining = set(currencies)
    rates: dict[str, EximKrwRate] = {}
    try:
        for days_back in range(0, 10):
            if not remaining:
                break
            rate_date = korea_today() - timedelta(days=days_back)
            response = requests.get(
                url,
                params={
                    "authkey": api_key,
                    "searchdate": rate_date.strftime("%Y%m%d"),
                    "data": "AP01",
                },
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                continue
            for item in payload:
                quote = _normalize_exim_quote(item, remaining, rate_date)
                if quote is not None:
                    rates[quote.currency_code] = quote
                    remaining.discard(quote.currency_code)
    except Exception:
        return rates
    return rates


def get_currency_krw_rate(
    currency_code: str,
    default_rate: float = 0.0,
) -> tuple[float, str, bool]:
    """Return one foreign-currency/KRW rate from Korea Eximbank.

    A caller-supplied fallback is returned on failure.  No non-EUR fallback is
    invented because the repository only has an approved EUR legacy default.
    """
    currency = str(currency_code or "").strip().upper()
    if currency not in {"EUR", "USD"}:
        raise ValueError(f"지원하지 않는 환율 통화입니다: {currency or '(empty)'}")
    api_key = os.environ.get("KOREAEXIM_API_KEY", "").strip()
    if not api_key:
        if currency == "EUR":
            warn_if_fallback_rate_stale(logger)
        return default_rate, "", False

    url = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
    _ensure_system_trust_store()
    try:
        for days_back in range(0, 10):
            rate_date = korea_today() - timedelta(days=days_back)
            params = {
                "authkey": api_key,
                "searchdate": rate_date.strftime("%Y%m%d"),
                "data": "AP01",
            }
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                continue
            for item in data:
                if item.get("cur_unit") == currency:
                    raw_rate = str(item.get("deal_bas_r", "")).replace(",", "")
                    return float(raw_rate), rate_date.isoformat(), True
        if currency == "EUR":
            warn_if_fallback_rate_stale(logger)
        return default_rate, "", False
    except Exception:
        if currency == "EUR":
            warn_if_fallback_rate_stale(logger)
        return default_rate, "", False


def get_eur_krw_rate(default_rate: float = _DEFAULT_EUR_KRW_RATE) -> tuple[float, str, bool]:
    """Backward-compatible EUR/KRW lookup."""
    return get_currency_krw_rate("EUR", default_rate)


_rate_lookup_cache: dict[str, tuple[date, tuple[float, str, bool]]] = {}
_rate_lookup_cache_lock = threading.Lock()


def get_cached_currency_krw_rate(
    currency_code: str,
    default_rate: float = 0.0,
) -> tuple[float, str, bool]:
    """Day-scoped in-process cache around get_currency_krw_rate.

    get_currency_krw_rate makes up to 10 sequential Korea Eximbank requests
    (5s timeout each) before falling back, so callers that invoke it on every
    click (e.g. order-logic-v2 Excel export) can block for tens of seconds.
    Caching per KST day, per currency avoids repeating that lookup — including
    the failure case, so a down API is only retried once per day per process.
    """
    currency = str(currency_code or "").strip().upper()
    today = korea_today()
    with _rate_lookup_cache_lock:
        cached = _rate_lookup_cache.get(currency)
        if cached is not None and cached[0] == today:
            return cached[1]
    result = get_currency_krw_rate(currency, default_rate)
    with _rate_lookup_cache_lock:
        _rate_lookup_cache[currency] = (today, result)
    return result


def get_cached_eur_krw_rate(default_rate: float = _DEFAULT_EUR_KRW_RATE) -> tuple[float, str, bool]:
    """Backward-compatible, day-cached EUR/KRW lookup."""
    return get_cached_currency_krw_rate("EUR", default_rate)


def is_uploaded_data_mode(context: SessionContext | None = None) -> bool:
    return any(df is not None for df in ensure_session_context(context).uploaded_data.values())


def calculate_day_over_day_rate(today_value: float, previous_value: float | None) -> float | None:
    if previous_value in (None, 0):
        return None
    return (today_value - previous_value) / previous_value * 100


def format_day_over_day_delta(today_value: float, previous_value: float | None) -> str:
    rate = calculate_day_over_day_rate(today_value, previous_value)
    if rate is None:
        return "-"
    arrow = "▲" if rate > 0 else "▼" if rate < 0 else ""
    return f"{arrow}{abs(rate):.1f}%"


def normalize_to_million_krw(value: float) -> float:
    """업로드 금액이 원 단위로 들어오면 M 원 단위로 보정한다."""
    value = float(value or 0)
    return value / 1_000_000 if abs(value) >= 10_000_000 else value


def format_money_readable(value: float) -> str:
    million_krw = normalize_to_million_krw(value)
    abs_value = abs(million_krw)
    if abs_value >= 100:
        return f"{million_krw:,.0f}M 원 / 약 {million_krw / 100:,.0f}억"
    if abs_value >= 1:
        return f"{million_krw * 100:,.0f}만 원"
    return f"{million_krw:,.0f}M 원"


def format_kpi_value(value: float, unit: str) -> str:
    if unit == "M 원":
        return format_money_readable(value)
    return f"{value:,.0f}{unit}"


def format_eok_from_million(value: float) -> str:
    million = float(value or 0)
    if abs(million) < 100:
        return f"{million:,.1f}M 원" if abs(million) < 10 and million != 0 else f"{million:,.0f}M 원"
    return f"약 {million / 100:,.0f}억 원"


def kpi_history_scope(settings: dict | None = None) -> str:
    if settings is None:
        return "전체"
    parts = [
        f"brand={settings.get('brand', '전체')}",
        f"demand={settings.get('demand_source', '재고파일 PA+CA 판매수량 기준')}",
        f"sample_excluded={settings.get('exclude_sample', True)}",
        f"discontinued_excluded={settings.get('exclude_discontinued', True)}",
        f"po_included={settings.get('include_inbound_po_in_coverage', False)}",
    ]
    return "|".join(parts)


def load_previous_kpi_history(base_date: date, settings: dict | None = None, history_path: str = "daily_kpi_history.csv") -> dict[str, float]:
    """Placeholder: daily_kpi_history.csv에서 기준일 전날 KPI 요약값을 불러온다."""
    return load_kpi_history_for_date(base_date - timedelta(days=1), settings=settings, history_path=history_path)


def load_kpi_history_for_date(target_date: date, settings: dict | None = None, history_path: str = "daily_kpi_history.csv") -> dict[str, float]:
    path = Path(history_path)
    if not path.exists():
        return {}

    history = pd.read_csv(path)
    if "base_date" not in history.columns:
        return {}

    history["base_date"] = pd.to_datetime(history["base_date"], errors="coerce").dt.date
    target_rows = history[history["base_date"] == target_date]
    if settings is not None and "history_scope" in history.columns:
        target_rows = target_rows[target_rows["history_scope"] == kpi_history_scope(settings)]
    if target_rows.empty:
        return {}

    row = target_rows.iloc[-1]
    return {col: float(row[col]) for col in history.columns if col not in {"base_date", "history_scope"} and pd.notna(row[col])}


def save_daily_kpi_history(base_date: date, kpi_summary: dict[str, float], settings: dict | None = None, history_path: str = "daily_kpi_history.csv") -> None:
    """Placeholder: 기준일별 KPI 요약값을 daily_kpi_history.csv에 저장한다."""
    path = Path(history_path)
    new_row = {"base_date": base_date.isoformat(), "history_scope": kpi_history_scope(settings), **kpi_summary}
    if path.exists():
        history = pd.read_csv(path)
        if "history_scope" not in history.columns:
            history["history_scope"] = "legacy"
        if "base_date" in history.columns:
            history = history[
                ~(
                    history["base_date"].astype(str).eq(new_row["base_date"])
                    & history["history_scope"].astype(str).eq(new_row["history_scope"])
                )
            ]
        history = pd.concat([history, pd.DataFrame([new_row])], ignore_index=True)
    else:
        history = pd.DataFrame([new_row])
    history.to_csv(path, index=False, encoding="utf-8-sig")


def compact_column_name(value: object) -> str:
    return str(value).replace(" ", "").replace("\n", "").replace("_", "").lower()


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    compact_candidates = [compact_column_name(candidate) for candidate in candidates]
    compact_columns = {compact_column_name(col): col for col in df.columns}
    for candidate in compact_candidates:
        if candidate in compact_columns:
            return compact_columns[candidate]
    for compact_col, original_col in compact_columns.items():
        if any(candidate in compact_col for candidate in compact_candidates):
            return original_col
    return None


def find_exact_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    compact_columns = {compact_column_name(col): col for col in df.columns}
    for candidate in candidates:
        compact_candidate = compact_column_name(candidate)
        if compact_candidate in compact_columns:
            return compact_columns[compact_candidate]
    return None


def cleaned_number_text_series(series: pd.Series) -> pd.Series:
    text = (
        series.astype(str)
        .str.replace(r"\s+", "", regex=True)
        .str.replace("원", "", regex=False)
        .str.replace("KRW", "", regex=False)
        .str.replace("krw", "", regex=False)
        .str.replace("EUR", "", regex=False)
        .str.replace("eur", "", regex=False)
        .str.replace("₩", "", regex=False)
        .str.replace("€", "", regex=False)
        .str.strip()
    )
    comma_count = text.str.count(",")
    dot_count = text.str.count(r"\.")
    last_part_after_comma = text.str.rsplit(",", n=1).str[-1].str.replace(r"[^0-9]", "", regex=True)
    comma_decimal = (
        comma_count.eq(1)
        & (
            (dot_count.eq(0) & last_part_after_comma.str.len().between(1, 2))
            | (dot_count.gt(0) & (text.str.rfind(",") > text.str.rfind(".")))
        )
    )
    normalized = text.copy()
    normalized.loc[comma_decimal] = (
        normalized.loc[comma_decimal]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    normalized.loc[~comma_decimal] = normalized.loc[~comma_decimal].str.replace(",", "", regex=False)
    return normalized


def to_number_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0)
    cleaned = cleaned_number_text_series(series)
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)


def to_unit_price_number_series(series: pd.Series) -> pd.Series:
    numeric = to_number_series(series)
    text = (
        series.astype(str)
        .str.replace(r"\s+", "", regex=True)
        .str.replace("EUR", "", regex=False)
        .str.replace("eur", "", regex=False)
        .str.replace("€", "", regex=False)
        .str.strip()
    )
    comma_decimal = (
        text.str.count(",").eq(1)
        & text.str.count(r"\.").eq(0)
        & text.str.rsplit(",", n=1).str[-1].str.replace(r"[^0-9]", "", regex=True).str.len().between(1, 3)
    )
    decimal_numeric = pd.to_numeric(text.str.replace(",", ".", regex=False), errors="coerce")
    likely_decimal_comma = comma_decimal & numeric.ge(_KRW_LIKE_UNIT_PRICE_THRESHOLD) & decimal_numeric.gt(0) & decimal_numeric.lt(_KRW_LIKE_UNIT_PRICE_THRESHOLD)
    repaired = numeric.mask(likely_decimal_comma, decimal_numeric)
    integer_like = (repaired - repaired.round()).abs().lt(1e-9)
    legacy_milli_eur = (
        ~comma_decimal
        & integer_like
        & repaired.ge(_KRW_LIKE_UNIT_PRICE_THRESHOLD)
        & (repaired / 1000).gt(0)
        & (repaired / 1000).lt(_KRW_LIKE_UNIT_PRICE_THRESHOLD)
    )
    return repaired.mask(legacy_milli_eur, repaired / 1000).fillna(0)


def unit_price_currency_from_label(label: object) -> str:
    compact = compact_column_name(label)
    if any(token in compact for token in ["krw", "won", "원"]):
        return "KRW"
    if any(token in compact for token in ["eur", "euro", "유로"]):
        return "EUR"
    return ""


def infer_unit_price_currency(price: pd.Series, source_label: object = "") -> str:
    label_currency = unit_price_currency_from_label(source_label)
    if label_currency:
        return label_currency
    positive = pd.to_numeric(price, errors="coerce").dropna()
    positive = positive[positive > 0]
    if positive.empty:
        return "EUR"
    return "KRW" if float(positive.median()) >= _KRW_LIKE_UNIT_PRICE_THRESHOLD else "EUR"


def unit_price_krw_multiplier(currency: object, eur_krw_rate: float) -> float:
    return 1.0 if str(currency).upper() == "KRW" else float(eur_krw_rate)


def unit_price_eur_divisor(currency: object, eur_krw_rate: float) -> float:
    return float(eur_krw_rate) if str(currency).upper() == "KRW" and float(eur_krw_rate) > 0 else 1.0


def number_conversion_failure_count(series: pd.Series) -> int:
    cleaned = cleaned_number_text_series(series)
    numeric = pd.to_numeric(cleaned, errors="coerce")
    meaningful = series.notna() & ~cleaned.str.lower().isin({"", "nan", "none", "-"})
    return int((meaningful & numeric.isna()).sum())


def numeric_column_sum(df: pd.DataFrame, candidates: list[str]) -> float:
    col = find_column(df, candidates)
    if col is None:
        return 0.0
    return float(to_number_series(df[col]).sum())


def numeric_column_sum_with_source(df: pd.DataFrame, candidates: list[str]) -> tuple[float, str | None]:
    col = find_column(df, candidates)
    if col is None:
        return 0.0, None
    return float(to_number_series(df[col]).sum()), col


def parse_date_series(series: pd.Series) -> pd.Series:
    """Parse common upload date shapes, including Excel serial dates."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Could not infer format.*", category=UserWarning)
        parsed = pd.to_datetime(series, errors="coerce")
    numeric_values = pd.to_numeric(series, errors="coerce")
    excel_serial_mask = numeric_values.between(20_000, 80_000)
    if excel_serial_mask.any():
        excel_dates = pd.to_datetime(numeric_values[excel_serial_mask], unit="D", origin="1899-12-30", errors="coerce")
        parsed.loc[excel_serial_mask] = excel_dates
    return parsed


def largest_amount_like_sum(df: pd.DataFrame, include_keywords: list[str], exclude_keywords: list[str] | None = None) -> float:
    exclude_keywords = exclude_keywords or []
    best = 0.0
    for col in df.columns:
        compact = compact_column_name(col)
        if not any(keyword in compact for keyword in include_keywords):
            continue
        if any(keyword in compact for keyword in exclude_keywords):
            continue
        total = float(to_number_series(df[col]).sum())
        if total > best:
            best = total
    return best


def eu_stock_amount_column_sum(df: pd.DataFrame) -> float:
    amount, _ = eu_stock_amount_column_sum_with_source(df)
    return amount


def eu_stock_amount_column_sum_with_source(df: pd.DataFrame) -> tuple[float, str]:
    # 지정된 후보 컬럼을 우선순위 순서대로 탐색한다.
    col = find_column(df, _EU_STOCK_AMOUNT_CANDIDATES)
    if col is not None:
        return float(to_number_series(df[col]).sum()), str(col)
    return 0.0, ""


def eu_stock_amount() -> float:
    """EU 현지 재고 파일의 재고금액 컬럼 합계를 반환한다.
    수량 × 단가 방식은 사용하지 않는다."""
    raw_stock = inventory_mod.get_eu_stock()
    col = find_column(raw_stock, _EU_STOCK_AMOUNT_CANDIDATES)
    if col is None:
        return 0.0
    return float(to_number_series(raw_stock[col]).sum())


def safe_stock_quantity_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    col = find_column(df, candidates)
    if col is None:
        return None
    compact = compact_column_name(col)
    blocked = ["금액", "amount", "단가", "price", "매출", "판매"]
    return None if any(keyword in compact for keyword in blocked) else col


def stock_unit_price_krw_multiplier(
    price_col: str,
    eur_krw_rate: float,
    price_values: pd.Series | None = None,
) -> tuple[float, str]:
    currency = unit_price_currency_from_label(price_col)
    if not currency and price_values is not None:
        currency = infer_unit_price_currency(price_values, price_col)
    if currency == "KRW":
        return 1.0, "KRW 단가"
    return float(eur_krw_rate), "EUR 단가 × 환율"


def hq_eu_stock_amount_for_df_with_source(df: pd.DataFrame, eur_krw_rate: float = _DEFAULT_EUR_KRW_RATE) -> tuple[float, str]:
    explicit_eur_col = find_exact_column(df, _HQ_STOCK_EXPLICIT_EUR_VALUE_CANDIDATES)
    if explicit_eur_col is not None:
        amount_eur = float(to_number_series(df[explicit_eur_col]).sum())
        amount_krw = amount_eur * float(eur_krw_rate)
        return amount_krw / 1_000_000, f"{explicit_eur_col} 열 합계 × EUR/KRW 환율"

    amount, amount_col = hq_eu_stock_amount_column_sum_with_source(df)
    if amount:
        return amount / 1_000_000, f"재고금액 컬럼 {amount_col} 원화 합계"

    eur_value_col = find_exact_column(df, _HQ_STOCK_EUR_VALUE_CANDIDATES)
    if eur_value_col is not None:
        amount_eur = float(to_number_series(df[eur_value_col]).sum())
        amount_krw = amount_eur * float(eur_krw_rate)
        return amount_krw / 1_000_000, f"{eur_value_col} 열 합계 × EUR/KRW 환율"

    qty_col = safe_stock_quantity_column(df, _HQ_STOCK_QTY_CANDIDATES)
    price_col = find_column(df, _HQ_STOCK_PRICE_CANDIDATES)
    if qty_col is None or price_col is None:
        return 0.0, ""

    qty = to_number_series(df[qty_col])
    if "가용" not in compact_column_name(qty_col) and "available" not in compact_column_name(qty_col):
        hold_col = safe_stock_quantity_column(df, _HQ_STOCK_HOLD_CANDIDATES)
        if hold_col is not None:
            qty = (qty - to_number_series(df[hold_col])).clip(lower=0)

    price = to_number_series(df[price_col])
    multiplier = unit_price_krw_multiplier(HQ_EU_STOCK_UNIT_PRICE_CURRENCY, eur_krw_rate)
    price_basis = "본사 창고 평균단가 KRW"
    amount_krw = float((qty * price * multiplier).sum())
    return amount_krw / 1_000_000, f"{qty_col} × {price_col} ({price_basis})"


def hq_eu_stock_amount(
    eur_krw_rate: float = _DEFAULT_EUR_KRW_RATE,
    settings: dict | None = None,
    context: SessionContext | None = None,
) -> float:
    stock = validation_mod.apply_raw_brand_filter(inventory_mod.get_hq_eu_stock(context), settings)
    amount, source = hq_eu_stock_amount_for_df_with_source(stock, eur_krw_rate)
    if amount or source:
        return amount

    prepared = preprocess_mod.prepare_hq_eu_stock(stock)
    price_col = find_column(stock, ["EU 입고단가", "입고단가", "단가"])
    if price_col is None:
        return 0.0

    price_source = stock.copy()
    sku_col = find_column(price_source, ["상품코드", "SKU", "품목코드"])
    if sku_col is None:
        return 0.0
    price_source = price_source.rename(columns={sku_col: "상품코드", price_col: "EU 입고단가"})
    priced = prepared.merge(price_source[["상품코드", "EU 입고단가"]], on="상품코드", how="left")
    qty = pd.to_numeric(priced["본사 EU창고 가용수량"], errors="coerce").fillna(0)
    price = pd.to_numeric(priced["EU 입고단가"], errors="coerce").fillna(0)
    multiplier = unit_price_krw_multiplier(HQ_EU_STOCK_UNIT_PRICE_CURRENCY, eur_krw_rate)
    return float((qty * price * multiplier).sum()) / 1_000_000


def hq_eu_stock_amount_column_sum_with_source(df: pd.DataFrame) -> tuple[float, str]:
    col = find_column(df, _EU_STOCK_AMOUNT_CANDIDATES)
    if col is not None:
        return float(to_number_series(df[col]).sum()), str(col)
    return 0.0, ""


def hq_to_eu_shipment_amount_eur(
    base_date: date | None = None,
    settings: dict | None = None,
    context: SessionContext | None = None,
) -> float:
    """Dashboard-only MTD shipment KPI source amount from HQ-to-EU sales detail.

    The HQ-to-EU sales detail amount columns are EUR in the current business files.
    """
    sales = validation_mod.apply_raw_brand_filter(sales_mod.get_hq_to_eu_sales_detail(context), settings)
    amount_candidates = ["환산금액", "출고금액", "금액", "매출"]
    if base_date is None:
        return numeric_column_sum(sales, amount_candidates)

    ship_date_col = find_column(sales, ["출고일", "출고 일자", "일자", "date"])
    if ship_date_col is None:
        return numeric_column_sum(sales, amount_candidates)

    ship_dates = parse_date_series(sales[ship_date_col])
    if not ship_dates.notna().any():
        return numeric_column_sum(sales, amount_candidates)

    month_start = pd.Timestamp(date(base_date.year, base_date.month, 1))
    base_ts = pd.Timestamp(base_date)
    mtd_sales = sales[(ship_dates >= month_start) & (ship_dates <= base_ts)].copy()
    return numeric_column_sum(mtd_sales, amount_candidates)


def hq_to_eu_shipment_amount(
    base_date: date | None = None,
    settings: dict | None = None,
    context: SessionContext | None = None,
) -> float:
    eur_amount = hq_to_eu_shipment_amount_eur(base_date, settings=settings, context=context)
    eur_krw_rate = float((settings or {}).get("eur_krw_rate", _DEFAULT_EUR_KRW_RATE))
    return eur_amount * eur_krw_rate


def sea_container_eur_amount(context: SessionContext | None = None) -> float:
    amount, _ = sea_container_eur_amount_with_source(context=context)
    return amount


def sea_container_eur_amount_with_source(
    settings: dict | None = None,
    context: SessionContext | None = None,
) -> tuple[float, str | None]:
    raw_shipping = validation_mod.apply_raw_transport_filter(validation_mod.apply_raw_brand_filter(loaders_mod.get_data_or_sample("shipping", loaders_mod.sample_shipping, context), settings), settings)
    return numeric_column_sum_with_source(raw_shipping, _SEA_CONTAINER_EUR_CANDIDATES)


def sea_container_amount(
    eur_krw_rate: float = _DEFAULT_EUR_KRW_RATE,
    context: SessionContext | None = None,
) -> float:
    return sea_container_eur_amount(context) * eur_krw_rate


def supply_pipeline_metrics(settings: dict, context: SessionContext | None = None) -> dict[str, float]:
    hq_shipment = hq_to_eu_shipment_amount(settings.get("base_date"), settings=settings, context=context)
    hq_shipment_million = normalize_to_million_krw(hq_shipment)
    adjustment = float(settings.get("stock_adjustment_factor", 1.15))
    eur_krw_rate = float(settings.get("eur_krw_rate", _DEFAULT_EUR_KRW_RATE))
    stock_amount = hq_eu_stock_amount(eur_krw_rate, settings=settings, context=context)
    eur_amount, eur_source = sea_container_eur_amount_with_source(settings=settings, context=context)
    shipping_amount = eur_amount * eur_krw_rate
    return {
        "hq_to_eu_shipment_amount": hq_shipment,
        "eu_stock_amount": stock_amount,
        "stock_adjustment_factor": adjustment,
        "eur_krw_rate": eur_krw_rate,
        "sea_container_eur_amount": eur_amount,
        "sea_container_eur_source": eur_source or "",
        "estimated_shippable_amount": hq_shipment_million + stock_amount * adjustment,
        "sea_container_amount": shipping_amount,
    }


def order_review_kpi_counts(settings: dict, context: SessionContext | None = None) -> dict[str, int]:
    review = validation_mod.apply_order_review_filters(loaders_mod.cached_order_review_df(settings, context=context), settings)
    stockout_risk = int((pd.to_numeric(order_review_mod.report_col(review, ["발주필요수량"], 0), errors="coerce").fillna(0) > 0).sum())
    pre_arrival_stockout = int(order_review_mod.report_col(review, ["입고 전 결품 위험 여부"], "N").astype(str).eq("Y").sum())
    return {
        "stockout_risk_sku": stockout_risk,
        "pre_arrival_stockout_sku": pre_arrival_stockout,
    }


def current_kpi_summary(settings: dict, context: SessionContext | None = None) -> dict[str, float]:
    metrics = supply_pipeline_metrics(settings, context=context)
    counts = order_review_kpi_counts(settings, context=context)
    return {
        "shipment_amount": metrics["hq_to_eu_shipment_amount"],
        "hq_to_eu_shipment_amount": metrics["hq_to_eu_shipment_amount"],
        "eu_stock_amount": metrics["eu_stock_amount"],
        "estimated_shippable_amount": metrics["estimated_shippable_amount"],
        "sea_container_amount": metrics["sea_container_amount"],
        "stockout_risk_sku": counts["stockout_risk_sku"],
        "pre_arrival_stockout_sku": counts["pre_arrival_stockout_sku"],
    }


def sample_kpi_values() -> list[dict]:
    return [
        {"key": "shipment_amount", "title": "유럽법인향 출고금액", "value": 5257, "previous": 5218, "unit": "M 원", "color": COLORS["blue"], "icon": "📈", "basis": ""},
        {"key": "eu_stock_amount", "title": "본사 EU창고 재고금액", "value": 11490, "previous": 11380, "unit": "M 원", "color": COLORS["green"], "icon": "🏠", "basis": ""},
        {"key": "estimated_shippable_amount", "title": "출고 가능 예상금액", "value": 21700, "previous": 21380, "unit": "M 원", "color": COLORS["blue"], "icon": "Σ", "basis": ""},
        {"key": "sea_container_amount", "title": "운송중 도착 예정 금액", "value": 90249, "previous": 89400, "unit": "M 원", "color": COLORS["orange"], "icon": "🚢", "basis": ""},
        {"key": "stockout_risk_sku", "title": "발주필요 SKU", "value": 128, "previous": 132, "unit": "개", "color": COLORS["red"], "icon": "⚠️", "basis": "발주 검토 결과의 발주필요수량 > 0 SKU"},
        {"key": "pre_arrival_stockout_sku", "title": "입고 전 품절위험 SKU", "value": 36, "previous": 41, "unit": "개", "color": COLORS["red"], "icon": "📅", "basis": "입고 전 품절 여부=Y SKU"},
    ]


def build_kpi_cards(settings: dict, context: SessionContext | None = None) -> tuple[list[tuple], dict[str, float]]:
    uploaded_mode = is_uploaded_data_mode(context)
    previous_history = load_previous_kpi_history(settings["base_date"], settings=settings) if uploaded_mode else {}
    metrics = supply_pipeline_metrics(settings, context=context)
    counts = order_review_kpi_counts(settings, context=context)
    current_values: dict[str, float] = {
        "shipment_amount": metrics["hq_to_eu_shipment_amount"],
        "hq_to_eu_shipment_amount": metrics["hq_to_eu_shipment_amount"],
        "eu_stock_amount": metrics["eu_stock_amount"],
        "estimated_shippable_amount": metrics["estimated_shippable_amount"],
        "sea_container_amount": metrics["sea_container_amount"],
        "stockout_risk_sku": counts["stockout_risk_sku"],
        "pre_arrival_stockout_sku": counts["pre_arrival_stockout_sku"],
    }
    cards = []

    for item in sample_kpi_values():
        if item["key"] == "estimated_shippable_amount":
            item = {**item, "title": f'{settings["base_date"].month}월 출고 가능 예상금액'}
        today_value = current_values.get(item["key"], item["value"])
        previous_value = previous_history.get(item["key"]) if uploaded_mode else item["previous"]
        if item["key"] == "shipment_amount" and uploaded_mode:
            previous_value = previous_history.get("hq_to_eu_shipment_amount", previous_value)
        if item["key"] == "sea_container_amount" and uploaded_mode:
            previous_value = previous_history.get("sea_container_amount", previous_value)
        value = format_kpi_value(today_value, item["unit"])
        if previous_value is None:
            previous = "전일 데이터 없음"
            delta = "-"
        else:
            previous = f'전일 {format_kpi_value(previous_value, item["unit"])}'
            delta = format_day_over_day_delta(today_value, previous_value)
        basis = item.get("basis", "")
        cards.append((item["title"], value, previous, delta, item["color"], item["icon"], basis))

    return cards, current_values


def format_amount(value: float) -> str:
    return format_money_readable(value)


def fmt_krw(amount: object) -> str:
    amount = 0 if amount is None or pd.isna(amount) else float(amount)
    if amount >= 1e8:
        return f"약 {amount / 1e8:.1f}억 원"
    if amount >= 1e7:
        return f"약 {amount / 1e7:.1f}천만 원"
    if amount >= 1e6:
        return f"약 {amount / 1e6:.0f}백만 원"
    return f"{amount:,.0f}원"


def fmt_krw_compact(amount: object) -> str:
    amount = 0 if amount is None or pd.isna(amount) else float(amount)
    if amount >= 1e8:
        return f"{amount / 1e8:,.1f}억"
    if amount >= 1e4:
        return f"{amount / 1e4:,.0f}만"
    return f"{amount:,.0f}"
