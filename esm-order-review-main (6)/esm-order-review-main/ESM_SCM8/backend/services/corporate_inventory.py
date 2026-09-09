"""Corporate inventory dashboard source mapping and safe status payloads.

Only the public dashboard shape lives here.  CMS raw payloads, invoice-level
rows and request exceptions must not be sent to the browser or written to the
repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from zoneinfo import ZoneInfo

from backend.cms_client import fetch_corporate_in_transit, fetch_corporate_stock_ledger
from core.transport import normalize_transport_code


KST = ZoneInfo("Asia/Seoul")
IN_TRANSIT_FAILURE_MESSAGE = "운송중 재고를 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요."
IN_TRANSIT_BUSINESS_GROUPS = {"COSMETIC", "KPOP"}
IN_TRANSIT_TRANSPORT_MODE_REVIEW_CODE = "REVIEW"
IN_TRANSIT_API_TRANSPORT_MODE_LABELS = {
    "SEA": "해운",
    "AIR": "항공",
    "RAIL": "철송",
    "TRUCKING": "트럭",
}
IN_TRANSIT_LEGACY_REMARK_TRANSPORT_MODE_CODES = {
    "OCEAN": "SEA",
    "AIR": "AIR",
    "RAIL": "RAIL",
    "TRUCKING": "TRUCKING",
}
IN_TRANSIT_SHIP_VIA_TRANSPORT_MODE_LABELS = {
    "OT": ("SEA", "해운"),
    "AIR": ("AIR", "항공"),
    "TK": ("TRUCKING", "트럭"),
    "RT": ("RAIL", "철송"),
    "BF": ("BF", "포워더"),
    "DHL": ("DHL", "특송"),
    "FIP": ("FIP", "특송"),
    "QMT": ("QMT", "택배"),
    "QSV": ("QSV", "택배"),
    "HCR": ("HCR", "핸드캐리"),
    "PU": ("PU", "픽업"),
}


@dataclass(frozen=True, slots=True)
class CorporateInventoryCompanyDefinition:
    company_code: str
    company_name: str
    country_name: str
    base_currency: str


# This roster is deliberately separate from the eight-entity analysis/auth
# matrix.  It defines the active legal entities that the corporate overview
# must show even when R14 omits every-zero warehouses for the selected date.
ACTIVE_CORPORATE_INVENTORY_COMPANIES: tuple[CorporateInventoryCompanyDefinition, ...] = (
    CorporateInventoryCompanyDefinition("CO000001", "(주)실리콘투", "Korea, Republic of", "KRW"),
    CorporateInventoryCompanyDefinition("CO000007", "Stylekorean Inc.", "United States", "USD"),
    CorporateInventoryCompanyDefinition("CO000009", "PT StyleKorean Indonesia", "Indonesia", "IDR"),
    CorporateInventoryCompanyDefinition("CO000012", "STYLEKOREAN MY SDN. BHD.", "Malaysia", "MYR"),
    CorporateInventoryCompanyDefinition("CO000013", "STYLEKOREAN EU B.V.", "Netherlands", "EUR"),
    CorporateInventoryCompanyDefinition("CO000015", "STYLEKOREAN VIETNAM CO.,LTD", "Vietnam", "VND"),
    CorporateInventoryCompanyDefinition("CO000016", "SKO Sp. z o.o.", "Poland", "EUR"),
    CorporateInventoryCompanyDefinition("CO000018", "STYLEKOREAN UK LIMITED", "United Kingdom", "GBP"),
    CorporateInventoryCompanyDefinition("CO000019", "STYLEKOREAN SG PTE. LTD.", "Singapore", "SGD"),
    CorporateInventoryCompanyDefinition("CO000020", "STYLEKOREAN FR SAS", "France", "EUR"),
    CorporateInventoryCompanyDefinition(
        "CO000021",
        "STYLEKOREAN MIDDLE EAST TRADING FZE",
        "United Arab Emirates",
        "AED",
    ),
    CorporateInventoryCompanyDefinition("CO000023", "STYLEKOREAN MX S. DE R.L. DE C.V.", "Mexico", "MXN"),
    CorporateInventoryCompanyDefinition("CO000024", "STYLEKOREAN ITALY S.R.L.", "Italy", "EUR"),
    CorporateInventoryCompanyDefinition(
        "CO000026",
        "STYLEKOREAN PORTUGAL, UNIPESSOAL LDA",
        "Portugal",
        "EUR",
    ),
    CorporateInventoryCompanyDefinition("CO000028", "UYU CORPORACION S.A. DE C.V.", "Mexico", "MXN"),
)
IDR_HOLDINGS_ADJUSTMENT_COMPANY_CODE = "CO000009"


def today_kst() -> date:
    return datetime.now(KST).date()


def _text(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _decimal_string(value: object, *, field: str) -> str:
    """Return a JSON-safe decimal without treating missing data as zero."""

    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} 값이 없습니다.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} 값이 숫자가 아닙니다.") from error
    if not amount.is_finite():
        raise ValueError(f"{field} 값이 유효하지 않습니다.")
    return format(amount, "f")


def _as_decimal(value: str) -> Decimal:
    return Decimal(value)


def _currency_code(value: object, *, field: str) -> str:
    currency = str(value or "").strip().upper()
    if re.fullmatch(r"[A-Z]{3}", currency) is None:
        raise ValueError(f"{field} 통화 코드가 올바르지 않습니다.")
    return currency


def normalize_holdings(
    rows: object,
    *,
    as_of: date,
    active_companies: tuple[CorporateInventoryCompanyDefinition, ...] | None = None,
) -> dict[str, object]:
    """Map all-company ledger rows without double-counting warehouse amounts.

    ``company.eqty_cost`` is normally the book-value KRW total while
    ``amount_krw_current`` is the same local-currency inventory valued with the
    latest published rate on or before the requested date. Indonesia is the
    confirmed source exception: its raw ``eqty_cost`` contains an IDR-scale
    amount, so its displayed book amount uses ``amount_krw_current`` too.
    Warehouse values remain drill-down rows and must never be added to either
    company-level total again.
    """

    if not isinstance(rows, list):
        raise ValueError("재고수불부 응답 형식이 올바르지 않습니다.")

    active_by_code = (
        {definition.company_code: definition for definition in active_companies}
        if active_companies is not None
        else None
    )
    if active_companies is not None and len(active_by_code or {}) != len(active_companies):
        raise ValueError("활성 법인 기준 목록에 중복 코드가 있습니다.")

    companies: list[dict[str, object]] = []
    seen_company_codes: set[str] = set()
    total_krw = Decimal("0")
    total_current_krw = Decimal("0")
    for company_index, raw_company in enumerate(rows, start=1):
        if not isinstance(raw_company, dict):
            raise ValueError("법인 재고 행 형식이 올바르지 않습니다.")
        company_code = _text(raw_company.get("comp_cd"), f"COMPANY-{company_index}")
        if company_code in seen_company_codes:
            raise ValueError(f"법인 코드가 중복되었습니다: {company_code}")
        if active_by_code is not None and company_code not in active_by_code:
            raise ValueError(f"활성 법인 기준 목록에 없는 재고 법인입니다: {company_code}")
        seen_company_codes.add(company_code)
        base_currency = _currency_code(
            raw_company.get("curr_nm"),
            field=f"법인 {company_index}의",
        )
        uses_current_value_for_book = company_code == IDR_HOLDINGS_ADJUSTMENT_COMPANY_CODE
        company_local_amount: Decimal | None = None
        if base_currency != "KRW":
            company_local_amount = _as_decimal(
                _decimal_string(
                    raw_company.get("eqty_cost_usd"),
                    field=f"법인 {company_index}의 eqty_cost_usd",
                )
            )
        company_current_amount = _decimal_string(
            raw_company.get("amount_krw_current"),
            field=f"법인 {company_index}의 amount_krw_current",
        )
        exchange_rate_krw: str | None = None
        exchange_rate_date: str | None = None
        if base_currency != "KRW":
            exchange_rate_krw = _decimal_string(
                raw_company.get("xrate"),
                field=f"법인 {company_index}의 xrate",
            )
            exchange_rate_date = _text(raw_company.get("xrate_dt"), "")
            if not exchange_rate_date:
                raise ValueError(f"법인 {company_index}의 xrate_dt 값이 없습니다.")

        if uses_current_value_for_book:
            if base_currency != "IDR":
                raise ValueError("인도네시아 법인의 기본통화가 IDR이 아닙니다.")
            company_amount = company_current_amount
        else:
            company_amount = _decimal_string(
                raw_company.get("eqty_cost"),
                field=f"법인 {company_index}의 eqty_cost",
            )
        raw_warehouses = raw_company.get("warehouses")
        if not isinstance(raw_warehouses, list):
            raise ValueError(f"법인 {company_index}의 창고 목록 형식이 올바르지 않습니다.")

        warehouses: list[dict[str, object]] = []
        for warehouse_index, raw_warehouse in enumerate(raw_warehouses, start=1):
            if not isinstance(raw_warehouse, dict):
                raise ValueError(f"법인 {company_index}의 창고 행 형식이 올바르지 않습니다.")
            warehouse_local_amount: Decimal | None = None
            if base_currency != "KRW":
                warehouse_local_amount = _as_decimal(
                    _decimal_string(
                        raw_warehouse.get("eqty_cost_usd"),
                        field=f"법인 {company_index} 창고 {warehouse_index}의 eqty_cost_usd",
                    )
                )
            warehouse_current_amount = _decimal_string(
                raw_warehouse.get("amount_krw_current"),
                field=f"법인 {company_index} 창고 {warehouse_index}의 amount_krw_current",
            )
            # The ledger returns each warehouse's current valuation but keeps
            # the common rate metadata on the parent company row.
            warehouse_exchange_rate_krw = exchange_rate_krw
            warehouse_exchange_rate_date = exchange_rate_date
            if uses_current_value_for_book:
                warehouse_amount = warehouse_current_amount
            else:
                warehouse_amount = _decimal_string(
                    raw_warehouse.get("eqty_cost"),
                    field=f"법인 {company_index} 창고 {warehouse_index}의 eqty_cost",
                )
            warehouses.append(
                {
                    "warehouse_code": _text(raw_warehouse.get("whouse_cd"), f"WAREHOUSE-{warehouse_index}"),
                    "warehouse_name": _text(raw_warehouse.get("whouse_nm"), f"창고 {warehouse_index}"),
                    "ending_inventory_krw": warehouse_amount,
                    "ending_inventory_current_krw": warehouse_current_amount,
                    "ending_inventory_local": (
                        format(warehouse_local_amount, "f") if warehouse_local_amount is not None else None
                    ),
                    "exchange_rate_krw": warehouse_exchange_rate_krw,
                    "exchange_rate_date": warehouse_exchange_rate_date,
                }
            )

        total_krw += _as_decimal(company_amount)
        total_current_krw += _as_decimal(company_current_amount)
        companies.append(
            {
                "company_code": company_code,
                "company_name": _text(raw_company.get("comp_nm"), f"법인 {company_index}"),
                "country_name": _text(raw_company.get("country_nm"), "국가 미지정"),
                "base_currency": base_currency,
                "warehouse_count": len(warehouses),
                "ending_inventory_krw": company_amount,
                "ending_inventory_current_krw": company_current_amount,
                "ending_inventory_local": (
                    format(company_local_amount, "f") if company_local_amount is not None else None
                ),
                "inventory_status": "available",
                "valuation_basis": "current_exchange_rate" if uses_current_value_for_book else "cms_eqty_cost",
                "exchange_rate_unit": base_currency if exchange_rate_krw is not None else None,
                "exchange_rate_krw": exchange_rate_krw,
                "exchange_rate_date": exchange_rate_date,
                "warehouses": warehouses,
            }
        )

    if active_companies is not None:
        for definition in active_companies:
            if definition.company_code in seen_company_codes:
                continue
            companies.append(
                {
                    "company_code": definition.company_code,
                    "company_name": definition.company_name,
                    "country_name": definition.country_name,
                    "base_currency": definition.base_currency,
                    "warehouse_count": 0,
                    "ending_inventory_krw": "0",
                    "ending_inventory_current_krw": "0",
                    "ending_inventory_local": None,
                    "inventory_status": "no_inventory",
                    "valuation_basis": "no_inventory",
                    "exchange_rate_unit": None,
                    "exchange_rate_krw": None,
                    "exchange_rate_date": None,
                    "warehouses": [],
                }
            )

    companies.sort(key=lambda company: str(company["company_name"]))
    return {
        "status": "ready",
        "as_of": as_of.isoformat(),
        "total_krw": format(total_krw, "f"),
        "total_current_krw": format(total_current_krw, "f"),
        "difference_krw": format(total_current_krw - total_krw, "f"),
        "active_company_count": len(active_companies) if active_companies is not None else len(companies),
        "companies_with_inventory_count": sum(
            company["inventory_status"] == "available" for company in companies
        ),
        "companies": companies,
    }


def _transit_currency_summary(
    currency_code: str,
    *,
    original_amount: Decimal,
    converted_krw: Decimal,
    qty: Decimal,
    exchange_rates: set[tuple[str, str]],
) -> dict[str, object]:
    return {
        "currency_code": currency_code,
        "original_amount": format(original_amount, "f"),
        "quantity": format(qty, "f"),
        "converted_krw": format(converted_krw, "f"),
        "exchange_rate_basis": "krw" if currency_code == "KRW" else "invoice_contract",
        "exchange_rates": [
            {"rate": rate, "rate_date": rate_date}
            for rate, rate_date in sorted(exchange_rates, key=lambda item: (item[1], _as_decimal(item[0])))
        ],
    }


def _in_transit_transport_mode(
    transport_mode: object,
    transport_mode_source: object,
    remark: object,
    ship_via: object,
) -> tuple[str, str, str]:
    """Use the CMS transport decision, with legacy-field fallback only when absent.

    ``/esm/in-transit`` now resolves each invoice as ``SEA``/``AIR``/``RAIL``
    and supplies its decision source.  An explicit ``OTHER`` or ``UNRESOLVED``
    response is authoritative and must not be overwritten by local heuristics.
    """

    api_mode = str(transport_mode or "").strip().upper()
    api_source = str(transport_mode_source or "").strip().upper()
    if api_mode or api_source:
        api_label = IN_TRANSIT_API_TRANSPORT_MODE_LABELS.get(api_mode)
        if api_label and api_source in {"INVOICE_REMARK", "SHIP_VIA"}:
            return api_mode, api_label, api_source
        return IN_TRANSIT_TRANSPORT_MODE_REVIEW_CODE, "운송수단 확인필요", "UNRESOLVED"

    remark_code = normalize_transport_code(remark or "")
    legacy_mode = IN_TRANSIT_LEGACY_REMARK_TRANSPORT_MODE_CODES.get(remark_code)
    if legacy_mode:
        return legacy_mode, IN_TRANSIT_API_TRANSPORT_MODE_LABELS.get(legacy_mode, "운송수단 확인필요"), "INVOICE_REMARK"

    ship_via_code = str(ship_via or "").strip().upper()
    ship_via_mode = IN_TRANSIT_SHIP_VIA_TRANSPORT_MODE_LABELS.get(ship_via_code)
    if ship_via_mode:
        return *ship_via_mode, "SHIP_VIA"
    return IN_TRANSIT_TRANSPORT_MODE_REVIEW_CODE, "운송수단 확인필요", "UNRESOLVED"


def normalize_in_transit(rows: object, *, as_of: date) -> dict[str, object]:
    """Aggregate HQ-origin in-transit invoices by destination, mode and currency.

    CMS splits a mixed invoice into COSMETIC and KPOP rows when ``biz_gbn=ALL``.
    Those rows are separate inventory amounts and must all be summed rather than
    deduplicated by invoice number.  CMS converts each row with the contract rate
    stored on the invoice and returns that value as ``amount_krw``.  We sum those
    authoritative values in memory, drop invoice identifiers and remarks, and
    retain only the distinct rate/date pairs needed to explain the aggregate. A
    missing or unknown business group, amount, currency, converted amount or
    foreign-currency rate invalidates the whole transit snapshot instead of
    quietly omitting a portion of the total.
    """

    if not isinstance(rows, list):
        raise ValueError("운송중 재고 응답 형식이 올바르지 않습니다.")

    destinations: list[dict[str, object]] = []
    for destination_index, raw_destination in enumerate(rows, start=1):
        if not isinstance(raw_destination, dict):
            raise ValueError("도착 법인 운송중 재고 행 형식이 올바르지 않습니다.")
        destination_code = _text(raw_destination.get("dest_comp_cd"), "")
        destination_name = _text(raw_destination.get("dest_comp_nm"), "")
        if not destination_code or not destination_name:
            raise ValueError(f"도착 법인 {destination_index}의 코드 또는 명칭이 없습니다.")
        raw_invoices = raw_destination.get("invoices")
        if not isinstance(raw_invoices, list):
            raise ValueError(f"도착 법인 {destination_index}의 인보이스 목록 형식이 올바르지 않습니다.")

        currencies: dict[str, dict[str, object]] = {}
        transport_modes: dict[tuple[str, str], dict[str, dict[str, object]]] = {}
        transport_mode_sources: dict[tuple[str, str], set[str]] = {}
        for invoice_index, raw_invoice in enumerate(raw_invoices, start=1):
            if not isinstance(raw_invoice, dict):
                raise ValueError(f"도착 법인 {destination_index} 인보이스 {invoice_index} 형식이 올바르지 않습니다.")
            business_group = str(raw_invoice.get("biz_gbn") or "").strip().upper()
            if business_group not in IN_TRANSIT_BUSINESS_GROUPS:
                raise ValueError(
                    f"도착 법인 {destination_index} 인보이스 {invoice_index}의 biz_gbn 값이 올바르지 않습니다."
                )
            currency_code = _currency_code(
                raw_invoice.get("currency"),
                field=f"도착 법인 {destination_index} 인보이스 {invoice_index}의",
            )
            amount = _as_decimal(
                _decimal_string(
                    raw_invoice.get("amount"),
                    field=f"도착 법인 {destination_index} 인보이스 {invoice_index}의 amount",
                )
            )
            amount_krw = _as_decimal(
                _decimal_string(
                    raw_invoice.get("amount_krw"),
                    field=f"도착 법인 {destination_index} 인보이스 {invoice_index}의 amount_krw",
                )
            )
            quantity = _as_decimal(
                _decimal_string(
                    raw_invoice.get("qty"),
                    field=f"도착 법인 {destination_index} 인보이스 {invoice_index}의 qty",
                )
            )
            exchange_rate: tuple[str, str] | None = None
            if currency_code != "KRW":
                rate_source = _text(raw_invoice.get("xrate_source"), "")
                if rate_source != "INVOICE":
                    raise ValueError(
                        f"도착 법인 {destination_index} 인보이스 {invoice_index}의 환율 출처가 계약환율이 아닙니다."
                    )
                rate = _decimal_string(
                    raw_invoice.get("xrate"),
                    field=f"도착 법인 {destination_index} 인보이스 {invoice_index}의 xrate",
                )
                rate_date = _text(raw_invoice.get("xrate_dt"), "")
                if not rate_date:
                    raise ValueError(
                        f"도착 법인 {destination_index} 인보이스 {invoice_index}의 xrate_dt 값이 없습니다."
                    )
                exchange_rate = (rate, rate_date)

            bucket = currencies.setdefault(
                currency_code,
                {"amount": Decimal("0"), "amount_krw": Decimal("0"), "qty": Decimal("0"), "rates": set()},
            )
            bucket["amount"] = _as_decimal(str(bucket["amount"])) + amount
            bucket["amount_krw"] = _as_decimal(str(bucket["amount_krw"])) + amount_krw
            bucket["qty"] = _as_decimal(str(bucket["qty"])) + quantity
            if exchange_rate is not None:
                rates = bucket["rates"]
                if not isinstance(rates, set):
                    raise ValueError("운송중 환율 집계 형식이 올바르지 않습니다.")
                rates.add(exchange_rate)
            transport_mode_code, transport_mode_name, transport_mode_source = _in_transit_transport_mode(
                raw_invoice.get("transport_mode"),
                raw_invoice.get("transport_mode_source"),
                raw_invoice.get("remark"),
                raw_invoice.get("ship_via"),
            )
            transport_mode_key = (transport_mode_code, transport_mode_name)
            mode_currencies = transport_modes.setdefault(transport_mode_key, {})
            transport_mode_sources.setdefault(transport_mode_key, set()).add(transport_mode_source)
            mode_bucket = mode_currencies.setdefault(
                currency_code,
                {"amount": Decimal("0"), "amount_krw": Decimal("0"), "qty": Decimal("0"), "rates": set()},
            )
            mode_bucket["amount"] = _as_decimal(str(mode_bucket["amount"])) + amount
            mode_bucket["amount_krw"] = _as_decimal(str(mode_bucket["amount_krw"])) + amount_krw
            mode_bucket["qty"] = _as_decimal(str(mode_bucket["qty"])) + quantity
            if exchange_rate is not None:
                mode_rates = mode_bucket["rates"]
                if not isinstance(mode_rates, set):
                    raise ValueError("운송수단별 환율 집계 형식이 올바르지 않습니다.")
                mode_rates.add(exchange_rate)

        destinations.append(
            {
                "destination_code": destination_code,
                "destination_name": destination_name,
                "currencies": currencies,
                "transport_modes": transport_modes,
                "transport_mode_sources": transport_mode_sources,
            }
        )

    result_destinations: list[dict[str, object]] = []
    total_krw = Decimal("0")
    for destination in destinations:
        currencies = destination["currencies"]
        if not isinstance(currencies, dict):  # Defensive narrowing for the public payload.
            raise ValueError("운송중 통화 합계 형식이 올바르지 않습니다.")
        currency_summaries: list[dict[str, object]] = []
        destination_total = Decimal("0")
        destination_qty = Decimal("0")
        for currency_code in sorted(currencies):
            bucket = currencies[currency_code]
            if not isinstance(bucket, dict):
                raise ValueError("운송중 통화 금액 형식이 올바르지 않습니다.")
            amount = bucket.get("amount")
            converted_krw = bucket.get("amount_krw")
            quantity = bucket.get("qty")
            exchange_rates = bucket.get("rates")
            if (
                not isinstance(amount, Decimal)
                or not isinstance(converted_krw, Decimal)
                or not isinstance(quantity, Decimal)
                or not isinstance(exchange_rates, set)
            ):
                raise ValueError("운송중 통화 금액이 올바르지 않습니다.")
            summary = _transit_currency_summary(
                currency_code,
                original_amount=amount,
                converted_krw=converted_krw,
                qty=quantity,
                exchange_rates=exchange_rates,
            )
            destination_total += converted_krw
            destination_qty += quantity
            currency_summaries.append(summary)

        transport_mode_summaries: list[dict[str, object]] = []
        transport_modes = destination["transport_modes"]
        if not isinstance(transport_modes, dict):
            raise ValueError("운송수단별 운송중 재고 형식이 올바르지 않습니다.")
        transport_mode_sources = destination["transport_mode_sources"]
        if not isinstance(transport_mode_sources, dict):
            raise ValueError("운송수단별 운송중 재고 원천 형식이 올바르지 않습니다.")
        for (transport_mode_code, transport_mode_name), mode_currencies in transport_modes.items():
            if not isinstance(mode_currencies, dict):
                raise ValueError("운송수단별 통화 합계 형식이 올바르지 않습니다.")
            mode_currency_summaries: list[dict[str, object]] = []
            mode_total = Decimal("0")
            mode_qty = Decimal("0")
            for currency_code in sorted(mode_currencies):
                bucket = mode_currencies[currency_code]
                if not isinstance(bucket, dict):
                    raise ValueError("운송수단별 통화 금액 형식이 올바르지 않습니다.")
                amount = bucket.get("amount")
                converted_krw = bucket.get("amount_krw")
                quantity = bucket.get("qty")
                exchange_rates = bucket.get("rates")
                if (
                    not isinstance(amount, Decimal)
                    or not isinstance(converted_krw, Decimal)
                    or not isinstance(quantity, Decimal)
                    or not isinstance(exchange_rates, set)
                ):
                    raise ValueError("운송수단별 통화 금액이 올바르지 않습니다.")
                summary = _transit_currency_summary(
                    currency_code,
                    original_amount=amount,
                    converted_krw=converted_krw,
                    qty=quantity,
                    exchange_rates=exchange_rates,
                )
                mode_total += converted_krw
                mode_qty += quantity
                mode_currency_summaries.append(summary)
            transport_mode_summaries.append(
                {
                    "transport_mode_code": transport_mode_code,
                    "transport_mode_name": transport_mode_name,
                    "transport_mode_sources": sorted(
                        str(source) for source in transport_mode_sources.get((transport_mode_code, transport_mode_name), set())
                    ),
                    "quantity": format(mode_qty, "f"),
                    "total_krw": format(mode_total, "f"),
                    "currencies": mode_currency_summaries,
                }
            )
        transport_mode_summaries.sort(
            key=lambda mode: (-_as_decimal(str(mode["total_krw"])), str(mode["transport_mode_name"]))
        )

        result_destinations.append(
            {
                "destination_code": destination["destination_code"],
                "destination_name": destination["destination_name"],
                "quantity": format(destination_qty, "f"),
                "total_krw": format(destination_total, "f"),
                "currencies": currency_summaries,
                "transport_modes": transport_mode_summaries,
            }
        )
        total_krw += destination_total

    result_destinations.sort(key=lambda destination: _as_decimal(str(destination["total_krw"])), reverse=True)
    return {
        "status": "ready",
        "as_of": as_of.isoformat(),
        "total_krw": format(total_krw, "f"),
        "destinations": result_destinations,
    }


def total_inventory_payload(holdings: dict[str, object], in_transit: dict[str, object]) -> dict[str, object]:
    """Return a corporate total only when both independent sources are ready."""

    if holdings.get("status") != "ready" or in_transit.get("status") != "ready":
        return {
            "status": "unavailable",
            "message": "보유 또는 운송중 재고를 갱신하지 못해 총 재고 규모를 산출하지 않았습니다.",
        }
    holdings_total = _as_decimal(_decimal_string(holdings.get("total_krw"), field="보유 재고 합계"))
    transit_total = _as_decimal(_decimal_string(in_transit.get("total_krw"), field="운송중 재고 합계"))
    return {
        "status": "ready",
        "total_krw": format(holdings_total + transit_total, "f"),
    }


def corporate_inventory_payload(*, as_of: date | None = None) -> dict[str, object]:
    """Build independent source statuses so a failure never becomes a zero."""

    snapshot_date = as_of or today_kst()
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    try:
        raw_holdings = fetch_corporate_stock_ledger(snapshot_date.isoformat())
        holdings = normalize_holdings(
            raw_holdings,
            as_of=snapshot_date,
            active_companies=ACTIVE_CORPORATE_INVENTORY_COMPANIES,
        )
    except Exception:  # CMS errors are intentionally reduced to a safe UI status.
        holdings: dict[str, object] = {
            "status": "failed",
            "as_of": snapshot_date.isoformat(),
            "message": "보유 재고를 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        }

    try:
        in_transit = normalize_in_transit(
            fetch_corporate_in_transit(snapshot_date.isoformat()),
            as_of=snapshot_date,
        )
    except Exception:  # Never emit a partial transport aggregate or a zero fallback.
        in_transit: dict[str, object] = {
            "status": "failed",
            "as_of": snapshot_date.isoformat(),
            "message": IN_TRANSIT_FAILURE_MESSAGE,
        }

    return {
        "as_of": snapshot_date.isoformat(),
        "generated_at": generated_at,
        "holdings": holdings,
        "in_transit": in_transit,
        "total_inventory": total_inventory_payload(holdings, in_transit),
    }
