"""Server-built aggregates for the brand report screen.

The report consumes the complete country/SKU cubes created by season analysis.
Use the cube column constants here rather than copied display strings: a copied
column name can silently turn every sales amount into zero.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.season_calendar import (
    AMOUNT_COL,
    BRAND_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
    COUNTRY_COL,
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    QTY_COL,
)


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(row: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "-"


def _summary_totals(summary_rows: list[object]) -> dict[str, tuple[float, float]]:
    """Return source amount/quantity totals by brand from the complete cube."""
    totals: dict[str, list[float]] = {}
    for raw in summary_rows:
        if not isinstance(raw, dict):
            continue
        brand = _text(raw, BRAND_COL, "brand")
        if brand == "-":
            continue
        amount, qty = totals.setdefault(brand, [0.0, 0.0])
        totals[brand] = [
            amount + _number(raw.get(AMOUNT_COL, raw.get("amount"))),
            qty + _number(raw.get(QTY_COL, raw.get("qty"))),
        ]
    return {brand: (values[0], values[1]) for brand, values in totals.items()}


def brand_report_summaries_match_source(season: dict[str, object], reports: object) -> bool:
    """Check cached report totals against the source cube before serving them."""
    summary_rows = season.get("countrySkuSummary")
    if not isinstance(summary_rows, list) or not isinstance(reports, list):
        return False

    expected = _summary_totals(summary_rows)
    actual: dict[str, tuple[float, float]] = {}
    for row in reports:
        if not isinstance(row, dict):
            return False
        brand = _text(row, "brand")
        if brand == "-" or brand in actual:
            return False
        actual[brand] = (_number(row.get("amount")), _number(row.get("qty")))

    if expected.keys() != actual.keys():
        return False
    for brand, (expected_amount, expected_qty) in expected.items():
        actual_amount, actual_qty = actual[brand]
        amount_tolerance = max(0.01, abs(expected_amount) * 1e-9)
        qty_tolerance = max(0.01, abs(expected_qty) * 1e-9)
        if abs(expected_amount - actual_amount) > amount_tolerance or abs(expected_qty - actual_qty) > qty_tolerance:
            return False
    return True


def build_brand_report_summaries(season: dict[str, object]) -> list[dict[str, object]]:
    """Build bounded brand-report aggregates from a cached analysis payload."""
    summary_rows = season.get("countrySkuSummary")
    monthly_rows = season.get("countrySkuMonthly")
    if not isinstance(summary_rows, list):
        return []

    brands: dict[str, dict[str, Any]] = {}
    for raw in summary_rows:
        if not isinstance(raw, dict):
            continue
        brand = _text(raw, BRAND_COL, "brand")
        if brand == "-":
            continue
        item = brands.setdefault(brand, {
            "brand": brand, "amount": 0.0, "qty": 0.0, "skus": set(), "countries": set(), "categories": set(),
            "country_amounts": defaultdict(float), "sku_rows": {}, "category_amounts": defaultdict(float), "monthly_amounts": defaultdict(float),
        })
        amount = _number(raw.get(AMOUNT_COL, raw.get("amount")))
        qty = _number(raw.get(QTY_COL, raw.get("qty")))
        sku = _text(raw, PRODUCT_CODE_COL, "sku")
        country = _text(raw, COUNTRY_COL, "country")
        category1 = _text(raw, CATEGORY1_COL, "category1")
        category2 = _text(raw, CATEGORY2_COL, "category2")
        name = _text(raw, PRODUCT_NAME_COL, "productName", "name")
        item["amount"] += amount
        item["qty"] += qty
        if sku != "-":
            item["skus"].add(sku)
        if country != "-":
            item["countries"].add(country)
            item["country_amounts"][country] += amount
        if category1 != "-":
            item["categories"].add(category1)
        sku_item = item["sku_rows"].setdefault(sku, {"sku": sku, "name": name, "category": category1, "amount": 0.0, "qty": 0.0})
        sku_item["amount"] += amount
        sku_item["qty"] += qty
        item["category_amounts"][(category1, category2)] += amount

    if isinstance(monthly_rows, list):
        for raw in monthly_rows:
            if not isinstance(raw, dict):
                continue
            brand = _text(raw, BRAND_COL, "brand")
            item = brands.get(brand)
            if not item:
                continue
            month = _text(raw, "year_month", "yearMonth", "month")
            if month != "-":
                item["monthly_amounts"][month] += _number(raw.get(AMOUNT_COL, raw.get("amount")))

    reports: list[dict[str, object]] = []
    for item in brands.values():
        country_rows = sorted(
            ({"name": name, "amount": amount} for name, amount in item["country_amounts"].items()),
            key=lambda row: float(row["amount"]), reverse=True,
        )[:5]
        sku_rows = sorted(item["sku_rows"].values(), key=lambda row: float(row["amount"]), reverse=True)[:5]
        category_rows = sorted(
            ({"category1": first, "category2": second, "amount": amount} for (first, second), amount in item["category_amounts"].items()),
            key=lambda row: float(row["amount"]), reverse=True,
        )[:3]
        monthly = sorted(
            ({"month": month, "amount": amount} for month, amount in item["monthly_amounts"].items()),
            key=lambda row: str(row["month"]),
        )
        reports.append({
            "brand": item["brand"], "amount": item["amount"], "qty": item["qty"],
            "skuCount": len(item["skus"]), "countryCount": len(item["countries"]), "categoryCount": len(item["categories"]),
            "countries": country_rows, "topSkus": sku_rows, "categories": category_rows, "monthly": monthly,
        })
    return sorted(reports, key=lambda row: float(row["amount"]), reverse=True)
