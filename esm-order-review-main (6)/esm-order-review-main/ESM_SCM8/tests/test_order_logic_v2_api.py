from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import pytest

import backend.auth.user_store as user_store_module
import backend.routers.auth as auth_router
import backend.services.auth as auth_service
from backend.auth.models import UserAccount
from backend.main import app as main_app
from backend.routers import order_logic_v2 as order_logic_router
from backend.services import order_logic_v2_jobs as jobs
from backend.services import order_logic_v2_service as service
from backend.services import order_logic_v2_store as store
from backend.services.order_logic_v2_excel import (
    AMOUNT_COLUMNS,
    BASE_COLUMNS,
)
from backend.services.order_logic_v2_source import PreparedOrderLogicSource
from core.order_logic_v2 import DEFAULT_CONFIG, REQUIRED_SALES_WEEKS
from tests.auth_helpers import TEST_PASSWORDS, TestUserStore


FIXED_VECTOR_DELTA = 45.0
FIXED_VECTOR_HISTORY = (
    (100.0 - FIXED_VECTOR_DELTA, 100.0 + FIXED_VECTOR_DELTA) * 6 + (100.0,)
)
FRESH_CACHE_INFO = {
    "hit": True,
    "source": "memory",
    "created_at": "2026-07-27T00:00:00+00:00",
    "age_seconds": 10.0,
    "ttl_seconds": 14400,
}


def _user(username: str) -> UserAccount:
    return UserAccount(
        username=username,
        password_hash="test",
        role="MASTER" if username == "adminmaster" else "TEAM",
        allowed_entities=("PL",),
        is_active=True,
        display_name=username,
        account_type="TEST",
        is_admin=username == "adminmaster",
    )


def _source_row(
    sku_code: str,
    *,
    revenue: float,
    weekly_sales=FIXED_VECTOR_HISTORY,
    validation_error: str | None = None,
) -> dict[str, object]:
    return {
        "sku_code": sku_code,
        "product_name": f"Product {sku_code}",
        "brand": "BRAND",
        "weekly_sales": list(weekly_sales),
        "revenue": revenue,
        "incoming_qty": 0.0,
        "eu_available_qty": 0.0,
        "transit_qty": 0.0,
        "local_available_qty": 0.0,
        "next_eta": None,
        "unit_price_eur": 4.0,
        "unit_price_krw": 6_400.0,
        "warnings": [],
        "validation_error": validation_error,
    }


def _prepared_source() -> PreparedOrderLogicSource:
    return PreparedOrderLogicSource(
        period_start=date(2026, 4, 27),
        period_end=date(2026, 7, 26),
        rows=(
            _source_row("SKU_MAJOR", revenue=80),
            _source_row(
                "SKU_MINOR",
                revenue=20,
                weekly_sales=(0.0,) * REQUIRED_SALES_WEEKS,
            ),
            _source_row(
                "SKU_INVALID",
                revenue=1,
                validation_error="음수 판매량",
            ),
        ),
        source_counts={"sales_detail": 100, "eu_stock": 3},
        warnings=("품절 잠재수요는 보정하지 않습니다.",),
    )


def _result(
    applied_mode: str = "CASH",
    *,
    config=DEFAULT_CONFIG,
    preview: bool = False,
) -> dict[str, object]:
    return service.build_order_logic_v2_result(
        _prepared_source(),
        cache_info=FRESH_CACHE_INFO,
        applied_mode=applied_mode,
        job_id="order2_test",
        as_of="2026-07-27",
        config=config,
        preview=preview,
    )


def _row(payload: dict[str, object], sku_code: str) -> dict[str, object]:
    rows = payload["rows"]
    assert isinstance(rows, list)
    return next(row for row in rows if row["sku_code"] == sku_code)


def test_one_snapshot_produces_both_modes_and_applied_mode_is_official():
    payload = _result("CASH")

    assert payload["result_schema_version"] == service.RESULT_SCHEMA_VERSION
    assert payload["duration_unit"] == "CALENDAR_DAY"
    assert payload["period_unit"] == "week"
    assert payload["demand_period_count"] == REQUIRED_SALES_WEEKS
    assert payload["observation_window_days"] == 91
    assert payload["demand_grain"] == "WEEK_7D"
    assert payload["demand_grain_days"] == 7
    assert payload["applied_mode"] == "CASH"
    assert payload["policy_mode"] == "CASH"
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, dict)
    cash = scenarios["CASH"]
    shortage = scenarios["SHORTAGE"]
    assert cash["source_snapshot_id"] == shortage["source_snapshot_id"]
    assert cash["source_snapshot_id"] == payload["source_snapshot_id"]

    official = _row(payload, "SKU_MAJOR")
    cash_major = next(
        row for row in cash["rows"] if row["sku_code"] == "SKU_MAJOR"
    )
    shortage_major = next(
        row for row in shortage["rows"] if row["sku_code"] == "SKU_MAJOR"
    )
    assert official == cash_major
    assert official["policy_mode"] == "CASH"
    assert official["order_signal"] == "발주"
    assert official["protection_days"] == pytest.approx(official["protection_weeks"] * 7)
    assert official["review_days"] == pytest.approx(
        official["protection_days"] - official["lead_time_days"]
    )
    assert official["lead_time_sigma_days"] == pytest.approx(
        official["lead_time_sigma_weeks"] * 7
    )
    assert shortage_major["policy_mode"] == "SHORTAGE"
    assert shortage_major["target_stock"] > cash_major["target_stock"]

    invalid = _row(payload, "SKU_INVALID")
    assert invalid["calculable"] is False
    assert invalid["data_status"] == "계산불가"
    assert invalid["validation_error"] == "음수 판매량"
    assert invalid["suggested_qty"] is None
    assert invalid["upper_suggested_qty"] is None
    assert invalid["order_signal"] == "-"

    # The newest core contract grades the cutoff-crossing row MAJOR by using
    # cumulative revenue before the current row.
    assert official["grade"] == "MAJOR"
    assert official["upper_suggested_qty"] == official["suggested_qty"]
    # Invalid calculation rows still belong to the revenue population. Their
    # revenue can therefore move the next calculable SKU across the cutoff.
    assert _row(payload, "SKU_MINOR")["grade"] == "MAJOR"
    assert _row(payload, "SKU_INVALID")["grade"] == "MINOR"
    assert _row(payload, "SKU_MINOR")["order_signal"] == "-"
    assert payload["settings"]["lt_air_days"] == 16.4
    assert payload["settings"]["sigma_l_air_weeks"] == 0.68


