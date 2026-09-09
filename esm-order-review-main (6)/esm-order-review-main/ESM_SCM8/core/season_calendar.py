from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from core.export_excel_util import append_df, autosize_columns


PRODUCT_CODE_COL = "상품코드"
PRODUCT_NAME_COL = "상품명"
MASTER_PRODUCT_NAME_COL = "상품명_마스터"
BRAND_COL = "브랜드"
MASTER_BRAND_COL = "브랜드_마스터"
CATEGORY1_COL = "기능구분1"
CATEGORY2_COL = "기능구분2"
COUNTRY_COL = "국가"
UNKNOWN_COUNTRY = "미상"
CUSTOMER_COL = "거래처"
CUSTOMER_SHORT_COL = "거래처 약칭"
UNKNOWN_CUSTOMER = "미상"
DATE_COL = "출고일"
QTY_COL = "판매수량"
AMOUNT_COL = "판매금액"
UNMAPPED = "미분류"
PRODUCT_MASTER_MATCHED_COL = "_상품마스터_매칭"
PRODUCT_MASTER_CATEGORY1_CODE_COL = "_상품마스터_기능구분1코드"
PRODUCT_MASTER_CATEGORY1_COL = "_상품마스터_기능구분1"
PRODUCT_MASTER_CATEGORY2_COL = "_상품마스터_기능구분2"
DIAGNOSTIC_REASON_COL = "진단사유"
DIAGNOSTIC_EDITABLE_COL = "수정가능"
COSMETIC_CATEGORY1_BY_CODE = {
    "01": "스킨케어",
    "02": "페이스메이크업",
    "03": "컬러메이크업",
    "04": "썬케어",
    "05": "바디",
    "06": "네일",
    "07": "헤어",
    "08": "마스크",
    "09": "비비/씨씨크림",
    "10": "옴므",
    "11": "클렌징",
    "13": "향수/아로마",
    "15": "화장소품",
    "60": "디바이스",
}
COSMETIC_CATEGORY1_VALUES = frozenset(COSMETIC_CATEGORY1_BY_CODE.values())
EXCLUDED_SEASON_CATEGORY1_VALUES = {
    "기타",
    "포토카드",
    "생활용품",
    "식품",
    "건강식품",
    "치약",
    "렌즈",
    "패드",
    "비누",
    "악세사리",
    "화장품 진열 집기",
}
EXCLUDED_SEASON_PRODUCT_CODE_KEYWORDS = ("sample",)
EXCLUDED_SEASON_PRODUCT_NAME_KEYWORDS = (
    "샘플",
    "sample",
    "사쉐",
    "샤쉐",
    "리플렛",
    "키링",
    "keychain",
    "key chain",
    "스크런치",
    "vmd",
    "집기",
    "테스터",
)
SEASON_SALES_BIZ_TYPES = {"KR-DOMESTIC", "KR-DOMESTIC 0%", "KR-OVERSEAS", "자사간거래"}
EU_LOCAL_SALES_BIZ_TYPES = {"EU-OVERSEAS", "EU-PL", "KR-OVERSEAS", "자사간거래"}
US_LOCAL_SALES_BIZ_TYPES = {
    "US-DOMESTIC",
    "US-OVERSEAS",
    "KR-OVERSEAS",
    "자사간거래",
}
OFFICIAL_CATEGORY1_VALUES = [
    "스킨케어",
    "페이스메이크업",
    "컬러메이크업",
    "썬케어",
    "바디",
    "네일",
    "헤어",
    "마스크",
    "비비/씨씨크림",
    "옴므",
    "클렌징",
    "악세사리",
    "향수/아로마",
    "차",
    "음료",
    "화장소품",
    "치약",
    "파스",
    "스카프",
    "반창고",
    "직물",
    "생활용품",
    "식품",
    "칫솔",
    "세정제품",
    "이불 등 기타 침구류",
    "면 담요",
    "유아 의류",
    "패드",
    "기저귀",
    "색연필",
    "크래용",
    "비누",
    "필통",
    "지갑, 가방",
    "지우개",
    "일기장",
    "연필깎이",
    "장갑",
    "연고",
    "음반",
    "기타",
    "가구",
    "의류(상의)",
    "의류(하의)",
    "렌즈",
    "건강식품",
    "스티커",
    "세제",
    "포스터",
    "포토카드",
    "응원봉",
    "소품",
    "문구",
    "포토북",
    "잡지",
    "시즌그리팅",
    "KPOP 기타",
    "햇츠카드",
    "뷰티 이벤트박스(PA전용)",
    "디바이스",
    "가글",
    "양말",
    "화장품 진열 집기",
]
OFFICIAL_CATEGORY2_BY_CATEGORY1 = {
    "스킨케어": [
        "토너",
        "에멀전",
        "에센스",
        "크림",
        "아이크림",
        "나이트크림",
        "데이크림",
        "미스트",
        "수분크림",
        "앰플",
        "필러",
        "Set",
        "오일",
        "패치",
        "젤",
        "세럼",
        "립밤",
        "파우더",
    ],
    "페이스메이크업": [
        "파운데이션",
        "팩트/파우더/트윈케익",
        "컨실러",
        "프라이머/베이스",
        "쿠션",
        "픽서",
    ],
    "컬러메이크업": [
        "립스틱/립틴트/립글로스",
        "아이라이너",
        "마스카라",
        "블러셔/하이라이터",
        "아이섀도",
        "아이브로우",
    ],
    "썬케어": [
        "크림",
        "에센스",
    ],
    "바디": [
        "샤워볼",
        "패치",
        "세니타이저",
        "티슈",
        "데오드란트",
        "바디워시",
        "바디 모이스춰라이저",
        "바디오일/스크럽",
        "핸드/풋",
        "제모크림",
    ],
    "네일": [
        "네일컬러",
        "네일케어",
    ],
    "헤어": [
        "오일",
        "토닉",
        "빗",
        "타투",
        "브러시",
        "헤어도구",
        "스프레이",
        "왁스",
        "디바이스",
        "입욕제",
        "마스카라",
        "샴푸",
        "컨디셔너",
        "트리트먼트",
        "에센스",
        "헤어크림",
        "쿠션",
        "미스트",
        "염색약",
        "Set",
    ],
    "마스크": [
        "시트마스크",
        "마스크/팩",
    ],
    "비비/씨씨크림": [
        "비비크림",
        "씨씨크림",
    ],
    "클렌징": [
        "클렌징폼",
        "클렌징오일/워터/밀크",
        "스크럽/필링",
        "립/아이 리무버",
        "워시",
        "클렌징크림",
        "비누",
        "클렌징 스틱",
        "패드",
    ],
    "악세사리": [
        "스트랩",
        "파우치",
        "거울",
    ],
    "향수/아로마": [
        "방향제",
        "향수",
    ],
    "화장소품": [
        "오일페이퍼",
        "브러쉬",
        "퍼프",
        "버블 메이커",
        "스폰지",
        "화장솜",
        "헤어밴드(6117.80.0000)",
        "헤어롤",
        "뷰러",
        "마사지기",
    ],
    "치약": [
        "치약",
    ],
    "생활용품": [
        "마스크",
    ],
    "칫솔": [
        "칫솔",
    ],
    "가글": [
        "가글",
    ],
    "디바이스": [
        "페이스",
        "바디",
    ],
    "소품": [
        "쇼핑백",
    ],
    "의류(상의)": [
        "티셔츠",
    ],
    "렌즈": [
        "서클렌즈",
    ],
    "기타": [
        "필터",
        "어드벤트 캘린더",
    ],
}


