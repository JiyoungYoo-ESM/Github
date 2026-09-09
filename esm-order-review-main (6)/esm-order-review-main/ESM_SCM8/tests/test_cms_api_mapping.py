import pandas as pd
import pytest

from backend import cms_client
from backend.cms_mapping import build_uploaded_data_from_cms
from backend.services.request_validation import cms_date_settings
from core.lead_times import analysis_lead_time_settings
from core.transport import prepare_shipping


def test_cms_stock_available_qty_maps_to_analysis_columns():
    data = build_uploaded_data_from_cms(
        {
            "stock_local": [
                {
                    "prod_cd": "SKU-1",
                    "stock_qty": 10,
                    "hold_qty": 3,
                    "avbl_qty": 4,
                    "stock_ucost": 1.2,
                    "sales_qty_3m": 9,
                }
            ],
            "stock_hq": [
                {
                    "prod_cd": "SKU-1",
                    "stock_qty": 20,
                    "hold_qty": 5,
                    "avbl_qty": 11,
                    "stock_ucost": 1.3,
                }
            ],
        }
    )

    assert data["eu_stock"].loc[0, "EU 현지 가용수량"] == "4"
    assert data["hq_eu_stock"].loc[0, "본사 EU창고 가용수량"] == "11"


def test_cms_shipping_eta_dt_is_preserved_as_eta_not_ship_date():
    data = build_uploaded_data_from_cms(
        {
            "shipping": [
                {
                    "prod_cd": "SKU-1",
                    "qty": 7,
                    "amount": 70,
                    "cust_nm": "SKO Sp. z o.o.",
                    "eta_dt": "2026-07-31",
                    "remark": "해운 224차",
                    "invc_no": "INV-1",
                }
            ]
        }
    )

    shipping = data["shipping"]
    assert shipping.loc[0, "거래처"] == "SKO Sp. z o.o."
    assert shipping.loc[0, "ETA"] == "2026-07-31"
    assert pd.isna(shipping.loc[0, "출고일"])

    prepared = prepare_shipping(
        shipping,
        {"lead_times": {"해운": 80, "항공": 15, "철송": 35, "트럭": 30}},
    )

    assert prepared.loc[0, "운송수단"] == "해운"
    assert prepared.loc[0, "ETA"] == "2026-07-31"
    assert prepared.loc[0, "ETA 구분"] == "CMS eta_dt"


def test_us_shipping_uses_strict_remark_eta_and_recognizes_air_token():
    data = build_uploaded_data_from_cms(
        {
            "shipping": [
                {
                    "pckg_no": "PK-REVIEW",
                    "prod_cd": "SKU-REVIEW",
                    "qty": 10,
                    "amount": 100,
                    "ship_dt": "2026-07-31",
                    "remark": "HJ 73rd (ETA 8/15)",
                },
                {
                    "pckg_no": "PK-AIR",
                    "prod_cd": "SKU-AIR",
                    "qty": 20,
                    "amount": 200,
                    "ship_dt": "2026-08-01",
                    "remark": "UPS CA AIR_ULTA (1~8th)",
                },
                {
                    "pckg_no": "PK-BAD-DATE",
                    "prod_cd": "SKU-BAD-DATE",
                    "qty": 30,
                    "amount": 300,
                    "ship_dt": "2026-07-31",
                    "remark": "HJ 74th (ETA 2/30)",
                },
            ],
            "lead_time": [
                {"pckg_no": "PK-REVIEW", "ship_via": "OT", "transport_mode": "해운"},
                {"pckg_no": "PK-AIR", "ship_via": "UPS", "transport_mode": "항공"},
                {"pckg_no": "PK-BAD-DATE", "ship_via": "OT", "transport_mode": "해운"},
            ],
        },
        entity_code="USA",
    )

    shipping = data["shipping"]
    assert shipping.loc[0, "ETA"] == "2026-08-15"
    assert shipping.loc[0, "ETA 출처"] == "Invoice 비고 ETA"
    assert pd.isna(shipping.loc[1, "ETA"])
    assert pd.isna(shipping.loc[2, "ETA"])

    prepared = prepare_shipping(shipping, analysis_lead_time_settings("USA"))
    # The lead-time feed's ship_via mapping resolves the transport mode.
    assert prepared.loc[0, "운송수단"] == "해운"
    assert prepared.loc[0, "ETA"] == "2026-08-15"
    assert prepared.loc[0, "ETA 구분"] == "Invoice 비고 ETA"
    assert prepared.loc[1, "운송수단"] == "항공"
    assert prepared.loc[1, "ETA"] == "2026-08-06"
    assert prepared.loc[1, "ETA 구분"] == "적용LT계산ETA"
    assert prepared.loc[2, "운송수단"] == "해운"
    # An invalid remark ETA must still fall back to the applied ocean lead time.
    assert prepared.loc[2, "ETA"] == "2026-08-30"


