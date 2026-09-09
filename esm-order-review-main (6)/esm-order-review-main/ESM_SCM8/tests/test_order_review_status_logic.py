from datetime import date

import pandas as pd

from core import inbound, inventory, loaders, order_review, order_review_report, preprocess, sales, transport, validation


def _settings(**overrides):
    settings = validation.default_settings_for_validation()
    settings.update(
        {
            "base_date": date(2026, 5, 19),
            "period_start": date(2026, 2, 18),
            "period_end": date(2026, 5, 18),
            "safety_months": 3.0,
            "include_inbound_po_in_coverage": False,
            "include_hq_eu_in_order_coverage": True,
            "eur_krw_rate": 1500,
        }
    )
    settings.update(overrides)
    return settings


def _eu_row(sku, sales, eu_qty, unit=2, name=None, stock_qty=None, hold_qty=0, pa_ca_sales=None):
    row = {
        "상품코드": sku,
        "브랜드": "BRAND",
        "상품명": name or sku,
        "제품상태": "정상",
        "재고수량": eu_qty if stock_qty is None else stock_qty,
        "Hold수량": hold_qty,
        "EU 현지 가용수량": eu_qty,
        "EU 입고단가": unit,
        "바코드": sku,
    }
    if pa_ca_sales is not None:
        row["최근 3개월 판매수량"] = pa_ca_sales
        row["PA+CA 판매수량"] = pa_ca_sales
    return row


def _install_order_review_data(monkeypatch, eu_rows, hq_qty=None, shipping_qty=None, po_qty=None):
    hq_qty = hq_qty or {}
    shipping_qty = shipping_qty or {}
    po_qty = po_qty or {}
    eu_df = pd.DataFrame(eu_rows)
    hq_df = pd.DataFrame(
        [{"상품코드": sku, "재고수량": qty, "Hold수량": 0} for sku, qty in hq_qty.items()],
        columns=["상품코드", "재고수량", "Hold수량"],
    )
    shipping_df = pd.DataFrame(
        [
            {
                "SKU": sku,
                "수량": qty,
                "ETA": "2026-05-25",
                "출고일": "2026-05-10",
                "운송수단": "해운",
                "상품명": sku,
                "브랜드": "BRAND",
            }
            for sku, qty in shipping_qty.items()
        ],
        columns=["SKU", "수량", "ETA", "출고일", "운송수단", "상품명", "브랜드"],
    )
    po_df = pd.DataFrame(
        [{"SKU": sku, "미입고수량": qty} for sku, qty in po_qty.items()],
        columns=["SKU", "미입고수량"],
    )
    validation_sales = eu_df["최근 3개월 판매수량"] if "최근 3개월 판매수량" in eu_df.columns else 0
    validation_df = pd.DataFrame({"SKU": eu_df["상품코드"], "판매내역상세_3M_판매수량": validation_sales})

    monkeypatch.setattr(inventory, "get_eu_stock", lambda context=None: eu_df)
    monkeypatch.setattr(inventory, "get_hq_eu_stock", lambda context=None: hq_df)
    monkeypatch.setattr(transport, "get_shipping", lambda settings=None, context=None: shipping_df)
    monkeypatch.setattr(inbound, "get_open_po", lambda context=None: po_df)
    monkeypatch.setattr(sales, "sales_detail_validation_qty_by_sku", lambda settings, context=None: validation_df)


