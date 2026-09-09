"""Versioned persistence for V3 monthly season-factor artifacts.

Only aggregate factors and validation metadata are stored here. Raw CMS rows
must never be copied into an artifact. PostgreSQL snapshots are used when the
runtime database is configured; development falls back to atomic JSON files.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile
import threading
from typing import Mapping

from backend.config import ORDER_LOGIC_V3_SEASON_FACTOR_DIR
from backend.services import persistent_state


ARTIFACT_SCHEMA_VERSION = 1
NEUTRAL_DEFAULT_STATUS = "DEFAULT_1"
NEUTRAL_DEFAULT_REASON = "SEASON_FACTOR_CALC_FAILED_USE_DEFAULT_1"
SNAPSHOT_KIND = "order_logic_v3_season_factor"
_CONTENT_FIELDS = (
    "artifact_schema_version",
    "entity_code",
    "date_basis",
    "window_start",
    "window_end",
    "calculation_logic_version",
    "source_request",
    "profiles",
    "errors",
)
_ACTIVATION_LOCK = threading.RLock()


class SeasonFactorArtifactError(ValueError):
    """Raised when an active artifact is absent or fails integrity checks."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _entity_code(value: object) -> str:
    code = str(value or "").strip().upper()
    if code not in {"HQ", "PL", "USA"}:
        raise ValueError(f"V3 시즌팩터 적용 대상이 아닌 법인입니다: {code or '(empty)'}")
    return code


def _canonical_content(artifact: Mapping[str, object]) -> dict[str, object]:
    return {field: deepcopy(artifact.get(field)) for field in _CONTENT_FIELDS}


