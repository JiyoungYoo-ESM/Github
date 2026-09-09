from __future__ import annotations

from datetime import date, datetime
import json

import pytest

from backend.services import order_logic_v3_season_factor_scheduler as scheduler
from backend.services import order_logic_v3_season_factor_service as service
from backend.services import order_logic_v3_season_factor_store as store
from backend.services.order_logic_v3_source import (
    FUNCTION_CLASS_1_AGGREGATE,
    SEASON_FACTOR_VERSION,
    _SeasonalProfileCatalog,
    _select_seasonal_profile,
)
from core.order_logic_v3 import SeasonalProfile


@pytest.fixture
def artifact_store(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store.persistent_state, "enabled", lambda: False)
    monkeypatch.setattr(store, "ORDER_LOGIC_V3_SEASON_FACTOR_DIR", tmp_path)
    return tmp_path


def _catalog(*, factor_offset: float = 0.0, with_error: bool = False):
    factors = {month: 1.0 for month in range(1, 13)}
    factors[1] += factor_offset
    factors[2] -= factor_offset
    return _SeasonalProfileCatalog(
        by_class_1_and_2={},
        by_class_1={
            "선케어": SeasonalProfile(
                version=SEASON_FACTOR_VERSION,
                entity_code="USA",
                function_class_1_code="선케어",
                function_class_2_code=FUNCTION_CLASS_1_AGGREGATE,
                factors_by_month=factors,
            )
        },
        class_1_and_2_errors=(
            {("네일", "네일케어"): "zero monthly factor"} if with_error else {}
        ),
        class_1_errors={},
        identities={},
    )


def _candidate(
    *,
    window_start: date = date(2024, 8, 1),
    window_end: date = date(2026, 7, 31),
    factor_offset: float = 0.0,
    with_error: bool = False,
):
    return service._candidate_from_catalog(
        entity_code="USA",
        window_start=window_start,
        window_end=window_end,
        catalog=_catalog(factor_offset=factor_offset, with_error=with_error),
        source_request={
            "source": "test",
            "demand_policy": service.LEDGER_POLICY,
            "date_from": window_start.isoformat(),
            "date_to": window_end.isoformat(),
            "requested_completed_months": 24,
            "sales_row_count": 10,
            "product_row_count": 2,
        },
    )


def test_calculation_failure_uses_neutral_profile_with_original_reason(
    artifact_store,
):
    activated = store.save_candidate_and_auto_activate(_candidate(with_error=True))

    assert activated["status"] == "active"
    assert activated["validation"]["passed"] is True
    assert activated["errors"] == []
    default = activated["profiles"][1]
    assert default["application_status"] == "DEFAULT_1"
    assert default["original_reason_code"] == "SEASON_FACTOR_CALC_FAILED"
    assert default["original_message"] == "zero monthly factor"
    assert [factor["factor"] for factor in default["factors"]] == [1.0] * 12
    assert store.load_active_artifact("USA")["version"] == activated["version"]

    catalog, meta = service.load_active_season_factor_catalog("USA")
    assert catalog.by_class_1["선케어"].version == activated["version"]
    assert catalog.class_1_and_2_errors == {}
    assert meta["status"] == "active"
    assert meta["default_profile_count"] == 1
    selected = _select_seasonal_profile(
        catalog,
        entity_code="USA",
        function_class_1_code="네일",
        function_class_2_code="네일케어",
    )
    assert selected.blocking_reason_code is None
    assert selected.application_reason_code == store.NEUTRAL_DEFAULT_REASON
    assert selected.original_message == "zero monthly factor"
    assert selected.profile.version == activated["version"]


