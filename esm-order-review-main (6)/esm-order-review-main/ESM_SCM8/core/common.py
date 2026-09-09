from __future__ import annotations
import calendar
import ast
import html as html_lib
import re
import os
import hashlib
import warnings
from numbers import Number
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from io import BytesIO, StringIO
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from plotly.subplots import make_subplots
from core.exchange_rate import DEFAULT_EUR_KRW_RATE
from core.lead_times import pl_default_lead_times
from core.versions import ORDER_REVIEW_EXPORT_VERSION, ORDER_REVIEW_LOGIC_VERSION

PROJECT_ROOT = Path(__file__).resolve().parent.parent

KST = ZoneInfo("Asia/Seoul")
def korea_today() -> date:
    return datetime.now(KST).date()
def korea_now() -> datetime:
    return datetime.now(KST)
def format_months(value: object) -> str:
    try:
        months = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    if months.is_integer():
        return f"{int(months)}개월"
    return f"{months:g}개월"
COLORS = {
    "blue": "#2f80ed",
    "green": "#2fa84f",
    "orange": "#ff8b22",
    "purple": "#8a5cf6",
    "red": "#e5484d",
    "yellow": "#f7c948",
    "muted": "#667085",
    "text": "#111827",
    "border": "#d9dee8",
    "bg": "#f8fafc",
}
MODE_COLORS = {"해운": "#2f80ed", "철송": "#2fa84f", "항공": "#ff8b22", "트럭": "#8a5cf6"}
STANDARD_TRANSPORT_MODES = {"해운", "항공", "철송", "트럭"}
TRANSPORT_MODES = ["항공", "트럭", "철송", "해운"]
TRANSPORT_REVIEW_REQUIRED = "운송수단 확인필요"
ORDER_REVIEW_EXCLUDED_BRANDS = {"기타제조사"}
_DEFAULT_EUR_KRW_RATE = DEFAULT_EUR_KRW_RATE
_ORDER_REVIEW_EXPORT_VERSION = ORDER_REVIEW_EXPORT_VERSION
_ORDER_REVIEW_LOGIC_VERSION = ORDER_REVIEW_LOGIC_VERSION
_KRW_LIKE_UNIT_PRICE_THRESHOLD = 300.0
EU_LOCAL_STOCK_UNIT_PRICE_CURRENCY = "EUR"
LOCAL_STOCK_UNIT_PRICE_CURRENCY_BY_ENTITY = {
    "PL": "EUR",
    "USA": "USD",
}
HQ_EU_STOCK_UNIT_PRICE_CURRENCY = "KRW"
EU_LOCAL_SALES_AMOUNT_CURRENCY = "EUR"
HQ_TO_EU_SALES_AMOUNT_CURRENCY = "EUR"
SHIPPING_CONTAINER_AMOUNT_CURRENCY = "EUR"
_DECISION_CACHE_PATH = os.path.join(str(PROJECT_ROOT), "data", "exception_decisions.csv")
DEFAULT_LEAD_TIME_DAYS = pl_default_lead_times()
REPORT_TABLE_HEADER_FILL = "305496"
RISK_BG = {
    "입고 전 품절": "#fff0f0",
    "긴급": "#fff0f0",
    "임박위험": "#fff5e8",
    "주의": "#fff9db",
    "안정": "#effaf2",
    "영향적음": "#ffffff",
    "낮음": "#effaf2",
    "중간": "#fff9db",
    "높음": "#fff0f0",
}
ALERT_URGENT_LABEL = "OOS"
ALERT_LOCAL_SHORT_LABEL = "발주필요"
ALERT_SHIPPING_SHORT_LABEL = "발주필요"
PA_CA_SALES_CANDIDATES = [
    "판매수량",
    "최근3개월 판매수량",
    "최근 3개월 판매수량",
    "판매수량(PA+CA)",
    "PA+CA 판매수량",
    "최근3개월 PA+CA",
    "최근 3개월 PA+CA",
    "최근3개월 판매수량(PA+CA)",
    "최근 3개월 판매수량(PA+CA)",
    "판매 수량 (3개월내 PA+CA)",
]
DATA_SPECS = {
    "eu_stock": {
        "name": "EU 현지 재고",
        "meaning": "SKO Multi / 유럽 현지 판매 가능 재고 / 평균단가 통화 자동 판별",
        "tabs": "발주 검토, 고갈 시뮬레이션, 판매속도 이상 감지",
        "required_columns": ["브랜드", "상품코드", "바코드", "상품명", "재고수량", "Hold수량", "EU 입고단가"],
    },
    "hq_eu_stock": {
        "name": "본사 EU창고 재고",
        "meaning": "실리콘투 재고-EU창고 / 유럽 이동 가능 보완 재고 / 평균단가 KRW",
        "tabs": "발주 검토",
        "required_columns": ["브랜드", "상품코드", "바코드", "상품명", "재고수량", "Hold수량"],
    },
    "sales_detail": {
        "name": "판매내역상세",
        "meaning": "판매속도 계산 / 금액 EUR",
        "tabs": "전체 분석",
        "required_columns": ["브랜드", "SKU", "상품명", "판매 기준기간 판매량", "최근 판매량", "매출"],
    },
    "hq_to_eu_sales_detail": {
        "name": "본사→유럽법인향 판매내역상세",
        "meaning": "공급 파이프라인 출고금액 계산 / 금액 EUR",
        "tabs": "대시보드, 공급 파이프라인",
        "required_columns": ["브랜드", "SKU", "상품명", "출고일", "환산금액"],
    },
    "open_po": {
        "name": "미입고현황",
        "meaning": "브랜드사 발주 후 아직 본사 창고 미입고된 PO 잔량",
        "tabs": "발주 검토",
        "required_columns": ["SKU", "미입고수량"],
    },
    "shipping": {
        "name": "해상/운송중",
        "meaning": "출고일 + 리드타임 기반 ETA 계산 / 금액 EUR",
        "tabs": "ETA 캘린더, ETA 타임라인, 발주 검토",
        "required_columns": ["운송수단", "SKU", "브랜드", "상품명", "수량", "출고일", "금액"],
    },
    "past_sales": {
        "name": "과거 판매내역",
        "meaning": "시즌 발주 캘린더",
        "tabs": "시즌 발주 캘린더",
        "required_columns": ["브랜드", "SKU", "상품명", "성수기 월"],
    },
    "sales_history": {
        "name": "장기 판매이력",
        "meaning": "시즌/성분 분석용 장기 판매내역",
        "tabs": "시즌/성분 보조 분석",
        "required_columns": ["출고일", "상품코드", "상품명", "브랜드", "판매수량", "판매금액"],
    },
    "prod_list": {
        "name": "상품목록",
        "meaning": "기능구분1/2 매핑용 상품 마스터",
        "tabs": "시즌/성분 보조 분석",
        "required_columns": ["상품코드", "상품명_마스터", "브랜드_마스터", "기능구분1", "기능구분2"],
    },
}
UPLOAD_COLUMN_GROUPS = {
    "hq_to_eu_sales_detail": [
        ["환산금액", "출고금액", "금액", "매출"],
        ["출고일", "출고 일자", "일자", "date"],
        ["SKU", "상품코드", "품목코드", "itemcode"],
    ],
    "sales_history": [
        ["출고일", "출고 일자", "일자", "date", "Date"],
        ["상품코드", "SKU", "품목코드", "itemcode"],
        ["상품명", "품목명", "itemname", "productname"],
        ["브랜드", "브랜드명", "brand", "brandname"],
        ["수량", "판매수량", "판매 수량", "qty", "quantity"],
        ["환산금액", "판매금액", "금액", "매출", "amount"],
    ],
    "prod_list": [
        ["prod_cd", "상품코드", "SKU", "품목코드", "itemcode"],
        ["prod_nm", "상품명_마스터", "상품명", "품목명"],
        ["brand_nm", "브랜드_마스터", "브랜드", "브랜드명"],
        ["class1_nm", "기능구분1"],
        ["class2_nm", "기능구분2"],
        ["bar_code", "바코드"],
        ["prod_gbn", "상품구분"],
        ["use_yn", "사용여부"],
    ],
}
NON_PRODUCT_SKU_TOKENS = {
    "total",
    "subtotal",
    "grandtotal",
    "sum",
    "deliverycharge",
    "deliveryfee",
    "shippingcharge",
    "shippingfee",
    "freight",
    "freightcharge",
    "합계",
    "총계",
    "소계",
    "배송비",
    "운송비",
    "운임",
    "운임비",
}
SALES_BIZ_ALWAYS_INCLUDE = {"EU-OVERSEAS", "KR-OVERSEAS", "자사간거래"}
SALES_BIZ_OPTIONAL_INCLUDE = {"EU-PL", "ETC"}
SALES_BIZ_ALWAYS_EXCLUDE = {
    "EU-STAFFSALES",
    "STAFFSALES",
    "STAFF SALES",
    "추후상계",
    "반품",
    "FREE SAMPLE",
    "FREESAMPLE",
    "TP ADJUST",
    "TP-ADJUSTMENT",
    "TP ADJUSTMENT",
    "ADVANCE_TO_RELATED_PARTY",
    "ADVANCE TO RELATED PARTY",
    "CUM",
    "기타제조사",
}
SALES_QTY_DIFF_ALERT_RATE = 30.0
MASTER_UNREGISTERED_SHEET_NAME = "상품코드 확인필요"
MASTER_UNREGISTERED_REASON = "현지 재고 목록 미존재 / 원본 데이터에 존재"
_RAW_TRANSPORT_CANDIDATES = ["운송수단", "배송수단", "mode", "Invoice 비고", "INVOICE 비고", "Invoice비고", "운송 비고", "비고"]
SAMPLE_SKU_PATTERN = r"샘플|sample|tester|foc|무상|goodie|goody|구디"
DISCONTINUED_SKU_PATTERN = r"단종|discontinue|discontinued|판매중지|사용안함"
def _load_tracked_debug_skus() -> list[str]:
    raw = os.environ.get("SCM_DEBUG_TRACKED_SKUS", "")
    return [s.strip() for s in raw.split(",") if s.strip()]