def test_us_shipping_takes_transport_mode_from_lead_time_feed_when_ids_match():
    data = build_uploaded_data_from_cms(
        {
            "shipping": [
                {
                    "pckg_no": "PK1",
                    "invc_no": "IN1",
                    "prod_cd": "SKU-OCEAN",
                    "qty": 10,
                    "ship_dt": "2026-07-01",
                    "remark": "OSL 12th (ETA 7/25)",
                    "amount": 100.0,
                    "curr": "USD",
                },
                {
                    "pckg_no": "PK-NONE",
                    "invc_no": "IN2",
                    "prod_cd": "SKU-BY-INVOICE",
                    "qty": 20,
                    "ship_dt": "2026-07-02",
                    "remark": "HJ 34th (ETA 7/26)",
                    "amount": 200.0,
                    "curr": "USD",
                },
                {
                    "pckg_no": "PK-UNMATCHED",
                    "invc_no": "IN-UNMATCHED",
                    "prod_cd": "SKU-UNKNOWN",
                    "qty": 30,
                    "ship_dt": "2026-07-03",
                    "remark": "ER 21st (ETA 7/27)",
                    "amount": 300.0,
                    "curr": "USD",
                },
            ],
            "lead_time": [
                {"pckg_no": "PK1", "invc_no": "IN1", "ship_via": "OT", "transport_mode": "\ud574\uc6b4"},
                {"pckg_no": None, "invc_no": "IN2", "ship_via": "UPS", "transport_mode": "\ud56d\uacf5"},
                # A ship_via without a resolved mode must go to manual review.
                {"pckg_no": "PK-UNMATCHED", "invc_no": "IN-UNMATCHED", "ship_via": "QMT", "transport_mode": ""},
            ],
        },
        entity_code="USA",
    )

    shipping = data["shipping"]
    mode_column = "\uc6b4\uc1a1\uc218\ub2e8"
    assert shipping.loc[0, mode_column] == "\ud574\uc6b4"
    assert shipping.loc[1, mode_column] == "\ud56d\uacf5"
    assert shipping.loc[2, mode_column] == "운송수단 확인필요"
    assert shipping.loc[0, "\uc6b4\uc1a1\uc218\ub2e8 \ucd9c\ucc98"] == "CMS lead-time ship_via"
    assert shipping.loc[2, "\uc6b4\uc1a1\uc218\ub2e8 \ucd9c\ucc98"] == "CMS lead-time ship_via 확인필요"
    assert shipping.loc[2, "운송수단 API 원본값"] == "QMT"

    prepared = prepare_shipping(shipping, analysis_lead_time_settings("USA"))
    assert prepared.loc[0, mode_column] == "\ud574\uc6b4"
    assert prepared.loc[1, mode_column] == "\ud56d\uacf5"
    assert prepared.loc[2, mode_column] == "운송수단 확인필요"
    assert prepared.loc[0, "운송수단 코드"] == "OCEAN"
    assert prepared.loc[1, "운송수단 코드"] == "AIR"
    assert prepared.loc[0, "운송수단 출처"] == "CMS lead-time ship_via"
    assert prepared.loc[1, "운송수단 출처"] == "CMS lead-time ship_via"
    assert prepared.loc[0, "운송 L/T"] == 30
    assert prepared.loc[1, "운송 L/T"] == 5
    assert prepared.loc[0, "ETA 출처"] == "Invoice 비고 ETA"