@pytest.mark.parametrize("identity_policy,expected_version", [
    (None, "v3.4-calculation-failure-default-one"),
    ("V3_CASE_INSENSITIVE_CODE_EXACT_PRODUCT_NAME_V1", "v3.5-exact-name-case-alias"),
    ("V3_CASE_INSENSITIVE_CODE_PRESERVE_SUFFIX_V2", "v3.6-case-insensitive-literal-code"),
    (service.PRODUCT_IDENTITY_POLICY, "v3.7-exact-name-literal-code"),
])
def test_existing_active_migration_preserves_normal_values_and_retires_original(
    artifact_store, identity_policy, expected_version,
):
    legacy = _candidate(factor_offset=0.2)
    legacy["source_request"].pop("demand_policy")
    legacy["calculation_logic_version"] = "legacy-test"
    if identity_policy:
        legacy["source_request"]["product_identity"] = {"policy": identity_policy}
    legacy["errors"] = [service._error_payload(
        "FUNCTION_CLASS_1", "USA", "네일", FUNCTION_CLASS_1_AGGREGATE, "zero monthly factor",
    )]
    legacy["checksum"] = store.artifact_checksum(legacy)
    legacy["version"] = store.artifact_version("USA", legacy["window_end"], legacy["checksum"])
    first = store.save_candidate_and_auto_activate(legacy)

    migrated = service.apply_neutral_defaults_to_active_artifact("USA")
    assert migrated["status"] == "active"
    assert migrated["version"] != first["version"]
    assert migrated["profiles"][0] == first["profiles"][0]
    for key in ("window_start", "window_end", "calculated_at"):
        assert migrated[key] == first[key]
    assert migrated["source_request"]["default_policy_source_version"] == first["version"]
    assert migrated["calculation_logic_version"] == expected_version
    assert migrated["source_request"].get("product_identity") == legacy["source_request"].get("product_identity")
    retired = json.loads((artifact_store / "USA" / "versions" / f"{first['version']}.json").read_text(encoding="utf-8"))
    assert retired["status"] == "retired"
    assert service.apply_neutral_defaults_to_active_artifact("USA")["version"] == migrated["version"]

    catalog, _ = service.load_active_season_factor_catalog("USA")
    selected = _select_seasonal_profile(catalog, entity_code="USA", function_class_1_code="네일", function_class_2_code="미분류")
    assert selected.scope == "FUNCTION_CLASS_1"
    assert selected.application_reason_code == store.NEUTRAL_DEFAULT_REASON
    assert selected.original_reason_code == "SEASON_FACTOR_CALC_FAILED"
    assert selected.blocking_reason_code is None
    assert set(selected.profile.factors_by_month.values()) == {1.0}
    missing = _select_seasonal_profile(catalog, entity_code="USA", function_class_1_code="없는분류", function_class_2_code="없는분류2")
    assert missing.blocking_reason_code == "SEASON_FACTOR_MISSING"


@pytest.mark.parametrize("invalid_metadata", [False, True])
def test_default_profile_cannot_hide_changed_values_or_missing_reason(artifact_store, invalid_metadata):
    candidate = _candidate(with_error=True)
    default = candidate["profiles"][1]
    if invalid_metadata:
        default.pop("original_message")
    else:
        default["factors"][0]["factor"] = 1.2
        default["factors"][1]["factor"] = 0.8
    candidate["checksum"] = store.artifact_checksum(candidate)
    candidate["version"] = store.artifact_version("USA", candidate["window_end"], candidate["checksum"])
    assert store.save_candidate_and_auto_activate(candidate)["validation"]["passed"] is False


def test_policy_migration_does_not_create_an_absent_artifact(artifact_store):
    with pytest.raises(store.SeasonFactorArtifactError) as exc:
        service.apply_neutral_defaults_to_active_artifact("PL")
    assert exc.value.reason_code == "SEASON_FACTOR_ARTIFACT_NOT_ACTIVE"


def test_new_active_retires_the_previous_version(artifact_store):
    first = store.save_candidate_and_auto_activate(_candidate())
    second = store.save_candidate_and_auto_activate(
        _candidate(
            window_start=date(2024, 9, 1),
            window_end=date(2026, 8, 31),
            factor_offset=0.1,
        )
    )

    assert second["status"] == "active"
    assert second["version"] != first["version"]
    assert store.load_active_artifact("USA")["version"] == second["version"]
    retired_path = (
        artifact_store / "USA" / "versions" / f"{first['version']}.json"
    )
    retired = json.loads(retired_path.read_text(encoding="utf-8"))
    assert retired["status"] == "retired"
    assert retired["retired_at"]