def _install_order_review_uploaded_data(monkeypatch, eu_rows, hq_qty=None, shipping_qty=None, po_qty=None, shipping_rows=None):
    hq_qty = hq_qty or {}
    shipping_qty = shipping_qty or {}
    po_qty = po_qty or {}
    empty = pd.DataFrame()
    eu_df = pd.DataFrame(eu_rows)
    hq_df = pd.DataFrame(
        [{"상품코드": sku, "재고수량": qty, "Hold수량": 0} for sku, qty in hq_qty.items()],
        columns=["상품코드", "재고수량", "Hold수량"],
    )
    shipping_df = pd.DataFrame(shipping_rows) if shipping_rows is not None else pd.DataFrame(
        [
            {
                "SKU": sku,
                "수량": qty,
                "ETA": "2026-05-25",
                "출고일": "2026-05-10",
                "운송수단": "해운",
                "상품명": sku,
                "브랜드": "BRAND",
            }
            for sku, qty in shipping_qty.items()
        ],
        columns=["SKU", "수량", "ETA", "출고일", "운송수단", "상품명", "브랜드"],
    )
    if not shipping_df.empty and not any(
        column in shipping_df.columns for column in ("거래처", "거래처명", "cust_nm")
    ):
        shipping_df["거래처"] = "SKO Sp. z o.o."
    po_df = pd.DataFrame(
        [{"SKU": sku, "미입고수량": qty} for sku, qty in po_qty.items()],
        columns=["SKU", "미입고수량"],
    )
    uploaded = {
        "eu_stock": eu_df,
        "hq_eu_stock": hq_df,
        "shipping": shipping_df,
        "open_po": po_df,
        "sales_detail": empty,
        "hq_to_eu_sales_detail": empty,
    }

    def data_for_key(key: str, sample_func, context=None) -> pd.DataFrame:
        return uploaded.get(key, empty).copy()

    monkeypatch.setattr(loaders, "get_order_review_data_or_empty", data_for_key)
    monkeypatch.setattr(loaders, "get_data_or_sample", data_for_key)
    validation_sales = eu_df["최근 3개월 판매수량"] if "최근 3개월 판매수량" in eu_df.columns else 0
    validation_df = pd.DataFrame({"SKU": eu_df["상품코드"], "판매내역상세_3M_판매수량": validation_sales})
    monkeypatch.setattr(sales, "sales_detail_validation_qty_by_sku", lambda settings, context=None: validation_df)


def _row(df, sku):
    return df[df["상품코드"].astype(str).eq(sku)].iloc[0]


def test_prepare_eu_stock_prefers_uploaded_available_qty():
    prepared = preprocess.prepare_eu_stock(
        pd.DataFrame(
            [
                {
                    "상품코드": "SKU_AVAILABLE",
                    "상품명": "SKU_AVAILABLE",
                    "브랜드": "BRAND",
                    "재고수량": 100,
                    "Hold수량": 0,
                    "가용수량": 7,
                    "EU 입고단가": 1,
                    "최근 3개월 판매수량": 0,
                }
            ]
        )
    )

    assert int(prepared.loc[0, "EU 현지 가용수량"]) == 7


def test_prepare_eu_stock_accepts_reference_template_columns():
    prepared = preprocess.prepare_eu_stock(
        pd.DataFrame(
            [
                {
                    "상품코드": "SKU_REF_TEMPLATE",
                    "상품명": "Reference template SKU",
                    "브랜드": "BRAND",
                    "재고 수량": 100,
                    "Hold 수량": 30,
                    "가용 수량": 7,
                    "평균 단가 ( )": 2.85,
                    "판매 수량 (3개월내 PA+CA)": 11416,
                    "제품 상태": "정상",
                }
            ]
        )
    )

    assert int(prepared.loc[0, "재고수량"]) == 100
    assert int(prepared.loc[0, "Hold수량"]) == 30
    assert int(prepared.loc[0, "EU 현지 가용수량"]) == 7
    assert float(prepared.loc[0, "EU 입고단가"]) == 2.85
    assert int(prepared.loc[0, "최근 3개월 판매수량"]) == 11416
    assert prepared.loc[0, "제품상태"] == "정상"


def test_order_review_merges_case_variant_skus_to_master_display(monkeypatch):
    _install_order_review_uploaded_data(
        monkeypatch,
        [
            _eu_row("RLSM04-SCeu", 300, 10, pa_ca_sales=300),
            _eu_row("RLSM04-SCeu", 0, 5, pa_ca_sales=0),
            _eu_row("RLSM04-Sceu", 0, 7, pa_ca_sales=0),
            _eu_row("RLSM04-SCEU", 0, 3, pa_ca_sales=0),
        ],
        shipping_qty={"RLSM04-SCEU": 20},
        po_qty={"RLSM04-Sceu": 4},
    )

    review = order_review.order_review_df(_settings())

    assert review["상품코드"].tolist() == ["RLSM04-SCeu"]
    row = review.iloc[0]
    assert int(row["EU 현지 가용수량"]) == 25
    assert int(row["운송중 수량"]) == 20
    assert int(row["미입고수량"]) == 4