def test_us_shipping_without_api_match_uses_explicit_shipping_source_only():
    data = build_uploaded_data_from_cms(
        {
            "shipping": [
                {
                    "prod_cd": "SKU-BLANK",
                    "qty": 10,
                    "amount": 100,
                    "ship_dt": "2026-07-31",
                    "remark": "",
                },
                {
                    "prod_cd": "SKU-FREE-TEXT",
                    "qty": 20,
                    "amount": 200,
                    "ship_dt": "2026-07-31",
                    "remark": "sample re-send, no container",
                },
                {
                    "prod_cd": "SKU-VOYAGE",
                    "qty": 30,
                    "amount": 300,
                    "ship_dt": "2026-07-31",
                    "remark": "ES 22th (ETA 8/8)",
                },
                {
                    "prod_cd": "SKU-AIR",
                    "qty": 40,
                    "amount": 400,
                    "ship_dt": "2026-07-31",
                    "remark": "UPS CA AIR_ULTA",
                },
            ]
        },
        entity_code="USA",
    )

    mode_column = "\uc6b4\uc1a1\uc218\ub2e8"
    shipping = data["shipping"]
    assert shipping[mode_column].tolist() == [
        "운송수단 확인필요",
        "운송수단 확인필요",
        "해운",
        "항공",
    ]
    assert shipping["운송수단 출처"].tolist() == [
        "운송수단 원천 확인필요",
        "운송수단 원천 확인필요",
        "해상컨테이너 원천",
        "Invoice 비고",
    ]

    prepared = prepare_shipping(shipping, analysis_lead_time_settings("USA"))
    review_label = "\uc6b4\uc1a1\uc218\ub2e8 \ud655\uc778\ud544\uc694"
    assert prepared[mode_column].tolist() == [review_label, review_label, "해운", "항공"]


def test_shipping_mode_enrichment_is_skipped_without_a_lead_time_feed():
    data = build_uploaded_data_from_cms(
        {
            "shipping": [
                {
                    "pckg_no": "PK1",
                    "invc_no": "IN1",
                    "prod_cd": "SKU-1",
                    "qty": 10,
                    "ship_dt": "2026-07-01",
                    "remark": "\ud574\uc6b4 12th",
                    "amount": 100.0,
                    "curr": "EUR",
                }
            ]
        },
        entity_code="PL",
    )

    # Without the feed the remark-based detection must remain untouched.
    prepared = prepare_shipping(data["shipping"], analysis_lead_time_settings("PL"))
    assert prepared.loc[0, "\uc6b4\uc1a1\uc218\ub2e8"] == "\ud574\uc6b4"


def test_cms_shipping_new_ship_dt_is_used_when_eta_dt_is_absent():
    data = build_uploaded_data_from_cms(
        {
            "shipping": [
                {
                    "prod_cd": "SKU-1",
                    "prod_nm": "상품",
                    "brand_nm": "브랜드",
                    "qty": 7,
                    "amount": 70,
                    "ship_dt": "2026-06-08",
                    "remark": "해운 224차",
                    "invc_no": "INV-1",
                    "pckg_no": "PKG-1",
                }
            ]
        }
    )

    shipping = data["shipping"]
    assert shipping.loc[0, "상품명"] == "상품"
    assert shipping.loc[0, "브랜드"] == "브랜드"
    assert shipping.loc[0, "Packing No"] == "PKG-1"
    assert shipping.loc[0, "출고일"] == "2026-06-08"
    assert pd.isna(shipping.loc[0, "ETA"])

    prepared = prepare_shipping(
        shipping,
        {"lead_times": {"해운": 80, "항공": 15, "철송": 35, "트럭": 30}},
    )

    assert prepared.loc[0, "운송수단"] == "해운"
    assert prepared.loc[0, "ETA"] == "2026-08-27"
    assert prepared.loc[0, "ETA 구분"] == "적용LT계산ETA"


def test_cms_open_po_new_amount_and_product_fields_are_preserved():
    data = build_uploaded_data_from_cms(
        {
            "open_po": [
                {
                    "prod_cd": "SKU-1",
                    "prod_nm": "상품",
                    "bar_code": "8800000000000",
                    "brand_nm": "브랜드",
                    "po_qty": 100,
                    "pnfm_qty": 30,
                    "pnfm_confirmed_qty": 20,
                    "inbound_in_progress_qty": 5,
                    "open_qty": 70,
                    "open_amt": 1234.5,
                    "completed_qty": 10,
                }
            ]
        }
    )

    open_po = data["open_po"]
    assert open_po.loc[0, "상품명"] == "상품"
    assert open_po.loc[0, "바코드"] == "8800000000000"
    assert open_po.loc[0, "브랜드"] == "브랜드"
    assert open_po.loc[0, "미입고 수량"] == 70
    assert open_po.loc[0, "미입고 금액"] == 1234.5
    assert open_po.loc[0, "PNFM확정 수량"] == 20
    assert open_po.loc[0, "입고진행중 수량"] == 5
    assert open_po.loc[0, "입고완료 수량"] == 10