def test_invalid_candidate_never_replaces_active(artifact_store):
    first = store.save_candidate_and_auto_activate(_candidate())
    invalid = _candidate(
        window_start=date(2024, 9, 1),
        window_end=date(2026, 8, 31),
        factor_offset=0.1,
    )
    invalid["profiles"][0]["factors"][0]["factor"] = 0

    rejected = store.save_candidate_and_auto_activate(invalid)

    assert rejected["status"] == "candidate"
    assert rejected["validation"]["passed"] is False
    assert store.load_active_artifact("USA")["version"] == first["version"]


def test_monthly_refresh_fetches_completed_months_and_auto_activates(
    artifact_store,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return [{}], {"sha256": "synthetic", "scope": {}, "included_types": ["OUT-SALE", "OUT-SALE (ONLINE)"]}

    monkeypatch.setattr(service, "fetch_v3_ledger_sales", fake_fetch)
    monkeypatch.setattr(service, "_fetch_cached_product_master", lambda **_: ([{}], {}))
    monkeypatch.setattr(
        service,
        "_ledger_demand",
        lambda *_, **__: type("Demand", (), {"empty": False})(),
    )
    monkeypatch.setattr(service, "_profiles", lambda *_, **__: _catalog())

    artifact = service.refresh_order_logic_v3_season_factors(
        as_of="2026-08-28",
        entity_code="USA",
    )

    assert captured["date_from"] == "2024-08-01"
    assert captured["date_to"] == "2026-07-31"
    assert artifact["status"] == "active"
    assert artifact["window_end"] == "2026-07-31"


def test_hq_refresh_uses_ledger_source_without_hq_order_snapshot(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return [{}], {"sha256": "synthetic", "scope": {}, "included_types": ["OUT-SALE", "OUT-SALE (ONLINE)"]}

    monkeypatch.setattr(service, "fetch_v3_ledger_sales", fake_fetch)
    monkeypatch.setattr(service, "_fetch_cached_product_master", lambda **_: ([{}], {}))
    monkeypatch.setattr(
        service,
        "_ledger_demand",
        lambda *_, **__: type("Demand", (), {"empty": False})(),
    )
    monkeypatch.setattr(service, "_profiles", lambda *_, **__: _catalog())
    monkeypatch.setattr(service, "save_candidate_and_auto_activate", lambda candidate: candidate)

    artifact = service.refresh_order_logic_v3_season_factors(
        as_of="2026-08-28",
        entity_code="HQ",
    )

    assert captured == {
        "date_from": "2024-08-01",
        "date_to": "2026-07-31",
        "force_refresh": True,
        "entity_code": "HQ",
    }
    assert artifact["source_request"]["source"] == "CMS_STOCK_IN_OUT"
    assert artifact["source_request"]["demand_policy"] == service.LEDGER_POLICY


def test_scheduler_runs_each_completed_month_target_only_once(
    artifact_store,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(scheduler, "SCM_V3_SEASON_FACTOR_MONTHLY_DAY", 5)
    monkeypatch.setattr(scheduler, "SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST", 3)
    now = datetime.fromisoformat("2026-08-05T03:00:00+09:00")

    assert scheduler.refresh_due_for_entity(now, "USA") is True
    store.save_candidate_and_auto_activate(_candidate())
    assert scheduler.refresh_due_for_entity(now, "USA") is False


def test_scheduler_recalculates_same_month_when_source_policy_is_legacy(artifact_store, monkeypatch):
    monkeypatch.setattr(scheduler, "SCM_V3_SEASON_FACTOR_MONTHLY_DAY", 5)
    monkeypatch.setattr(scheduler, "SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST", 3)
    legacy = _candidate()
    legacy["source_request"].pop("demand_policy")
    legacy["checksum"] = store.artifact_checksum(legacy)
    legacy["version"] = store.artifact_version("USA", legacy["window_end"], legacy["checksum"])
    store.save_candidate_and_auto_activate(legacy)
    assert scheduler.refresh_due_for_entity(datetime.fromisoformat("2026-08-05T03:00:00+09:00"), "USA") is True