def test_order_review_shipping_qty_includes_unrecognized_transport_rows(monkeypatch):
    rows = [_eu_row("SKU_UNRECOGNIZED_SHIPPING", 100, 0, pa_ca_sales=300)]
    _install_order_review_uploaded_data(
        monkeypatch,
        rows,
        shipping_rows=[
            {
                "SKU": "SKU_UNRECOGNIZED_SHIPPING",
                "수량": 50,
                "ETA": "2026-05-25",
                "출고일": "2026-05-10",
                "운송수단": "확인필요",
                "상품명": "SKU_UNRECOGNIZED_SHIPPING",
                "브랜드": "BRAND",
            }
        ],
    )

    review = order_review.order_review_df(_settings())
    row = _row(review, "SKU_UNRECOGNIZED_SHIPPING")

    assert int(row["운송중 수량"]) == 50
    assert int(row["추가 발주 필요 수량"]) == 250


def test_order_review_pl_uses_only_sko_shipping_for_qty_amount_and_eta(monkeypatch):
    sku = "SKU_SKO_ONLY"
    shipping_rows = [
        {
            "SKU": sku,
            "수량": 40,
            "금액": 80,
            "ETA": "2026-05-25",
            "출고일": "2026-05-10",
            "운송수단": "해운",
            "상품명": sku,
            "브랜드": "BRAND",
            "거래처": "SKO Sp. z o.o.",
        },
        {
            "SKU": sku,
            "수량": 60,
            "금액": 600,
            "ETA": "2026-05-20",
            "출고일": "2026-05-05",
            "운송수단": "해운",
            "상품명": sku,
            "브랜드": "BRAND",
            "거래처": "STYLEKOREAN UK LIMITED",
        },
        {
            "SKU": sku,
            "수량": 80,
            "금액": 800,
            "ETA": "2026-05-15",
            "출고일": "2026-05-01",
            "운송수단": "해운",
            "상품명": sku,
            "브랜드": "BRAND",
            "거래처": None,
        },
    ]
    filtered_shipping = order_review._shipping_rows_for_entity(
        pd.DataFrame(shipping_rows),
        entity_code="PL",
    )

    assert filtered_shipping["수량"].sum() == 40
    assert filtered_shipping["금액"].sum() == 80

    _install_order_review_uploaded_data(
        monkeypatch,
        [_eu_row(sku, 100, 0, pa_ca_sales=300)],
        shipping_rows=shipping_rows,
    )

    review = order_review.order_review_df(_settings(entity_code="PL"))
    row = _row(review, sku)

    assert int(row["운송중 수량"]) == 40
    assert row["최초 ETA"] == date(2026, 5, 25)
    assert int(row["최초 ETA 수량"]) == 40


