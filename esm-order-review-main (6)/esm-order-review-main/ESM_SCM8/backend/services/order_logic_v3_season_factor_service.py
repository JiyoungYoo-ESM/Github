"""Monthly V3 season-factor generation and active-artifact lookup."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import threading
import time
from typing import Callable, Mapping

from backend.season_trend_api_client import _fetch_cached_product_master
from backend.services.order_logic_v3_ledger import LEDGER_POLICY, fetch_v3_ledger_sales
from backend.services.order_logic_v3_product_identity import PRODUCT_IDENTITY_POLICY, ProductIdentityResolver
from backend.services.order_logic_v3_season_factor_store import (
    ARTIFACT_SCHEMA_VERSION,
    NEUTRAL_DEFAULT_REASON,
    NEUTRAL_DEFAULT_STATUS,
    artifact_checksum,
    artifact_version,
    load_active_artifact,
    save_candidate_and_auto_activate,
)
from backend.services.order_logic_v3_source import (
    FUNCTION_CLASS_1_AGGREGATE,
    SEASON_FACTOR_SCOPE_CLASS_1,
    SEASON_FACTOR_SCOPE_CLASS_1_AND_2,
    SEASON_FACTOR_VERSION,
    SOURCE_DATE_BASIS,
    _SeasonalProfileCatalog,
    _ledger_demand,
    _profiles,
)
from core.order_logic_v3 import SeasonalProfile


_REFRESH_LOCK = threading.RLock()


def _entity_code(value: object) -> str:
    code = str(value or "").strip().upper()
    if code not in {"HQ", "PL", "USA"}:
        raise ValueError(f"V3 시즌팩터 적용 대상이 아닌 법인입니다: {code or '(empty)'}")
    return code


def _shift_month(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    return date(absolute // 12, absolute % 12 + 1, 1)


def monthly_completed_window(as_of: date) -> tuple[date, date, tuple[date, ...]]:
    """Use the 24 calendar months completed before the run month."""

    end = as_of.replace(day=1) - timedelta(days=1)
    start = _shift_month(end.replace(day=1), -23)
    months = tuple(_shift_month(start, offset) for offset in range(24))
    return start, end, months


def _profile_payload(scope: str, profile: SeasonalProfile) -> dict[str, object]:
    return {
        "scope": scope,
        "entity_code": profile.entity_code,
        "function_class_1_code": profile.function_class_1_code,
        "function_class_2_code": profile.function_class_2_code,
        "application_status": "APPLICABLE",
        "reason_code": None,
        "factors": [
            {"calendar_month": month, "factor": float(profile.factors_by_month[month])}
            for month in range(1, 13)
        ],
    }


def _error_payload(
    scope: str,
    entity_code: str,
    function_class_1_code: str,
    function_class_2_code: str,
    message: str,
) -> dict[str, object]:
    return {
        "scope": scope,
        "entity_code": entity_code,
        "function_class_1_code": function_class_1_code,
        "function_class_2_code": function_class_2_code,
        "application_status": "BLOCKED",
        "reason_code": "SEASON_FACTOR_CALC_FAILED",
        "message": message,
    }


def _candidate_from_catalog(
    *,
    entity_code: str,
    window_start: date,
    window_end: date,
    catalog: _SeasonalProfileCatalog,
    source_request: Mapping[str, object],
) -> dict[str, object]:
    profiles = [
        _profile_payload(SEASON_FACTOR_SCOPE_CLASS_1, profile)
        for _class1, profile in sorted(catalog.by_class_1.items())
    ]
    profiles.extend(
        _profile_payload(SEASON_FACTOR_SCOPE_CLASS_1_AND_2, profile)
        for _key, profile in sorted(catalog.by_class_1_and_2.items())
    )
    errors = [
        _error_payload(
            SEASON_FACTOR_SCOPE_CLASS_1,
            entity_code,
            class1,
            FUNCTION_CLASS_1_AGGREGATE,
            message,
        )
        for class1, message in sorted(catalog.class_1_errors.items())
    ]
    errors.extend(
        _error_payload(
            SEASON_FACTOR_SCOPE_CLASS_1_AND_2,
            entity_code,
            class1,
            class2,
            message,
        )
        for (class1, class2), message in sorted(catalog.class_1_and_2_errors.items())
    )
    candidate: dict[str, object] = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "status": "candidate",
        "entity_code": entity_code,
        "date_basis": SOURCE_DATE_BASIS,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "calculation_logic_version": SEASON_FACTOR_VERSION,
        "source_request": dict(source_request),
        "profiles": profiles,
        "errors": errors,
    }
    return _apply_calculation_failure_defaults(candidate)


def _apply_calculation_failure_defaults(
    candidate: dict[str, object], *, calculation_logic_version: str = SEASON_FACTOR_VERSION,
) -> dict[str, object]:
    """SF-018: replace only classified calculation failures, never artifact errors."""

    candidate = deepcopy(candidate)
    profiles = list(candidate["profiles"])
    remaining_errors = []
    for error in candidate["errors"]:
        if error.get("reason_code") != "SEASON_FACTOR_CALC_FAILED":
            remaining_errors.append(error)
            continue
        profiles.append({
            **{key: error[key] for key in (
                "scope", "entity_code", "function_class_1_code", "function_class_2_code",
            )},
            "application_status": NEUTRAL_DEFAULT_STATUS,
            "reason_code": NEUTRAL_DEFAULT_REASON,
            "original_reason_code": error["reason_code"],
            "original_message": error["message"],
            "factors": [
                {"calendar_month": month, "factor": 1.0} for month in range(1, 13)
            ],
        })
    candidate["profiles"] = profiles
    candidate["errors"] = remaining_errors
    candidate["calculation_logic_version"] = calculation_logic_version
    checksum = artifact_checksum(candidate)
    candidate["checksum"] = checksum
    candidate["version"] = artifact_version(
        str(candidate["entity_code"]),
        str(candidate["window_end"]),
        checksum,
    )
    return candidate


def apply_neutral_defaults_to_active_artifact(entity_code: str) -> dict[str, object]:
    """Explicit policy migration: validate the old active and retain its source window."""

    with _REFRESH_LOCK:
        active = load_active_artifact(entity_code)
        if not any(
            error.get("reason_code") == "SEASON_FACTOR_CALC_FAILED"
            for error in active["errors"]
        ):
            return active
        candidate = deepcopy(active)
        candidate["status"] = "candidate"
        candidate.pop("activated_at", None)
        candidate.pop("validation", None)
        candidate["source_request"] = {
            **candidate["source_request"],
            "default_policy_source_version": active["version"],
            "default_policy_applied_at": datetime.now(timezone.utc).isoformat(),
        }
        # Replacing failed factors with 1.0 does not re-read or remap sales.
        # Do not label a legacy artifact as using the new identity policy.
        identity = candidate["source_request"].get("product_identity") or {}
        version = (
            SEASON_FACTOR_VERSION
            if candidate["source_request"].get("demand_policy") == LEDGER_POLICY
            else "v3.7-exact-name-literal-code"
            if identity.get("policy") == PRODUCT_IDENTITY_POLICY
            else "v3.6-case-insensitive-literal-code"
            if identity.get("policy") == "V3_CASE_INSENSITIVE_CODE_PRESERVE_SUFFIX_V2"
            else "v3.5-exact-name-case-alias"
            if identity.get("policy") == "V3_CASE_INSENSITIVE_CODE_EXACT_PRODUCT_NAME_V1"
            else "v3.4-calculation-failure-default-one"
        )
        return save_candidate_and_auto_activate(_apply_calculation_failure_defaults(
            candidate, calculation_logic_version=version,
        ))


def refresh_order_logic_v3_season_factors(
    *,
    as_of: str,
    entity_code: str,
    force_refresh: bool = True,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Build one monthly candidate and automatically activate it if valid."""

    with _REFRESH_LOCK:
        refresh_started_at = time.perf_counter()
        parsed_as_of = date.fromisoformat(as_of)
        code = _entity_code(entity_code)
        window_start, window_end, months = monthly_completed_window(parsed_as_of)
        sales_rows, source_meta = fetch_v3_ledger_sales(
            date_from=window_start.isoformat(),
            date_to=window_end.isoformat(),
            force_refresh=force_refresh,
            entity_code=code,
            **({"progress": progress} if progress else {}),
        )
        if progress:
            progress({"stage": "product_master"})
        product_rows, _product_meta = _fetch_cached_product_master(
            eu_sold_only=False, force_refresh=force_refresh,
        )
        source_name = "CMS_STOCK_IN_OUT"
        source_seconds = time.perf_counter() - refresh_started_at

        calculation_started_at = time.perf_counter()
        if progress:
            progress({"stage": "calculating"})
        identity_resolver = ProductIdentityResolver.build(product_rows, [sales_rows])
        demand = _ledger_demand(
            sales_rows, product_rows, entity_code=code, identity_resolver=identity_resolver,
        )
        if demand.empty:
            raise ValueError("V3 시즌팩터 판매 모집단에 OUT-SALE 또는 온라인 판매출고가 없습니다.")
        catalog = _profiles(demand, months, entity_code=code)
        candidate = _candidate_from_catalog(
            entity_code=code,
            window_start=window_start,
            window_end=window_end,
            catalog=catalog,
            source_request={
                "source": source_name,
                "demand_policy": LEDGER_POLICY,
                "included_types": source_meta["included_types"],
                "scope": source_meta["scope"],
                "ledger_sales_sha256": source_meta["sha256"],
                "date_from": window_start.isoformat(),
                "date_to": window_end.isoformat(),
                "requested_completed_months": 24,
                "sales_row_count": len(sales_rows),
                "product_row_count": len(product_rows),
                # Store policy/counts, never raw product identities, in the artifact.
                "product_identity": identity_resolver.summary(),
            },
        )
        artifact = save_candidate_and_auto_activate(candidate)
        print(
            "[perf][v3_season_factor] refresh_done "
            f"entity={code} source_seconds={source_seconds:.3f} "
            f"calculation_seconds={time.perf_counter() - calculation_started_at:.3f} "
            f"total_seconds={time.perf_counter() - refresh_started_at:.3f} "
            f"sales_rows={len(sales_rows)} product_rows={len(product_rows)}",
            flush=True,
        )
        return artifact


