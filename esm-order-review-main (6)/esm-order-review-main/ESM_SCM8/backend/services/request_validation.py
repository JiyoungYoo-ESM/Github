"""Request-level validation and normalization: filenames, upload roles,
analysis settings and CMS date windows. Raises ``HTTPException`` on bad input."""

from __future__ import annotations

import json
import math
import re
from calendar import monthrange
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from core.lead_times import normalize_lead_time_overrides

from backend.services.upload_classification import (
    ALLOWED_UPLOAD_ROLES,
    normalize_upload_role,
    upload_key_for_role,
)
from backend.config import ALLOWED_EXCEL_EXTENSIONS


def format_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    if size >= 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size}B"


def sanitize_filename(filename: str | None) -> str:
    if not filename:
        return "uploaded_file"
    raw_name = Path(filename).name.replace("\\", "_").replace("/", "_")
    suffix = Path(raw_name).suffix.lower()
    stem = Path(raw_name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "uploaded_file"
    safe_suffix = suffix if re.fullmatch(r"\.[A-Za-z0-9]+", suffix) else ""
    return f"{safe_stem}{safe_suffix}"


def upload_display_name(filename: str | None) -> str:
    if not filename:
        return "uploaded_file"
    return Path(filename).name.replace("\\", "_").replace("/", "_") or "uploaded_file"


def validate_excel_file(filename: str) -> None:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXCEL_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXCEL_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"엑셀 파일만 업로드할 수 있습니다. 허용 확장자: {allowed}",
        )


def normalize_roles(roles: list[str] | None, file_count: int) -> list[str] | None:
    if not roles:
        return None

    if len(roles) == 1 and "," in roles[0]:
        roles = [role.strip() for role in roles[0].split(",") if role.strip()]

    if len(roles) != file_count:
        raise HTTPException(
            status_code=400,
            detail="파일 role 개수는 업로드한 파일 개수와 같아야 합니다.",
        )

    try:
        normalized_roles = [normalize_upload_role(role) for role in roles]
    except ValueError as exc:
        allowed = ", ".join(ALLOWED_UPLOAD_ROLES)
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 role입니다. 허용 role: {allowed}",
        ) from exc

    seen_keys: set[str] = set()
    for role in normalized_roles:
        key = upload_key_for_role(role)
        if key in seen_keys:
            raise HTTPException(
                status_code=400,
                detail=f"같은 종류의 파일이 중복되었습니다: {role}",
            )
        seen_keys.add(key)

    return normalized_roles


def validate_eur_krw_rate(eur_krw_rate: float | None) -> float | None:
    if eur_krw_rate is None:
        return None
    rate = float(eur_krw_rate)
    if not math.isfinite(rate) or rate <= 0:
        raise HTTPException(status_code=400, detail="EUR/KRW 환율은 0보다 큰 숫자로 입력해 주세요.")
    return rate


def validate_month_setting(value: float | None, field_name: str, allow_zero: bool = False) -> float | None:
    if value is None:
        return None
    number = float(value)
    minimum_ok = number >= 0 if allow_zero else number > 0
    if not math.isfinite(number) or not minimum_ok:
        if allow_zero:
            detail = f"{field_name} 값은 0 이상 숫자로 입력해 주세요."
        else:
            detail = f"{field_name} 값은 0보다 큰 숫자로 입력해 주세요."
        raise HTTPException(status_code=400, detail=detail)
    return number


def validate_percent_threshold(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0 or number > 100:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a number between 0 and 100.")
    return number


def validate_lead_time(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    number = int(value)
    if number <= 0:
        raise HTTPException(status_code=400, detail=f"{field_name} 값은 1 이상의 정수로 입력해 주세요.")
    return number


def validate_lead_time_overrides(
    value: object,
    entity_code: str,
) -> dict[str, int]:
    """Validate a JSON object or multipart JSON string of method overrides."""

    if value is None or value == "":
        return {}
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail="lead_time_overrides must be a valid JSON object",
            ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=400,
            detail="lead_time_overrides must be an object mapping transport codes to days",
        )
    try:
        return normalize_lead_time_overrides(entity_code, parsed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def validate_date_string(value: str | None, field_name: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise HTTPException(status_code=400, detail=f"{field_name} 값은 YYYY-MM-DD 형식으로 입력해 주세요.")
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 값은 올바른 날짜 형식이어야 합니다.") from exc
    return text


def compact_optional_settings(settings: dict[str, float | int | None]) -> dict[str, float | int]:
    return {key: value for key, value in settings.items() if value is not None}


def add_months(base_date, months: int):
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return base_date.replace(year=year, month=month, day=day)


def cms_date_settings(as_of: str) -> dict[str, object]:
    base_date = datetime.strptime(as_of, "%Y-%m-%d").date()
    return {
        "base_date": base_date,
        "period_start": add_months(base_date, -3),
        "logistics_period_start": base_date.replace(month=1, day=1),
        "period_end": base_date,
    }
