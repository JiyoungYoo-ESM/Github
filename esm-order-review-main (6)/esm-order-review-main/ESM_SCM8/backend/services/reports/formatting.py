"""값·텍스트·숫자 포매팅 프리미티브.

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계)의 공유 리프 계층. 이 함수들은
서로(및 stdlib/config)에만 의존하는 닫힌 집합이라, 상위 렌더러(html/pptx/snapshot)들이
여기로만 의존하면 클러스터 간 순환(SCC)이 끊긴다. 여기에는 파일 I/O나 렌더링 로직을
두지 않는다 — 순수 변환/포맷만."""

from __future__ import annotations

import json
import re
from html import escape
from typing import Any

from backend.config import SCM_REPORT_SELF_BRAND
from core.exchange_rate import DEFAULT_EUR_KRW_RATE

def normalize_report_title(title: str | None) -> str:
    text = str(title or "").strip()
    default_title = "ESM 데이터 분석 리포트"
    if not text or "?" in text:
        return default_title
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    compact = normalized.replace(" ", "")
    placeholder_titles = {
        "report cart",
        "web card charts final",
        "silicon2 market report",
        "silicon2 market report - web card charts final",
        "보고서 장바구니",
        "보고서 장바구니 실데이터 분석",
        "장바구니 보고서",
    }
    placeholder_compact = {"보고서장바구니", "reportcart"}
    if normalized in placeholder_titles or compact in placeholder_compact or "market report" in normalized:
        return default_title
    return text


