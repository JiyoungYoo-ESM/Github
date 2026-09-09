import pandas as pd

from core.season_calendar import (
    AMOUNT_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
    BRAND_COL,
    COUNTRY_COL,
    MASTER_PRODUCT_NAME_COL,
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    QTY_COL,
    build_monthly_category1_summary,
    build_top_sku_by_category,
    exclude_season_category1_values,
    merge_sales_with_product_master,
)


def test_season_analysis_counts_only_meaningful_biz_types():
    sales = pd.DataFrame(
        [
            {"출고일": "2026-01-01", "상품코드": "SKU1", "판매수량": 1, "판매금액": 100, "Biz Type": "KR-DOMESTIC"},
            {"출고일": "2026-01-02", "상품코드": "SKU1", "판매수량": 2, "판매금액": 200, "Biz Type": "KR-DOMESTIC 0%"},
            {"출고일": "2026-01-03", "상품코드": "SKU1", "판매수량": 3, "판매금액": 300, "Biz Type": "KR-OVERSEAS"},
            {"출고일": "2026-01-04", "상품코드": "SKU1", "판매수량": 4, "판매금액": 400, "Biz Type": "자사간거래"},
            {"출고일": "2026-01-05", "상품코드": "SKU1", "판매수량": 50, "판매금액": 5000, "Biz Type": "EU-OVERSEAS"},
            {"출고일": "2026-01-06", "상품코드": "SKU1", "판매수량": 60, "판매금액": 6000, "Biz Type": "STAFFSALES"},
        ]
    )
    product_master = pd.DataFrame(
        [{"상품코드": "SKU1", "상품명_마스터": "Item", "브랜드_마스터": "Brand", "기능구분1": "스킨케어", "기능구분2": "토너"}]
    )

    merged = merge_sales_with_product_master(sales, product_master)
    summary = build_monthly_category1_summary(merged)

    assert len(merged) == 4
    assert set(merged[PRODUCT_CODE_COL]) == {"SKU1"}
    assert set(merged[CATEGORY1_COL]) == {"스킨케어"}
    assert set(merged[CATEGORY2_COL]) == {"토너"}
    assert summary[QTY_COL].sum() == 10
    assert summary[AMOUNT_COL].sum() == 1000


def test_eu_local_flag_applies_eu_biz_types_regardless_of_site():
    # 2026-07 팀 확정: EU 판매로 보는 거래유형 = EU-OVERSEAS, EU-PL, 자사간거래, KR-OVERSEAS.
    # 추후상계/샘플(FREE SAMPLE)/반품 등은 제외. site 값은 전혀 보지 않으므로(다양/누락)
    # 판매 법인 코드에 좌우되지 않는다.
    sales = pd.DataFrame(
        [
            {"ship_dt": "2026-06-01", "prod_cd": "SKU1", "qty": 1, "amount_krw": 100, "biz_type": "EU-OVERSEAS", "site": "CO000016", "country": "France"},
            {"ship_dt": "2026-06-02", "prod_cd": "SKU1", "qty": 2, "amount_krw": 200, "biz_type": "EU-PL", "site": "CO999999", "country": "Poland"},
            {"ship_dt": "2026-06-03", "prod_cd": "SKU1", "qty": 4, "amount_krw": 400, "biz_type": "자사간거래", "site": None, "country": "Germany"},
            {"ship_dt": "2026-06-04", "prod_cd": "SKU1", "qty": 8, "amount_krw": 800, "biz_type": "KR-OVERSEAS", "site": "CO000016", "country": "Netherlands"},
            {"ship_dt": "2026-06-05", "prod_cd": "SKU1", "qty": 30, "amount_krw": 3000, "biz_type": "추후상계", "site": "CO000016", "country": "Italy"},
            {"ship_dt": "2026-06-06", "prod_cd": "SKU1", "qty": 40, "amount_krw": 4000, "biz_type": "반품", "site": None, "country": "Germany"},
            {"ship_dt": "2026-06-07", "prod_cd": "SKU1", "qty": 50, "amount_krw": 5000, "biz_type": "FREE SAMPLE", "site": "CO000016", "country": "Spain"},
        ]
    )
    product_master = pd.DataFrame(
        [{"prod_cd": "SKU1", "prod_nm": "Item", "brand_nm": "Brand", "class1_nm": "Skin", "class2_nm": "Toner"}]
    )

    merged = merge_sales_with_product_master(sales, product_master, eu_local=True)

    assert len(merged) == 4
    assert set(merged[COUNTRY_COL]) == {"France", "Poland", "Germany", "Netherlands"}
    assert merged[QTY_COL].sum() == 1 + 2 + 4 + 8
    assert merged[AMOUNT_COL].sum() == 100 + 200 + 400 + 800