def test_fetch_hq_opo_data_includes_full_product_master(monkeypatch):
    calls: list[tuple[str, dict[str, object] | None]] = []

    def fake_fetch_paged(
        path: str,
        date_from: str | None = None,
        date_to: str | None = None,
        extra_params: dict[str, object] | None = None,
    ):
        calls.append((path, extra_params))
        if path == "/eu/products":
            return [
                {
                    "prod_cd": "SKU-1",
                    "prod_nm": "상품",
                    "brand_nm": "브랜드",
                }
            ]
        return []

    monkeypatch.setattr(cms_client, "_fetch_paged", fake_fetch_paged)
    monkeypatch.setattr(
        cms_client,
        "_get_json",
        lambda *_args, **_kwargs: {
            "sample_count": 2,
            "avg_days": 10,
            "stddev_days": 1,
        },
    )

    result = cms_client.fetch_hq_opo_data(
        date_from="2026-05-01",
        date_to="2026-08-01",
    )

    assert result["products"][0]["prod_cd"] == "SKU-1"
    assert ("/eu/products", {"eu_sold_only": False}) in calls


def test_fetch_cms_data_can_use_separate_sales_and_logistics_date_ranges(monkeypatch):
    calls: list[tuple[str, dict[str, object] | None]] = []

    def fake_fetch_list(path: str, params: dict[str, object] | None = None):
        calls.append((path, params))
        return []

    def fake_fetch_paged(path: str, date_from: str | None = None, date_to: str | None = None):
        calls.append((path, {"date_from": date_from, "date_to": date_to}))
        return []

    monkeypatch.setattr(cms_client, "_fetch_list", fake_fetch_list)
    monkeypatch.setattr(cms_client, "_fetch_paged", fake_fetch_paged)

    cms_client.fetch_cms_data(
        "2026-06-12",
        date_from="2026-03-12",
        date_to="2026-06-12",
        shipping_date_from="2026-01-01",
        open_po_date_from="2026-01-01",
    )

    params_by_path = {path: params for path, params in calls}
    assert params_by_path["/eu/stock/local"] == {"as_of": "2026-06-12"}
    assert params_by_path["/eu/stock/hq"] == {"as_of": "2026-06-12"}
    assert params_by_path["/eu/sales/local"] == {
        "date_from": "2026-03-12",
        "date_to": "2026-06-12",
    }
    assert params_by_path["/eu/sales/hq-to-eu"] == {
        "date_from": "2026-03-12",
        "date_to": "2026-06-12",
    }
    assert params_by_path["/eu/shipping/containers"] == {
        "date_from": "2026-01-01",
        "date_to": "2026-06-12",
    }
    assert params_by_path["/eu/open-po"] == {
        "date_from": "2026-01-01",
        "date_to": "2026-06-12",
    }


def test_fetch_cms_data_routes_every_source_to_us_endpoints(monkeypatch):
    calls: list[tuple[str, dict[str, object] | None]] = []

    def fake_fetch_list(path: str, params: dict[str, object] | None = None):
        calls.append((path, params))
        return []

    def fake_fetch_paged(
        path: str,
        date_from: str | None = None,
        date_to: str | None = None,
        extra_params: dict[str, object] | None = None,
    ):
        calls.append((path, {"date_from": date_from, "date_to": date_to, **(extra_params or {})}))
        return []

    monkeypatch.setattr(cms_client, "_fetch_list", fake_fetch_list)
    monkeypatch.setattr(cms_client, "_fetch_paged", fake_fetch_paged)

    cms_client.fetch_cms_data(
        "2026-07-28",
        date_from="2026-04-28",
        date_to="2026-07-28",
        shipping_date_from="2026-01-01",
        open_po_date_from="2026-01-01",
        entity_code="USA",
    )

    assert {path for path, _params in calls} == {
        "/us/stock/local",
        "/us/stock/hq",
        "/us/sales/local",
        "/us/sales/hq-to-us",
        "/us/shipping/containers",
        "/us/open-po",
        "/us/logistics/lead-time",
    }

    lead_time_params = next(params for path, params in calls if path == "/us/logistics/lead-time")
    assert lead_time_params == {
        "date_from": "2026-01-01",
        "date_to": "2026-07-28",
        "include_in_transit": "true",
    }


def test_us_lead_time_enrichment_failure_stops_v1_analysis(monkeypatch):
    def failing_fetch(*_args, **_kwargs):
        raise RuntimeError("lead-time unavailable")

    monkeypatch.setattr(cms_client, "fetch_cms_lead_time", failing_fetch)

    with pytest.raises(RuntimeError, match="미주 운송수단 확인용 리드타임 API"):
        cms_client._fetch_lead_time_rows("USA", "2026-01-01", "2026-07-28")