def artifact_checksum(artifact: Mapping[str, object]) -> str:
    encoded = json.dumps(
        _canonical_content(artifact),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def artifact_version(entity_code: str, window_end: str, checksum: str) -> str:
    code = _entity_code(entity_code)
    compact_end = date.fromisoformat(window_end).strftime("%Y%m%d")
    return f"v3sf_{code}_{compact_end}_{checksum[:12]}"


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _profile_key(item: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(item.get("scope") or "").strip(),
        str(item.get("function_class_1_code") or "").strip(),
        str(item.get("function_class_2_code") or "").strip(),
    )


def validate_artifact(artifact: Mapping[str, object]) -> list[str]:
    """Return structural/integrity errors without inventing quality thresholds."""

    problems: list[str] = []
    if artifact.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION:
        problems.append("지원하지 않는 시즌팩터 artifact 스키마입니다.")
    try:
        entity = _entity_code(artifact.get("entity_code"))
    except ValueError as exc:
        problems.append(str(exc))
        entity = ""
    if artifact.get("date_basis") != "SOURCE_CALENDAR_DATE":
        problems.append("시즌팩터 날짜 기준은 SOURCE_CALENDAR_DATE여야 합니다.")
    if not str(artifact.get("calculation_logic_version") or "").strip():
        problems.append("시즌팩터 계산 로직 버전이 필요합니다.")
    source_request = artifact.get("source_request")
    if not isinstance(source_request, dict):
        problems.append("시즌팩터 원천 요청 메타데이터가 필요합니다.")
    elif source_request.get("requested_completed_months") != 24:
        problems.append("시즌팩터 원천 요청은 완료월 24개여야 합니다.")

    try:
        window_start = date.fromisoformat(str(artifact.get("window_start") or ""))
        window_end = date.fromisoformat(str(artifact.get("window_end") or ""))
        if window_start.day != 1:
            problems.append("관측 시작일은 달력월 첫날이어야 합니다.")
        if window_end != _next_month(window_end.replace(day=1)) - timedelta(days=1):
            problems.append("관측 종료일은 달력월 마지막 날이어야 합니다.")
        cursor = window_start
        for _ in range(24):
            cursor = _next_month(cursor)
        if cursor - timedelta(days=1) != window_end:
            problems.append("관측기간은 연속된 완료월 24개여야 합니다.")
        if isinstance(source_request, dict) and (
            str(source_request.get("date_from") or "") != window_start.isoformat()
            or str(source_request.get("date_to") or "") != window_end.isoformat()
        ):
            problems.append("원천 요청기간과 artifact 관측기간이 일치하지 않습니다.")
    except ValueError:
        problems.append("관측기간 날짜 형식이 올바르지 않습니다.")

    profiles = artifact.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        problems.append("적용 가능한 시즌팩터 프로파일이 하나 이상 필요합니다.")
        profiles = []
    seen_profiles: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(profiles):
        if not isinstance(raw, dict):
            problems.append(f"profiles[{index}] 형식이 올바르지 않습니다.")
            continue
        key = _profile_key(raw)
        if key[0] not in {"FUNCTION_CLASS_1", "FUNCTION_CLASS_1_AND_2"}:
            problems.append(f"profiles[{index}]의 scope가 올바르지 않습니다.")
        if not key[1] or not key[2]:
            problems.append(f"profiles[{index}]의 기능구분 키가 비어 있습니다.")
        if key in seen_profiles:
            problems.append(f"중복 시즌팩터 프로파일이 있습니다: {key}")
        seen_profiles.add(key)
        if str(raw.get("entity_code") or "").strip().upper() != entity:
            problems.append(f"profiles[{index}]의 법인이 artifact 법인과 다릅니다.")
        factors = raw.get("factors")
        if not isinstance(factors, list):
            problems.append(f"profiles[{index}]의 월별 팩터 형식이 올바르지 않습니다.")
            continue
        month_values: dict[int, float] = {}
        for factor_index, factor_raw in enumerate(factors):
            if not isinstance(factor_raw, dict):
                problems.append(
                    f"profiles[{index}].factors[{factor_index}] 형식이 올바르지 않습니다."
                )
                continue
            try:
                month = int(factor_raw.get("calendar_month"))
                factor = float(factor_raw.get("factor"))
            except (TypeError, ValueError):
                problems.append(
                    f"profiles[{index}].factors[{factor_index}] 값이 올바르지 않습니다."
                )
                continue
            if month in month_values:
                problems.append(f"profiles[{index}]에 {month}월 팩터가 중복됐습니다.")
            month_values[month] = factor
            if not 1 <= month <= 12 or not math.isfinite(factor) or not (factor > 0):
                problems.append(f"profiles[{index}]의 월 또는 팩터가 유효하지 않습니다.")
        if set(month_values) != set(range(1, 13)):
            problems.append(f"profiles[{index}]에 1~12월 팩터가 모두 필요합니다.")
        elif all(math.isfinite(value) for value in month_values.values()) and not math.isclose(
            sum(month_values.values()) / 12.0,
            1.0,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            problems.append(f"profiles[{index}]의 12개월 팩터 평균이 1.0이 아닙니다.")

        if (
            raw.get("application_status") == NEUTRAL_DEFAULT_STATUS
            or raw.get("reason_code") == NEUTRAL_DEFAULT_REASON
        ):
            if (
                raw.get("application_status") != NEUTRAL_DEFAULT_STATUS
                or raw.get("reason_code") != NEUTRAL_DEFAULT_REASON
                or raw.get("original_reason_code") != "SEASON_FACTOR_CALC_FAILED"
                or not str(raw.get("original_message") or "").strip()
            ):
                problems.append(f"profiles[{index}]의 기본값 적용 사유가 올바르지 않습니다.")
            if any(value != 1.0 for value in month_values.values()):
                problems.append(f"profiles[{index}]의 기본값은 모든 월에 1.0이어야 합니다.")

    errors = artifact.get("errors")
    if not isinstance(errors, list):
        problems.append("계산 실패 목록 형식이 올바르지 않습니다.")
        errors = []
    seen_errors: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(errors):
        if not isinstance(raw, dict):
            problems.append(f"errors[{index}] 형식이 올바르지 않습니다.")
            continue
        key = _profile_key(raw)
        if key[0] not in {"FUNCTION_CLASS_1", "FUNCTION_CLASS_1_AND_2"}:
            problems.append(f"errors[{index}]의 scope가 올바르지 않습니다.")
        if not key[1] or not key[2]:
            problems.append(f"errors[{index}]의 기능구분 키가 비어 있습니다.")
        if key in seen_errors:
            problems.append(f"중복 계산 실패 항목이 있습니다: {key}")
        seen_errors.add(key)
        if key in seen_profiles:
            problems.append(f"동일 분류가 성공과 실패에 동시에 존재합니다: {key}")
        if not str(raw.get("reason_code") or "").strip():
            problems.append(f"errors[{index}]의 reason_code가 비어 있습니다.")
        if str(raw.get("entity_code") or "").strip().upper() != entity:
            problems.append(f"errors[{index}]의 법인이 artifact 법인과 다릅니다.")

    expected_checksum = artifact_checksum(artifact)
    if str(artifact.get("checksum") or "") != expected_checksum:
        problems.append("시즌팩터 artifact checksum이 일치하지 않습니다.")
    try:
        expected_version = artifact_version(
            entity,
            str(artifact.get("window_end") or ""),
            expected_checksum,
        )
    except (ValueError, TypeError):
        expected_version = ""
    if str(artifact.get("version") or "") != expected_version:
        problems.append("시즌팩터 artifact 버전이 내용과 일치하지 않습니다.")
    return problems


def _snapshot_key(entity_code: str, suffix: str) -> str:
    return f"{SNAPSHOT_KIND}:{_entity_code(entity_code)}:{suffix}"


def _entity_dir(entity_code: str) -> Path:
    return ORDER_LOGIC_V3_SEASON_FACTOR_DIR / _entity_code(entity_code)


def _version_path(entity_code: str, version: str) -> Path:
    return _entity_dir(entity_code) / "versions" / f"{version}.json"


def _active_path(entity_code: str) -> Path:
    return _entity_dir(entity_code) / "active.json"


def _latest_candidate_path(entity_code: str) -> Path:
    return _entity_dir(entity_code) / "latest_candidate.json"


def _atomic_write(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(payload, temporary, ensure_ascii=False, sort_keys=True, default=str)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _save_version(artifact: dict[str, object]) -> None:
    entity = _entity_code(artifact.get("entity_code"))
    version = str(artifact.get("version") or "").strip()
    if persistent_state.enabled():
        persistent_state.save_snapshot(
            _snapshot_key(entity, f"version:{version}"),
            SNAPSHOT_KIND,
            artifact,
        )
        return
    _atomic_write(_version_path(entity, version), artifact)


def _save_active(artifact: dict[str, object]) -> None:
    entity = _entity_code(artifact.get("entity_code"))
    if persistent_state.enabled():
        persistent_state.save_snapshot(
            _snapshot_key(entity, "active"),
            SNAPSHOT_KIND,
            artifact,
        )
        return
    _atomic_write(_active_path(entity), artifact)


def _save_latest_candidate(artifact: dict[str, object]) -> None:
    entity = _entity_code(artifact.get("entity_code"))
    if persistent_state.enabled():
        persistent_state.save_snapshot(
            _snapshot_key(entity, "latest_candidate"),
            SNAPSHOT_KIND,
            artifact,
        )
        return
    _atomic_write(_latest_candidate_path(entity), artifact)


def _load_active_unchecked(entity_code: str) -> dict[str, object] | None:
    entity = _entity_code(entity_code)
    if persistent_state.enabled():
        return persistent_state.load_snapshot(_snapshot_key(entity, "active"))
    path = _active_path(entity)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def save_candidate_and_auto_activate(candidate: dict[str, object]) -> dict[str, object]:
    """Persist a candidate and switch active only after validation passes."""

    with _ACTIVATION_LOCK:
        prepared = deepcopy(candidate)
        validation_errors = validate_artifact(prepared)
        prepared["validation"] = {
            "passed": not validation_errors,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "errors": validation_errors,
        }
        _save_version(prepared)
        _save_latest_candidate(prepared)
        if validation_errors:
            return prepared

        current = _load_active_unchecked(str(prepared["entity_code"]))
        if current and current.get("version") != prepared.get("version"):
            retired = deepcopy(current)
            retired["status"] = "retired"
            retired["retired_at"] = datetime.now(timezone.utc).isoformat()
            _save_version(retired)

        activated = deepcopy(prepared)
        activated["status"] = "active"
        activated["activated_at"] = (
            current.get("activated_at")
            if current and current.get("version") == prepared.get("version")
            else datetime.now(timezone.utc).isoformat()
        )
        _save_version(activated)
        _save_active(activated)
        return activated


def load_active_artifact(entity_code: str) -> dict[str, object]:
    artifact = _load_active_unchecked(entity_code)
    if artifact is None:
        raise SeasonFactorArtifactError(
            "SEASON_FACTOR_ARTIFACT_NOT_ACTIVE",
            "해당 법인의 활성 시즌팩터 artifact가 없습니다.",
        )
    problems = validate_artifact(artifact)
    if artifact.get("status") != "active":
        problems.append("활성 포인터의 artifact 상태가 active가 아닙니다.")
    validation = artifact.get("validation")
    if not isinstance(validation, dict) or validation.get("passed") is not True:
        problems.append("활성 artifact의 검증 통과 기록이 없습니다.")
    if problems:
        raise SeasonFactorArtifactError(
            "SEASON_FACTOR_ARTIFACT_INVALID",
            "활성 시즌팩터 artifact 검증에 실패했습니다: " + "; ".join(problems),
        )
    return deepcopy(artifact)


def load_latest_candidate(entity_code: str) -> dict[str, object] | None:
    entity = _entity_code(entity_code)
    if persistent_state.enabled():
        payload = persistent_state.load_snapshot(
            _snapshot_key(entity, "latest_candidate")
        )
        return deepcopy(payload) if payload is not None else None
    path = _latest_candidate_path(entity)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "SeasonFactorArtifactError",
    "artifact_checksum",
    "artifact_version",
    "load_active_artifact",
    "load_latest_candidate",
    "save_candidate_and_auto_activate",
    "validate_artifact",
]