def test_snapshot_id_ignores_lead_time_calculation_timestamp():
    prepared = _prepared_source()
    first_audit = {
        "response_hash": "same-response",
        "calculated_at": "2026-08-04T10:00:00+09:00",
        "stats": {"AIR": {"sample_size": 3, "mean_days": 12.0}},
    }
    second_audit = {
        **first_audit,
        "calculated_at": "2026-08-04T10:05:00+09:00",
    }

    assert service._source_snapshot_id(
        prepared, FRESH_CACHE_INFO, first_audit
    ) == service._source_snapshot_id(prepared, FRESH_CACHE_INFO, second_audit)


def test_service_rows_cover_the_excel_display_contract():
    payload = _result("CASH")
    required_keys = {
        column.key
        for column in BASE_COLUMNS + AMOUNT_COLUMNS
        if not column.key.endswith("_krw")
    }

    assert payload["rows"]
    for row in payload["rows"]:
        assert required_keys <= set(row)
    for scenario in payload["scenarios"].values():
        for row in scenario["rows"]:
            assert required_keys <= set(row)


def test_custom_per_run_config_is_applied_to_both_modes_and_preserved():
    config = replace(
        DEFAULT_CONFIG,
        lt_air_days=9.5,
        lt_rail_days=14.0,
        lt_sea_days=21.0,
        sigma_l_air_weeks=0.4,
        sigma_l_rail_weeks=0.8,
        sigma_l_sea_weeks=1.2,
        cover_weeks=3.0,
    )

    payload = _result("CASH", config=config, preview=True)
    scenarios = payload["scenarios"]
    cash = next(
        row for row in scenarios["CASH"]["rows"] if row["sku_code"] == "SKU_MAJOR"
    )
    shortage = next(
        row
        for row in scenarios["SHORTAGE"]["rows"]
        if row["sku_code"] == "SKU_MAJOR"
    )

    assert payload["preview"] is True
    assert payload["settings"] == config.as_dict()
    assert cash["lead_time_days"] == 14
    assert cash["lead_time_sigma_weeks"] == 0.8
    assert cash["protection_weeks"] == 5
    assert shortage["lead_time_days"] == 21
    assert shortage["lead_time_sigma_weeks"] == 1.2
    assert shortage["protection_weeks"] == 6
    assert cash["layer3"] == shortage["layer3"] == 300