def test_us_mapping_keeps_local_currency_and_quarantines_krw_open_po_amount():
    data = build_uploaded_data_from_cms(
        {
            "sales_local": [{"prod_cd": "SKU-1", "amount": 10, "amount_krw": 10, "amount_krw_actual": 14_500}],
            "sales_hq": [{"prod_cd": "SKU-1", "amount": 20, "amount_krw": 20, "amount_krw_actual": 29_000}],
            "open_po": [{"prod_cd": "SKU-1", "open_qty": 3, "open_amt": 4_350}],
        },
        entity_code="USA",
    )

    assert data["sales_detail"].loc[0, "법인 기준통화 환산금액"] == 10
    assert data["sales_detail"].loc[0, "환산금액"] == 14_500
    assert data["hq_to_eu_sales_detail"].loc[0, "환산금액"] == 29_000
    assert pd.isna(data["open_po"].loc[0, "미입고 금액"])
    assert data["open_po"].loc[0, "미입고 금액(KRW)"] == 4_350


def test_us_stock_unit_cost_is_marked_as_usd_local_currency():
    data = build_uploaded_data_from_cms(
        {
            "stock_local": [{"prod_cd": "SKU-USD", "stock_ucost": 8.5, "unit_cost_krw": 12_325, "stock_amount_krw": 123_250}],
            "stock_hq": [],
        },
        entity_code="USA",
    )

    row = data["eu_stock"].iloc[0]
    assert row["현지 입고단가"] == "8.5"
    assert row["현지 입고단가 통화"] == "USD"
    assert row["EU 입고단가"] == "8.5"
    assert row["EU 입고단가 통화"] == "USD"
    assert row["CMS 원화 입고단가"] == "12325"
    assert row["CMS 재고금액(KRW)"] == "123250"


def test_fetch_cms_data_can_skip_sales_and_lead_time_detail_for_inventory_only(monkeypatch):
    calls: list[tuple[str, dict[str, object] | None]] = []

    def fake_fetch_list(path: str, params: dict[str, object] | None = None):
        calls.append((path, params))
        return [{"path": path}]

    def fake_fetch_paged(path: str, date_from: str | None = None, date_to: str | None = None):
        raise AssertionError(f"sales detail API should not be called: {path}")

    def fake_fetch_lead_time(*_args: object, **_kwargs: object):
        raise AssertionError("lead-time API should not be called")

    monkeypatch.setattr(cms_client, "_fetch_list", fake_fetch_list)
    monkeypatch.setattr(cms_client, "_fetch_paged", fake_fetch_paged)
    monkeypatch.setattr(cms_client, "_fetch_lead_time_rows", fake_fetch_lead_time)

    result = cms_client.fetch_cms_data(
        "2026-06-12",
        date_from="2026-03-12",
        date_to="2026-06-12",
        shipping_date_from="2026-01-01",
        open_po_date_from="2026-01-01",
        include_sales_detail=False,
        include_lead_time_detail=False,
    )

    called_paths = {path for path, _params in calls}
    assert "/eu/sales/local" not in called_paths
    assert "/eu/sales/hq-to-eu" not in called_paths
    assert result["sales_local"] == []
    assert result["sales_hq"] == []


def test_get_json_adds_cms_api_key_header(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_get(url: str, **kwargs: object):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setenv("CMS_API_KEY", "secret-key")
    monkeypatch.setattr(cms_client, "_http_get", fake_get)

    assert cms_client._get_json("/eu/products") == {"ok": True}
    assert captured["headers"] == {"X-API-Key": "secret-key"}


def test_get_json_omits_auth_header_without_cms_api_key(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_get(url: str, **kwargs: object):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.delenv("CMS_API_KEY", raising=False)
    monkeypatch.setattr(cms_client, "_http_get", fake_get)

    assert cms_client._get_json("/eu/products") == {"ok": True}
    assert captured["headers"] is None


def test_get_json_raises_clear_auth_error_on_unauthorized(monkeypatch):
    class FakeResponse:
        status_code = 401

    def fake_get(url: str, **kwargs: object):
        return FakeResponse()

    monkeypatch.delenv("CMS_API_KEY", raising=False)
    monkeypatch.setattr(cms_client, "_http_get", fake_get)

    with pytest.raises(cms_client.CmsAuthenticationError, match="CMS_API_KEY"):
        cms_client._get_json("/eu/products")


def test_cms_date_settings_uses_same_day_three_month_window():
    settings = cms_date_settings("2026-06-12")

    assert str(settings["period_start"]) == "2026-03-12"
    assert str(settings["logistics_period_start"]) == "2026-01-01"
    assert str(settings["period_end"]) == "2026-06-12"
