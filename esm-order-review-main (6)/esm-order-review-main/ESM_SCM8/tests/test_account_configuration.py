from __future__ import annotations

from dataclasses import replace

import pytest

from backend.auth.passwords import hash_password, verify_password
from backend.auth.user_store import ACCOUNT_SPECS, EnvironmentUserStore, validate_user_store
from backend.entities import ENTITY_CODES
from backend.services.cms_fetch_cache import _cache_key
from tests.auth_helpers import TEST_ALLOWED_ENTITIES, TestUserStore


class StaticUserStore:
    def __init__(self, accounts):
        self._accounts = tuple(accounts)

    def all(self):
        return self._accounts


def test_shipped_account_matrix_matches_policy():
    # Base team accounts must match the documented policy.
    policy_specs = [spec for spec in ACCOUNT_SPECS if spec.username in TEST_ALLOWED_ENTITIES]
    assert tuple(spec.username for spec in policy_specs) == tuple(TEST_ALLOWED_ENTITIES)
    assert {spec.username: spec.allowed_entities for spec in policy_specs} == TEST_ALLOWED_ENTITIES
    assert ACCOUNT_SPECS[0].allowed_entities == ENTITY_CODES


def test_adminmaster_is_the_only_shipped_master_account():
    assert [(spec.username, spec.role) for spec in ACCOUNT_SPECS if spec.role == "MASTER"] == [
        ("adminmaster", "MASTER")
    ]


def test_production_validation_rejects_missing_password_hashes(monkeypatch: pytest.MonkeyPatch):
    for spec in ACCOUNT_SPECS:
        monkeypatch.delenv(spec.password_hash_env, raising=False)
    with pytest.raises(RuntimeError, match="비밀번호 해시"):
        validate_user_store(EnvironmentUserStore(), require_all_hashes=True)


def test_complete_test_store_passes_configuration_validation():
    validate_user_store(TestUserStore(), require_all_hashes=True)


def test_configuration_rejects_duplicate_usernames():
    accounts = list(TestUserStore().all())
    accounts.append(accounts[0])
    with pytest.raises(RuntimeError, match="중복"):
        validate_user_store(StaticUserStore(accounts), require_all_hashes=True)


def test_configuration_rejects_unknown_entity_code():
    accounts = list(TestUserStore().all())
    accounts[1] = replace(accounts[1], allowed_entities=("HQ", "UNKNOWN"))
    with pytest.raises(RuntimeError, match="존재하지 않는 법인 코드"):
        validate_user_store(StaticUserStore(accounts), require_all_hashes=True)


def test_configuration_rejects_empty_entity_list():
    accounts = list(TestUserStore().all())
    accounts[1] = replace(accounts[1], allowed_entities=())
    with pytest.raises(RuntimeError, match="비어"):
        validate_user_store(StaticUserStore(accounts), require_all_hashes=True)


def test_configuration_rejects_incomplete_master_permissions():
    accounts = list(TestUserStore().all())
    accounts[0] = replace(accounts[0], allowed_entities=("HQ", "PL"))
    with pytest.raises(RuntimeError, match="8개 법인"):
        validate_user_store(StaticUserStore(accounts), require_all_hashes=True)


def test_configuration_rejects_only_inactive_accounts():
    accounts = [replace(account, is_active=False) for account in TestUserStore().all()]
    with pytest.raises(RuntimeError, match="활성화된 계정"):
        validate_user_store(StaticUserStore(accounts), require_all_hashes=True)


def test_password_hash_round_trip_and_wrong_password_rejection():
    encoded = hash_password("test-password-for-hash")
    assert "test-password-for-hash" not in encoded
    assert verify_password("test-password-for-hash", encoded)
    assert not verify_password("wrong", encoded)


def test_raw_cms_cache_key_is_isolated_by_entity():
    common = {
        "as_of": "2026-07-22",
        "date_from": "2026-01-01",
        "date_to": "2026-07-22",
        "logistics_date_from": None,
    }
    assert _cache_key(entity_code="PL", **common) != _cache_key(entity_code="MY", **common)
