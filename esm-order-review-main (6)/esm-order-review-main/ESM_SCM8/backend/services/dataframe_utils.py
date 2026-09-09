"""Shared DataFrame lookup and JSON-safe serialization helpers."""

from __future__ import annotations

from datetime import date, datetime
import math

import numpy as np
import pandas as pd

from backend.services.upload_classification import normalized_column_name


PREVIEW_LIMIT = 300


def jsonable_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, dict):
        return {str(key): jsonable_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable_value(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if pd.isna(value):
        return None
    return value


def dataframe_preview(df: pd.DataFrame, limit: int = PREVIEW_LIMIT) -> list[dict[str, object]]:
    preview = pd.DataFrame(df).head(limit).copy()
    return [
        {str(key): jsonable_value(value) for key, value in row.items()}
        for row in preview.to_dict(orient="records")
    ]


def dataframe_records(df: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {str(key): jsonable_value(value) for key, value in row.items()}
        for row in pd.DataFrame(df).to_dict(orient="records")
    ]


def first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    frame = pd.DataFrame(df)
    normalized_to_column = {normalized_column_name(column): str(column) for column in frame.columns}
    for column in candidates:
        if column in frame.columns:
            return column
        normalized_column = normalized_to_column.get(normalized_column_name(column))
        if normalized_column:
            return normalized_column
    return None


def date_range_label(df: pd.DataFrame, candidates: list[str]) -> str:
    frame = pd.DataFrame(df)
    column = first_existing_column(frame, candidates)
    if column is None or frame.empty:
        return "확인 불가"
    dates = pd.to_datetime(frame[column], errors="coerce").dropna()
    if dates.empty:
        return "확인 불가"
    return f"{dates.min().strftime('%Y-%m-%d')} ~ {dates.max().strftime('%Y-%m-%d')}"


__all__ = [
    "dataframe_preview",
    "dataframe_records",
    "date_range_label",
    "first_existing_column",
    "jsonable_value",
]
