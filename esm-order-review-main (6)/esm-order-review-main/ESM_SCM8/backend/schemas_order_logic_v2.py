"""Request models for the BETA order-logic v2 API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PolicyMode = Literal["CASH", "SHORTAGE"]


class OrderLogicV2Settings(BaseModel):
    """Per-run immutable policy snapshot; defaults match the approved spec."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    grade_cutoff: float = Field(0.80, ge=0, le=1)
    # API 호환을 위해 기존 이름을 유지하지만 의미는 정기 검토주기 R이다.
    cover_weeks: float = Field(4.0, ge=0)
    ss_floor_weeks: float = Field(2.0, ge=0)
    ss_cap_weeks: float = Field(13.0, ge=0)

    lt_air_days: float = Field(16.4, gt=0)
    lt_rail_days: float = Field(36.6, gt=0)
    lt_sea_days: float = Field(72.9, gt=0)
    sigma_l_air_weeks: float = Field(0.68, ge=0)
    sigma_l_rail_weeks: float = Field(1.15, ge=0)
    sigma_l_sea_weeks: float = Field(2.18, ge=0)

    z_cash_major: float = Field(1.28, gt=0)
    z_cash_minor: float = Field(1.08, gt=0)
    z_shortage_major: float = Field(1.68, gt=0)
    z_shortage_minor: float = Field(1.28, gt=0)

    @model_validator(mode="after")
    def validate_safety_stock_bounds(self) -> "OrderLogicV2Settings":
        if self.ss_cap_weeks < self.ss_floor_weeks:
            raise ValueError(
                "ss_cap_weeks must be greater than or equal to ss_floor_weeks"
            )
        return self


class OrderLogicV2JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date
    applied_mode: PolicyMode
    preview: bool = False
    settings: OrderLogicV2Settings = Field(
        default_factory=OrderLogicV2Settings
    )


class OrderLogicV2JobStartResponse(BaseModel):
    job_id: str
    status: Literal["queued"]


class OrderLogicV2DecisionOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    sku_code: str = Field(..., min_length=1, max_length=160)
    confirmed_qty: float = Field(..., ge=0)
    memo: str | None = Field(None, max_length=2000)


class OrderLogicV2ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1, max_length=160)
    export_mode: PolicyMode
    row_ids: list[str] | None = None
    overrides: list[OrderLogicV2DecisionOverride] = Field(default_factory=list)


__all__ = [
    "OrderLogicV2DecisionOverride",
    "OrderLogicV2ExportRequest",
    "OrderLogicV2JobRequest",
    "OrderLogicV2JobStartResponse",
    "OrderLogicV2Settings",
    "PolicyMode",
]