def load_active_season_factor_catalog(
    entity_code: str,
) -> tuple[_SeasonalProfileCatalog, dict[str, object]]:
    """Rehydrate the active aggregate artifact for the V3 request path."""

    artifact = load_active_artifact(entity_code)
    code = _entity_code(entity_code)
    version = str(artifact["version"])
    by_class_1: dict[str, SeasonalProfile] = {}
    by_class_1_and_2: dict[tuple[str, str], SeasonalProfile] = {}
    application_metadata: dict[tuple[str, str, str], dict[str, str]] = {}
    for raw in artifact["profiles"]:  # type: ignore[index]
        item = dict(raw)
        factors = {
            int(factor["calendar_month"]): float(factor["factor"])
            for factor in item["factors"]
        }
        profile = SeasonalProfile(
            version=version,
            entity_code=code,
            function_class_1_code=str(item["function_class_1_code"]),
            function_class_2_code=str(item["function_class_2_code"]),
            factors_by_month=factors,
        )
        if item.get("application_status") == NEUTRAL_DEFAULT_STATUS:
            application_metadata[(
                str(item["scope"]), profile.function_class_1_code, profile.function_class_2_code,
            )] = {key: str(item[key]) for key in (
                "reason_code", "original_reason_code", "original_message",
            )}
        if item["scope"] == SEASON_FACTOR_SCOPE_CLASS_1:
            by_class_1[profile.function_class_1_code] = profile
        else:
            by_class_1_and_2[
                (profile.function_class_1_code, profile.function_class_2_code)
            ] = profile

    class_1_errors: dict[str, str] = {}
    class_1_and_2_errors: dict[tuple[str, str], str] = {}
    for raw in artifact["errors"]:  # type: ignore[index]
        item = dict(raw)
        message = str(item.get("message") or "시즌팩터 계산 실패")
        class1 = str(item["function_class_1_code"])
        class2 = str(item["function_class_2_code"])
        if item["scope"] == SEASON_FACTOR_SCOPE_CLASS_1:
            class_1_errors[class1] = message
        else:
            class_1_and_2_errors[(class1, class2)] = message

    return (
        _SeasonalProfileCatalog(
            by_class_1_and_2=by_class_1_and_2,
            by_class_1=by_class_1,
            class_1_and_2_errors=class_1_and_2_errors,
            class_1_errors=class_1_errors,
            identities={},
            artifact_version=version,
            application_metadata=application_metadata,
        ),
        {
            "version": version,
            "status": artifact["status"],
            "window_start": artifact["window_start"],
            "window_end": artifact["window_end"],
            "calculated_at": artifact["calculated_at"],
            "activated_at": artifact.get("activated_at"),
            "checksum": artifact["checksum"],
            "profile_count": len(artifact["profiles"]),  # type: ignore[arg-type]
            "error_count": len(artifact["errors"]),  # type: ignore[arg-type]
            "default_profile_count": len(application_metadata),
            "source_policy": artifact["source_request"].get("demand_policy"),
        },
    )


__all__ = [
    "apply_neutral_defaults_to_active_artifact",
    "load_active_season_factor_catalog",
    "monthly_completed_window",
    "refresh_order_logic_v3_season_factors",
]