def test_hq_entity_uses_api_filtered_history_population_and_amount_krw():
    sales = pd.DataFrame(
        [
            {"ship_dt": "2026-06-01", "prod_cd": "SKU1", "qty": 2, "amount_krw": "120000", "biz_type": "KR-DOMESTIC", "country": "Korea"},
            {"ship_dt": "2026-06-02", "prod_cd": "SKU1", "qty": 3, "amount_krw": "180000", "biz_type": "KR-OVERSEAS", "country": "United States"},
            {"ship_dt": "2026-06-03", "prod_cd": "SKU1", "qty": 90, "amount_krw": "9000000", "biz_type": "US-DOMESTIC", "country": "United States"},
        ]
    )
    product_master = pd.DataFrame(
        [{"prod_cd": "SKU1", "prod_nm": "Item", "brand_nm": "Brand", "class1_nm": "Skin", "class2_nm": "Toner"}]
    )

    merged = merge_sales_with_product_master(sales, product_master, entity_code="HQ")

    assert merged[QTY_COL].sum() == 95
    assert merged[AMOUNT_COL].sum() == 9300000


def test_us_entity_uses_us_local_sales_types():
    sales = pd.DataFrame(
        [
            {"ship_dt": "2026-06-01", "prod_cd": "SKU1", "qty": 2, "amount": 20, "biz_type": "US-DOMESTIC", "country": "United States"},
            {"ship_dt": "2026-06-02", "prod_cd": "SKU1", "qty": 3, "amount": 30, "biz_type": "US-OVERSEAS", "country": "Canada"},
            {"ship_dt": "2026-06-03", "prod_cd": "SKU1", "qty": 90, "amount": 900, "biz_type": "KR-DOMESTIC", "country": "Korea"},
        ]
    )
    product_master = pd.DataFrame(
        [{"prod_cd": "SKU1", "prod_nm": "Item", "brand_nm": "Brand", "class1_nm": "Skin", "class2_nm": "Toner"}]
    )

    merged = merge_sales_with_product_master(sales, product_master, entity_code="USA")

    assert merged[QTY_COL].sum() == 5
    assert merged[AMOUNT_COL].sum() == 50


def test_season_analysis_excludes_free_of_charge_quantity_from_sales_kpis():
    sales = pd.DataFrame(
        [
            {"ship_dt": "2026-06-01", "prod_cd": "PAID", "qty": 10, "amount_krw": 100, "biz_type": "EU-OVERSEAS", "country": "France"},
            {"ship_dt": "2026-06-01", "prod_cd": "FREE", "qty": 500, "amount_krw": 0, "biz_type": "EU-OVERSEAS", "country": "France"},
            {"ship_dt": "2026-06-01", "prod_cd": "RETURN", "qty": -2, "amount_krw": 0, "biz_type": "EU-OVERSEAS", "country": "France"},
        ]
    )
    product_master = pd.DataFrame(
        [
            {"prod_cd": "PAID", "prod_nm": "Paid Item", "brand_nm": "Brand", "class1_nm": "Skin", "class2_nm": "Toner"},
            {"prod_cd": "FREE", "prod_nm": "Gift Item", "brand_nm": "Brand", "class1_nm": "Skin", "class2_nm": "Toner"},
            {"prod_cd": "RETURN", "prod_nm": "Return Item", "brand_nm": "Brand", "class1_nm": "Skin", "class2_nm": "Toner"},
        ]
    )

    merged = merge_sales_with_product_master(sales, product_master, eu_local=True)

    assert merged[PRODUCT_CODE_COL].tolist() == ["PAID", "RETURN"]
    assert merged[QTY_COL].sum() == 8
    assert merged[AMOUNT_COL].sum() == 100


