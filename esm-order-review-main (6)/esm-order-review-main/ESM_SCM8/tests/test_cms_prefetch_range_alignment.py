"""예열 구간이 화면 기본값과 일치해야 한다.

2026-07-30 실측: 예열은 종료일을 오늘로, 화면은 어제로 잡아 캐시 키가 하루
어긋났다. 그래서 25분마다 2~3분씩 22만 행을 받아놓고도 사용자의 기본값 분석은
매번 CMS를 처음부터 다시 받았다.

기대값은 프론트 ``demandRange(12)``에서 손으로 계산해 하드코딩한다. 양쪽 로직을
그대로 옮겨 적으면 같이 틀렸을 때 테스트도 같이 통과해 버린다.
"""

from __future__ import annotations

import pytest

from backend.services.cms_prefetch import _season_default_range

# (as_of, 기대 date_from, 기대 date_to)
# demandRange(12): end = as_of - 1일, start = end - 12개월(말일 클램프)
ALIGNMENT_CASES = [
    ("2026-07-30", "2025-07-29", "2026-07-29"),
    # 달의 첫날 → 어제는 지난달 말일
    ("2026-08-01", "2025-07-31", "2026-07-31"),
    # 연초 → 어제는 작년 말일
    ("2026-01-01", "2024-12-31", "2025-12-31"),
    # 3월 1일 → 어제는 2월 말일(평년 28일)
    ("2026-03-01", "2025-02-28", "2026-02-28"),
    # 윤년 2월 29일이 어제인 경우 → 12개월 전은 말일로 클램프
    ("2028-03-01", "2027-02-28", "2028-02-29"),
]


@pytest.mark.parametrize(("as_of", "expected_from", "expected_to"), ALIGNMENT_CASES)
def test_prefetch_range_matches_screen_default(
    as_of: str,
    expected_from: str,
    expected_to: str,
) -> None:
    assert _season_default_range(as_of) == (expected_from, expected_to)


def test_prefetch_never_ends_on_the_as_of_day() -> None:
    """종료일이 오늘이면 화면 기본값과 어긋나 예열이 헛돈다."""
    for as_of, _expected_from, _expected_to in ALIGNMENT_CASES:
        _date_from, date_to = _season_default_range(as_of)
        assert date_to != as_of, f"예열 종료일이 as_of({as_of})와 같아 캐시 키가 어긋난다"