def excel_safe_html_snapshot(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 32000:
        return value
    return f"[html snapshot omitted from xlsx: {len(value)} chars]"


def html_text(value: object) -> str:
    return escape(stringify_report_value(value), quote=False)


def escape_attr(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", stringify_report_value(value)).strip("-") or "section"


def normalize_key(value: str) -> str:
    return str(value or "").replace(" ", "").replace("_", "").lower()


def is_self_brand(value: str, row: dict[str, Any] | None = None) -> bool:
    if row:
        if is_truthy(row.get("is_self")):
            return True
        if str(row.get("brand_role") or "").strip().lower() == "self":
            return True
    normalized = normalize_brand_name(value)
    return any(normalized == normalize_brand_name(name) for name in self_brand_names())


def normalize_brand_name(value: str) -> str:
    return str(value or "").strip().casefold()


def self_brand_names() -> list[str]:
    return [name.strip() for name in SCM_REPORT_SELF_BRAND.split(",") if name.strip()] or ["아누아", "Anua"]


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "self"}


def row_sales_value(row: dict[str, Any]) -> float:
    best = 0.0
    for key, value in row.items():
        normalized = normalize_key(key)
        if "매출" not in normalized and "amount" not in normalized and "sales" not in normalized and "revenue" not in normalized and key != "값":
            continue
        best = max(best, numeric_value(value))
    return best


def numeric_value(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "")
    number_match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", text)
    if not number_match:
        return 0.0
    number = float(number_match.group(0).replace(",", ""))
    unit_window = text[number_match.end() : number_match.end() + 8].lower()
    if "조" in unit_window:
        return number * 1_000_000_000_000
    if "억" in unit_window:
        return number * 100_000_000
    if "m" in unit_window or "백만" in unit_window:
        return number * 1_000_000
    if "만" in unit_window:
        return number * 10_000
    if "k" in unit_window or "천" in unit_window:
        return number * 1_000
    return number


def clean_metric_display(value: object) -> str:
    text = stringify_report_value(value).strip()
    if not text or text in {"-", "None", "nan"}:
        return "-"
    return text


def format_percent(ratio: float) -> str:
    value = ratio * 100
    if abs(value - round(value)) < 0.05:
        return f"{round(value):.0f}%"
    return f"{value:.1f}%"


def percent_numeric_value(value: object) -> float:
    text = stringify_report_value(value).strip()
    match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
    return float(match.group(1)) if match else 0.0


def format_percent_value(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return f"{round(value):.0f}%"
    return f"{value:.1f}%"


def first_value(row: dict[str, object], keys: tuple[str, ...], default: object = "") -> object:
    for key in keys:
        if key in row:
            value = row[key]
            if value is not None and value != "":
                return value
    return default


def display_amount(row: dict[str, object]) -> str:
    display = first_value(row, ("매출표시", "amount_display", "sales_display"), "")
    if display:
        return stringify_report_value(display)
    amount = first_value(row, ("매출액", "amount", "sales", "revenue", "값"), "")
    value = numeric_value(amount)
    return format_large_amount(value) if value > 0 else stringify_report_value(amount or "-")


def display_krw_amount(row: dict[str, object], *, eur_krw_rate: float | None = None) -> str:
    display = first_value(row, ("원화표시", "KRW표시", "krw_display", "sales_krw_display", "amount_krw_display"), "")
    if display:
        return stringify_report_value(display)
    for key in ("매출액", "amount", "sales", "revenue", "값"):
        extracted = first_krw_display_from_text(stringify_report_value(row.get(key, "")))
        if extracted:
            return extracted
    return format_krw_amount(row_sales_value(row), eur_krw_rate)

def amount_with_krw(row: dict[str, object], *, eur_krw_rate: float | None = None) -> str:
    amount = display_amount(row)
    krw_amount = display_krw_amount(row, eur_krw_rate=eur_krw_rate)
    if krw_amount and krw_amount != "-" and krw_amount != amount:
        return f"{amount} / {krw_amount}"
    return amount


def first_krw_display_from_text(text: str) -> str:
    for part in re.split(r"\s*(?:·|/|\||\n)\s*", str(text or "")):
        candidate = part.strip()
        if not candidate:
            continue
        if numeric_value(candidate) > 0 and any(token in candidate for token in ("₩", "원", "억원", "만원", "조", "KRW")) and "€" not in candidate:
            return candidate
    return ""


def format_amount_with_krw_value(value: float, *, eur_krw_rate: float | None = None) -> str:
    amount = format_large_amount(value)
    krw_amount = format_krw_amount(value, eur_krw_rate)
    return f"{amount} / {krw_amount}" if krw_amount else amount


def format_krw_amount(eur_value: float, eur_krw_rate: float | None) -> str:
    rate = float(eur_krw_rate or DEFAULT_EUR_KRW_RATE or 0)
    if eur_value <= 0 or rate <= 0:
        return ""
    krw = eur_value * rate
    abs_krw = abs(krw)
    if abs_krw >= 1_000_000_000_000:
        return f"약 ₩{format_scaled_number(krw / 1_000_000_000_000, 1 if abs_krw >= 10_000_000_000_000 else 2)}조"
    if abs_krw >= 100_000_000:
        return f"약 ₩{format_scaled_number(krw / 100_000_000, 1 if abs_krw >= 1_000_000_000 else 2)}억"
    if abs_krw >= 10_000:
        return f"약 ₩{format_scaled_number(krw / 10_000, 0 if abs_krw >= 1_000_000 else 1)}만원"
    return f"약 ₩{format_scaled_number(krw, 0)}원"


def format_scaled_number(value: float, digits: int) -> str:
    text = f"{value:,.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_integer_like(value: object) -> str:
    text = clean_metric_display(value)
    if text == "-":
        return "-"
    number = numeric_value(value)
    if number:
        return f"{number:,.0f}"
    return text




def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def format_large_amount(value: float) -> str:
    if value <= 0:
        return "-"
    if abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"€{value / 1_000:.1f}K"
    return f"€{value:,.0f}"


def stringify_report_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)[:120]
    return str(value)


def parse_json_object(value: object) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def safe_sheet_name(value: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]+", "_", value).strip() or "summary"
    return cleaned[:31]


def clamp_text(value: object, limit: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip(" .")
    return cleaned[:120] or "report"


# Override: fix cover metadata text that was left with mojibake in the legacy
# template-fill function above.


def disable_spellcheck(run) -> None:
    try:
        r_pr = run._r.get_or_add_rPr()
        r_pr.set("noProof", "1")
    except Exception:
        return


def top_rows_by_sales(rows: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    return sorted(rows, key=row_sales_value, reverse=True)[:limit]


def first_amount_display_from_text(text: str) -> str:
    for part in re.split(r"\s*(?:·|/|\||\n)\s*", str(text or "")):
        candidate = part.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if numeric_value(candidate) > 0 and any(token in lowered for token in ("€", "$", "₩", "원", "m", "k", "eur")):
            return candidate
    return ""


__all__ = [
    "disable_spellcheck",
    "top_rows_by_sales",
    "first_amount_display_from_text",
    "normalize_report_title",
    "excel_safe_html_snapshot",
    "html_text",
    "escape_attr",
    "normalize_key",
    "is_self_brand",
    "normalize_brand_name",
    "self_brand_names",
    "is_truthy",
    "row_sales_value",
    "numeric_value",
    "clean_metric_display",
    "format_percent",
    "percent_numeric_value",
    "format_percent_value",
    "first_value",
    "display_amount",
    "display_krw_amount",
    "amount_with_krw",
    "first_krw_display_from_text",
    "format_amount_with_krw_value",
    "format_krw_amount",
    "format_scaled_number",
    "format_integer_like",
    "is_number",
    "format_large_amount",
    "stringify_report_value",
    "parse_json_object",
    "safe_sheet_name",
    "clamp_text",
    "safe_filename",
]
