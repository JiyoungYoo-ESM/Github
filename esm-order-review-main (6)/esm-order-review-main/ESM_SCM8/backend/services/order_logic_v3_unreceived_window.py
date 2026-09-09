"""V3-only 미입고(① open-PO 잔량) 조회창.

V3까지의 기존 동작은 CMS 미입고현황을 ``as_of`` 연도의 1월 1일부터 전부
가져왔다(``cms_date_settings``의 ``logistics_period_start``). 그 창은 운송중
(shipping) 조회와 공유하던 값이라, PO 등록일이 오래된 잔량까지 계속 입고예정으로
누적돼 IP가 과대계상되고 실제로 발주가 필요한 SKU가 제안수량 0으로 판정되는
사례가 확인됐다.

사용자 결정(2026-09-04)에 따라 V3는 **① 미입고 수량만** PO 등록일 기준 최근
30 달력일로 좁힌다. 적용 범위는 그 한 수량뿐이다.

- ② PNFM확정·③ 입고진행중·④ 입고완료는 **이미 입고 통보되었거나 입고가 진행
  중인 확실히 들어올 물량**이므로 PO 등록일이 오래되었다는 이유로 빼지 않는다.
- SKU의 미입고/입고 원천 행 존재 여부(``inbound_status_source_present``),
  상품명·바코드 등 식별 증거, 계산 모집단도 창 적용 전과 같다. 창은 수량 하나만
  바꾸며 상품을 분석에서 사라지게 하지 않는다.
- 음수 미입고(PNFM 수량 > PO 수량)는 창을 좁혀도 **계속 차단**한다. V2가
  ``INCOMING_QTY_NEGATIVE``로 계산을 막는 불량 데이터이며, 0으로 덮으면 그
  fail-closed 검증이 조용히 사라진다(사용자 결정 2026-09-04).

법인별 적용 지점은 원천 API 형태에 따라 다르지만 창의 정의는 하나다.

- HQ/OPO: ``/opo/po/open``이 행마다 ``created_date``(PO 등록일)를 주므로 창을
  벗어난 행의 ``remaining_qty``만 0으로 만든다. ②③④는 별도 엔드포인트
  (``/opo/inbound/confirmed``)라 애초에 영향이 없다.
- PL/USA: ``/eu/open-po``·``/us/open-po``가 상품 단위 집계라 행에 PO 등록일이
  없다. 그래서 같은 피드를 전체 창과 30일 창으로 두 번 조회하고, ① 미입고
  수량·금액만 30일 창 값으로 교체한다.

이 창의 길이(``V3_UNRECEIVED_LOOKBACK_DAYS``)는 PL/USA 스냅샷 캐시 scope에
접혀 들어간다. 캐시 키 자체에는 창 길이가 없어서, 상수만 바꾸면 이전 창으로
받아둔 스냅샷이 그대로 재사용된다. 상수를 바꿀 때 scope도 함께 바뀌도록
``unreceived_cache_scope()``를 쓴다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Mapping, Sequence

# as_of를 포함한 총 달력일 수. 30일 = as_of-29일 ~ as_of.
V3_UNRECEIVED_LOOKBACK_DAYS = 30
V3_UNRECEIVED_WINDOW_BASIS = "PO_REGISTRATION_DATE"
V3_UNRECEIVED_WINDOW_VERSION = "v3-unreceived-po-30d-2026-09-04"

# ① 미입고 계열 필드. 수량과 그 금액 환산만 창을 따른다.
#
# `po_qty`(PO 수량)·`pnfm_qty`(PNFM 수량)는 여기 넣지 않는다. 이 둘은 미입고가
# 아니라 PO 단위 총계이며, 30일 값으로 바꾸면 `po_qty < completed_qty`처럼
# 물리적으로 불가능한 행이 스냅샷에 남는다(실측 PL 198행·USA 116행).
# `open_qty = po_qty - pnfm_qty` 관계도 실제 피드에서 성립하지 않으므로
# (PL 263/920행, USA 204/1252행 불일치) 함께 움직일 근거가 없다.
PL_USA_UNRECEIVED_FIELDS = ("open_qty", "open_amt")
# 창의 적용을 받지 않는 필드. 확실히 들어올 물량과 PO 단위 총계는 전체 창을 쓴다.
# (식별 컬럼 `prod_cd`/`prod_nm`/`bar_code`/`brand_nm`도 전체 창 값을 유지한다.)
PL_USA_PRESERVED_FIELDS = (
    "pnfm_confirmed_qty", "inbound_in_progress_qty", "completed_qty", "trouble_qty",
    "po_qty", "pnfm_qty",
)


def _parsed_as_of(as_of: str | date) -> date:
    if isinstance(as_of, date):
        return as_of
    return datetime.strptime(str(as_of), "%Y-%m-%d").date()


def unreceived_cache_scope() -> str:
    """Cache scope for a PL/USA snapshot, bound to the applied window length.

    ``cms_fetch_cache._cache_key`` hashes only version/entity/as_of/date_from/
    date_to/logistics_date_from/cache_scope — the 미입고 lookback is not part of
    it. Folding the constant into the scope means changing
    ``V3_UNRECEIVED_LOOKBACK_DAYS`` invalidates the affected snapshots instead
    of silently serving a payload built for the previous window.
    """

    return f"v3_inventory_position_unreceived_po_{V3_UNRECEIVED_LOOKBACK_DAYS}d_v3"


def unreceived_po_window(as_of: str | date) -> tuple[date, date]:
    """Return the inclusive PO-registration window for the ① 미입고 quantity."""

    end = _parsed_as_of(as_of)
    start = end - timedelta(days=V3_UNRECEIVED_LOOKBACK_DAYS - 1)
    return start, end


def unreceived_po_window_audit(as_of: str | date) -> dict[str, object]:
    """Return the audit record that makes the applied window reproducible."""

    start, end = unreceived_po_window(as_of)
    return {
        "version": V3_UNRECEIVED_WINDOW_VERSION,
        "basis": V3_UNRECEIVED_WINDOW_BASIS,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "calendar_days": V3_UNRECEIVED_LOOKBACK_DAYS,
        "scope": "UNRECEIVED_OPEN_PO_QUANTITY_ONLY",
        "note": (
            "① 미입고 수량만 PO 등록일 최근 30 달력일로 제한한다. "
            "② PNFM확정·③ 입고진행중·④ 입고완료는 확실히 들어올 물량이므로 전체 창을 "
            "유지하며, 원천 행 존재 여부·식별 증거·계산 모집단도 바꾸지 않는다. "
            "음수 미입고는 PO 등록일과 무관하게 V2 기준으로 계속 차단한다. "
            "운송중·재고·판매·리드타임 조회창과 V2 조회창도 변경하지 않는다."
        ),
    }


def _parsed_registration_date(value: object) -> date | None:
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def zero_stale_hq_unreceived_quantities(
    rows: Sequence[Mapping[str, object]],
    *,
    as_of: str | date,
    date_field: str = "created_date",
    quantity_field: str = "remaining_qty",
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Zero the ① quantity of HQ open-PO rows registered outside the window.

    Rows are kept rather than dropped.  Dropping one would also remove the
    SKU's inbound-source presence, its product-identity evidence, and — for a
    SKU with no sales, stock, or confirmed inbound — the SKU itself from the
    calculation population.  Zeroing changes only the operand this decision is
    about, so a SKU whose IP was inflated by a stale PO reappears with a real
    order need instead of vanishing.

    A row whose registration date cannot be parsed is treated as outside the
    window: PL/USA never receive such a PO from a date-bounded query, and
    inferring a date would keep the very over-count this window removes.  The
    counts are returned so the exclusion is never silent.

    A negative quantity is never zeroed. V2 blocks such a SKU with
    ``INCOMING_QTY_NEGATIVE`` as unhandled bad data, and per the 2026-09-04 user
    decision that guard must survive the window regardless of PO age.
    """

    start, end = unreceived_po_window(as_of)
    kept: list[dict[str, object]] = []
    zeroed_rows = 0
    zeroed_quantity = 0.0
    unparsable_rows = 0
    blocked_negative_rows = 0
    blocked_negative_quantity = 0.0
    for row in rows:
        registered_at = _parsed_registration_date(row.get(date_field))
        if registered_at is not None and start <= registered_at <= end:
            kept.append(dict(row))
            continue
        quantity = _number(row.get(quantity_field))
        if quantity < 0:
            # Keep the negative so V2's fail-closed check still fires.
            blocked_negative_rows += 1
            blocked_negative_quantity += quantity
            kept.append(dict(row))
            continue
        if registered_at is None:
            unparsable_rows += 1
        zeroed_rows += 1
        zeroed_quantity += quantity
        kept.append({**row, quantity_field: 0})
    return kept, {
        **unreceived_po_window_audit(as_of),
        "entity_scope": "HQ",
        "method": "ZERO_STALE_ROW_QUANTITY",
        "date_field": date_field,
        "quantity_field": quantity_field,
        "source_rows": len(rows),
        "rows_in_window": len(rows) - zeroed_rows - blocked_negative_rows,
        "zeroed_rows": zeroed_rows,
        "zeroed_quantity": zeroed_quantity,
        "unparsable_date_rows": unparsable_rows,
        "blocked_negative_rows": blocked_negative_rows,
        "blocked_negative_quantity": blocked_negative_quantity,
    }