def test_usa_lead_time_api_resolves_cash_air_and_shortage_sea(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_fetch(entity_code, **kwargs):
        calls.append({"entity_code": entity_code, **kwargs})
        return [
            {"pckg_no": "A1", "transport_mode": "AIR", "ow_dt": "2026-06-01", "iw_dt": "2026-06-06", "ow_to_iw_days": 5},
            {"pckg_no": "A2", "transport_mode": "항공", "ow_dt": "2026-06-01", "iw_dt": "2026-06-08", "ow_to_iw_days": 7},
            {"pckg_no": "S1", "transport_mode": "SEA", "ow_dt": "2026-06-01", "iw_dt": "2026-06-21", "ow_to_iw_days": 20},
            {"pckg_no": "S2", "transport_mode": "해운", "ow_dt": "2026-06-01", "iw_dt": "2026-06-25", "ow_to_iw_days": 24},
        ]

    monkeypatch.setattr(service, "fetch_cms_lead_time", fake_fetch)

    config, audit = service._config_with_entity_lead_times(
        DEFAULT_CONFIG,
        entity_code="USA",
        as_of="2026-07-27",
    )

    assert config.cash_transport_mode == "AIR"
    assert config.shortage_transport_mode == "SEA"
    assert config.lt_air_days == 6
    assert config.lt_sea_days == 22
    assert audit is not None
    assert audit["modes"]["AIR"]["sample_size"] == 2
    assert calls[0]["include_in_transit"] is False


def test_eu_lead_time_api_resolves_cash_rail_and_shortage_sea(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_fetch(entity_code, **kwargs):
        calls.append({"entity_code": entity_code, **kwargs})
        return [
            {"pckg_no": "R1", "transport_mode": "RAIL", "ow_dt": "2026-06-01", "iw_dt": "2026-07-06", "ow_to_iw_days": 35},
            {"pckg_no": "R2", "transport_mode": "철송", "ow_dt": "2026-06-01", "iw_dt": "2026-07-16", "ow_to_iw_days": 45},
            {"pckg_no": "S1", "transport_mode": "SEA", "ow_dt": "2026-06-01", "iw_dt": "2026-08-10", "ow_to_iw_days": 70},
            {"pckg_no": "S2", "transport_mode": "해운", "ow_dt": "2026-06-01", "iw_dt": "2026-08-14", "ow_to_iw_days": 74},
            # The EU feed also carries air and truck shipments. Neither mode is a
            # V2 policy transport, so they must not shift the measured values.
            {"pckg_no": "A1", "transport_mode": "항공", "ow_dt": "2026-06-01", "iw_dt": "2026-06-03", "ow_to_iw_days": 2},
            {"pckg_no": "T1", "transport_mode": "트럭", "ow_dt": "2026-06-01", "iw_dt": "2026-06-04", "ow_to_iw_days": 3},
        ]

    monkeypatch.setattr(service, "fetch_cms_lead_time", fake_fetch)

    config, audit = service._config_with_entity_lead_times(
        DEFAULT_CONFIG,
        entity_code="PL",
        as_of="2026-08-20",
    )

    assert config.cash_transport_mode == "RAIL"
    assert config.shortage_transport_mode == "SEA"
    assert config.lt_rail_days == 40
    assert config.lt_sea_days == 72
    # EU air is not a policy transport, so it keeps the reviewed fixed value.
    assert config.lt_air_days == DEFAULT_CONFIG.lt_air_days
    assert config.sigma_l_air_weeks == DEFAULT_CONFIG.sigma_l_air_weeks
    assert audit is not None
    assert audit["entity_code"] == "PL"
    assert set(audit["modes"]) == {"RAIL", "SEA"}
    assert audit["modes"]["RAIL"]["sample_size"] == 2
    assert audit["policy_transport_modes"] == {"CASH": "RAIL", "SHORTAGE": "SEA"}
    assert calls[0]["entity_code"] == "PL"
    assert calls[0]["include_in_transit"] is False


def test_eu_lead_time_failure_blocks_the_calculation(monkeypatch):
    def fake_fetch(entity_code, **kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(service, "fetch_cms_lead_time", fake_fetch)

    with pytest.raises(service.OrderLogicV2SourceUnavailable, match="EU 운송 리드타임"):
        service._config_with_entity_lead_times(
            DEFAULT_CONFIG,
            entity_code="PL",
            as_of="2026-08-20",
        )


def test_hq_lead_time_does_not_fall_back_to_pl_policy() -> None:
    with pytest.raises(service.OrderLogicV2SourceUnavailable, match="HQ 법인"):
        service._config_with_entity_lead_times(
            DEFAULT_CONFIG,
            entity_code="HQ",
            as_of="2026-08-20",
        )


def test_hq_result_does_not_fall_back_to_eur_or_pl_source() -> None:
    with pytest.raises(service.OrderLogicV2SourceUnavailable, match="결과 원천·통화"):
        service.build_order_logic_v2_result(
            _prepared_source(),
            cache_info=FRESH_CACHE_INFO,
            applied_mode="SHORTAGE",
            job_id="hq-blocked",
            as_of="2026-08-20",
            entity_code="HQ",
        )


def test_warning_order_signal_is_canonical_check_then_order():
    prepared = PreparedOrderLogicSource(
        period_start=date(2026, 4, 27),
        period_end=date(2026, 7, 26),
        rows=(
            _source_row(
                "SKU_INTERMITTENT",
                revenue=100,
                weekly_sales=(10.0,) * 6 + (0.0,) * (REQUIRED_SALES_WEEKS - 6),
            ),
        ),
        source_counts={"sales_detail": 6},
        warnings=(),
    )
    payload = service.build_order_logic_v2_result(
        prepared,
        cache_info=FRESH_CACHE_INFO,
        applied_mode="CASH",
        job_id="warning-job",
        as_of="2026-07-27",
    )

    row = _row(payload, "SKU_INTERMITTENT")
    assert row["data_status"] == "⚠확인(간헐)"
    assert row["suggested_qty"] > 0
    assert row["order_signal"] == "확인후발주"


def test_stale_cms_snapshot_is_refreshed_then_blocked_if_still_over_24h(
    monkeypatch,
):
    calls: list[bool] = []

    def stale_fetch(**kwargs):
        calls.append(bool(kwargs.get("force_refresh")))
        return (
            {},
            {
                "created_at": "2026-07-25T00:00:00+00:00",
                "age_seconds": service.MAX_SOURCE_AGE_SECONDS + 1,
            },
            object(),
        )

    monkeypatch.setattr(service, "fetch_cached_cms_raw_data", stale_fetch)

    with pytest.raises(service.OrderLogicV2SourceUnavailable, match="24시간"):
        service.calculate_order_logic_v2_from_cms(
            as_of="2026-07-27",
            applied_mode="CASH",
            job_id="stale-job",
        )
    assert calls == [False, True]


def test_cms_fetch_failure_blocks_calculation_without_exposing_upstream_text(
    monkeypatch,
):
    def failed_fetch(**_kwargs):
        raise RuntimeError("secret upstream credential")

    monkeypatch.setattr(service, "fetch_cached_cms_raw_data", failed_fetch)

    with pytest.raises(service.OrderLogicV2SourceUnavailable) as exc_info:
        service.calculate_order_logic_v2_from_cms(
            as_of="2026-07-27",
            applied_mode="CASH",
            job_id="failed-job",
        )
    assert "secret upstream credential" not in str(exc_info.value)


def test_quantity_override_requires_memo_and_integer_quantity():
    payload = _result("CASH")
    suggested = float(_row(payload, "SKU_MAJOR")["suggested_qty"])
    assert suggested == 1152

    with pytest.raises(service.OrderLogicV2DecisionError, match="메모"):
        service.apply_order_decision_overrides(
            payload,
            [
                {
                    "sku_code": "SKU_MAJOR",
                    "confirmed_qty": 1000,
                    "memo": "",
                }
            ],
        )

    with pytest.raises(service.OrderLogicV2DecisionError, match="정수"):
        service.apply_order_decision_overrides(
            payload,
            [
                {
                    "sku_code": "SKU_MAJOR",
                    "confirmed_qty": 950.5,
                    "memo": "브랜드 협의",
                }
            ],
        )

    exported = service.apply_order_decision_overrides(
        payload,
        [
            {
                "sku_code": "SKU_MAJOR",
                "confirmed_qty": 1000,
                "memo": "브랜드 협의",
            }
        ],
    )
    changed = _row(exported, "SKU_MAJOR")
    assert changed["confirmed_qty"] == 1000
    assert changed["memo"] == "브랜드 협의"
    assert changed["confirmed_amount_eur"] == 4000
    assert exported["decision_override_count"] == 1

    # Equal-to-suggestion decisions do not need a memo.
    unchanged = service.apply_order_decision_overrides(
        payload,
        [
            {
                "sku_code": "SKU_MAJOR",
                "confirmed_qty": suggested,
            }
        ],
    )
    assert _row(unchanged, "SKU_MAJOR")["memo"] is None


def test_export_row_selection_filters_and_preserves_visible_order():
    payload = _result("CASH")

    selected = service.apply_order_decision_overrides(
        payload,
        [],
        row_ids=["SKU_MINOR", "SKU_MAJOR"],
    )

    assert [row["sku_code"] for row in selected["rows"]] == [
        "SKU_MINOR",
        "SKU_MAJOR",
    ]
    assert selected["export_filter_applied"] is True
    assert selected["export_row_count"] == 2
    assert selected["summary"]["total_skus"] == 2

    with pytest.raises(service.OrderLogicV2DecisionError, match="없는 SKU"):
        service.apply_order_decision_overrides(
            payload,
            [],
            row_ids=["UNKNOWN"],
        )
    with pytest.raises(service.OrderLogicV2DecisionError, match="중복"):
        service.apply_order_decision_overrides(
            payload,
            [],
            row_ids=["SKU_MAJOR", "SKU_MAJOR"],
        )
    with pytest.raises(service.OrderLogicV2DecisionError, match="선택되지 않은"):
        service.apply_order_decision_overrides(
            payload,
            [
                {
                    "sku_code": "SKU_MAJOR",
                    "confirmed_qty": 1100,
                }
            ],
            row_ids=["SKU_MINOR"],
        )


def test_order_analysis_response_and_excel_show_amounts_to_all_accounts(
    monkeypatch,
):
    payload = _result("CASH")
    limited = _user("eu_manager")
    allowed = _user("adminmaster")

    limited_payload = service.payload_visible_to_user(payload, limited)
    assert _row(limited_payload, "SKU_MAJOR")["unit_price_eur"] == 4
    assert _row(limited_payload, "SKU_MAJOR")["suggested_amount_eur"] == 4608
    assert limited_payload["summary"]["suggested_amount_eur_total"] > 0
    assert _row(limited_payload, "SKU_MAJOR")["unit_price_krw"] == 6400
    assert _row(limited_payload, "SKU_MAJOR")["suggested_amount_krw"] > 0

    full = service.payload_visible_to_user(payload, allowed)
    assert _row(full, "SKU_MAJOR")["unit_price_eur"] == 4
    assert _row(full, "SKU_MAJOR")["suggested_amount_eur"] == 4608

    captured: list[tuple[dict[str, object], bool]] = []

    def fake_owned(_job_id, _client_id):
        return {"status": "succeeded", "result": payload}

    def fake_excel(result, include_amounts, entity_code="PL"):
        captured.append((result, include_amounts))
        return b"PK-test"

    monkeypatch.setattr(service, "owned_order_logic_v2_job", fake_owned)
    monkeypatch.setattr(service, "generate_order_logic_v2_excel", fake_excel)
    service.build_order_logic_v2_export(
        job_id="job",
        client_id="owner",
        user=limited,
        overrides=[],
        export_mode="CASH",
    )
    limited_excel_payload, include_amounts = captured[-1]
    assert include_amounts is True
    assert _row(limited_excel_payload, "SKU_MAJOR")["unit_price_eur"] == 4
    assert _row(limited_excel_payload, "SKU_MAJOR")["unit_price_krw"] == 6400
    assert limited_excel_payload["exchange_rate_source"] == "CMS_STOCK_DAILY_RATE"

    service.build_order_logic_v2_export(
        job_id="job",
        client_id="owner",
        user=allowed,
        overrides=[],
        export_mode="CASH",
    )
    allowed_excel_payload, include_amounts = captured[-1]
    assert include_amounts is True
    assert _row(allowed_excel_payload, "SKU_MAJOR")["unit_price_eur"] == 4
    assert _row(allowed_excel_payload, "SKU_MAJOR")["unit_price_krw"] == 6400
    assert allowed_excel_payload["exchange_rate_source"] == "CMS_STOCK_DAILY_RATE"


def test_export_uses_the_explicitly_selected_scenario(monkeypatch):
    payload = _result("CASH")
    generated: list[dict[str, object]] = []
    monkeypatch.setattr(
        service,
        "owned_order_logic_v2_job",
        lambda _job_id, _client_id: {"status": "succeeded", "result": payload},
    )
    monkeypatch.setattr(
        service,
        "generate_order_logic_v2_excel",
        lambda result, include_amounts, entity_code="PL": (
            generated.append(result) or b"PK-shortage"
        ),
    )

    content, filename = service.build_order_logic_v2_export(
        job_id="job",
        client_id="owner",
        user=_user("eu_manager"),
        overrides=[],
        export_mode="SHORTAGE",
    )

    assert content == b"PK-shortage"
    assert "_shortage_" in filename
    exported = generated[-1]
    assert exported["official_applied_mode"] == "CASH"
    assert exported["policy_mode"] == "SHORTAGE"
    assert all(row["policy_mode"] == "SHORTAGE" for row in exported["rows"])


def test_job_ownership_is_client_id_scoped(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_order_logic_v2_job",
        lambda _job_id: {
            "job_id": "owned",
            "status": "succeeded",
            "client_id": "owner-client",
            "result": _result(),
        },
    )

    assert (
        service.owned_order_logic_v2_job("owned", "owner-client")["job_id"]
        == "owned"
    )
    with pytest.raises(Exception) as exc_info:
        service.owned_order_logic_v2_job("owned", "other-client")
    assert getattr(exc_info.value, "status_code", None) == 403


def test_export_recovers_matching_latest_result_after_job_registry_restart(
    monkeypatch,
):
    payload = _result()
    generated: list[dict[str, object]] = []

    def missing_job(_job_id, _client_id):
        raise HTTPException(status_code=404, detail="missing")

    monkeypatch.setattr(service, "owned_order_logic_v2_job", missing_job)
    monkeypatch.setattr(
        service,
        "latest_order_logic_v2_result",
        lambda client_id, entity_code: (
            payload if (client_id, entity_code) == ("owner-client", "PL") else None
        ),
    )
    monkeypatch.setattr(
        service,
        "generate_order_logic_v2_excel",
        lambda result, include_amounts, entity_code="PL": (
            generated.append(result) or b"PK-recovered"
        ),
    )

    content, filename = service.build_order_logic_v2_export(
        job_id="order2_test",
        client_id="owner-client",
        user=_user("adminmaster"),
        overrides=[],
        export_mode="CASH",
    )

    assert content == b"PK-recovered"
    assert filename == "PL_order_logic_v2_cash_order2_test.xlsx"
    assert generated[-1]["job_id"] == "order2_test"


def test_export_does_not_recover_a_different_latest_job(monkeypatch):
    payload = _result()

    def missing_job(_job_id, _client_id):
        raise HTTPException(status_code=404, detail="missing")

    monkeypatch.setattr(service, "owned_order_logic_v2_job", missing_job)
    monkeypatch.setattr(
        service,
        "latest_order_logic_v2_result",
        lambda _client_id, _entity_code: payload,
    )

    with pytest.raises(HTTPException) as exc_info:
        service.build_order_logic_v2_export(
            job_id="other-job",
            client_id="owner-client",
            user=_user("adminmaster"),
            overrides=[],
            export_mode="CASH",
        )

    assert getattr(exc_info.value, "status_code", None) == 404


def test_previous_period_contract_is_not_presented_as_current(monkeypatch):
    legacy = _result()
    legacy["result_schema_version"] = 5
    monkeypatch.setattr(
        service,
        "load_latest_order_logic_v2_result",
        lambda _client_id, _entity_code: legacy,
    )

    assert service.latest_order_logic_v2_result("owner-client", "PL") is None


def test_latest_result_is_rejected_when_its_entity_does_not_match(monkeypatch):
    payload = _result()
    calls: list[tuple[str, str]] = []

    def load_latest(client_id: str, entity_code: str):
        calls.append((client_id, entity_code))
        return payload

    monkeypatch.setattr(service, "load_latest_order_logic_v2_result", load_latest)

    assert service.latest_order_logic_v2_result("owner-client", "PL") == payload
    assert service.latest_order_logic_v2_result("owner-client", "HQ") is None
    assert calls == [("owner-client", "PL"), ("owner-client", "HQ")]


def test_latest_store_isolated_by_entity_code(monkeypatch, tmp_path):
    monkeypatch.setattr(store.persistent_state, "enabled", lambda: False)
    monkeypatch.setattr(store, "LATEST_ORDER_LOGIC_V2_DIR", tmp_path)
    payload = {"entity_code": "PL", "result_schema_version": service.RESULT_SCHEMA_VERSION}

    store.save_latest_order_logic_v2_result("owner-client", "PL", payload)

    assert store.load_latest_order_logic_v2_result("owner-client", "PL") == payload
    assert store.load_latest_order_logic_v2_result("owner-client", "HQ") is None


def test_export_rejects_result_from_a_different_entity(monkeypatch):
    monkeypatch.setattr(
        service,
        "owned_order_logic_v2_job",
        lambda _job_id, _client_id: {"status": "succeeded", "result": _result()},
    )

    with pytest.raises(HTTPException, match="다른 분석 결과") as exc_info:
        service.build_order_logic_v2_export(
            job_id="pl-job",
            client_id="owner-client",
            user=_user("adminmaster"),
            overrides=[],
            export_mode="CASH",
            entity_code="HQ",
        )

    assert exc_info.value.status_code == 409


def test_export_rejects_previous_period_contract(monkeypatch):
    legacy = _result()
    legacy["result_schema_version"] = 5
    monkeypatch.setattr(
        service,
        "owned_order_logic_v2_job",
        lambda _job_id, _client_id: {
            "status": "succeeded",
            "result": legacy,
        },
    )

    with pytest.raises(HTTPException, match="분석 실행을 다시") as exc_info:
        service.build_order_logic_v2_export(
            job_id="legacy-job",
            client_id="owner-client",
            user=_user("adminmaster"),
            overrides=[],
            export_mode="CASH",
        )

    assert exc_info.value.status_code == 409


def test_preview_and_superseded_jobs_never_publish_latest(monkeypatch):
    saved: list[tuple[str, str, dict[str, object]]] = []
    patches: list[tuple[str, dict[str, object]]] = []
    latest = {"value": True}

    def fake_calculation(**kwargs):
        return {
            "preview": bool(kwargs["preview"]),
            "applied_mode": kwargs["applied_mode"],
            "source_snapshot_id": f"snapshot-{kwargs['job_id']}",
            "rows": [],
        }

    monkeypatch.setattr(
        service,
        "calculate_order_logic_v2_from_cms",
        fake_calculation,
    )
    monkeypatch.setattr(
        service,
        "update_order_logic_v2_job",
        lambda job_id, **patch: patches.append((job_id, patch)),
    )
    monkeypatch.setattr(
        service,
        "_is_latest_order_logic_v2_job",
        lambda _job_id, _client_id, _entity_code: latest["value"],
    )
    monkeypatch.setattr(
        service,
        "save_latest_order_logic_v2_result",
        lambda client_id, entity_code, result: saved.append((client_id, entity_code, result)),
    )

    asyncio.run(
        service.run_order_logic_v2_job(
            "preview-job",
            "client",
            {
                "as_of": "2026-07-27",
                "applied_mode": "CASH",
                "preview": True,
                "settings": DEFAULT_CONFIG.as_dict(),
            },
        )
    )
    assert patches[-1][1]["status"] == "succeeded"
    assert saved == []

    asyncio.run(
        service.run_order_logic_v2_job(
            "official-job",
            "client",
            {
                "as_of": "2026-07-27",
                "applied_mode": "SHORTAGE",
                "preview": False,
                "settings": DEFAULT_CONFIG.as_dict(),
            },
        )
    )
    assert saved[-1][0] == "client"
    assert saved[-1][1] == "PL"
    assert saved[-1][2]["preview"] is False
    assert saved[-1][2]["applied_mode"] == "SHORTAGE"

    latest["value"] = False
    asyncio.run(
        service.run_order_logic_v2_job(
            "superseded-job",
            "client",
            {
                "as_of": "2026-07-27",
                "applied_mode": "CASH",
                "preview": False,
            },
        )
    )
    assert len(saved) == 1


def test_preview_job_does_not_supersede_official_job(monkeypatch):
    created: list[tuple[str, dict[str, object], bool]] = []

    def fake_create(client_id, body, *, is_latest):
        created.append((client_id, body, is_latest))
        return f"job-{len(created)}"

    async def fake_run(_job_id, _client_id, _body):
        return None

    monkeypatch.setattr(service, "create_order_logic_v2_job", fake_create)
    monkeypatch.setattr(service, "run_order_logic_v2_job", fake_run)

    async def queue_both():
        service.queue_order_logic_v2_job(
            "client",
            {
                "as_of": "2026-07-27",
                "applied_mode": "CASH",
                "preview": True,
            },
        )
        service.queue_order_logic_v2_job(
            "client",
            {
                "as_of": "2026-07-27",
                "applied_mode": "CASH",
                "preview": False,
            },
        )
        await asyncio.gather(*tuple(service._RUNNING_TASKS))

    asyncio.run(queue_both())

    assert created[0][2] is False
    assert created[1][2] is True


def test_latest_job_scope_isolated_by_entity(monkeypatch):
    monkeypatch.setattr(jobs.persistent_state, "enabled", lambda: False)
    monkeypatch.setattr(jobs, "_JOBS", {})

    pl_first = jobs.create_order_logic_v2_job(
        "client",
        {"entity_code": "PL"},
    )
    hq_first = jobs.create_order_logic_v2_job(
        "client",
        {"entity_code": "HQ"},
    )
    pl_second = jobs.create_order_logic_v2_job(
        "client",
        {"entity_code": "PL"},
    )

    assert jobs.get_order_logic_v2_job(pl_first)["is_latest"] is False
    assert jobs.get_order_logic_v2_job(pl_second)["is_latest"] is True
    assert jobs.get_order_logic_v2_job(hq_first)["is_latest"] is True


def test_database_latest_check_uses_persistent_job_flag(monkeypatch):
    monkeypatch.setattr(service.persistent_state, "enabled", lambda: True)
    monkeypatch.setattr(
        service.persistent_state,
        "job_is_latest",
        lambda job_id, scope: (job_id, scope) == ("latest-job", "client::PL"),
    )
    monkeypatch.setattr(
        service,
        "get_order_logic_v2_job",
        lambda _job_id: pytest.fail(
            "database get_job omits is_latest and must not be used"
        ),
    )

    assert service._is_latest_order_logic_v2_job("latest-job", "client", "PL") is True
    assert service._is_latest_order_logic_v2_job("older-job", "client", "PL") is False


def test_failed_source_job_reaches_terminal_503(monkeypatch):
    patches: list[dict[str, object]] = []

    def fail_calculation(**_kwargs):
        raise service.OrderLogicV2SourceUnavailable("CMS stale")

    monkeypatch.setattr(service, "calculate_order_logic_v2_from_cms", fail_calculation)
    monkeypatch.setattr(
        service,
        "update_order_logic_v2_job",
        lambda _job_id, **patch: patches.append(patch),
    )

    asyncio.run(
        service.run_order_logic_v2_job(
            "job",
            "client",
            {"as_of": "2026-07-27", "applied_mode": "CASH"},
        )
    )

    assert patches[0]["status"] == "running"
    assert patches[-1] == {
        "status": "failed",
        "status_code": 503,
        "error": "CMS stale",
    }


def test_router_exposes_contract_and_sanitizes_job_result(monkeypatch):
    app = FastAPI()
    limited = _user("eu_manager")
    queued: list[tuple[str, dict[str, object]]] = []
    exported: list[dict[str, object]] = []

    @app.middleware("http")
    async def attach_identity(request: Request, call_next):
        request.state.current_user = limited
        request.state.entity_code = "PL"
        return await call_next(request)

    app.include_router(order_logic_router.router)

    def fake_queue(client_id, body):
        queued.append((client_id, body))
        return "order2_router_test"

    monkeypatch.setattr(
        order_logic_router,
        "queue_order_logic_v2_job",
        fake_queue,
    )
    monkeypatch.setattr(
        order_logic_router,
        "owned_order_logic_v2_job",
        lambda _job_id, client_id: {
            "job_id": "order2_router_test",
            "client_id": client_id,
            "status": "succeeded",
            "result": _result(),
        },
    )
    monkeypatch.setattr(
        order_logic_router,
        "build_order_logic_v2_export",
        lambda **kwargs: (
            exported.append(kwargs) or b"PK-test",
            "filtered.xlsx",
        ),
    )

    client = TestClient(app)
    start = client.post(
        "/api/order-logic-v2/jobs",
        headers={"x-client-id": "browser-a"},
        json={"as_of": "2026-07-27", "applied_mode": "CASH"},
    )
    assert start.status_code == 202
    assert start.json() == {
        "job_id": "order2_router_test",
        "status": "queued",
    }
    assert queued[-1][0] == "eu_manager__PL__browser-a"
    assert queued[-1][1]["preview"] is False
    assert queued[-1][1]["settings"]["lt_air_days"] == 16.4
    assert queued[-1][1]["settings"]["sigma_l_air_weeks"] == 0.68

    custom_start = client.post(
        "/api/order-logic-v2/jobs",
        headers={"x-client-id": "browser-a"},
        json={
            "as_of": "2026-07-27",
            "applied_mode": "SHORTAGE",
            "preview": True,
            "settings": {
                "lt_air_days": 9.5,
                "lt_rail_days": 14,
                "lt_sea_days": 21,
                "sigma_l_air_weeks": 0.4,
                "sigma_l_rail_weeks": 0.8,
                "sigma_l_sea_weeks": 1.2,
            },
        },
    )
    assert custom_start.status_code == 403
    assert "일반계정은 적용 시나리오만 선택" in custom_start.json()["detail"]

    invalid_settings = client.post(
        "/api/order-logic-v2/jobs",
        headers={"x-client-id": "browser-a"},
        json={
            "as_of": "2026-07-27",
            "applied_mode": "CASH",
            "settings": {
                "ss_floor_weeks": 13,
                "ss_cap_weeks": 2,
            },
        },
    )
    assert invalid_settings.status_code == 422
    assert len(queued) == 1

    invalid_override = client.post(
        "/api/order-logic-v2/export",
        headers={"x-client-id": "browser-a"},
        json={
            "job_id": "order2_router_test",
            "export_mode": "CASH",
            "overrides": [
                {
                    "sku_code": "SKU_MAJOR",
                    "confirmed_qty": -1,
                }
            ],
        },
    )
    assert invalid_override.status_code == 422

    valid_export = client.post(
        "/api/order-logic-v2/export",
        headers={"x-client-id": "browser-a"},
        json={
            "job_id": "order2_router_test",
            "export_mode": "SHORTAGE",
            "row_ids": ["SKU_MINOR", "SKU_MAJOR"],
            "overrides": [],
        },
    )
    assert valid_export.status_code == 200
    assert valid_export.content == b"PK-test"
    assert valid_export.headers["content-length"] == str(len(b"PK-test"))
    assert exported[-1]["row_ids"] == ["SKU_MINOR", "SKU_MAJOR"]
    assert exported[-1]["export_mode"] == "SHORTAGE"

    status = client.get(
        "/api/order-logic-v2/jobs/order2_router_test",
        headers={"x-client-id": "browser-a"},
    )
    assert status.status_code == 200
    visible_row = status.json()["result"]["rows"][0]
    assert visible_row["unit_price_eur"] == 4
    assert "suggested_qty" in visible_row
    assert "upper_suggested_qty" in visible_row

    paths = {route.path for route in order_logic_router.router.routes}
    assert paths == {
        "/api/order-logic-v2/jobs",
        "/api/order-logic-v2/jobs/{job_id}",
        "/api/order-logic-v2/latest",
        "/api/order-logic-v2/export",
    }


def test_main_app_openapi_and_authenticated_entity_permission_smoke(
    monkeypatch,
):
    expected_paths = {
        "/api/order-logic-v2/jobs",
        "/api/order-logic-v2/jobs/{job_id}",
        "/api/order-logic-v2/latest",
        "/api/order-logic-v2/export",
    }
    assert expected_paths <= set(main_app.openapi()["paths"])

    queued: list[tuple[str, dict[str, object]]] = []

    def fake_queue(client_id, body):
        queued.append((client_id, body))
        return "order2_main_app_smoke"

    monkeypatch.setattr(user_store_module, "_user_store", TestUserStore())
    monkeypatch.setattr(
        order_logic_router,
        "queue_order_logic_v2_job",
        fake_queue,
    )
    monkeypatch.setattr(
        order_logic_router,
        "latest_order_logic_v2_result",
        lambda _client_id, _entity_code: None,
    )
    monkeypatch.setattr(
        order_logic_router,
        "owned_order_logic_v2_job",
        lambda _job_id, client_id: {
            "job_id": "order2_main_app_smoke",
            "client_id": client_id,
            "status": "succeeded",
            "result": _result(),
        },
    )
    auth_service.reset_sessions()
    auth_router._login_limiter.reset()

    client = TestClient(main_app)
    entity_headers = {
        "X-Entity-Code": "PL",
        "X-Client-Id": "browser-a",
    }

    anonymous = client.get(
        "/api/order-logic-v2/latest",
        headers=entity_headers,
    )
    assert anonymous.status_code == 401

    login = client.post(
        "/api/auth/login",
        headers={"X-Requested-With": "fetch"},
        json={
            "id": "eu_manager",
            "password": TEST_PASSWORDS["eu_manager"],
        },
    )
    assert login.status_code == 200

    missing_entity = client.get("/api/order-logic-v2/latest")
    assert missing_entity.status_code == 400
    forbidden_entity = client.get(
        "/api/order-logic-v2/latest",
        headers={"X-Entity-Code": "USA"},
    )
    assert forbidden_entity.status_code == 403

    allowed_latest = client.get(
        "/api/order-logic-v2/latest",
        headers=entity_headers,
    )
    assert allowed_latest.status_code == 200
    assert allowed_latest.json()["status"] == "empty"

    csrf_blocked = client.post(
        "/api/order-logic-v2/jobs",
        headers=entity_headers,
        json={"as_of": "2026-07-27", "applied_mode": "CASH"},
    )
    assert csrf_blocked.status_code == 403

    started = client.post(
        "/api/order-logic-v2/jobs",
        headers={**entity_headers, "X-Requested-With": "fetch"},
        json={
            "as_of": "2026-07-27",
            "applied_mode": "CASH",
            "preview": True,
        },
    )
    assert started.status_code == 202
    assert started.json() == {
        "job_id": "order2_main_app_smoke",
        "status": "queued",
    }
    assert queued[-1][0] == "eu_manager__PL__browser-a"

    limited_job = client.get(
        "/api/order-logic-v2/jobs/order2_main_app_smoke",
        headers=entity_headers,
    )
    assert limited_job.status_code == 200
    limited_row = limited_job.json()["result"]["rows"][0]
    assert "suggested_qty" in limited_row
    assert "upper_suggested_qty" in limited_row
    assert limited_row["suggested_amount_eur"] == 4608

    auth_service.reset_sessions()
    admin_client = TestClient(main_app)
    admin_login = admin_client.post(
        "/api/auth/login",
        headers={"X-Requested-With": "fetch"},
        json={
            "id": "adminmaster",
            "password": TEST_PASSWORDS["adminmaster"],
        },
    )
    assert admin_login.status_code == 200
    amount_allowed_job = admin_client.get(
        "/api/order-logic-v2/jobs/order2_main_app_smoke",
        headers=entity_headers,
    )
    assert amount_allowed_job.status_code == 200
    amount_allowed_row = amount_allowed_job.json()["result"]["rows"][0]
    assert amount_allowed_row["suggested_amount_eur"] == 4608

    admin_custom_start = admin_client.post(
        "/api/order-logic-v2/jobs",
        headers={**entity_headers, "X-Requested-With": "fetch"},
        json={
            "as_of": "2026-07-27",
            "applied_mode": "SHORTAGE",
            "preview": True,
            "settings": {
                "lt_air_days": 9.5,
                "lt_rail_days": 14,
                "lt_sea_days": 21,
                "sigma_l_air_weeks": 0.4,
                "sigma_l_rail_weeks": 0.8,
                "sigma_l_sea_weeks": 1.2,
            },
        },
    )
    assert admin_custom_start.status_code == 202
    assert queued[-1][0] == "adminmaster__PL__browser-a"
    assert queued[-1][1]["settings"]["lt_rail_days"] == 14

    auth_service.reset_sessions()