def test_default_flag_uses_kr_biz_types_and_drops_eu_sales():
    # eu_local 미지정(기본=False)이면 KR 기준이라, EU 전용 거래유형은 site와 무관하게 제외된다.
    sales = pd.DataFrame(
        [
            {"ship_dt": "2026-06-01", "prod_cd": "SKU1", "qty": 1, "amount_krw": 100, "biz_type": "KR-DOMESTIC", "site": "CO000016", "country": "Korea"},
            {"ship_dt": "2026-06-02", "prod_cd": "SKU1", "qty": 30, "amount_krw": 3000, "biz_type": "EU-OVERSEAS", "site": "CO000016", "country": "France"},
        ]
    )
    product_master = pd.DataFrame(
        [{"prod_cd": "SKU1", "prod_nm": "Item", "brand_nm": "Brand", "class1_nm": "Skin", "class2_nm": "Toner"}]
    )

    merged = merge_sales_with_product_master(sales, product_master)

    assert len(merged) == 1
    assert set(merged[COUNTRY_COL]) == {"Korea"}
    assert merged[QTY_COL].sum() == 1


def test_season_analysis_keeps_legacy_sales_when_biz_type_column_is_missing():
    sales = pd.DataFrame(
        [
            {"출고일": "2026-01-01", "상품코드": "SKU1", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-02", "상품코드": "SKU2", "판매수량": 2, "판매금액": 200},
        ]
    )
    product_master = pd.DataFrame(
        [
            {"상품코드": "SKU1", "상품명_마스터": "Item 1", "브랜드_마스터": "Brand", "기능구분1": "스킨케어", "기능구분2": "토너"},
            {"상품코드": "SKU2", "상품명_마스터": "Item 2", "브랜드_마스터": "Brand", "기능구분1": "스킨케어", "기능구분2": "토너"},
        ]
    )

    merged = merge_sales_with_product_master(sales, product_master)

    assert len(merged) == 2
    assert merged[QTY_COL].sum() == 3


def test_season_analysis_fills_missing_sales_brand_from_product_master():
    sales = pd.DataFrame(
        [
            {"date": "2026-01-01", "prod_cd": "SKU1", "productname": "", "brand": "", "qty": 1, "amount": 100},
            {"date": "2026-01-01", "prod_cd": "SKU2", "productname": "Sales Item", "brand": "Sales Brand", "qty": 1, "amount": 100},
        ]
    )
    product_master = pd.DataFrame(
        [
            {"prod_cd": "SKU1", "prod_nm": "Master Item", "brand_nm": "Master Brand", "class1_nm": "스킨케어", "class2_nm": "토너"},
            {"prod_cd": "SKU2", "prod_nm": "Other Master Item", "brand_nm": "Other Master Brand", "class1_nm": "스킨케어", "class2_nm": "토너"},
        ]
    )

    merged = merge_sales_with_product_master(sales, product_master)
    by_sku = merged.set_index(PRODUCT_CODE_COL)

    assert by_sku.loc["SKU1", BRAND_COL] == "Master Brand"
    assert by_sku.loc["SKU1", PRODUCT_NAME_COL] == "Master Item"
    assert by_sku.loc["SKU2", BRAND_COL] == "Sales Brand"
    assert by_sku.loc["SKU2", PRODUCT_NAME_COL] == "Sales Item"


def test_season_analysis_keeps_case_variant_skus_separate():
    sales = pd.DataFrame(
        [
            {"date": "2026-01-01", "prod_cd": "A-001", "qty": 2, "amount": 100},
            {"date": "2026-01-01", "prod_cd": "a-001", "qty": 3, "amount": 150},
        ]
    )
    product_master = pd.DataFrame(
        [
            {"prod_cd": "A-001", "prod_nm": "Upper Item", "brand_nm": "Brand", "class1_nm": "Skin", "class2_nm": "Toner"},
            {"prod_cd": "a-001", "prod_nm": "Lower Item", "brand_nm": "Brand", "class1_nm": "Skin", "class2_nm": "Toner"},
        ]
    )

    merged = merge_sales_with_product_master(sales, product_master)
    by_sku = merged.set_index(PRODUCT_CODE_COL)

    assert set(by_sku.index) == {"A-001", "a-001"}
    assert by_sku.loc["A-001", QTY_COL] == 2
    assert by_sku.loc["a-001", QTY_COL] == 3
    assert by_sku.loc["A-001", PRODUCT_NAME_COL] == "Upper Item"
    assert by_sku.loc["a-001", PRODUCT_NAME_COL] == "Lower Item"


def test_nail_unmapped_care_items_are_inferred_from_product_name():
    sales = pd.DataFrame(
        [
            {"출고일": "2026-01-01", "상품코드": "REMOVER", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "GEL_OFF", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "LAMP", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "COLOR", "판매수량": 1, "판매금액": 100},
        ]
    )
    product_master = pd.DataFrame(
        [
            {"상품코드": "REMOVER", "상품명_마스터": "네일리무버 100ml", "브랜드_마스터": "Brand", "기능구분1": "네일", "기능구분2": ""},
            {"상품코드": "GEL_OFF", "상품명_마스터": "샵케어 젤 오프 세럼", "브랜드_마스터": "Brand", "기능구분1": "네일", "기능구분2": ""},
            {"상품코드": "LAMP", "상품명_마스터": "네일툴 베이크드 젤티이 램프", "브랜드_마스터": "Brand", "기능구분1": "네일", "기능구분2": ""},
            {"상품코드": "COLOR", "상품명_마스터": "네일 핑크 발레아쥬", "브랜드_마스터": "Brand", "기능구분1": "네일", "기능구분2": ""},
        ]
    )

    merged = merge_sales_with_product_master(sales, product_master)
    by_sku = dict(zip(merged[PRODUCT_CODE_COL], merged[CATEGORY2_COL], strict=False))

    assert by_sku["REMOVER"] == "네일케어"
    assert by_sku["GEL_OFF"] == "네일케어"
    assert by_sku["LAMP"] == "네일케어"
    assert by_sku["COLOR"] == "미분류"


def test_reviewed_unmapped_product_name_patterns_are_classified():
    sales = pd.DataFrame(
        [
            {"출고일": "2026-01-01", "상품코드": "GLITTER", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "EYELINER", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "LASH_SERUM", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "SCRUB_FOAM", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "FEMININE_WASH", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "PRIMER", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "CLEANSING_GEL", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "MASCARA", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "EMULSION", "판매수량": 1, "판매금액": 100},
            {"출고일": "2026-01-01", "상품코드": "OIL_MIST", "판매수량": 1, "판매금액": 100},
        ]
    )
    product_master = pd.DataFrame(
        [
            {"상품코드": "GLITTER", "상품명_마스터": "트윙클 글리터 2.7 #2 별총총베이지", "브랜드_마스터": "Brand", "기능구분1": "", "기능구분2": ""},
            {"상품코드": "EYELINER", "상품명_마스터": "롱 웨어 미티어라이트 아이라이너 팬슬 1ml", "브랜드_마스터": "Brand", "기능구분1": "컬러메이크업", "기능구분2": ""},
            {"상품코드": "LASH_SERUM", "상품명_마스터": "코스노리 롱 액티브 아이래쉬 세럼 9g", "브랜드_마스터": "Brand", "기능구분1": "", "기능구분2": ""},
            {"상품코드": "SCRUB_FOAM", "상품명_마스터": "아워 비건 오곡라떼 스크럽 폼 120ml", "브랜드_마스터": "Brand", "기능구분1": "스킨케어", "기능구분2": ""},
            {"상품코드": "FEMININE_WASH", "상품명_마스터": "약산성 여성청결제 500ml", "브랜드_마스터": "Brand", "기능구분1": "바디", "기능구분2": ""},
            {"상품코드": "PRIMER", "상품명_마스터": "포어마스터 세범 컨트롤 프라이머", "브랜드_마스터": "Brand", "기능구분1": "페이스메이크업", "기능구분2": ""},
            {"상품코드": "CLEANSING_GEL", "상품명_마스터": "[단종]세라마이드 클렌징젤 200ml", "브랜드_마스터": "Brand", "기능구분1": "클렌징", "기능구분2": ""},
            {"상품코드": "MASCARA", "상품명_마스터": "이니스프리 스키니 롱롱카라 [Innisfree]", "브랜드_마스터": "Brand", "기능구분1": "컬러메이크업", "기능구분2": ""},
            {"상품코드": "EMULSION", "상품명_마스터": "상추오이 워터리 에멀전 140ml", "브랜드_마스터": "Brand", "기능구분1": "스킨케어", "기능구분2": ""},
            {"상품코드": "OIL_MIST", "상품명_마스터": "(단종) 이니스프리 올리브 리얼 오일 미스트 80mL", "브랜드_마스터": "Brand", "기능구분1": "", "기능구분2": ""},
        ]
    )

    merged = merge_sales_with_product_master(sales, product_master)
    by_sku = {
        sku: (category1, category2)
        for sku, category1, category2 in zip(
            merged[PRODUCT_CODE_COL], merged[CATEGORY1_COL], merged[CATEGORY2_COL], strict=False
        )
    }

    assert by_sku == {
        "GLITTER": ("컬러메이크업", "아이섀도"),
        "EYELINER": ("컬러메이크업", "아이라이너"),
        "LASH_SERUM": ("스킨케어", "세럼"),
        "SCRUB_FOAM": ("클렌징", "클렌징폼"),
        "FEMININE_WASH": ("바디", "바디워시"),
        "PRIMER": ("페이스메이크업", "프라이머/베이스"),
        "CLEANSING_GEL": ("클렌징", "클렌징오일/워터/밀크"),
        "MASCARA": ("컬러메이크업", "마스카라"),
        "EMULSION": ("스킨케어", "에멀전"),
        "OIL_MIST": ("스킨케어", "미스트"),
    }


def test_season_analysis_excludes_promo_accessory_sample_and_sachet_items():
    rows = pd.DataFrame(
        [
            {
                PRODUCT_CODE_COL: "TKBSM05-SAMPLE",
                MASTER_PRODUCT_NAME_COL: "[샘플] 바이오 워터리 선크림",
                CATEGORY1_COL: "썬케어",
            },
            {
                PRODUCT_CODE_COL: "HBUS1-LS",
                MASTER_PRODUCT_NAME_COL: "[샤쉐] 3종 리플렛 살몬케어링 센텔라 스킨케어 라인",
                CATEGORY1_COL: "스킨케어",
            },
            {
                PRODUCT_CODE_COL: "FWCM01-BK",
                MASTER_PRODUCT_NAME_COL: "푸딩팟 키링(색깔 랜덤)",
                CATEGORY1_COL: "악세사리",
            },
            {
                PRODUCT_CODE_COL: "REAL-SUN",
                MASTER_PRODUCT_NAME_COL: "바이오 워터리 선크림 50ml",
                CATEGORY1_COL: "썬케어",
            },
        ]
    )

    filtered = exclude_season_category1_values(rows)

    assert filtered[PRODUCT_CODE_COL].tolist() == ["REAL-SUN"]


def test_country_top_sku_uses_country_scoped_recent_window():
    rows = pd.DataFrame(
        [
            {
                "출고일": "2026-01-01",
                COUNTRY_COL: "France",
                CATEGORY1_COL: "스킨케어",
                CATEGORY2_COL: "토너",
                PRODUCT_CODE_COL: "SKU-FR",
                BRAND_COL: "Brand",
                PRODUCT_NAME_COL: "FR Item",
                QTY_COL: 10,
                AMOUNT_COL: 100,
            },
            {
                "출고일": "2026-04-01",
                COUNTRY_COL: "France",
                CATEGORY1_COL: "스킨케어",
                CATEGORY2_COL: "토너",
                PRODUCT_CODE_COL: "SKU-FR",
                BRAND_COL: "Brand",
                PRODUCT_NAME_COL: "FR Item",
                QTY_COL: 20,
                AMOUNT_COL: 200,
            },
            {
                "출고일": "2026-01-01",
                COUNTRY_COL: "Spain",
                CATEGORY1_COL: "스킨케어",
                CATEGORY2_COL: "토너",
                PRODUCT_CODE_COL: "SKU-ES",
                BRAND_COL: "Brand",
                PRODUCT_NAME_COL: "ES Item",
                QTY_COL: 7,
                AMOUNT_COL: 70,
            },
        ]
    )
    rows["출고일"] = pd.to_datetime(rows["출고일"])

    result = build_top_sku_by_category(rows, group_columns=[COUNTRY_COL]).set_index(COUNTRY_COL)

    assert result.loc["France", QTY_COL] == 30
    assert result.loc["France", "최근3M_수량"] == 20
    assert result.loc["France", "최근6M_수량"] == 30
    assert result.loc["Spain", QTY_COL] == 7
    assert result.loc["Spain", "최근3M_수량"] == 7
    assert result.loc["Spain", "최근6M_수량"] == 7