def _norm(value: object) -> str:
    return "".join(str(value or "").split()).lower()


OFFICIAL_CATEGORY1_BY_NORM = {_norm(value): value for value in OFFICIAL_CATEGORY1_VALUES}
OFFICIAL_CATEGORY2_BY_CATEGORY1_NORM = {
    _norm(category1): {_norm(category2): category2 for category2 in values}
    for category1, values in OFFICIAL_CATEGORY2_BY_CATEGORY1.items()
}
CATEGORY1_ALIASES = {
    _norm("선케어"): "썬케어",
    _norm("비비/씨씨 크림"): "비비/씨씨크림",
    _norm("지갑가방"): "지갑, 가방",
    _norm("지갑,가방"): "지갑, 가방",
}
CATEGORY2_ALIASES_BY_CATEGORY1 = {
    _norm("스킨케어"): {
        _norm("세트"): "Set",
        _norm("set"): "Set",
    }
}
NAIL_CARE_NAME_KEYWORDS = ("네일리무버", "리무버", "젤 오프", "젤오프", "램프")
PRODUCT_NAME_CATEGORY_RULES = (
    (("트윙클 글리터", "글리터"), "컬러메이크업", "아이섀도"),
    (("아이라이너",), "컬러메이크업", "아이라이너"),
    (("롱롱카라", "마스카라"), "컬러메이크업", "마스카라"),
    (("아이래쉬 세럼", "속눈썹 세럼"), "스킨케어", "세럼"),
    (("스크럽 폼", "스크럽폼"), "클렌징", "클렌징폼"),
    (("클렌징젤", "클렌징 젤"), "클렌징", "클렌징오일/워터/밀크"),
    (("여성청결제", "이너 클렌저"), "바디", "바디워시"),
    (("포어마스터 세범 컨트롤 프라이머", "프라이머"), "페이스메이크업", "프라이머/베이스"),
    (("광채 볼류머", "볼류머"), "페이스메이크업", "프라이머/베이스"),
    (("상추오이 워터리 에멀전", "에멀전"), "스킨케어", "에멀전"),
    (("올리브 리얼 오일 미스트", "오일 미스트"), "스킨케어", "미스트"),
)


def infer_category_from_product_name(product_name: object) -> tuple[str, str] | None:
    normalized_name = _norm(product_name)
    for keywords, category1, category2 in PRODUCT_NAME_CATEGORY_RULES:
        if any(_norm(keyword) in normalized_name for keyword in keywords):
            return category1, category2
    return None


