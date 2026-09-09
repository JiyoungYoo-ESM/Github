"""Pydantic request/response models shared across the API routers."""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    status: int
    request_id: str
    details: Any | None = None


class ApiErrorResponse(BaseModel):
    """Stable error envelope; ``detail`` remains for older clients."""

    detail: str
    error: ApiErrorDetail


class AuthActionResponse(BaseModel):
    ok: bool


class AuthStatusResponse(BaseModel):
    authenticated: bool
    username: str
    display_name: str
    role: str
    account_type: str
    allowed_entities: list[str]
    entities: list[dict[str, Any]]
    is_admin: bool = False
    permissions: dict[str, bool]


class StorageDirectoryStatus(BaseModel):
    path: str
    exists: bool
    writable: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    timestamp: str
    service: str
    storage: dict[str, StorageDirectoryStatus]
    retention: dict[str, int]
    limits: dict[str, int]
    analysis: dict[str, Any]
    reports: dict[str, int]
    redis: dict[str, str]
    object_storage: dict[str, str]
    monitoring: dict[str, str]
    requests: dict[str, Any]
    disk: dict[str, int]
    system: dict[str, Any]


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    timestamp: str
    service: str


class ReadinessResponse(LivenessResponse):
    status: Literal["ok", "degraded"]
    checks: dict[str, str]


class ExchangeRateResponse(BaseModel):
    eur_krw_rate: float
    currency_code: Literal["EUR", "USD"] = "EUR"
    currency_krw_rate: float
    rate_source: Literal["api", "default"]
    rate_date: str
    fallback_rate: float | None = None
    fallback_rate_as_of: str | None = None
    fallback_rate_source: str | None = None
    fallback_rate_age_days: int | None = None
    rate_warning: str | None = None


class CategoryCorrectionOptionsResponse(BaseModel):
    category1: list[str]
    category2ByCategory1: dict[str, list[str]]


class CategoryCorrectionSaveResponse(BaseModel):
    status: str
    saved_count: int
    total_count: int


UploadRole: TypeAlias = Literal[
    "eu_stock",
    "hq_eu_stock",
    "sales_detail",
    "hq_to_eu_sales_detail",
    "shipping",
    "inbound",
    "sales_history",
    "prod_list",
    "category_correction",
]


class ClassificationCandidateResponse(BaseModel):
    role: UploadRole
    key: str
    score: int
    rows: int
    columns: int
    detected_columns: list[str]
    matched_required_columns: list[str]
    missing_required_columns: list[str]
    assigned: bool


class ClassificationItemResponse(BaseModel):
    index: int
    original_name: str
    suggested_role: UploadRole | Literal[""]
    suggested_key: str
    score: int | None
    confidence: Literal["high", "medium", "low"]
    rows: int
    columns: int
    detected_columns: list[str]
    matched_required_columns: list[str]
    missing_required_columns: list[str]
    evidence: list[str]
    candidates: list[ClassificationCandidateResponse]
    error: str | None


class ClassificationResponse(BaseModel):
    status: str
    files: list[ClassificationItemResponse]
    required_roles: list[UploadRole]


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    status: str
    summary: dict[str, Any]
    tables: dict[str, Any]
    download_url: str
    settings: dict[str, Any]
    file_mapping: dict[str, Any]
    uploaded_files: list[dict[str, Any]]
    season_analysis: Any | None = None
    ingredient_analysis: Any | None = None


class AnalysisJobStartResponse(BaseModel):
    job_id: str
    status: str


class AnalysisJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    status: str
    created_at: str
    updated_at: str


class CmsAnalyzeRequest(BaseModel):
    as_of: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="분석 기준일(YYYY-MM-DD). 재고의 최근 3개월 판매수량 기준일.")
    date_from: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="판매 내역 조회 시작일. 미지정 시 CMS 기본값.")
    eur_krw_rate: float | None = Field(None, description="고정 EUR/KRW 환율(선택).")
    safety_months: float | None = None
    sku_shortage_threshold_pct: float | None = None
    sku_overstock_threshold_pct: float | None = None
    lead_time_air: int | None = None
    lead_time_sea: int | None = None
    lead_time_rail: int | None = None
    lead_time_truck: int | None = None
    lead_time_overrides: dict[str, int] | None = None


class AiChatRequest(BaseModel):
    job_id: str = Field(..., min_length=1, description="Analysis job id.")
    token: str = Field(..., min_length=1, description="Temporary download/access token.")
    question: str = Field(..., min_length=1, description="Question for the SCM AI assistant.")


class AiChatResponse(BaseModel):
    job_id: str
    answer: str
    model: str
    context_summary: dict[str, int]


class CategoryCorrectionItem(BaseModel):
    productCode: str = Field(..., min_length=1)
    category1: str = Field(..., min_length=1)
    category2: str = Field(..., min_length=1)
    productName: str | None = None
    brand: str | None = None


class CategoryCorrectionRequest(BaseModel):
    items: list[CategoryCorrectionItem]