TRACKED_SHIPPING_DEBUG_SKUS: list[str] = _load_tracked_debug_skus()
_EU_STOCK_AMOUNT_CANDIDATES = [
    "재고금액",
    "재고 금액",
    "재고금액(KRW)",
    "재고금액 KRW",
    "재고평가금액",
    "재고 평가 금액",
    "총재고금액",
    "총 재고 금액",
    "원화금액",
    "원화 금액",
    "환산금액",
    "환산 금액",
    "금액(KRW)",
    "금액 KRW",
    "Stock Amount",
    "Inventory Amount",
    "Amount KRW",
    "Amount(KRW)",
    "금액",
]
_HQ_STOCK_QTY_CANDIDATES = [
    "본사 EU창고 가용수량",
    "본사EU창고가용수량",
    "가용수량",
    "가용 재고",
    "가용재고",
    "재고수량",
    "현재고수량",
    "현재고",
    "보유수량",
    "Stock Qty",
    "Stock Quantity",
    "Available Qty",
    "Available Stock",
]
_HQ_STOCK_HOLD_CANDIDATES = ["Hold수량", "Hold 수량", "홀드수량", "보류수량", "예약수량", "Hold Qty"]
_HQ_STOCK_PRICE_CANDIDATES = [
    "EU 입고단가",
    "EU입고단가",
    "입고단가(EUR)",
    "입고단가 EUR",
    "EUR단가",
    "EUR 단가",
    "단가(EUR)",
    "단가 EUR",
    "입고단가",
    "Unit Price EUR",
    "Unit Price",
    "단가",
]
_HQ_STOCK_EXPLICIT_EUR_VALUE_CANDIDATES = [
    "재고(EUR)",
    "재고 EUR",
    "재고금액(EUR)",
    "재고금액 EUR",
    "Inventory EUR",
    "Stock EUR",
]
_HQ_STOCK_EUR_VALUE_CANDIDATES = ["재고"]
_SEA_CONTAINER_EUR_CANDIDATES = [
    "금액(EUR)",
    "금액 EUR",
    "EUR금액",
    "EUR 금액",
    "Amount(EUR)",
    "Amount EUR",
    "EUR Amount",
    "EUR AMOUNT",
    "금액",
    "Amount",
    "AMOUNT",
]
ORDER_NEEDED_ACTIONS = {"발주 필요"}
# 발주 검토에서 빠진 행은 안전재고 목표를 못 채워도 발주 수량을 만들지 않는다.
# 재고 적정성 신호(재고 ETA 상태·안전재고 목표수량)는 그대로 남긴다.
ORDER_EXCLUDED_REVIEW_STATUSES = {"발주제외", "확인필요"}
ORDER_REVIEW_ELIGIBILITY_HELPER = "_발주검토대상"
PRE_ARRIVAL_HQ_STOCK_CANDIDATES = [
    "본사 EU창고 가용수량",
    "본사 EU창고",
    "본사 EU창고 재고",
    "본사 EU창고 가용재고",
    "본사 EU 재고",
]
ORDER_REVIEW_STATUS_SORT = {
    "본사이동": 1,
    "운송대기": 2,
    "확인필요": 3,
    "발주제외": 4,
    "정상": 5,
}
CHECK_REQUIRED_COLUMNS = [
    "확인 구분",
    "상품코드",
    "상품명",
    "브랜드",
    "발견 원본",
    "판매수량",
    "운송중 수량",
    "미입고 수량",
    "확인대상 수량",
    "출고일",
    "예상 입고일",
    "운송수단",
    "원본값",
    "확인필요 사유",
    "권장 확인 액션",
]
CHECK_REQUIRED_OUTPUT_COLUMNS = CHECK_REQUIRED_COLUMNS + ["담당자판단", "판단일시", "담당자"]
CHECK_REQUIRED_DISPLAY_COLUMNS = [
    "상품코드",
    "상품명",
    "브랜드",
    "발견 원본",
    "판매수량",
    "운송중 수량",
    "미입고 수량",
    "출고일",
    "예상 입고일",
    "운송수단",
    "원본 비고",
    "확인 내용",
    "권장 확인 액션",
    "담당자판단",
    "판단일시",
    "담당자",
]
CHECK_REQUIRED_INTERNAL_COLUMNS = ["instance_key", "pattern_key"]
ARRIVAL_REFERENCE_COLUMNS = ["입고 예정", "해운", "항공", "철송", "트럭", "합계", "금액(EUR)", "금액(KRW)", "금액(억원)"]
ARRIVAL_REFERENCE_MODES = [("해운", "해운"), ("항공", "항공"), ("철송", "철송"), ("트럭", "트럭")]
ARRIVAL_REFERENCE_DETAIL_COLUMNS = [
    "도착일",
    "운송수단",
    "브랜드",
    "SKU",
    "상품명",
    "수량",
    "도착예정금액(KRW)",
    "출고일",
    "운송 L/T",
    "도착예정일",
    "D-Day",
]
UNIFIED_ESM_ORDER_REVIEW_COLUMNS = [
    "코드",
    "No",
    "SKU",
    "브랜드",
    "3개월 판매량",
    "월평균 판매량",
    "안전재고",
    "1. 현지 재고",
    "2. 운송 재고",
    "3. 현지+운송",
    "1. 현지 재고(M)",
    "2. 운송중(M)",
    "3. 합산(M)",
    "알림",
    "미입고 현황",
    "현지 창고 재고",
    "발주필요수량",
]
ORDER_SHEET_COLUMNS = [
    "No",
    "SKU",
    "상품명",
    "브랜드",
    "현지재고",
    "월평균판매량",
    "운송재고",
    "① 현지\n(M)",
    "② 운송중\n(M)",
    "③ 합산\n(M)",
    "안전재고 기준(M)",
    "확보재고 수량",
    "안전재고 목표수량",
    "⚠ 알람",
    "미입고\n현황",
    "현지창고 재고",
    "발주총\n필요수량",
    "총발주금액",
    "고갈\n예정일",
    "운송수단\n추천",
    "항공\n필요량",
    "철송\n필요량",
    "해운\n필요량",
    "★담당자\n발주",
    "발주\n신호등",
    "★발주 메모",
]

__all__ = [name for name in globals() if not name.startswith("__")]