def merge_open_po_unreceived_window(
    full_window_rows: Sequence[Mapping[str, object]],
    recent_window_rows: Sequence[Mapping[str, object]],
    *,
    as_of: str | date,
    sku_field: str = "prod_cd",
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Take ① from the 30-day feed and every other value from the full feed.

    ``/eu/open-po``·``/us/open-po`` aggregate ①~④ into one row per product and
    expose no per-PO registration date, so the window can only be applied by
    querying twice.  ② PNFM confirmed and ③ inbound-in-progress quantities are
    goods already on their way; they keep the full window even when the
    originating PO is old.

    CMS has been observed returning one product under two spellings of the same
    code across the two queries (``KOEP05-FP`` / ``KoeP05-FP``).  The approved
    V3 identity policy already treats a case-only code difference as the same
    product, so an exact match is tried first and a case-folded match is used
    only when that folded code is unambiguous on both sides.  An ambiguous fold
    is left unmatched rather than pooling two products onto one row.
    """

    recent_by_sku: dict[str, dict[str, float]] = {}
    recent_spellings: dict[str, set[str]] = {}
    for row in recent_window_rows:
        sku = str(row.get(sku_field) or "").strip()
        if not sku:
            continue
        totals = recent_by_sku.setdefault(
            sku, {field: 0.0 for field in PL_USA_UNRECEIVED_FIELDS}
        )
        for field in PL_USA_UNRECEIVED_FIELDS:
            totals[field] += _number(row.get(field))
        recent_spellings.setdefault(sku.lower(), set()).add(sku)

    full_spellings: dict[str, set[str]] = {}
    for row in full_window_rows:
        sku = str(row.get(sku_field) or "").strip()
        if sku:
            full_spellings.setdefault(sku.lower(), set()).add(sku)

    # A recent total may be applied to at most one merged row, so consumption
    # is tracked by the recent code itself. Do NOT also gate on the full row's
    # folded code: an ambiguous fold claims nothing, and gating on it would
    # block a later exact match and then re-append the recent row, double
    # counting its ② and ③.
    matched_recent_codes: set[str] = set()

    def recent_totals(sku: str) -> tuple[dict[str, float] | None, str, bool]:
        """Resolve one full-window code to an unconsumed recent total."""
        exact = recent_by_sku.get(sku)
        if exact is not None and sku not in matched_recent_codes:
            return exact, sku, False
        folded = sku.lower()
        candidates = recent_spellings.get(folded) or set()
        if len(candidates) != 1 or len(full_spellings.get(folded) or set()) != 1:
            return None, "", False
        source = next(iter(candidates))
        if source in matched_recent_codes:
            return None, "", False
        return recent_by_sku.get(source), source, True

    merged: list[dict[str, object]] = []
    changed_rows = 0
    case_only_matches = 0
    blocked_negative_rows = 0
    blocked_negative_quantity = 0.0
    for row in full_window_rows:
        sku = str(row.get(sku_field) or "").strip()
        totals: dict[str, float] | None = None
        if sku:
            totals, source_code, by_case = recent_totals(sku)
            if totals is not None:
                matched_recent_codes.add(source_code)
                if by_case:
                    case_only_matches += 1
        replacement = {
            field: (totals or {}).get(field, 0.0)
            for field in PL_USA_UNRECEIVED_FIELDS
        }
        # CMS can return a negative 미입고 (PNFM 수량 > PO 수량). V2 treats that as
        # unhandled bad data and blocks the SKU with INCOMING_QTY_NEGATIVE.
        # Narrowing the window must not clear that fail-closed guard: user
        # decision 2026-09-04 is that a negative ① keeps blocking regardless of
        # PO age. Pass the source ① figures through so V2 still sees the
        # negative. The SKU is blocked, so this value never enters a
        # calculation — it only preserves the diagnostic.
        source_open_qty = _number(row.get("open_qty"))
        if source_open_qty < 0:
            replacement = {field: row.get(field) for field in PL_USA_UNRECEIVED_FIELDS}
            blocked_negative_rows += 1
            blocked_negative_quantity += source_open_qty
        if any(
            _number(row.get(field)) != _number(replacement[field])
            for field in PL_USA_UNRECEIVED_FIELDS
        ):
            changed_rows += 1
        merged.append({**row, **replacement})

    # A recent row that no full-window row claimed means the two queries saw
    # different data, or its code fold was ambiguous. Keep its ① quantity
    # instead of discarding it.
    full_folded_codes = set(full_spellings)
    unmatched: list[dict[str, object]] = []
    rescued_preserved_zeroed = 0
    for row in recent_window_rows:
        code = str(row.get(sku_field) or "").strip()
        if code in matched_recent_codes:
            continue
        rescue = dict(row)
        if code.lower() in full_folded_codes:
            # This product IS in the full feed, so its ②③④ are already carried
            # by the full-window row(s) above. Keep only the ① figures here.
            for field in PL_USA_PRESERVED_FIELDS:
                if field in rescue:
                    rescue[field] = 0
            rescued_preserved_zeroed += 1
        unmatched.append(rescue)
    merged.extend(unmatched)
    return merged, {
        **unreceived_po_window_audit(as_of),
        "method": "REPLACE_UNRECEIVED_FIELDS_FROM_RECENT_QUERY",
        "unreceived_fields": list(PL_USA_UNRECEIVED_FIELDS),
        "preserved_fields": list(PL_USA_PRESERVED_FIELDS),
        "full_window_rows": len(full_window_rows),
        "recent_window_rows": len(recent_window_rows),
        "merged_rows": len(merged),
        "changed_rows": changed_rows,
        "case_only_code_matches": case_only_matches,
        "recent_only_rows": len(unmatched),
        "rescued_rows_with_preserved_fields_zeroed": rescued_preserved_zeroed,
        "blocked_negative_rows": blocked_negative_rows,
        "blocked_negative_quantity": blocked_negative_quantity,
    }


__all__ = [
    "PL_USA_PRESERVED_FIELDS",
    "PL_USA_UNRECEIVED_FIELDS",
    "unreceived_cache_scope",
    "V3_UNRECEIVED_LOOKBACK_DAYS",
    "V3_UNRECEIVED_WINDOW_BASIS",
    "V3_UNRECEIVED_WINDOW_VERSION",
    "merge_open_po_unreceived_window",
    "unreceived_po_window",
    "unreceived_po_window_audit",
    "zero_stale_hq_unreceived_quantities",
]
