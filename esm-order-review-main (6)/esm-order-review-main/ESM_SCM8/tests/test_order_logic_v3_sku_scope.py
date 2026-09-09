"""V3 entity-specific SKU scope uses explicit codes, not country-name matching."""

import pytest

from backend.services import order_logic_v3_source as source


@pytest.fixture
def scope_policy(monkeypatch):
    codes = frozenset({"TEST-CREAM-EU", "Test-Serum", "TEST-PAD2.0"})
    monkeypatch.setattr(source, "_V3_EXCLUDED_SKUS_BY_ENTITY", {"USA": codes})
    return codes


@pytest.mark.parametrize("entity", ["USA", "PL", "HQ"])
def test_exact_codes_are_excluded_only_in_selected_entity(scope_policy, entity):
    other = {"UNLISTED-EU", "TEST-CREAM-EU-NEW", "TEST-SERUM", "TEST-PAD2"}
    candidates = set(scope_policy) | other
    kept, audit = source._analysis_sku_scope(
        candidates, entity_code=entity, identity_source_codes={},
    )
    assert kept == sorted(other if entity == "USA" else candidates)
    assert audit["excluded_sku_count"] == (3 if entity == "USA" else 0)
    assert audit["candidate_sku_count"] == len(candidates)
    assert audit["included_sku_count"] == len(kept)
    assert candidates == set(scope_policy) | other
    assert all(code not in str(audit) for code in candidates)


def test_only_already_validated_identity_links_follow_exclusion(scope_policy):
    candidates = {"TEST-SERUM", "UNLINKED", "KEEP"}
    kept, audit = source._analysis_sku_scope(
        candidates, entity_code="USA",
        identity_source_codes={"TEST-SERUM": ["Test-Serum"]},
    )
    assert kept == ["KEEP", "UNLINKED"]
    assert audit["excluded_sku_count"] == 1


@pytest.mark.parametrize("candidates", [set(), {"KEEP"}, {"Test-Serum"}])
def test_empty_absent_and_all_excluded_populations(scope_policy, candidates):
    kept, audit = source._analysis_sku_scope(
        candidates, entity_code="USA", identity_source_codes={},
    )
    assert kept == sorted(candidates - scope_policy)
    assert audit["configured_sku_count"] == 3
    assert audit["excluded_sku_count"] == len(candidates & scope_policy)


def test_policy_fingerprint_changes_even_when_excluded_counts_match(monkeypatch):
    def run(codes):
        monkeypatch.setattr(source, "_V3_EXCLUDED_SKUS_BY_ENTITY", {"USA": frozenset(codes)})
        return source._analysis_sku_scope(
            {"A", "B", "KEEP"}, entity_code="USA", identity_source_codes={},
        )[1]

    first = run(["A"])
    second = run(["B"])
    assert first["excluded_sku_count"] == second["excluded_sku_count"] == 1
    assert first["configuration_sha256"] != second["configuration_sha256"]
    assert run(["A", "B"]) == run(["B", "A"])