def test_order_review_status_priority_and_quantities(monkeypatch):
    rows = [
        _eu_row("SKU_EU_OK", 100, 100, pa_ca_sales=30),
        _eu_row("SKU_TRANSPORT", 100, 50, pa_ca_sales=100),
        _eu_row("SKU_HQ_FULL", 100, 20, pa_ca_sales=30),
        _eu_row("SKU_HQ_PART", 100, 20, pa_ca_sales=30),
        _eu_row("SKU_NO_HQ", 100, 20, pa_ca_sales=30),
        _eu_row("SKU_NO_SALES", 0, 0),
    ]
    _install_order_review_uploaded_data(
        monkeypatch,
        rows,
        hq_qty={"SKU_HQ_FULL": 60, "SKU_HQ_PART": 30},
        shipping_qty={"SKU_TRANSPORT": 150},
    )

    review = order_review.order_review_df(_settings())

    eu_ok = _row(review, "SKU_EU_OK")
    assert eu_ok["최종 액션"] == "발주 필요 없음"
    assert eu_ok["상태"] == "정상"
    assert int(eu_ok["추가 발주 필요 수량"]) == 0

    transport = _row(review, "SKU_TRANSPORT")
    assert transport["최종 액션"] == "발주 필요 없음"
    assert transport["상태"] == "정상"
    assert int(transport["추가 발주 필요 수량"]) == 0

    hq_full = _row(review, "SKU_HQ_FULL")
    assert hq_full["최종 액션"] == "발주 필요"
    assert hq_full["상태"] == "정상"
    assert int(hq_full["본사 이동 수량"]) == 0
    assert int(hq_full["추가 발주 필요 수량"]) == 10

    hq_part = _row(review, "SKU_HQ_PART")
    assert hq_part["최종 액션"] == "발주 필요"
    assert hq_part["상태"] == "정상"
    assert int(hq_part["본사 이동 수량"]) == 0
    assert int(hq_part["추가 발주 필요 수량"]) == 10
    assert "신규 발주" in hq_part["조치 요약"]

    no_hq = _row(review, "SKU_NO_HQ")
    assert no_hq["최종 액션"] == "발주 필요"
    assert no_hq["상태"] == "정상"
    assert int(no_hq["추가 발주 필요 수량"]) > 0

    no_sales = _row(review, "SKU_NO_SALES")
    assert no_sales["최종 액션"] == "발주 필요 없음"
    assert no_sales["상태"] == "발주제외"
    assert int(no_sales["추가 발주 필요 수량"]) == 0


def test_foc_sample_sku_is_excluded_and_zeroed(monkeypatch):
    rows = [_eu_row("SKU_FOC", 100, 0, unit=0, name="FOC SAMPLE")]
    _install_order_review_uploaded_data(monkeypatch, rows)

    review = order_review.order_review_df(_settings())
    assert review[review["상품코드"].astype(str).eq("SKU_FOC")].empty

    excluded = order_review.excluded_order_review_df(_settings())
    foc = _row(excluded, "SKU_FOC")
    assert foc["최종 액션"] == "발주 필요 없음"
    assert foc["상태"] == "발주제외"
    assert int(foc["추가 발주 필요 수량"]) == 0
    assert bool(foc["제외 SKU"]) is True
    assert foc["제외유형"] == "0단가/무상"

    excluded_sheet = order_review_report.build_excluded_order_review_df(excluded, _settings())
    check_required = order_review_report.build_check_required_sheet_df(
        pd.DataFrame(), pd.DataFrame(), excluded_sheet, pd.DataFrame()
    )
    assert check_required.empty
    for col in ["최종 액션", "상태", "조치 요약", "근거", "예외 플래그", "예외 사유"]:
        assert col in excluded_sheet.columns
    assert set(excluded_sheet["최종 액션"]) == {"발주 필요 없음"}
    assert (excluded_sheet["우선 액션"] == excluded_sheet["최종 액션"]).all()
    assert (excluded_sheet["판단 사유"] == excluded_sheet["근거"]).all()


def test_report_keeps_excluded_sku_order_qty_at_zero(monkeypatch):
    """제외 행은 canonical 재계산에서도 발주 수량이 살아나지 않는다.

    살아나면 표에는 "발주 불필요 + 발주필요수량 > 0" 행이 남고, 액션 기준 KPI(발주 필요
    SKU)와 수량 기준 화면 집계가 서로 다른 수를 보여준다.
    """
    from backend.analysis import order_template_review_basis
    from core import export_excel_report

    settings = _settings()
    rows = [
        _eu_row("SKU_NORMAL", 300, 0, unit=2, pa_ca_sales=300),
        _eu_row("SKU_FOC_ZERO_PRICE", 300, 0, unit=0, pa_ca_sales=300),
    ]
    _install_order_review_uploaded_data(monkeypatch, rows)

    combined = order_review.order_review_df(settings, excluded_only=None)
    filtered = combined[~combined["제외 SKU"].astype(bool)].copy()
    report = order_review_report.build_order_review_report_df(
        order_template_review_basis(combined, filtered, settings),
        settings,
    )

    foc = _row(report, "SKU_FOC_ZERO_PRICE")
    assert foc["상태"] == "발주제외"
    assert foc["최종 액션"] == "발주 필요 없음"
    assert foc["우선 액션"] != "발주 필요"
    for col in ["발주필요수량", "발주 필요 수량", "추가 발주 필요 수량", "부족수량", "최종 부족수량"]:
        assert float(foc[col]) == 0, col
    for col in ["부족금액_EUR", "부족금액_KRW", "추가 발주 필요 금액"]:
        assert float(foc[col]) == 0, col
    # 재고 적정성 신호는 유지한다: 제외 사유가 있어도 안전재고 미달 사실은 남아야 한다.
    assert foc["재고 ETA 상태"] == "OOS"
    assert float(foc["안전재고 목표수량"]) == 300

    normal = _row(report, "SKU_NORMAL")
    assert normal["최종 액션"] == "발주 필요"
    assert float(normal["발주필요수량"]) == 300

    # 요약 총계와 액션 기준 SKU 수, 수량 기준 SKU 수가 같은 기준을 쓴다.
    summary = export_excel_report.build_order_review_report_summary(report, settings)
    kpi_values = order_review_report.order_review_dashboard_kpi_values(report)
    order_qty = pd.to_numeric(report["발주필요수량"], errors="coerce").fillna(0)
    assert summary["total_order_qty"] == 300
    assert kpi_values["order_needed_qty"] == 300
    assert kpi_values["order_needed_sku"] == float(int((order_qty > 0).sum())) == 1.0


