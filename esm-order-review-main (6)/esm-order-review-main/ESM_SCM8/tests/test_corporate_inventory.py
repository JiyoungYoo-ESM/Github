"""Corporate inventory dashboard authorization and source-mapping tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import backend.auth.user_store as user_store_module
import backend.routers.auth as auth_router
import backend.services.auth as auth_service
from backend.cms_client import fetch_corporate_in_transit, fetch_corporate_stock_ledger
from backend.main import app
from backend.services.corporate_inventory import (
    ACTIVE_CORPORATE_INVENTORY_COMPANIES,
    corporate_inventory_payload,
    normalize_holdings,
    normalize_in_transit,
)
from core.kpi import EximKrwRate, get_exim_currency_krw_rates
from tests.auth_helpers import TEST_PASSWORDS, TestUserStore


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(user_store_module, "_user_store", TestUserStore())
    auth_service.reset_sessions()
    auth_router._login_limiter.reset()
    return TestClient(app)


def login(client: TestClient, username: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"id": username, "password": TEST_PASSWORDS[username]},
    )
    assert response.status_code == 200


def stock_ledger_rows() -> list[dict[str, object]]:
    return [
        {
            "comp_cd": "CO000016",
            "comp_nm": "폴란드 법인",
            "country_nm": "폴란드",
            "curr_nm": "PLN",
            "eqty_cost": "1000000000",
            "eqty_cost_usd": "2500000",
            "amount_krw_current": "900000000",
            "xrate": "360",
            "xrate_dt": "2026-08-20",
            "warehouses": [
                {
                    "whouse_cd": "PL-A",
                    "whouse_nm": "폴란드 A",
                    "eqty_cost": "600000000",
                    "eqty_cost_usd": "1500000",
                    "amount_krw_current": "540000000",
                    "xrate": "360",
                    "xrate_dt": "2026-08-20",
                },
                {
                    "whouse_cd": "PL-B",
                    "whouse_nm": "폴란드 B",
                    "eqty_cost": "400000000",
                    "eqty_cost_usd": "1000000",
                    "amount_krw_current": "360000000",
                    "xrate": "360",
                    "xrate_dt": "2026-08-20",
                },
            ],
        },
        {
            "comp_cd": "CO000007",
            "comp_nm": "미국 법인",
            "country_nm": "미국",
            "curr_nm": "USD",
            "eqty_cost": "2000000000",
            "eqty_cost_usd": "1500000",
            "amount_krw_current": "2050000000",
            "xrate": "1366.6666666667",
            "xrate_dt": "2026-08-20",
            "warehouses": [
                {
                    "whouse_cd": "US-A",
                    "whouse_nm": "미국 A",
                    "eqty_cost": "2000000000",
                    "eqty_cost_usd": "1500000",
                    "amount_krw_current": "2050000000",
                    "xrate": "1366.6666666667",
                    "xrate_dt": "2026-08-20",
                },
            ],
        },
    ]


def indonesia_stock_ledger_rows() -> list[dict[str, object]]:
    return [
        {
            "comp_cd": "CO000009",
            "comp_nm": "PT StyleKorean Indonesia",
            "country_nm": "Indonesia",
            "curr_nm": "IDR",
            "eqty_cost": "100000000000",
            "eqty_cost_usd": "100000000000",
            "amount_krw_current": "8000000000",
            "xrate": "0.08",
            "xrate_dt": "2026-08-20",
            "warehouses": [
                {
                    "whouse_cd": "ID-A",
                    "whouse_nm": "Indonesia A",
                    "eqty_cost": "60000000000",
                    "eqty_cost_usd": "60000000000",
                    "amount_krw_current": "4800000000",
                    "xrate": "0.08",
                    "xrate_dt": "2026-08-20",
                },
                {
                    "whouse_cd": "ID-B",
                    "whouse_nm": "Indonesia B",
                    "eqty_cost": "40000000000",
                    "eqty_cost_usd": "40000000000",
                    "amount_krw_current": "3200000000",
                    "xrate": "0.08",
                    "xrate_dt": "2026-08-20",
                },
            ],
        }
    ]


def in_transit_rows() -> list[dict[str, object]]:
    return [
        {
            "dest_comp_cd": "CO000007",
            "dest_comp_nm": "미국 법인",
            "invoices": [
                {
                    "biz_gbn": "COSMETIC",
                    "currency": "EUR",
                    "amount": "10000",
                    "amount_krw": "15000000",
                    "xrate": "1500",
                    "xrate_dt": "2026-07-01",
                    "xrate_source": "INVOICE",
                    "ow_dt": "2026-07-01",
                    "qty": "3",
                    "remark": "해운 1차",
                    "ship_via": "OT",
                    "transport_mode": "SEA",
                    "transport_mode_source": "INVOICE_REMARK",
                },
                {
                    "biz_gbn": "COSMETIC",
                    "currency": "EUR",
                    "amount": "5000",
                    "amount_krw": "9000000",
                    "xrate": "1800",
                    "xrate_dt": "2026-07-15",
                    "xrate_source": "INVOICE",
                    "ow_dt": "2026-07-15",
                    "qty": "2",
                    "remark": "해운 1차",
                    "ship_via": "OT",
                    "transport_mode": "SEA",
                    "transport_mode_source": "INVOICE_REMARK",
                },
                {
                    "biz_gbn": "KPOP",
                    "currency": "KRW",
                    "amount": "5000000",
                    "amount_krw": "5000000",
                    "ow_dt": "2026-07-20",
                    "qty": "1",
                    "remark": "항공 AIR",
                    "ship_via": "AIR",
                    "transport_mode": "AIR",
                    "transport_mode_source": "INVOICE_REMARK",
                },
            ],
        },
        {
            "dest_comp_cd": "JP",
            "dest_comp_nm": "일본 법인",
            "invoices": [
                {
                    "biz_gbn": "COSMETIC",
                    "currency": "JPY",
                    "amount": "100000",
                    "amount_krw": "900000",
                    "xrate": "9",
                    "xrate_dt": "2026-08-01",
                    "xrate_source": "INVOICE",
                    "ow_dt": "2026-08-01",
                    "qty": "7",
                    "remark": "해운 SEA",
                    "ship_via": "BF",
                    "transport_mode": "SEA",
                    "transport_mode_source": "INVOICE_REMARK",
                },
            ],
        },
    ]


def exim_rates() -> dict[str, EximKrwRate]:
    return {
        "IDR": EximKrwRate(
            currency_code="IDR",
            quote_unit="IDR(100)",
            quote_krw=Decimal("8"),
            krw_per_unit=Decimal("0.08"),
            rate_date="2026-08-20",
        ),
        "EUR": EximKrwRate(
            currency_code="EUR",
            quote_unit="EUR",
            quote_krw=Decimal("1600"),
            krw_per_unit=Decimal("1600"),
            rate_date="2026-08-20",
        ),
        "JPY": EximKrwRate(
            currency_code="JPY",
            quote_unit="JPY(100)",
            quote_krw=Decimal("900"),
            krw_per_unit=Decimal("9"),
            rate_date="2026-08-20",
        ),
    }


def test_corporate_inventory_allows_only_adminmaster(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "backend.services.corporate_inventory.fetch_corporate_stock_ledger",
        lambda as_of: stock_ledger_rows(),
    )
    monkeypatch.setattr("backend.services.corporate_inventory.fetch_corporate_in_transit", lambda as_of: in_transit_rows())
    login(client, "adminmaster")

    response = client.get("/api/corporate-inventory")

    assert response.status_code == 200
    assert response.json()["holdings"]["status"] == "ready"
    assert response.json()["in_transit"]["status"] == "ready"

    auth_service.reset_sessions()
    login(client, "ia")
    denied = client.get("/api/corporate-inventory")
    assert denied.status_code == 403
    assert denied.json()["error"]["message"] == "전사 재고 현황 접근 권한이 없습니다."


def test_holdings_total_uses_company_eqty_cost_once_not_warehouse_amounts():
    holdings = normalize_holdings(stock_ledger_rows(), as_of=date(2026, 8, 20))

    # 10억(PL) + 20억(USA) = 30억. 하위 창고 10억 + 20억을 다시 더하면 60억이 된다.
    assert holdings["total_krw"] == "3000000000"
    assert holdings["total_current_krw"] == "2950000000"
    assert holdings["difference_krw"] == "-50000000"
    companies = holdings["companies"]
    assert isinstance(companies, list)
    assert companies[0]["ending_inventory_krw"] == "2000000000"
    assert companies[1]["ending_inventory_krw"] == "1000000000"


def test_holdings_missing_amount_is_not_silently_converted_to_zero():
    broken = stock_ledger_rows()
    broken[0]["eqty_cost"] = None

    with pytest.raises(ValueError, match="eqty_cost 값이 없습니다"):
        normalize_holdings(broken, as_of=date(2026, 8, 20))


def test_holdings_missing_current_amount_is_not_silently_fallback_to_book_value():
    broken = stock_ledger_rows()
    broken[0]["amount_krw_current"] = None

    with pytest.raises(ValueError, match="amount_krw_current 값이 없습니다"):
        normalize_holdings(broken, as_of=date(2026, 8, 20))


def test_holdings_missing_warehouse_current_amount_fails_the_snapshot():
    broken = stock_ledger_rows()
    broken[0]["warehouses"][0]["amount_krw_current"] = None

    with pytest.raises(ValueError, match="amount_krw_current 값이 없습니다"):
        normalize_holdings(broken, as_of=date(2026, 8, 20))


def test_successful_holdings_snapshot_pads_active_company_without_inventory_as_zero(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.services.corporate_inventory.fetch_corporate_stock_ledger",
        lambda as_of: stock_ledger_rows(),
    )
    monkeypatch.setattr(
        "backend.services.corporate_inventory.fetch_corporate_in_transit",
        lambda as_of: in_transit_rows(),
    )
    payload = corporate_inventory_payload(as_of=date(2026, 8, 20))

    holdings = payload["holdings"]
    assert holdings["status"] == "ready"
    assert holdings["total_krw"] == "3000000000"
    assert holdings["total_current_krw"] == "2950000000"
    assert holdings["difference_krw"] == "-50000000"
    assert holdings["active_company_count"] == len(ACTIVE_CORPORATE_INVENTORY_COMPANIES) == 15
    assert holdings["companies_with_inventory_count"] == 2
    assert len(holdings["companies"]) == 15
    eu_company = next(
        company for company in holdings["companies"] if company["company_code"] == "CO000013"
    )
    assert eu_company == {
        "company_code": "CO000013",
        "company_name": "STYLEKOREAN EU B.V.",
        "country_name": "Netherlands",
        "base_currency": "EUR",
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


def test_uyu_mexico_holdings_are_included_in_corporate_totals():
    rows = stock_ledger_rows()
    rows.append(
        {
            "comp_cd": "CO000028",
            "comp_nm": "UYU CORPORACION S.A. DE C.V.",
            "country_nm": "Mexico",
            "curr_nm": "MXN",
            "eqty_cost": "50000000",
            "eqty_cost_usd": "700000",
            "amount_krw_current": "55000000",
            "xrate": "78.5714285714",
            "xrate_dt": "2026-09-01",
            "warehouses": [
                {
                    "whouse_cd": "MX-UYU",
                    "whouse_nm": "UYU Mexico Warehouse",
                    "eqty_cost": "50000000",
                    "eqty_cost_usd": "700000",
                    "amount_krw_current": "55000000",
                }
            ],
        }
    )

    holdings = normalize_holdings(
        rows,
        as_of=date(2026, 9, 1),
        active_companies=ACTIVE_CORPORATE_INVENTORY_COMPANIES,
    )

    assert holdings["status"] == "ready"
    assert holdings["active_company_count"] == 15
    assert holdings["companies_with_inventory_count"] == 3
    assert holdings["total_krw"] == "3050000000"
    assert holdings["total_current_krw"] == "3005000000"
    uyu = next(company for company in holdings["companies"] if company["company_code"] == "CO000028")
    assert uyu["company_name"] == "UYU CORPORACION S.A. DE C.V."
    assert uyu["base_currency"] == "MXN"
    assert uyu["ending_inventory_krw"] == "50000000"
    assert uyu["ending_inventory_current_krw"] == "55000000"


def test_indonesia_holdings_use_upstream_current_value_instead_of_bad_book_field():
    holdings = normalize_holdings(indonesia_stock_ledger_rows(), as_of=date(2026, 8, 20))

    # 원화 컬럼 1,000억원은 IDR 단위가 섞인 값이므로 현재환율 평가액 80억원을 사용한다.
    assert holdings["total_krw"] == "8000000000"
    assert holdings["total_current_krw"] == "8000000000"
    assert holdings["difference_krw"] == "0"
    company = holdings["companies"][0]
    assert company["ending_inventory_krw"] == "8000000000"
    assert company["ending_inventory_current_krw"] == "8000000000"
    assert company["ending_inventory_local"] == "100000000000"
    assert company["valuation_basis"] == "current_exchange_rate"
    assert company["exchange_rate_unit"] == "IDR"
    assert company["exchange_rate_krw"] == "0.08"
    assert [warehouse["ending_inventory_krw"] for warehouse in company["warehouses"]] == [
        "4800000000",
        "3200000000",
    ]
    assert [warehouse["ending_inventory_local"] for warehouse in company["warehouses"]] == [
        "60000000000",
        "40000000000",
    ]


def test_indonesia_holdings_current_value_failure_never_falls_back_to_bad_cms_krw(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.services.corporate_inventory.fetch_corporate_stock_ledger",
        lambda as_of: indonesia_stock_ledger_rows(),
    )
    monkeypatch.setattr(
        "backend.services.corporate_inventory.fetch_corporate_in_transit",
        lambda as_of: [],
    )
    broken = indonesia_stock_ledger_rows()
    broken[0]["amount_krw_current"] = None
    monkeypatch.setattr(
        "backend.services.corporate_inventory.fetch_corporate_stock_ledger",
        lambda as_of: broken,
    )

    payload = corporate_inventory_payload(as_of=date(2026, 8, 20))

    assert payload["holdings"] == {
        "status": "failed",
        "as_of": "2026-08-20",
        "message": "보유 재고를 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    }
    assert payload["total_inventory"]["status"] == "unavailable"


def test_source_failure_is_exposed_as_refresh_failed_not_zero(monkeypatch: pytest.MonkeyPatch):
    def failing_fetch(_: str) -> list[dict[str, object]]:
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr("backend.services.corporate_inventory.fetch_corporate_stock_ledger", failing_fetch)
    monkeypatch.setattr("backend.services.corporate_inventory.fetch_corporate_in_transit", lambda as_of: in_transit_rows())
    payload = corporate_inventory_payload(as_of=date(2026, 8, 20))

    assert payload["holdings"] == {
        "status": "failed",
        "as_of": "2026-08-20",
        "message": "보유 재고를 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    }
    assert "total_krw" not in payload["holdings"]
    assert payload["total_inventory"]["status"] == "unavailable"


def test_transit_groups_each_destination_by_transport_mode_and_currency(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "backend.services.corporate_inventory.fetch_corporate_stock_ledger",
        lambda as_of: stock_ledger_rows(),
    )
    monkeypatch.setattr("backend.services.corporate_inventory.fetch_corporate_in_transit", lambda as_of: in_transit_rows())
    payload = corporate_inventory_payload(as_of=date(2026, 8, 20))

    transit = payload["in_transit"]
    assert transit["status"] == "ready"
    # 미국: EUR 10,000 × 출고일 환율 1,500 + EUR 5,000 × 출고일 환율 1,800
    #       + KPOP KRW 500만 = 2,900만원. 일본: JPY 100,000 × 출고일 환율 9 = 90만원.
    assert transit["total_krw"] == "29900000"
    assert transit["destinations"] == [
        {
            "destination_code": "CO000007",
            "destination_name": "미국 법인",
            "quantity": "6",
            "total_krw": "29000000",
            "currencies": [
                {
                    "currency_code": "EUR",
                    "original_amount": "15000",
                    "quantity": "5",
                    "converted_krw": "24000000",
                    "exchange_rate_basis": "invoice_contract",
                    "exchange_rates": [
                        {"rate": "1500", "rate_date": "2026-07-01"},
                        {"rate": "1800", "rate_date": "2026-07-15"},
                    ],
                },
                {
                    "currency_code": "KRW",
                    "original_amount": "5000000",
                    "quantity": "1",
                    "converted_krw": "5000000",
                    "exchange_rate_basis": "krw",
                    "exchange_rates": [],
                },
            ],
            "transport_modes": [
                {
                    "transport_mode_code": "SEA",
                    "transport_mode_name": "해운",
                    "transport_mode_sources": ["INVOICE_REMARK"],
                    "quantity": "5",
                    "total_krw": "24000000",
                    "currencies": [
                        {
                            "currency_code": "EUR",
                            "original_amount": "15000",
                            "quantity": "5",
                            "converted_krw": "24000000",
                            "exchange_rate_basis": "invoice_contract",
                            "exchange_rates": [
                                {"rate": "1500", "rate_date": "2026-07-01"},
                                {"rate": "1800", "rate_date": "2026-07-15"},
                            ],
                        },
                    ],
                },
                {
                    "transport_mode_code": "AIR",
                    "transport_mode_name": "항공",
                    "transport_mode_sources": ["INVOICE_REMARK"],
                    "quantity": "1",
                    "total_krw": "5000000",
                    "currencies": [
                        {
                            "currency_code": "KRW",
                            "original_amount": "5000000",
                            "quantity": "1",
                            "converted_krw": "5000000",
                            "exchange_rate_basis": "krw",
                            "exchange_rates": [],
                        },
                    ],
                },
            ],
        },
        {
            "destination_code": "JP",
            "destination_name": "일본 법인",
            "quantity": "7",
            "total_krw": "900000",
            "currencies": [
                {
                    "currency_code": "JPY",
                    "original_amount": "100000",
                    "quantity": "7",
                    "converted_krw": "900000",
                    "exchange_rate_basis": "invoice_contract",
                    "exchange_rates": [{"rate": "9", "rate_date": "2026-08-01"}],
                },
            ],
            "transport_modes": [
                {
                    "transport_mode_code": "SEA",
                    "transport_mode_name": "해운",
                    "transport_mode_sources": ["INVOICE_REMARK"],
                    "quantity": "7",
                    "total_krw": "900000",
                    "currencies": [
                        {
                            "currency_code": "JPY",
                            "original_amount": "100000",
                            "quantity": "7",
                            "converted_krw": "900000",
                            "exchange_rate_basis": "invoice_contract",
                            "exchange_rates": [{"rate": "9", "rate_date": "2026-08-01"}],
                        },
                    ],
                },
            ],
        },
    ]
    assert payload["total_inventory"] == {"status": "ready", "total_krw": "3029900000"}


def test_transit_sums_business_group_rows_split_from_the_same_invoice():
    rows = [
        {
            "dest_comp_cd": "CO000007",
            "dest_comp_nm": "미국 법인",
            "invoices": [
                {
                    "invc_no": "SPLIT-INVOICE",
                    "biz_gbn": "COSMETIC",
                    "currency": "KRW",
                    "amount": "1000000",
                    "amount_krw": "1000000",
                    "qty": "10",
                    "transport_mode": "SEA",
                    "transport_mode_source": "INVOICE_REMARK",
                },
                {
                    "invc_no": "SPLIT-INVOICE",
                    "biz_gbn": "KPOP",
                    "currency": "KRW",
                    "amount": "200000",
                    "amount_krw": "200000",
                    "qty": "2",
                    "transport_mode": "SEA",
                    "transport_mode_source": "INVOICE_REMARK",
                },
            ],
        }
    ]

    transit = normalize_in_transit(rows, as_of=date(2026, 8, 25))

    assert transit["total_krw"] == "1200000"
    assert transit["destinations"][0]["quantity"] == "12"
    assert transit["destinations"][0]["total_krw"] == "1200000"


def test_transit_unknown_ship_via_remains_in_review_group():
    rows = in_transit_rows()
    rows[0]["invoices"][0].pop("remark")
    rows[0]["invoices"][1].pop("remark")
    rows[0]["invoices"][0].pop("transport_mode")
    rows[0]["invoices"][0].pop("transport_mode_source")
    rows[0]["invoices"][1].pop("transport_mode")
    rows[0]["invoices"][1].pop("transport_mode_source")
    rows[0]["invoices"][0]["ship_via"] = "unknown"
    rows[0]["invoices"][1].pop("ship_via")
    transit = normalize_in_transit(rows, as_of=date(2026, 8, 20))

    usa = next(destination for destination in transit["destinations"] if destination["destination_code"] == "CO000007")
    assert usa["total_krw"] == "29000000"
    assert usa["quantity"] == "6"
    assert usa["transport_modes"] == [
        {
            "transport_mode_code": "REVIEW",
            "transport_mode_name": "운송수단 확인필요",
            "transport_mode_sources": ["UNRESOLVED"],
            "quantity": "5",
            "total_krw": "24000000",
            "currencies": [
                {
                    "currency_code": "EUR",
                    "original_amount": "15000",
                    "quantity": "5",
                    "converted_krw": "24000000",
                    "exchange_rate_basis": "invoice_contract",
                    "exchange_rates": [
                        {"rate": "1500", "rate_date": "2026-07-01"},
                        {"rate": "1800", "rate_date": "2026-07-15"},
                    ],
                },
            ],
        },
        {
            "transport_mode_code": "AIR",
            "transport_mode_name": "항공",
            "transport_mode_sources": ["INVOICE_REMARK"],
            "quantity": "1",
            "total_krw": "5000000",
            "currencies": [
                {
                    "currency_code": "KRW",
                    "original_amount": "5000000",
                    "quantity": "1",
                    "converted_krw": "5000000",
                    "exchange_rate_basis": "krw",
                    "exchange_rates": [],
                },
            ],
        },
    ]


def test_transit_uses_ship_via_only_when_remark_has_no_transport_mode():
    rows = in_transit_rows()
    rows[0]["invoices"] = [
        {
            "biz_gbn": "COSMETIC",
            "currency": "KRW",
            "amount": "5000000",
            "amount_krw": "5000000",
            "ow_dt": "2026-07-20",
            "qty": "1",
            "remark": "입고 일정 확인",
            "ship_via": "OT",
        }
    ]
    transit = normalize_in_transit(rows, as_of=date(2026, 8, 20))

    usa = next(destination for destination in transit["destinations"] if destination["destination_code"] == "CO000007")
    assert usa["transport_modes"] == [
        {
            "transport_mode_code": "SEA",
            "transport_mode_name": "해운",
            "transport_mode_sources": ["SHIP_VIA"],
            "quantity": "1",
            "total_krw": "5000000",
            "currencies": [
                {
                    "currency_code": "KRW",
                    "original_amount": "5000000",
                    "quantity": "1",
                    "converted_krw": "5000000",
                    "exchange_rate_basis": "krw",
                    "exchange_rates": [],
                },
            ],
        },
    ]


def test_transit_uses_api_transport_mode_before_raw_invoice_fields():
    rows = in_transit_rows()
    rows[0]["invoices"][0].update(
        {
            "remark": "철송 RAIL",
            "ship_via": "HCR",
            "transport_mode": "SEA",
            "transport_mode_source": "INVOICE_REMARK",
        }
    )
    rows[0]["invoices"][1].update(
        {
            "remark": "해운 SEA",
            "ship_via": "OT",
            "transport_mode": "OTHER",
            "transport_mode_source": "UNRESOLVED",
        }
    )
    transit = normalize_in_transit(rows, as_of=date(2026, 8, 20))

    usa = next(destination for destination in transit["destinations"] if destination["destination_code"] == "CO000007")
    modes = {mode["transport_mode_code"]: mode for mode in usa["transport_modes"]}
    assert modes["SEA"]["transport_mode_name"] == "해운"
    assert modes["SEA"]["transport_mode_sources"] == ["INVOICE_REMARK"]
    assert modes["SEA"]["total_krw"] == "15000000"
    assert modes["REVIEW"] == {
        "transport_mode_code": "REVIEW",
        "transport_mode_name": "운송수단 확인필요",
        "transport_mode_sources": ["UNRESOLVED"],
        "quantity": "2",
        "total_krw": "9000000",
        "currencies": [
            {
                "currency_code": "EUR",
                "original_amount": "5000",
                "quantity": "2",
                "converted_krw": "9000000",
                    "exchange_rate_basis": "invoice_contract",
                "exchange_rates": [{"rate": "1800", "rate_date": "2026-07-15"}],
            },
        ],
    }


def test_transit_missing_cms_krw_amount_never_returns_partial_total(monkeypatch: pytest.MonkeyPatch):
    broken = in_transit_rows()
    broken[0]["invoices"][0].pop("amount_krw")
    monkeypatch.setattr("backend.services.corporate_inventory.fetch_corporate_stock_ledger", lambda as_of: stock_ledger_rows())
    monkeypatch.setattr("backend.services.corporate_inventory.fetch_corporate_in_transit", lambda as_of: broken)

    payload = corporate_inventory_payload(as_of=date(2026, 8, 20))

    assert payload["in_transit"] == {
        "status": "failed",
        "as_of": "2026-08-20",
        "message": "운송중 재고를 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    }
    assert payload["total_inventory"]["status"] == "unavailable"


def test_in_transit_missing_currency_is_not_silently_dropped(monkeypatch: pytest.MonkeyPatch):
    broken = in_transit_rows()
    broken[0]["invoices"] = [
        {"biz_gbn": "COSMETIC", "currency": None, "amount": "100", "amount_krw": "150000", "qty": "1"}
    ]

    with pytest.raises(ValueError, match="통화 코드"):
        normalize_in_transit(broken, as_of=date(2026, 8, 20))


@pytest.mark.parametrize("biz_gbn", [None, "", "UNKNOWN"])
def test_in_transit_requires_a_known_business_group(biz_gbn: object):
    broken = in_transit_rows()
    broken[0]["invoices"][0]["biz_gbn"] = biz_gbn

    with pytest.raises(ValueError, match="biz_gbn"):
        normalize_in_transit(broken, as_of=date(2026, 8, 20))


def test_stock_ledger_request_uses_same_kst_date_for_the_required_range(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    def fake_fetch(path: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
        captured["path"] = path
        captured["params"] = params
        return []

    monkeypatch.setattr("backend.cms_client._fetch_list", fake_fetch)

    assert fetch_corporate_stock_ledger("2026-08-20") == []
    assert captured == {
        "path": "/esm/stock-ledger",
        "params": {"start_date": "2026-08-20", "end_date": "2026-08-20", "lang": "KOR"},
    }


def test_in_transit_request_uses_the_kst_date_as_packing_end_date(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    def fake_fetch(path: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
        captured["path"] = path
        captured["params"] = params
        return []

    monkeypatch.setattr("backend.cms_client._fetch_list", fake_fetch)

    assert fetch_corporate_in_transit("2026-08-20") == []
    assert captured == {
        "path": "/esm/in-transit",
        "params": {"start_date": "2026-01-01", "end_date": "2026-08-20", "biz_gbn": "ALL"},
    }


def test_exim_rate_normalizes_hundred_unit_currency(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, str]]:
            return [{"cur_unit": "JPY(100)", "deal_bas_r": "900"}]

    monkeypatch.setenv("KOREAEXIM_API_KEY", "test-key")
    monkeypatch.setattr("core.kpi.korea_today", lambda: date(2026, 8, 20))
    monkeypatch.setattr("core.kpi.requests.get", lambda *args, **kwargs: FakeResponse())

    rates = get_exim_currency_krw_rates({"JPY"})

    assert rates["JPY"].quote_unit == "JPY(100)"
    assert rates["JPY"].quote_krw == Decimal("900")
    assert rates["JPY"].krw_per_unit == Decimal("9")
