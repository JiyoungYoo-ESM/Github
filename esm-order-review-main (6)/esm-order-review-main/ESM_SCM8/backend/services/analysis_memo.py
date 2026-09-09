"""In-memory memoization of computed CMS analysis results.

cms_fetch_cache가 원본 CMS 응답(네트워크)을 캐시하는 것과 별개로, 이 모듈은
매핑·분류·핵심 분석(실측 7~10초 CPU)의 *결과*를 메모이즈한다. 동일한 원본
데이터(created_at으로 식별)와 동일한 분석 옵션이면 재계산 없이 이전 결과를
재사용하고, 원본이 갱신(재fetch)되면 created_at이 바뀌어 자동 무효화된다.

Excel 산출물은 최초 계산 잡의 output_dir에 이미 존재하므로, 메모 히트 시에는
그 잡의 download_url을 그대로 재사용한다(보존 기간 STORAGE_MAX_AGE_HOURS 동일).
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from typing import Any

# 결과 객체가 크므로(수 MB) 소수만 유지한다.
_MEMO_LIMIT = 2

_memo_lock = threading.Lock()
_memo: OrderedDict[str, dict[str, Any]] = OrderedDict()


def analysis_memo_key(
    *,
    security_scope: str,
    as_of: str | None,
    date_from: str | None,
    raw_created_at: str | None,
    eur_krw_rate: float | None,
    settings: dict[str, Any] | None,
) -> str | None:
    """메모 키. 원본 데이터 버전(raw_created_at)이 없으면 메모이즈하지 않는다."""
    if not raw_created_at:
        return None
    payload = json.dumps(
        {
            "version": 2,
            "security_scope": security_scope,
            "as_of": as_of,
            "date_from": date_from,
            "raw_created_at": raw_created_at,
            "eur_krw_rate": eur_krw_rate,
            "settings": settings or {},
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def get_memoized_analysis(key: str | None) -> dict[str, Any] | None:
    """메모 히트 시 엔트리를 반환한다. 반환 객체(특히 result)는 읽기 전용으로 다뤄야 한다."""
    if not key:
        return None
    with _memo_lock:
        entry = _memo.get(key)
        if entry is not None:
            _memo.move_to_end(key)
        return entry


def store_memoized_analysis(
    key: str | None,
    *,
    result: dict[str, Any],
    download_url: str,
    output_filename: str,
    origin_job_id: str,
) -> None:
    if not key:
        return
    entry = {
        "result": result,
        "download_url": download_url,
        "output_filename": output_filename,
        "origin_job_id": origin_job_id,
    }
    with _memo_lock:
        _memo[key] = entry
        _memo.move_to_end(key)
        while len(_memo) > _MEMO_LIMIT:
            _memo.popitem(last=False)


def clear_analysis_memo() -> None:
    with _memo_lock:
        _memo.clear()