def normalize_category1_name(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return UNMAPPED
    normalized = _norm(text)
    return CATEGORY1_ALIASES.get(normalized) or OFFICIAL_CATEGORY1_BY_NORM.get(normalized) or text


def normalize_category1_code(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(2) if text.isdigit() and len(text) < 2 else text.upper()


def infer_category1_name(category1: object, product_name: object) -> str:
    inferred = infer_category_from_product_name(product_name)
    if inferred is not None:
        return inferred[0]
    return normalize_category1_name(category1)


def is_official_category1(value: object) -> bool:
    text = normalize_category1_name(value)
    return text == UNMAPPED or _norm(text) in OFFICIAL_CATEGORY1_BY_NORM


def normalize_category2_name(category1: object, value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return UNMAPPED
    category1_key = _norm(normalize_category1_name(category1))
    normalized = _norm(text)
    aliases = CATEGORY2_ALIASES_BY_CATEGORY1.get(category1_key, {})
    official_values = OFFICIAL_CATEGORY2_BY_CATEGORY1_NORM.get(category1_key)
    if official_values is None:
        return text
    return aliases.get(normalized) or official_values.get(normalized) or text


def infer_category2_name(category1: object, category2: object, product_name: object) -> str:
    normalized_category2 = normalize_category2_name(category1, category2)
    if normalized_category2 != UNMAPPED:
        return normalized_category2
    inferred = infer_category_from_product_name(product_name)
    if inferred is not None:
        return inferred[1]
    if normalize_category1_name(category1) != "네일":
        return normalized_category2
    name = str(product_name or "").strip()
    normalized_name = _norm(name)
    if any(_norm(keyword) in normalized_name for keyword in NAIL_CARE_NAME_KEYWORDS):
        return "네일케어"
    return normalized_category2


def is_official_category2(category1: object, value: object) -> bool:
    category1_key = _norm(normalize_category1_name(category1))
    official_values = OFFICIAL_CATEGORY2_BY_CATEGORY1_NORM.get(category1_key)
    if official_values is None:
        return True
    text = normalize_category2_name(category1, value)
    return text == UNMAPPED or _norm(text) in official_values


def exclude_season_category1_values(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(df).copy()
    if out.empty:
        return out
    keep_mask = pd.Series(True, index=out.index)
    if CATEGORY1_COL in out.columns:
        keep_mask &= ~out[CATEGORY1_COL].astype(str).str.strip().isin(EXCLUDED_SEASON_CATEGORY1_VALUES)
    if PRODUCT_CODE_COL in out.columns:
        product_codes = out[PRODUCT_CODE_COL].map(_norm)
        keep_mask &= ~product_codes.map(
            lambda value: any(keyword in value for keyword in EXCLUDED_SEASON_PRODUCT_CODE_KEYWORDS)
        )
    if MASTER_PRODUCT_NAME_COL in out.columns:
        product_names = out[MASTER_PRODUCT_NAME_COL].map(_norm)
        keep_mask &= ~product_names.map(
            lambda value: any(_norm(keyword) in value for keyword in EXCLUDED_SEASON_PRODUCT_NAME_KEYWORDS)
        )
    return out[keep_mask].copy()


def filter_season_sales_by_biz_type(
    sales_df: pd.DataFrame,
    eu_local: bool = False,
    entity_code: str | None = None,
) -> pd.DataFrame:
    # eu_local은 데이터 출처로 결정한다. /eu/sales/local API에서 온 데이터는
    # 정의상 전부 EU 현지 판매이므로 eu_local=True로 호출하고 EU 거래유형 기준을
    # 적용한다. 그 외(엑셀 업로드 등)는 기존 KR 기준. site 값을 들여다보지 않으므로
    # 판매 법인 코드가 늘어나도 영향받지 않는다.
    out = pd.DataFrame(sales_df).copy()
    if out.empty:
        return out
    biz_col = _find_col(out, ("Biz Type", "BizType", "biz_type", "거래유형"))
    if biz_col is None:
        return out
    code = str(entity_code or "").strip().upper()
    if code == "HQ":
        # /us/sales/history is already the CMS-defined headquarters sales
        # population with EXCS removed. Its valid rows span several biz_type
        # families (the API contract itself uses US-DOMESTIC as an example),
        # so applying a subsidiary allow-list here would drop real HQ sales.
        return out
    biz = out[biz_col].astype(str).str.strip()
    if code == "USA":
        allowed = US_LOCAL_SALES_BIZ_TYPES
    elif code == "PL":
        allowed = EU_LOCAL_SALES_BIZ_TYPES
    else:
        # Preserve the existing upload behavior when no entity was supplied.
        allowed = EU_LOCAL_SALES_BIZ_TYPES if eu_local else SEASON_SALES_BIZ_TYPES
    return out[biz.isin(allowed)].copy()


def _find_col(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    normalized = {_norm(col): str(col) for col in df.columns}
    for alias in aliases:
        col = normalized.get(_norm(alias))
        if col is not None:
            return col
    return None


def _series(df: pd.DataFrame, aliases: Iterable[str], default: object = "") -> pd.Series:
    col = _find_col(df, aliases)
    if col is None:
        return pd.Series([default] * len(df), index=df.index)
    return df[col]


def _number_series(values: pd.Series) -> pd.Series:
    cleaned = (
        values.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False)
        .replace({"": "0", "nan": "0", "None": "0"})
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)


def normalize_product_code(s, *, preserve_suffix: bool = False) -> str:
    text = str(s or "").strip()
    return text[:-2] if not preserve_suffix and text.endswith(".0") else text


def _delivery_charge_mask(df: pd.DataFrame) -> pd.Series:
    code = _series(df, (PRODUCT_CODE_COL, "SKU", "prod_cd")).astype(str).str.upper().str.strip()
    name = _series(df, (PRODUCT_NAME_COL, MASTER_PRODUCT_NAME_COL, "prod_nm")).astype(str).str.upper().str.strip()
    return code.str.contains("DELIVERY CHARGE", na=False) | name.str.contains("DELIVERY CHARGE", na=False)


def _standard_sales_amount_series(
    df: pd.DataFrame,
    *,
    entity_code: str | None = None,
) -> pd.Series:
    actual_krw_col = _find_col(df, ("amount_krw_actual", "실제 원화 환산금액"))
    if actual_krw_col is not None:
        # EU/US 현지판매는 거래일(반품은 반품일) 환율이 이미 건별 반영돼 있다.
        return _number_series(df[actual_krw_col])

    if str(entity_code or "").strip().upper() == "HQ":
        hq_krw_col = _find_col(df, ("amount_krw", "환산금액"))
        if hq_krw_col is not None:
            # 본사 sales/history의 amount_krw는 원화 원천이다.
            return _number_series(df[hq_krw_col])

    source_col = _find_col(df, ("금액", AMOUNT_COL, "매출", "amount"))
    converted_col = _find_col(df, ("환산금액", "amount_krw"))
    if source_col is None and converted_col is None:
        return pd.Series([0.0] * len(df), index=df.index)
    if source_col is None:
        return _number_series(df[converted_col])
    source_amount = _number_series(df[source_col])
    if converted_col is None:
        return source_amount

    converted_amount = _number_series(df[converted_col])
    currency_col = _find_col(df, ("통화", "curr", "currency"))
    if currency_col is None:
        return source_amount

    currency = df[currency_col].astype(str).str.upper().str.strip()
    comparable = source_amount.abs().gt(0) & converted_amount.abs().gt(0)
    eur_reference = comparable & currency.eq("EUR")
    reference = eur_reference if eur_reference.any() else comparable
    if not reference.any():
        return source_amount

    median_ratio = (converted_amount[reference].abs() / source_amount[reference].abs()).median()
    # EU API의 amount는 거래 통화(GBP 등), amount_krw는 현재 응답에서 EUR 정규화값으로
    # 내려오는 경우가 있다. EUR 행의 비율이 1에 가깝거나 단일 통화 환산비가 상식 범위면
    # 정규화 열을 사용한다. 실제 KRW 값(비율 수백~수천)은 이 조건에서 제외한다.
    normalized_is_eur = (
        0.95 <= median_ratio <= 1.05
        if eur_reference.any()
        else 0.5 <= median_ratio <= 2.0
    )
    if not normalized_is_eur:
        return source_amount
    return converted_amount.where(converted_amount.ne(0) | source_amount.eq(0), source_amount)


def _standard_sales_df(
    sales_df: pd.DataFrame,
    *,
    entity_code: str | None = None,
    preserve_product_code_suffix: bool = False,
) -> pd.DataFrame:
    df = pd.DataFrame(sales_df).copy()
    if df.empty:
        return pd.DataFrame(columns=[DATE_COL, PRODUCT_CODE_COL, PRODUCT_NAME_COL, BRAND_COL, QTY_COL, AMOUNT_COL])

    out = pd.DataFrame(index=df.index)
    out[DATE_COL] = pd.to_datetime(_series(df, (DATE_COL, "출고 일자", "일자", "date", "Date", "ship_dt")), errors="coerce")
    out[PRODUCT_CODE_COL] = _series(df, (PRODUCT_CODE_COL, "SKU", "품목코드", "itemcode", "prod_cd")).map(
        lambda value: normalize_product_code(value, preserve_suffix=preserve_product_code_suffix)
    )
    out[PRODUCT_NAME_COL] = _series(df, (PRODUCT_NAME_COL, "품목명", "itemname", "productname", "prod_nm"))
    out[BRAND_COL] = _series(df, (BRAND_COL, "브랜드명", "brand", "brandname", "brand_nm"))
    out[COUNTRY_COL] = _series(df, (COUNTRY_COL, "country"), "")
    out[CUSTOMER_COL] = _series(df, (CUSTOMER_COL, "customer", "client", "account"), "")
    out[CUSTOMER_SHORT_COL] = _series(df, (CUSTOMER_SHORT_COL, "거래처약칭", "customer_short", "customer_short_name"), "")
    out["Site"] = _series(df, ("Site", "site"), "")
    out["창고"] = _series(df, ("창고", "warehouse"), "")
    out[QTY_COL] = _number_series(_series(df, (QTY_COL, "수량", "판매 수량", "qty", "quantity"), 0))
    out[AMOUNT_COL] = _standard_sales_amount_series(df, entity_code=entity_code)
    out = out[~out[DATE_COL].isna()].copy()
    out = out[~_delivery_charge_mask(out)].copy()
    # Business definition: free-of-charge shipments are inventory movements,
    # not paid sales. Exclude positive-quantity, zero-revenue rows from every
    # season/brand sales KPI, including quantity and selling-SKU counts.
    free_of_charge = out[QTY_COL].gt(0) & out[AMOUNT_COL].eq(0)
    out = out[~free_of_charge].copy()
    return out


def _filter_sales_period(
    sales: pd.DataFrame,
    start_date: pd.Timestamp | None = None,
    end_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    out = pd.DataFrame(sales)
    if out.empty or DATE_COL not in out.columns:
        return out
    if start_date is not None:
        out = out[out[DATE_COL] >= start_date]
    if end_date is not None:
        out = out[out[DATE_COL] <= end_date]
    return out.copy()


def _standard_prod_df(
    prod_df: pd.DataFrame, *, preserve_product_code_suffix: bool = False,
) -> pd.DataFrame:
    df = pd.DataFrame(prod_df).copy()
    if df.empty:
        return pd.DataFrame(
            columns=[
                PRODUCT_CODE_COL,
                MASTER_PRODUCT_NAME_COL,
                MASTER_BRAND_COL,
                CATEGORY1_COL,
                CATEGORY2_COL,
                PRODUCT_MASTER_MATCHED_COL,
                PRODUCT_MASTER_CATEGORY1_CODE_COL,
                PRODUCT_MASTER_CATEGORY1_COL,
                PRODUCT_MASTER_CATEGORY2_COL,
            ]
        )

    out = pd.DataFrame(index=df.index)
    out[PRODUCT_CODE_COL] = _series(df, (PRODUCT_CODE_COL, "SKU", "품목코드", "itemcode", "prod_cd")).map(
        lambda value: normalize_product_code(value, preserve_suffix=preserve_product_code_suffix)
    )
    out[MASTER_PRODUCT_NAME_COL] = _series(df, (MASTER_PRODUCT_NAME_COL, "prod_nm", PRODUCT_NAME_COL, "상품명마스터"))
    out[MASTER_BRAND_COL] = _series(df, (MASTER_BRAND_COL, "brand_nm", BRAND_COL, "브랜드마스터"))
    out[PRODUCT_MASTER_CATEGORY1_CODE_COL] = _series(df, ("class1", "기능구분1코드"), "").map(
        normalize_category1_code
    )
    category1_raw = _series(df, (CATEGORY1_COL, "class1_nm"), UNMAPPED)
    master_category1 = category1_raw.map(normalize_category1_name)
    code_category1 = out[PRODUCT_MASTER_CATEGORY1_CODE_COL].map(COSMETIC_CATEGORY1_BY_CODE)
    master_category1 = master_category1.mask(
        master_category1.eq(UNMAPPED) & code_category1.notna(),
        code_category1,
    )
    out[PRODUCT_MASTER_CATEGORY1_COL] = master_category1
    out[CATEGORY1_COL] = [
        infer_category1_name(category1, product_name)
        for category1, product_name in zip(master_category1, out[MASTER_PRODUCT_NAME_COL], strict=False)
    ]
    category2_raw = _series(df, (CATEGORY2_COL, "class2_nm"), UNMAPPED)
    master_category2 = pd.Series(
        [
            normalize_category2_name(category1, category2)
            for category1, category2 in zip(master_category1, category2_raw, strict=False)
        ],
        index=df.index,
    )
    out[PRODUCT_MASTER_CATEGORY2_COL] = master_category2
    out[CATEGORY2_COL] = [
        infer_category2_name(category1, category2, product_name)
        for category1, category2, product_name in zip(
            out[CATEGORY1_COL],
            master_category2,
            out[MASTER_PRODUCT_NAME_COL],
            strict=False,
        )
    ]
    out[PRODUCT_MASTER_MATCHED_COL] = True
    out["바코드"] = _series(df, ("바코드", "bar_code"), "")
    out["상품구분"] = _series(df, ("상품구분", "prod_gbn"), "")
    out["사용여부"] = _series(df, ("사용여부", "use_yn"), "")
    out = out[out[PRODUCT_CODE_COL].astype(str).str.strip() != ""].copy()
    return out.drop_duplicates(subset=[PRODUCT_CODE_COL], keep="first")


def merge_sales_with_product_master(
    sales_df: pd.DataFrame,
    prod_df: pd.DataFrame,
    start_date: pd.Timestamp | None = None,
    end_date: pd.Timestamp | None = None,
    eu_local: bool = False,
    entity_code: str | None = None,
    *,
    preserve_product_code_suffix: bool = False,
) -> pd.DataFrame:
    sales = _standard_sales_df(
        filter_season_sales_by_biz_type(
            sales_df,
            eu_local=eu_local,
            entity_code=entity_code,
        ),
        entity_code=entity_code,
        preserve_product_code_suffix=preserve_product_code_suffix,
    )
    sales = _filter_sales_period(sales, start_date=start_date, end_date=end_date)
    prod = _standard_prod_df(prod_df, preserve_product_code_suffix=preserve_product_code_suffix)
    if sales.empty:
        return sales.assign(
            **{
                CATEGORY1_COL: UNMAPPED,
                CATEGORY2_COL: UNMAPPED,
                PRODUCT_MASTER_MATCHED_COL: False,
            }
        )
    if prod.empty:
        sales[CATEGORY1_COL] = UNMAPPED
        sales[CATEGORY2_COL] = UNMAPPED
        sales[MASTER_PRODUCT_NAME_COL] = ""
        sales[MASTER_BRAND_COL] = ""
        sales[PRODUCT_MASTER_MATCHED_COL] = False
        sales[PRODUCT_MASTER_CATEGORY1_CODE_COL] = ""
        sales[PRODUCT_MASTER_CATEGORY1_COL] = UNMAPPED
        sales[PRODUCT_MASTER_CATEGORY2_COL] = UNMAPPED
        return sales
    merged = sales.merge(prod, on=PRODUCT_CODE_COL, how="left")
    for target_col, fallback_col in (
        (BRAND_COL, MASTER_BRAND_COL),
        (PRODUCT_NAME_COL, MASTER_PRODUCT_NAME_COL),
    ):
        if target_col in merged.columns and fallback_col in merged.columns:
            target = merged[target_col]
            missing = target.isna() | target.astype(str).str.strip().isin(["", "-", "nan", "None", "none", "N/A", "n/a", "<NA>"])
            merged[target_col] = target.mask(missing, merged[fallback_col]).fillna("").astype(str).str.strip()
    merged[CATEGORY1_COL] = merged[CATEGORY1_COL].replace("", pd.NA).fillna(UNMAPPED)
    merged[CATEGORY2_COL] = merged[CATEGORY2_COL].replace("", pd.NA).fillna(UNMAPPED)
    merged[PRODUCT_MASTER_MATCHED_COL] = merged[PRODUCT_MASTER_MATCHED_COL].fillna(False).astype(bool)
    merged[PRODUCT_MASTER_CATEGORY1_CODE_COL] = (
        merged[PRODUCT_MASTER_CATEGORY1_CODE_COL].fillna("").map(normalize_category1_code)
    )
    merged[PRODUCT_MASTER_CATEGORY1_COL] = (
        merged[PRODUCT_MASTER_CATEGORY1_COL].fillna(UNMAPPED).map(normalize_category1_name)
    )
    merged[PRODUCT_MASTER_CATEGORY2_COL] = (
        merged[PRODUCT_MASTER_CATEGORY2_COL].fillna(UNMAPPED)
    )
    return merged


def split_cosmetic_product_scope(merged_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep only master-designated Cosmetic rows and return actionable data issues."""
    merged = pd.DataFrame(merged_df).copy()
    if merged.empty:
        return merged, merged

    matched = merged.get(PRODUCT_MASTER_MATCHED_COL, False)
    if not isinstance(matched, pd.Series):
        matched = pd.Series(bool(matched), index=merged.index)
    matched = matched.fillna(False).astype(bool)

    category1_code = merged.get(PRODUCT_MASTER_CATEGORY1_CODE_COL, "")
    if not isinstance(category1_code, pd.Series):
        category1_code = pd.Series(str(category1_code or ""), index=merged.index)
    category1_code = category1_code.fillna("").map(normalize_category1_code)

    master_category1 = merged.get(PRODUCT_MASTER_CATEGORY1_COL, merged.get(CATEGORY1_COL, UNMAPPED))
    if not isinstance(master_category1, pd.Series):
        master_category1 = pd.Series(master_category1, index=merged.index)
    master_category1 = master_category1.fillna(UNMAPPED).map(normalize_category1_name)

    code_is_cosmetic = category1_code.isin(COSMETIC_CATEGORY1_BY_CODE)
    name_is_cosmetic = master_category1.isin(COSMETIC_CATEGORY1_VALUES)
    name_is_official = master_category1.map(is_official_category1) & master_category1.ne(UNMAPPED)
    code_name_conflict = (
        category1_code.ne("")
        & code_is_cosmetic.ne(name_is_cosmetic)
        & master_category1.ne(UNMAPPED)
    )
    cosmetic = matched & ~code_name_conflict & (code_is_cosmetic | (category1_code.eq("") & name_is_cosmetic))
    known_non_cosmetic = matched & ~code_name_conflict & ~cosmetic & name_is_official

    final_category2 = merged.get(CATEGORY2_COL, UNMAPPED)
    if not isinstance(final_category2, pd.Series):
        final_category2 = pd.Series(final_category2, index=merged.index)
    category2_missing = final_category2.fillna(UNMAPPED).astype(str).str.strip().isin({"", UNMAPPED, "nan", "None"})
    eligible_mask = cosmetic & ~category2_missing

    diagnosis_reason = pd.Series("", index=merged.index, dtype="object")
    diagnosis_editable = pd.Series(False, index=merged.index, dtype="bool")
    diagnosis_reason.loc[~matched] = "상품마스터 미매칭"
    diagnosis_reason.loc[matched & master_category1.eq(UNMAPPED)] = "상품마스터 대분류 누락"
    diagnosis_reason.loc[matched & code_name_conflict] = "상품마스터 대분류 코드/명 불일치"
    diagnosis_reason.loc[
        matched & ~known_non_cosmetic & ~cosmetic & master_category1.ne(UNMAPPED) & ~code_name_conflict
    ] = "상품마스터 대분류 확인 필요"
    diagnosis_reason.loc[cosmetic & category2_missing] = "상품마스터 중분류 누락"
    diagnosis_editable.loc[cosmetic & category2_missing] = True

    diagnostic_mask = diagnosis_reason.ne("")
    diagnostics = merged.loc[diagnostic_mask].copy()
    diagnostics[DIAGNOSTIC_REASON_COL] = diagnosis_reason.loc[diagnostic_mask]
    diagnostics[DIAGNOSTIC_EDITABLE_COL] = diagnosis_editable.loc[diagnostic_mask]

    eligible = merged.loc[eligible_mask].copy()
    if not eligible.empty:
        code_names = category1_code.loc[eligible.index].map(COSMETIC_CATEGORY1_BY_CODE)
        canonical_category1 = master_category1.loc[eligible.index].mask(code_names.notna(), code_names)
        eligible[CATEGORY1_COL] = canonical_category1
    return eligible, diagnostics


def _with_month_parts(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(df).copy()
    out["year"] = out[DATE_COL].dt.year.astype("Int64")
    out["month"] = out[DATE_COL].dt.month.astype("Int64")
    out["year_month"] = out[DATE_COL].dt.to_period("M").astype(str)
    out["quarter"] = "Q" + out[DATE_COL].dt.quarter.astype("Int64").astype(str)
    return out


def _summary(df: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["year", "month", "year_month", "quarter", *groups, QTY_COL, AMOUNT_COL, "SKU수", "브랜드수"])
    base = _with_month_parts(df)
    return (
        base.groupby(["year", "month", "year_month", "quarter", *groups], dropna=False)
        .agg(
            **{
                QTY_COL: (QTY_COL, "sum"),
                AMOUNT_COL: (AMOUNT_COL, "sum"),
                "SKU수": (PRODUCT_CODE_COL, "nunique"),
                "브랜드수": (BRAND_COL, "nunique"),
            }
        )
        .reset_index()
        .sort_values(["year_month", *groups])
    )


def build_monthly_category1_summary(merged_df: pd.DataFrame) -> pd.DataFrame:
    return _summary(merged_df, [CATEGORY1_COL])


def build_monthly_category2_summary(merged_df: pd.DataFrame) -> pd.DataFrame:
    return _summary(merged_df, [CATEGORY1_COL, CATEGORY2_COL])


def build_monthly_country_category_summary(merged_df: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(merged_df)
    if df.empty or COUNTRY_COL not in df.columns:
        return _summary(pd.DataFrame(columns=df.columns if not df.empty else [DATE_COL]), [COUNTRY_COL, CATEGORY1_COL])
    out = df.copy()
    country = out[COUNTRY_COL].astype(str).str.strip()
    out[COUNTRY_COL] = country.replace({"": UNKNOWN_COUNTRY, "nan": UNKNOWN_COUNTRY, "None": UNKNOWN_COUNTRY})
    return _summary(out, [COUNTRY_COL, CATEGORY1_COL])


def build_monthly_country_category2_summary(merged_df: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(merged_df)
    if df.empty or COUNTRY_COL not in df.columns:
        return _summary(pd.DataFrame(columns=df.columns if not df.empty else [DATE_COL]), [COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL])
    out = df.copy()
    country = out[COUNTRY_COL].astype(str).str.strip()
    out[COUNTRY_COL] = country.replace({"": UNKNOWN_COUNTRY, "nan": UNKNOWN_COUNTRY, "None": UNKNOWN_COUNTRY})
    return _summary(out, [COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL])


def build_country_customer_summary(merged_df: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(merged_df)
    columns = [
        COUNTRY_COL,
        CUSTOMER_COL,
        CUSTOMER_SHORT_COL,
        QTY_COL,
        AMOUNT_COL,
        "비중(%)",
        "SKU수",
        "브랜드수",
        "주요 기능구분",
    ]
    if df.empty or COUNTRY_COL not in df.columns or CUSTOMER_COL not in df.columns:
        return pd.DataFrame(columns=columns)

    out = df.copy()
    out[COUNTRY_COL] = (
        out[COUNTRY_COL]
        .astype(str)
        .str.strip()
        .replace({"": UNKNOWN_COUNTRY, "nan": UNKNOWN_COUNTRY, "None": UNKNOWN_COUNTRY})
    )
    out[CUSTOMER_COL] = (
        out[CUSTOMER_COL]
        .astype(str)
        .str.strip()
        .replace({"": UNKNOWN_CUSTOMER, "nan": UNKNOWN_CUSTOMER, "None": UNKNOWN_CUSTOMER})
    )
    if CUSTOMER_SHORT_COL not in out.columns:
        out[CUSTOMER_SHORT_COL] = ""
    out[CUSTOMER_SHORT_COL] = out[CUSTOMER_SHORT_COL].astype(str).str.strip().replace({"nan": "", "None": ""})

    grouped = (
        out.groupby([COUNTRY_COL, CUSTOMER_COL, CUSTOMER_SHORT_COL], dropna=False)
        .agg(
            **{
                QTY_COL: (QTY_COL, "sum"),
                AMOUNT_COL: (AMOUNT_COL, "sum"),
                "SKU수": (PRODUCT_CODE_COL, "nunique"),
                "브랜드수": (BRAND_COL, "nunique"),
            }
        )
        .reset_index()
    )
    country_qty = grouped.groupby(COUNTRY_COL)[QTY_COL].transform("sum").replace(0, pd.NA)
    grouped["비중(%)"] = (grouped[QTY_COL] / country_qty * 100).fillna(0).round(1)

    category_totals = (
        out.groupby([COUNTRY_COL, CUSTOMER_COL, CUSTOMER_SHORT_COL, CATEGORY1_COL], dropna=False)[QTY_COL]
        .sum()
        .reset_index()
        .sort_values([COUNTRY_COL, CUSTOMER_COL, CUSTOMER_SHORT_COL, QTY_COL], ascending=[True, True, True, False])
    )
    top_category = category_totals.drop_duplicates(subset=[COUNTRY_COL, CUSTOMER_COL, CUSTOMER_SHORT_COL])[
        [COUNTRY_COL, CUSTOMER_COL, CUSTOMER_SHORT_COL, CATEGORY1_COL]
    ].rename(columns={CATEGORY1_COL: "주요 기능구분"})

    return (
        grouped.merge(top_category, on=[COUNTRY_COL, CUSTOMER_COL, CUSTOMER_SHORT_COL], how="left")
        .sort_values([COUNTRY_COL, QTY_COL, AMOUNT_COL], ascending=[True, False, False])
        [columns]
    )


def build_country_category_customer_summary(merged_df: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(merged_df)
    columns = [
        COUNTRY_COL,
        CATEGORY1_COL,
        CATEGORY2_COL,
        CUSTOMER_COL,
        CUSTOMER_SHORT_COL,
        QTY_COL,
        AMOUNT_COL,
        "비중(%)",
        "SKU수",
        "브랜드수",
    ]
    if df.empty or COUNTRY_COL not in df.columns or CUSTOMER_COL not in df.columns:
        return pd.DataFrame(columns=columns)

    out = df.copy()
    out[COUNTRY_COL] = (
        out[COUNTRY_COL]
        .astype(str)
        .str.strip()
        .replace({"": UNKNOWN_COUNTRY, "nan": UNKNOWN_COUNTRY, "None": UNKNOWN_COUNTRY})
    )
    out[CUSTOMER_COL] = (
        out[CUSTOMER_COL]
        .astype(str)
        .str.strip()
        .replace({"": UNKNOWN_CUSTOMER, "nan": UNKNOWN_CUSTOMER, "None": UNKNOWN_CUSTOMER})
    )
    if CUSTOMER_SHORT_COL not in out.columns:
        out[CUSTOMER_SHORT_COL] = ""
    out[CUSTOMER_SHORT_COL] = out[CUSTOMER_SHORT_COL].astype(str).str.strip().replace({"nan": "", "None": ""})

    grouped = (
        out.groupby([COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL, CUSTOMER_COL, CUSTOMER_SHORT_COL], dropna=False)
        .agg(
            **{
                QTY_COL: (QTY_COL, "sum"),
                AMOUNT_COL: (AMOUNT_COL, "sum"),
                "SKU수": (PRODUCT_CODE_COL, "nunique"),
                "브랜드수": (BRAND_COL, "nunique"),
            }
        )
        .reset_index()
    )
    scope_qty = grouped.groupby([COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL])[QTY_COL].transform("sum").replace(0, pd.NA)
    grouped["비중(%)"] = (grouped[QTY_COL] / scope_qty * 100).fillna(0).round(1)
    return grouped.sort_values(
        [COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL, QTY_COL, AMOUNT_COL],
        ascending=[True, True, True, False, False],
    )[columns]


def build_customer_sales_summary(merged_df: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(merged_df)
    columns = [
        CUSTOMER_COL,
        CUSTOMER_SHORT_COL,
        "주요 국가",
        "국가수",
        QTY_COL,
        AMOUNT_COL,
        "비중(%)",
        "SKU수",
        "브랜드수",
        "주요 기능구분",
    ]
    if df.empty or CUSTOMER_COL not in df.columns:
        return pd.DataFrame(columns=columns)

    out = df.copy()
    if COUNTRY_COL not in out.columns:
        out[COUNTRY_COL] = UNKNOWN_COUNTRY
    out[COUNTRY_COL] = (
        out[COUNTRY_COL]
        .astype(str)
        .str.strip()
        .replace({"": UNKNOWN_COUNTRY, "nan": UNKNOWN_COUNTRY, "None": UNKNOWN_COUNTRY})
    )
    out[CUSTOMER_COL] = (
        out[CUSTOMER_COL]
        .astype(str)
        .str.strip()
        .replace({"": UNKNOWN_CUSTOMER, "nan": UNKNOWN_CUSTOMER, "None": UNKNOWN_CUSTOMER})
    )
    if CUSTOMER_SHORT_COL not in out.columns:
        out[CUSTOMER_SHORT_COL] = ""
    out[CUSTOMER_SHORT_COL] = out[CUSTOMER_SHORT_COL].astype(str).str.strip().replace({"nan": "", "None": ""})

    grouped = (
        out.groupby([CUSTOMER_COL, CUSTOMER_SHORT_COL], dropna=False)
        .agg(
            **{
                QTY_COL: (QTY_COL, "sum"),
                AMOUNT_COL: (AMOUNT_COL, "sum"),
                "국가수": (COUNTRY_COL, "nunique"),
                "SKU수": (PRODUCT_CODE_COL, "nunique"),
                "브랜드수": (BRAND_COL, "nunique"),
            }
        )
        .reset_index()
    )
    total_qty = grouped[QTY_COL].sum()
    grouped["비중(%)"] = ((grouped[QTY_COL] / total_qty * 100) if total_qty else 0).round(1)

    country_totals = (
        out.groupby([CUSTOMER_COL, CUSTOMER_SHORT_COL, COUNTRY_COL], dropna=False)[QTY_COL]
        .sum()
        .reset_index()
        .sort_values([CUSTOMER_COL, CUSTOMER_SHORT_COL, QTY_COL], ascending=[True, True, False])
    )
    top_country = country_totals.drop_duplicates(subset=[CUSTOMER_COL, CUSTOMER_SHORT_COL])[
        [CUSTOMER_COL, CUSTOMER_SHORT_COL, COUNTRY_COL]
    ].rename(columns={COUNTRY_COL: "주요 국가"})

    category_totals = (
        out.groupby([CUSTOMER_COL, CUSTOMER_SHORT_COL, CATEGORY1_COL], dropna=False)[QTY_COL]
        .sum()
        .reset_index()
        .sort_values([CUSTOMER_COL, CUSTOMER_SHORT_COL, QTY_COL], ascending=[True, True, False])
    )
    top_category = category_totals.drop_duplicates(subset=[CUSTOMER_COL, CUSTOMER_SHORT_COL])[
        [CUSTOMER_COL, CUSTOMER_SHORT_COL, CATEGORY1_COL]
    ].rename(columns={CATEGORY1_COL: "주요 기능구분"})

    return (
        grouped.merge(top_country, on=[CUSTOMER_COL, CUSTOMER_SHORT_COL], how="left")
        .merge(top_category, on=[CUSTOMER_COL, CUSTOMER_SHORT_COL], how="left")
        .sort_values([QTY_COL, AMOUNT_COL], ascending=[False, False])
        [columns]
    )


def build_category1_share(c1_monthly: pd.DataFrame, merged_df: pd.DataFrame) -> pd.DataFrame:
    return _add_share_columns(c1_monthly)


def build_category2_share(c2_monthly: pd.DataFrame, merged_df: pd.DataFrame) -> pd.DataFrame:
    return _add_share_columns(c2_monthly)


def _add_share_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(df).copy()
    if out.empty:
        out["qty_share_pct"] = []
        out["amount_share_pct"] = []
        return out
    month_qty = out.groupby("year_month")[QTY_COL].transform("sum").replace(0, pd.NA)
    month_amount = out.groupby("year_month")[AMOUNT_COL].transform("sum").replace(0, pd.NA)
    out["qty_share_pct"] = (out[QTY_COL] / month_qty * 100).fillna(0)
    out["amount_share_pct"] = (out[AMOUNT_COL] / month_amount * 100).fillna(0)
    return out


def build_ytd_comparison(
    merged_df: pd.DataFrame,
    complete_month_keys: set[str] | None = None,
) -> pd.DataFrame:
    if merged_df.empty:
        return pd.DataFrame(columns=[CATEGORY1_COL, CATEGORY2_COL])
    base = _with_month_parts(merged_df)
    observed_month_keys = set(base["year_month"].dropna().astype(str))
    if complete_month_keys is None:
        eligible_month_keys: set[str] = set()
        for month_key, month_rows in base.groupby("year_month", dropna=False):
            dates = pd.to_datetime(month_rows[DATE_COL], errors="coerce").dropna().dt.normalize()
            if dates.empty:
                continue
            period = dates.iloc[0].to_period("M")
            month_start = period.start_time.normalize()
            month_end = period.end_time.normalize()
            business_days = len(pd.bdate_range(month_start, month_end))
            active_business_days = sum(date.weekday() < 5 for date in pd.DatetimeIndex(dates.unique()))
            if (
                dates.min() <= month_start + pd.Timedelta(days=7)
                and dates.max() >= month_end - pd.Timedelta(days=7)
                and (active_business_days / business_days if business_days else 0) >= 0.35
            ):
                eligible_month_keys.add(str(month_key))
    else:
        eligible_month_keys = set(complete_month_keys)
    eligible_month_keys = {
        key for key in eligible_month_keys if isinstance(key, str) and len(key) == 7 and key[4] == "-"
    }
    if not eligible_month_keys:
        return pd.DataFrame(columns=[CATEGORY1_COL, CATEGORY2_COL])

    latest_key = max(eligible_month_keys)
    latest_month = int(latest_key[5:7])
    candidate_years = sorted({int(key[:4]) for key in eligible_month_keys})
    years = [
        year
        for year in candidate_years
        if all(f"{year:04d}-{month:02d}" in eligible_month_keys for month in range(1, latest_month + 1))
    ]
    if not years:
        return pd.DataFrame(columns=[CATEGORY1_COL, CATEGORY2_COL])

    comparable_keys = {
        f"{year:04d}-{month:02d}" for year in years for month in range(1, latest_month + 1)
    }
    base = base[base["year_month"].astype(str).isin(comparable_keys)].copy()
    grouped = (
        base.groupby([CATEGORY1_COL, CATEGORY2_COL, "year"], dropna=False)
        .agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum")})
        .reset_index()
    )
    rows = []
    for keys, group in grouped.groupby([CATEGORY1_COL, CATEGORY2_COL], dropna=False):
        row = {CATEGORY1_COL: keys[0], CATEGORY2_COL: keys[1]}
        by_year = {int(item["year"]): item for _, item in group.iterrows()}
        for year in years:
            item = by_year.get(year)
            row[f"YTD_수량_{year}"] = float(item[QTY_COL]) if item is not None else 0
            row[f"YTD_금액_{year}"] = float(item[AMOUNT_COL]) if item is not None else 0
        for prev, cur in zip(years, years[1:]):
            row[f"수량YTD성장률_{prev}_to_{cur}(%)"] = _growth(row[f"YTD_수량_{prev}"], row[f"YTD_수량_{cur}"])
            row[f"금액YTD성장률_{prev}_to_{cur}(%)"] = _growth(row[f"YTD_금액_{prev}"], row[f"YTD_금액_{cur}"])
        rows.append(row)
    return pd.DataFrame(rows)


def _growth(prev: float, cur: float) -> float | None:
    return None if prev == 0 else (cur - prev) / prev * 100


def build_top_sku_by_category(merged_df: pd.DataFrame, group_columns: list[str] | None = None) -> pd.DataFrame:
    group_columns = list(group_columns or [])
    result_columns = [
        *group_columns,
        CATEGORY1_COL,
        CATEGORY2_COL,
        PRODUCT_CODE_COL,
        BRAND_COL,
        PRODUCT_NAME_COL,
        QTY_COL,
        AMOUNT_COL,
        "판매월수",
        "최근3M_수량",
        "최근6M_수량",
        "월평균수량",
    ]
    if merged_df.empty:
        return pd.DataFrame(columns=result_columns)
    missing_columns = [
        column
        for column in [DATE_COL, CATEGORY1_COL, CATEGORY2_COL, PRODUCT_CODE_COL, QTY_COL, AMOUNT_COL, *group_columns]
        if column not in merged_df.columns
    ]
    if missing_columns:
        return pd.DataFrame(columns=result_columns)
    base = _with_month_parts(merged_df)
    if base.empty:
        return pd.DataFrame(columns=result_columns)
    base = base[base[DATE_COL].notna()].copy()
    if base.empty:
        return pd.DataFrame(columns=result_columns)

    group_by_columns = [*group_columns, CATEGORY1_COL, CATEGORY2_COL, PRODUCT_CODE_COL]
    base["_period_ordinal"] = (base[DATE_COL].dt.year * 12 + base[DATE_COL].dt.month).astype("int64")
    latest_ordinal = (
        base.groupby(group_columns, dropna=False)["_period_ordinal"].transform("max")
        if group_columns
        else base["_period_ordinal"].max()
    )
    base["_recent3_qty"] = np.where(base["_period_ordinal"] >= latest_ordinal - 2, base[QTY_COL], 0)
    base["_recent6_qty"] = np.where(base["_period_ordinal"] >= latest_ordinal - 5, base[QTY_COL], 0)

    for column in (BRAND_COL, PRODUCT_NAME_COL):
        if column not in base.columns:
            base[column] = ""
        clean_column = f"_{column}_first_text"
        base[clean_column] = base[column].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})

    summary = (
        base.groupby(group_by_columns, dropna=False)
        .agg(
            **{
                BRAND_COL: (f"_{BRAND_COL}_first_text", "first"),
                PRODUCT_NAME_COL: (f"_{PRODUCT_NAME_COL}_first_text", "first"),
                QTY_COL: (QTY_COL, "sum"),
                AMOUNT_COL: (AMOUNT_COL, "sum"),
                "판매월수": ("_period_ordinal", "nunique"),
                "최근3M_수량": ("_recent3_qty", "sum"),
                "최근6M_수량": ("_recent6_qty", "sum"),
            }
        )
        .reset_index()
    )

    monthly_qty = (
        base.groupby([*group_by_columns, "_period_ordinal"], dropna=False)[QTY_COL]
        .sum()
        .reset_index()
    )
    monthly_average = (
        monthly_qty.groupby(group_by_columns, dropna=False)[QTY_COL]
        .mean()
        .rename("월평균수량")
        .reset_index()
    )
    result = summary.merge(monthly_average, on=group_by_columns, how="left")
    for column in (BRAND_COL, PRODUCT_NAME_COL):
        result[column] = result[column].fillna("").astype(str)
    for column in (QTY_COL, AMOUNT_COL, "최근3M_수량", "최근6M_수량", "월평균수량"):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(float)
    result["판매월수"] = pd.to_numeric(result["판매월수"], errors="coerce").fillna(0).astype(int)
    sort_columns = [*group_columns, CATEGORY1_COL, CATEGORY2_COL, QTY_COL]
    ascending = [True] * (len(sort_columns) - 1) + [False]
    return result[result_columns].sort_values(sort_columns, ascending=ascending).reset_index(drop=True)


def _first_text(values: pd.Series) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def build_mapping_quality_report(sales_df: pd.DataFrame, merged_df: pd.DataFrame, prod_df_empty: bool = False) -> pd.DataFrame:
    merged = pd.DataFrame(merged_df)
    if merged.empty:
        return pd.DataFrame([{"구분": "데이터", "건수": 0, "비고": "분석 가능한 판매 데이터 없음"}])
    unmapped = merged[CATEGORY1_COL].astype(str).eq(UNMAPPED) | merged[CATEGORY2_COL].astype(str).eq(UNMAPPED)
    official_invalid = ~merged[CATEGORY1_COL].map(is_official_category1)
    category2_official_invalid = ~pd.Series(
        [
            is_official_category2(category1, category2)
            for category1, category2 in zip(merged[CATEGORY1_COL], merged[CATEGORY2_COL], strict=False)
        ],
        index=merged.index,
    )
    rows = [
        {"구분": "판매행", "건수": int(len(merged)), "비고": ""},
        {"구분": "미분류행", "건수": int(unmapped.sum()), "비고": "prod_list 미업로드" if prod_df_empty else ""},
        {
            "구분": "CMS 공식목록 외 기능구분1 행",
            "건수": int(official_invalid.sum()),
            "비고": "상품목록 class1_nm이 CMS 공식 기능구분1 목록에 없는 경우",
        },
        {
            "구분": "CMS 공식목록 외 기능구분2 행",
            "건수": int(category2_official_invalid.sum()),
            "비고": "현재 등록된 기능구분2 기준: 스킨케어, 페이스메이크업, 컬러메이크업, 썬케어, 바디, 네일, 헤어, 마스크, 비비/씨씨크림, 클렌징, 악세사리, 향수/아로마, 화장소품, 치약, 생활용품, 칫솔, 가글, 디바이스, 소품, 의류(상의), 렌즈, 기타",
        },
        {"구분": "SKU수", "건수": int(merged[PRODUCT_CODE_COL].nunique()), "비고": ""},
        {"구분": "CMS 공식 기능구분1 수", "건수": len(OFFICIAL_CATEGORY1_VALUES), "비고": ""},
        {"구분": "CMS 공식 기능구분2 수(스킨케어)", "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["스킨케어"]), "비고": ""},
        {
            "구분": "CMS 공식 기능구분2 수(페이스메이크업)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["페이스메이크업"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(컬러메이크업)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["컬러메이크업"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(썬케어)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["썬케어"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(바디)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["바디"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(네일)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["네일"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(헤어)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["헤어"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(마스크)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["마스크"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(비비/씨씨크림)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["비비/씨씨크림"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(클렌징)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["클렌징"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(악세사리)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["악세사리"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(향수/아로마)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["향수/아로마"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(화장소품)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["화장소품"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(치약)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["치약"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(생활용품)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["생활용품"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(칫솔)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["칫솔"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(가글)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["가글"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(디바이스)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["디바이스"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(소품)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["소품"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(의류(상의))",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["의류(상의)"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(렌즈)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["렌즈"]),
            "비고": "",
        },
        {
            "구분": "CMS 공식 기능구분2 수(기타)",
            "건수": len(OFFICIAL_CATEGORY2_BY_CATEGORY1["기타"]),
            "비고": "",
        },
    ]
    return pd.DataFrame(rows)


def _unique_sheet_name(wb, base_name: str) -> str:
    if base_name not in wb.sheetnames:
        return base_name
    idx = 2
    while f"{base_name}_{idx}" in wb.sheetnames:
        idx += 1
    return f"{base_name}_{idx}"


def _write_df_sheet(wb, name: str, df: pd.DataFrame) -> None:
    ws = wb.create_sheet(_unique_sheet_name(wb, name))
    append_df(ws, pd.DataFrame(df))
    autosize_columns(ws)
    ws.freeze_panes = "A2"


def append_season_sheets(wb, sales_history_df: pd.DataFrame, prod_df: pd.DataFrame, settings: dict) -> None:
    merged = merge_sales_with_product_master(sales_history_df, prod_df)
    merged = exclude_season_category1_values(merged)
    prod_df_empty = pd.DataFrame(prod_df).empty
    c1 = build_monthly_category1_summary(merged)
    c2 = build_monthly_category2_summary(merged)

    guide_lines = [
        "본 시즌/성분 트렌드 분석은 현재 확보 가능한 판매내역상세 데이터를 기준으로 한 1차 파일명 분석입니다.",
        "최종 발주 수량은 기존 발주 계산식 결과를 기준으로 하며, 시즌/성분 트렌드는 보조 판단 지표로 사용합니다.",
    ]
    if prod_df_empty:
        guide_lines.append("prod_list 미업로드로 기능구분 분석 정확도는 제한되며, 기능구분1/2 전체가 미분류로 처리됩니다.")
    _write_df_sheet(wb, "시즌_분석안내", pd.DataFrame({"안내": guide_lines}))
    _write_df_sheet(wb, "시즌_기능구분1_월별", c1)
    _write_df_sheet(wb, "시즌_기능구분2_월별", c2)
    _write_df_sheet(wb, "시즌_기능구분1_비중", build_category1_share(c1, merged))
    _write_df_sheet(wb, "시즌_기능구분2_비중", build_category2_share(c2, merged))
    _write_df_sheet(wb, "시즌_YTD비교", build_ytd_comparison(merged))
    _write_df_sheet(wb, "시즌_Top_SKU", build_top_sku_by_category(merged))
    _write_df_sheet(wb, "시즌_매핑현황", build_mapping_quality_report(sales_history_df, merged, prod_df_empty))
