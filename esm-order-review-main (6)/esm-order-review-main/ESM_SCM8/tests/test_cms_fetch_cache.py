"""CMS raw fetch 캐시(hit/miss/TTL) 동작 검증.

- 같은 (as_of, date_from, date_to, logistics_date_from) 조건이면 fetcher를 다시
  부르지 않고 memory → disk 순으로 재사용해야 한다.
- as_of=오늘은 CMS_TODAY_CACHE_TTL_SECONDS TTL이 적용되고, 과거 날짜는 무기한이다.
"""

import json
import os
import threading
import time

import pytest

from backend.services import cms_fetch_cache
from core.common import korea_today

PAST_AS_OF = "2020-01-01"


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()
    yield
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()


def _get(fetcher, *, as_of=PAST_AS_OF, date_from="2019-07-01"):
    return cms_fetch_cache.get_or_fetch_cms_raw_data(
        as_of=as_of,
        date_from=date_from,
        date_to=as_of,
        logistics_date_from=date_from,
        fetcher=fetcher,
    )


def _counting_fetcher(raw):
    calls = {"count": 0}

    def fetcher():
        calls["count"] += 1
        return raw

    return fetcher, calls


def _cache_key(*, as_of=PAST_AS_OF, date_from="2019-07-01"):
    return cms_fetch_cache._cache_key(
        as_of=as_of,
        date_from=date_from,
        date_to=as_of,
        logistics_date_from=date_from,
    )


def test_miss_fetches_once_then_hits_memory():
    fetcher, calls = _counting_fetcher({"sales_local": [{"prod_cd": "SKU-1"}]})

    raw, info = _get(fetcher)
    assert calls["count"] == 1
    assert raw == {"sales_local": [{"prod_cd": "SKU-1"}]}
    assert info["hit"] is False
    assert info["source"] == "cms_api"
    assert info["ttl_seconds"] is None  # 과거 날짜는 TTL 없음

    raw_again, info_again = _get(fetcher)
    assert calls["count"] == 1  # 캐시 재사용, fetcher 재호출 없음
    assert raw_again == raw
    assert info_again["hit"] is True
    assert info_again["source"] == "memory"
    assert info_again["age_seconds"] >= 0


def test_disk_hit_after_memory_cleared_and_promotes_back_to_memory(tmp_path):
    fetcher, calls = _counting_fetcher({"stock_local": []})
    _get(fetcher)
    assert (tmp_path / f"{_cache_key()}.json").is_file()

    cms_fetch_cache._MEMORY_CACHE.clear()  # 백엔드 재시작 시나리오

    raw, info = _get(fetcher)
    assert calls["count"] == 1
    assert raw == {"stock_local": []}
    assert info["hit"] is True
    assert info["source"] == "disk"

    _, info_memory = _get(fetcher)
    assert calls["count"] == 1
    assert info_memory["source"] == "memory"


def test_disk_hit_renews_idle_retention_mtime(tmp_path):
    fetcher, calls = _counting_fetcher({"sales_history": [{"prod_cd": "SKU-1"}]})
    _get(fetcher)
    path = tmp_path / f"{_cache_key()}.json"
    old_stamp = time.time() - 8 * 86400
    os.utime(path, (old_stamp, old_stamp))
    cms_fetch_cache._MEMORY_CACHE.clear()

    _, info = _get(fetcher)
    prune_result = cms_fetch_cache.prune_disk_cache(max_age_days=7)

    assert calls["count"] == 1
    assert info["source"] == "disk"
    assert path.stat().st_mtime > old_stamp
    assert prune_result["removed"] == 0
    assert path.is_file()


def test_today_cache_expires_after_ttl(tmp_path, monkeypatch):
    monkeypatch.setattr(cms_fetch_cache, "CMS_TODAY_CACHE_TTL_SECONDS", 100)
    today = korea_today().isoformat()
    fetcher, calls = _counting_fetcher({"open_po": []})

    _, info = _get(fetcher, as_of=today)
    assert calls["count"] == 1
    assert info["ttl_seconds"] == 100

    # memory/disk 양쪽의 created_at을 TTL보다 오래된 시각으로 되돌린다.
    key = _cache_key(as_of=today)
    created_at, raw = cms_fetch_cache._MEMORY_CACHE[key]
    cms_fetch_cache._MEMORY_CACHE[key] = (created_at - 200, raw)
    path = tmp_path / f"{key}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["created_at"] = time.time() - 200
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    _, info_refetched = _get(fetcher, as_of=today)
    assert calls["count"] == 2  # TTL 만료 → CMS API 재호출
    assert info_refetched["hit"] is False
    assert info_refetched["source"] == "cms_api"


def test_past_as_of_never_expires():
    fetcher, calls = _counting_fetcher({"shipping": []})
    _get(fetcher)

    key = _cache_key()
    created_at, raw = cms_fetch_cache._MEMORY_CACHE[key]
    cms_fetch_cache._MEMORY_CACHE[key] = (created_at - 10_000_000, raw)

    _, info = _get(fetcher)
    assert calls["count"] == 1  # 과거 날짜는 아무리 오래돼도 재사용
    assert info["hit"] is True


def test_different_conditions_use_different_cache_entries():
    fetcher, calls = _counting_fetcher({"sales_hq": []})
    _get(fetcher, date_from="2019-07-01")
    _get(fetcher, date_from="2019-08-01")
    assert calls["count"] == 2  # date_from이 다르면 캐시 키가 달라 재호출

    _get(fetcher, date_from="2019-07-01")
    assert calls["count"] == 2


def test_same_key_concurrent_miss_fetches_once():
    started = threading.Event()
    release = threading.Event()
    calls = {"count": 0}
    calls_lock = threading.Lock()
    results: list[tuple[dict[str, object], dict[str, object]]] = []
    errors: list[BaseException] = []

    def fetcher():
        with calls_lock:
            calls["count"] += 1
        started.set()
        assert release.wait(timeout=5)
        return {"sales_local": [{"prod_cd": "SKU-1"}]}

    def worker():
        try:
            results.append(_get(fetcher))
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=worker)
    second = threading.Thread(target=worker)

    first.start()
    assert started.wait(timeout=5)
    second.start()
    time.sleep(0.1)
    assert calls["count"] == 1

    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert calls["count"] == 1
    assert len(results) == 2
    assert {info["source"] for _, info in results} == {"cms_api", "memory"}
    assert all(raw == {"sales_local": [{"prod_cd": "SKU-1"}]} for raw, _ in results)


def test_corrupt_disk_cache_falls_back_to_fetch(tmp_path):
    fetcher, calls = _counting_fetcher({"stock_hq": []})
    _get(fetcher)

    cms_fetch_cache._MEMORY_CACHE.clear()
    path = tmp_path / f"{_cache_key()}.json"
    path.write_text("not-json", encoding="utf-8")

    raw, info = _get(fetcher)
    assert calls["count"] == 2
    assert raw == {"stock_hq": []}
    assert info["source"] == "cms_api"
    assert path.is_file()  # 손상 파일은 삭제 후 새로 기록됨