def test_open_po_without_eta_is_flagged_even_when_no_order_is_needed(monkeypatch):
    """미입고 ETA 미확인은 발주 필요 여부와 무관한 데이터 완결성 신호다.

    예전에는 발주가 필요한 행에만 플래그가 붙어서, 발주는 불필요하지만 미입고 물량이 언제
    들어오는지 모르는 행은 아무 표시 없이 지나갔다.
    """
    from backend.analysis import order_template_review_basis

    settings = _settings()
    rows = [
        # 재고 충분(발주 불필요) + 미입고 있음 + 운송 ETA 없음
        _eu_row("SKU_PO_NO_ETA_SUFFICIENT", 0, 500, pa_ca_sales=30),
        # 발주 필요 + 미입고 있음 + 운송 ETA 없음
        _eu_row("SKU_PO_NO_ETA_ORDER", 0, 0, pa_ca_sales=300),
        # 미입고 있고 운송 ETA도 있음 -> 도착 근거가 있으므로 플래그 없음
        _eu_row("SKU_PO_WITH_ETA", 0, 0, pa_ca_sales=300),
        # 미입고 없음 -> 대상 아님
        _eu_row("SKU_NO_PO", 0, 500, pa_ca_sales=30),
    ]
    _install_order_review_uploaded_data(
        monkeypatch,
        rows,
        shipping_qty={"SKU_PO_WITH_ETA": 50},
        po_qty={
            "SKU_PO_NO_ETA_SUFFICIENT": 100,
            "SKU_PO_NO_ETA_ORDER": 100,
            "SKU_PO_WITH_ETA": 100,
        },
    )

    combined = order_review.order_review_df(settings, excluded_only=None)
    report = order_review_report.build_order_review_report_df(
        order_template_review_basis(combined, combined[~combined["제외 SKU"].astype(bool)].copy(), settings),
        settings,
    )

    sufficient = _row(report, "SKU_PO_NO_ETA_SUFFICIENT")
    assert sufficient["우선 액션"] != "발주 필요"
    assert float(sufficient["미입고 수량"]) == 100
    assert sufficient["ETA미확인"] == "Y"

    ordered = _row(report, "SKU_PO_NO_ETA_ORDER")
    assert ordered["우선 액션"] == "발주 필요"
    assert ordered["ETA미확인"] == "Y"

    assert _row(report, "SKU_PO_WITH_ETA")["ETA미확인"] == "N"
    assert _row(report, "SKU_NO_PO")["ETA미확인"] == "N"

    # 발주 검토용 부분집합은 액션과 조합해 그대로 뽑을 수 있어야 한다.
    order_needed_and_missing = report[
        report["ETA미확인"].eq("Y") & report["우선 액션"].eq("발주 필요")
    ]
    assert order_needed_and_missing["상품코드"].tolist() == ["SKU_PO_NO_ETA_ORDER"]


