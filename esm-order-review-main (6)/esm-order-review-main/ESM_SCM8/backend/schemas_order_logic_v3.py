"""Request models for the V3 textbook calculation-preview workflow."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict


class OrderLogicV3JobRequest(BaseModel):
    """Start one non-operational V3 textbook calculation run."""

    model_config = ConfigDict(extra="forbid")

    as_of: date
    preview: Literal[True] = True
    force_refresh: bool = False


class OrderLogicV3JobStartResponse(BaseModel):
    job_id: str
    status: Literal["queued"]


class OrderLogicV3SeasonFactorCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date
    force_refresh: bool = False


class OrderLogicV3SeasonFactorReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function_class_1_code: str
    function_class_2_code: str
    decision: Literal["CONFIRMED", "NOT_CONFIRMED"]


__all__ = [
    "OrderLogicV3JobRequest",
    "OrderLogicV3JobStartResponse",
    "OrderLogicV3SeasonFactorCandidateRequest",
    "OrderLogicV3SeasonFactorReviewRequest",
]