def test_report_cover_months_uses_the_displayed_monthly_average(monkeypatch):
    """커버개월은 같은 시트에 표시되는 월평균·EU 현지 재고와 나누어 떨어져야 한다.

    리뷰 단계의 커버가능 개월수는 반올림 전 월평균(31/3=10.33)을 쓰고, 시트에 표시되는
    월평균은 canonical 반올림 값(10)이라 한 결과 안에 커버기간이 두 종류 존재했다.
    """
    from backend.analysis import order_template_review_basis

    settings = _settings()
    rows = [
        _eu_row("SKU_ROUNDING", 0, 19, pa_ca_sales=31),
        _eu_row("SKU_NO_SALES_COVER", 0, 5, pa_ca_sales=0),
    ]
    _install_order_review_uploaded_data(monkeypatch, rows)

    combined = order_review.order_review_df(settings, excluded_only=None)
    review_row = _row(combined, "SKU_ROUNDING")
    # 리뷰 단계 값은 반올림 전 월평균 기준이다.
    assert round(float(review_row["커버가능 개월수"]), 3) == round(19 / (31 / 3), 3)

    report = order_review_report.build_order_review_report_df(
        order_template_review_basis(combined, combined[~combined["제외 SKU"].astype(bool)].copy(), settings),
        settings,
    )
    row = _row(report, "SKU_ROUNDING")
    assert float(row["월평균"]) == 10
    assert float(row["EU 현지 재고"]) == 19
    assert float(row["커버개월"]) == float(row["EU 현지 재고"]) / float(row["월평균"]) == 1.9

    # 판매가 없으면 나눌 수 없으므로 기존 "판매없음" 표기값을 유지한다.
    assert float(_row(report, "SKU_NO_SALES_COVER")["커버개월"]) == 99


def test_hq_coverage_can_be_disabled(monkeypatch):
    rows = [_eu_row("SKU_HQ_DISABLED", 100, 20, pa_ca_sales=100)]
    _install_order_review_uploaded_data(monkeypatch, rows, hq_qty={"SKU_HQ_DISABLED": 80})

    review = order_review.order_review_df(_settings(include_hq_eu_in_order_coverage=False))
    row = _row(review, "SKU_HQ_DISABLED")
    assert int(row["본사 EU창고 가용수량"]) == 80
    assert int(row["본사 이동 수량"]) == 0
    assert int(row["추가 발주 필요 수량"]) == 80
    assert row["최종 액션"] == "발주 필요"


def test_order_required_uses_editable_safety_months(monkeypatch):
    rows = [_eu_row("SKU_TARGET_MONTHS", 100, 0, pa_ca_sales=90)]
    _install_order_review_uploaded_data(monkeypatch, rows)

    review = order_review.order_review_df(
        _settings(
            safety_months=2.5,
        )
    )
    row = _row(review, "SKU_TARGET_MONTHS")

    assert float(row["안전재고 개월 수"]) == 2.5
    assert int(row["안전재고수량"]) == 75
    assert int(row["안전재고 목표수량"]) == 75
    assert int(row["발주필요수량"]) == 75


def test_stock_eta_status_uses_local_oos_and_order_qty(monkeypatch):
    rows = [
        _eu_row("SKU_OOS", 90, 0, pa_ca_sales=90),
        _eu_row("SKU_ORDER_LABEL", 90, 10, pa_ca_sales=90),
        _eu_row("SKU_OK", 90, 90, pa_ca_sales=90),
    ]
    _install_order_review_uploaded_data(
        monkeypatch,
        rows,
        shipping_qty={
            "SKU_OOS": 80,
            "SKU_OK": 150,
        },
    )

    review = order_review.order_review_df(
        _settings(
            safety_months=3,
        )
    )

    assert _row(review, "SKU_OOS")["재고 ETA 상태"] == "OOS"
    assert _row(review, "SKU_ORDER_LABEL")["재고 ETA 상태"] == "발주필요"
    assert int(_row(review, "SKU_ORDER_LABEL")["발주필요수량"]) > 0
    assert _row(review, "SKU_OK")["재고 ETA 상태"] == "-"
