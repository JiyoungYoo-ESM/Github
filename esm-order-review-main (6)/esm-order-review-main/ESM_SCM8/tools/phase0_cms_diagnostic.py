#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 0 CMS 진단 — 신규 발주 로직 착수 전 '데이터 가용성' 실측 (읽기 전용).

이 스크립트는 CMS API에 GET(조회)만 합니다. 아무것도 저장/수정/삭제하지 않습니다.

무엇을 확인하나 (기술명세서 Phase 0):
  A/C. /eu/sales/local 이 정말 12~24개월 판매를 주는가 + 월마다 끊김 없이 있는가
  B.   24개월 전량 조회가 얼마나 느린가 (풀타임 추정 — 실제 전량은 안 받음)
  D.   /eu/products 에 유통기한 / MOQ / 통합코드(sku_alias) 후보가 숨어있는가
  E.   /eu/shipping/containers 의 remark 로 운송모드가 몇 % 파싱되나 + 실제 ETA/도착일 필드가 있는가
  F.   /eu/stock/local, /eu/open-po 가 실제로 어떤 필드를 주는가

실행 방법 (PowerShell, ESM_SCM8 폴더 안에서):
  $env:CMS_API_KEY="<발급받은 키>"; py -3.14 tools/phase0_cms_diagnostic.py
옵션:
  --as-of 2026-07-06   기준일 (기본: 오늘)
  --months 24          거슬러 올라가 확인할 개월 수 (기본 24)
  --report report.md   결과를 파일로도 저장 (기본: 화면 출력만)

핵심: 24개월치를 통째로 내려받지 않는다. 판매 API 응답에 들어있는 total(전체 건수)만
여러 date_from 시점으로 가볍게 찔러, 그 차이로 '월별 건수'를 역산한다 (데이터 미다운로드).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import date, datetime

# Windows 콘솔에서 한글 출력이 깨지지 않도록.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# backend/ 와 core/ 를 임포트할 수 있도록 ESM_SCM8 를 경로에 넣는다.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import backend.cms_client as cc
    from backend.cms_client import _get_json, cms_base_url, CmsAuthenticationError
except Exception as exc:  # pragma: no cover
    print(f"[에러] backend.cms_client 임포트 실패: {exc}")
    print("      → ESM_SCM8 폴더 안에서 'py -3.14 tools/phase0_cms_diagnostic.py' 로 실행하세요.")
    sys.exit(2)

# CMS 내부 perf 로그(줄마다 [perf][cms_api] ...)를 꺼서 출력이 깔끔하도록.
cc._perf_log = lambda *a, **k: None

MODE_RE = re.compile(r"(해운|헤운|헤은|항공|철송|트럭)")
SHELF_HINTS = ("expire", "expiry", "expir", "shelf", "valid_", "validity", "fr_", "frdate", "fresh",
               "유통", "사용기한", "제조", "소비기한", "limit_dt", "best_before")
MOQ_HINTS = ("moq", "min_order", "min_qty", "minimum", "최소", "발주단위", "order_unit")
OUTBOX_HINTS = ("outbox", "out_box", "case", "casepack", "box_qty", "inbox", "입수", "박스입수", "carton")
ALIAS_HINTS = ("parent", "canonical", "rep_", "represent", "대표", "통합", "alias", "old_cd", "new_cd",
               "prev_", "merge", "master_cd", "std_cd")
ETA_HINTS = ("eta", "arriv", "arrival", "warehouse_in", "whin", "입고", "도착", "expected_in", "receipt")

_REPORT_LINES: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    _REPORT_LINES.append(msg)


def month_start(as_of: date, months_back: int) -> date:
    """as_of 기준 months_back 개월 전의 '그 달 1일'."""
    y, m = as_of.year, as_of.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _scan_keys(keys, hints) -> list[str]:
    low = {k: k.lower() for k in keys}
    return [k for k, lk in low.items() if any(h in lk for h in hints)]


def _sales_total(date_from: date) -> tuple[int, float, dict | None]:
    """해당 date_from 이후 판매 건수(total)만 싸게 조회. (total, 소요초, 표본row)."""
    t0 = time.perf_counter()
    payload = _get_json("/eu/sales/local", {"date_from": date_from.isoformat(), "page": 1, "page_size": 1})
    elapsed = time.perf_counter() - t0
    total = int(payload.get("total") or 0) if isinstance(payload, dict) else 0
    items = payload.get("items") if isinstance(payload, dict) else None
    sample = items[0] if items else None
    return total, elapsed, sample


def probe_sales_depth(as_of: date, months: int) -> dict:
    log("\n" + "=" * 78)
    log("A/C. 판매 이력 깊이 & 월별 연속성  (/eu/sales/local)")
    log("=" * 78)
    log("  방법: date_from 을 한 달씩 뒤로 밀며 total(전체 건수)만 조회 → 차이로 월별 건수 역산.")
    log("        (실제 데이터는 안 내려받음)\n")

    boundaries = [month_start(as_of, k) for k in range(0, months + 2)]
    totals: dict[date, int] = {}
    latencies: list[float] = []
    sample_row: dict | None = None
    for b in boundaries:
        try:
            total, elapsed, sample = _sales_total(b)
        except CmsAuthenticationError:
            raise
        except Exception as exc:
            log(f"  [경고] date_from={b} 조회 실패: {exc}")
            total, elapsed = -1, 0.0
            sample = None
        totals[b] = total
        latencies.append(elapsed)
        if sample_row is None and sample:
            sample_row = sample

    # 월별 건수 = total(그 달 1일) - total(다음 달 1일)
    log("  월(ship_dt 기준)   |   해당 월 판매건수   | 막대")
    log("  " + "-" * 60)
    monthly: list[tuple[str, int]] = []
    max_cnt = 1
    for k in range(0, months + 1):
        older, newer = boundaries[k + 1], boundaries[k]
        if totals.get(older, -1) < 0 or totals.get(newer, -1) < 0:
            continue
        cnt = totals[older] - totals[newer]
        max_cnt = max(max_cnt, cnt)
        monthly.append((older.strftime("%Y-%m"), cnt))
    for label, cnt in monthly:
        bar = "#" * int(round(40 * cnt / max_cnt)) if cnt > 0 else ""
        flag = "" if cnt > 0 else "   ← 데이터 없음"
        log(f"  {label}          | {cnt:>12,} | {bar}{flag}")

    full = totals.get(boundaries[months], 0)
    recent3 = totals.get(boundaries[3], 0)
    nonzero = [lbl for lbl, c in monthly if c > 0]
    oldest = nonzero[-1] if nonzero else "없음"
    months_with_data = len(nonzero)
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    log("")
    log(f"  · {months}개월 전부터의 총 판매건수: {full:,} 건")
    log(f"  · 최근 3개월 총 판매건수:          {recent3:,} 건")
    log(f"  · 데이터가 있는 월 수:            {months_with_data} / {months} 개월")
    log(f"  · 가장 오래된 데이터가 있는 월:    {oldest}")
    log(f"  · total 조회 1건당 평균 응답시간:  {avg_latency:.2f} 초")

    # 판정
    if full <= 0:
        verdict = ("FAIL", "판매 데이터를 못 받음 (권한/네트워크 확인 필요)")
    elif full <= recent3 * 1.2:
        verdict = ("FAIL", "date_from 을 늘려도 건수가 안 늘어남 → 서버가 과거를 안 주는 것으로 보임 (Holt/σ 불가)")
    elif months_with_data >= 18:
        verdict = ("PASS", f"과거 {months_with_data}개월치 판매를 제공함 → Holt/σ 계산용 이력 확보 가능")
    else:
        verdict = ("WARN", f"과거 {months_with_data}개월치만 있음 → 24개월 미만, 계절학습은 뒤로 미뤄야")

    log(f"\n  판정 [{verdict[0]}] {verdict[1]}")
    return {"boundaries": boundaries, "totals": totals, "full": full, "pages": None,
            "verdict": verdict, "sample_row": sample_row, "months": months}


def probe_pull_speed(depth: dict) -> None:
    log("\n" + "=" * 78)
    log("B. 24개월 전량 조회가 얼마나 느린가  (풀타임 추정)")
    log("=" * 78)
    full = depth.get("full", 0)
    if full <= 0:
        log("  (판매 데이터가 없어 추정 생략)")
        return
    page_size = 1000
    pages = (full + page_size - 1) // page_size
    date_from = depth["boundaries"][depth["months"]]
    log(f"  · 24개월 전량 = {full:,} 건 ≒ {pages:,} 페이지 (페이지당 {page_size:,}건)")
    log(f"  · 실제 페이지 3개만 시간을 재서 전체를 추정합니다 (전량은 안 받음)...")
    per_page: list[float] = []
    for pg in (1, 2, 3):
        try:
            t0 = time.perf_counter()
            _get_json("/eu/sales/local", {"date_from": date_from.isoformat(), "page": pg, "page_size": page_size})
            per_page.append(time.perf_counter() - t0)
        except Exception as exc:
            log(f"    [경고] {pg}페이지 조회 실패: {exc}")
    if not per_page:
        log("  (페이지 조회 실패로 추정 불가)")
        return
    avg = sum(per_page) / len(per_page)
    seq = avg * pages
    par = seq / 6  # 코드가 6페이지 병렬 호출 → 대략 1/6 (단, 무리하면 502 위험)
    log(f"  · 페이지 1개 평균: {avg:.2f} 초")
    log(f"  · 순차로 전량: 약 {seq/60:.1f} 분")
    log(f"  · 6개 병렬(현재 코드 방식): 약 {par/60:.1f} 분 (서버 과부하 시 502로 더 걸릴 수 있음)")
    if par > 120:
        log("\n  판정 [WARN] 한 번에 받기엔 무거움 → '처음 한 번만 받아 저장, 이후 월 1회만 갱신' 방식 필수")
    else:
        log("\n  판정 [PASS] 한 번 받는 시간이 감당 가능한 수준")


def probe_products() -> None:
    log("\n" + "=" * 78)
    log("D. /eu/products 에 유통기한 / MOQ / 통합코드(alias) 후보가 있는가")
    log("=" * 78)
    try:
        payload = _get_json("/eu/products", {"page": 1, "page_size": 50})
    except Exception as exc:
        log(f"  [경고] /eu/products 조회 실패: {exc}  (엔드포인트가 없거나 권한 문제일 수 있음)")
        return
    items = payload.get("items") if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
    total = payload.get("total") if isinstance(payload, dict) else (len(items) if items else 0)
    if not items:
        log("  (상품 데이터가 비어 있음)")
        return
    keys = list(items[0].keys())
    log(f"  · 상품 건수: {total:,}")
    log(f"  · 실제 제공되는 필드 전체 ({len(keys)}개):")
    log("      " + ", ".join(keys))
    row = items[0]
    log("  · 첫 행 샘플 값:")
    for k in keys:
        v = str(row.get(k))
        log(f"      {k:<22} = {v[:50]}")

    def report(name, hits):
        if hits:
            log(f"  · [발견] {name} 후보 필드: {', '.join(hits)}")
        else:
            log(f"  · [없음] {name} 관련 필드 없음")
    log("")
    report("유통기한/FR date", _scan_keys(keys, SHELF_HINTS))
    report("MOQ(최소주문수량)", _scan_keys(keys, MOQ_HINTS))
    report("아웃박스/입수량", _scan_keys(keys, OUTBOX_HINTS))
    report("통합코드(sku_alias)", _scan_keys(keys, ALIAS_HINTS))
    log("\n  판정 [정보] 위 '발견/없음'으로 유통기한·MOQ·alias 를 API로 얻을지, 별도 마스터로 관리할지 결정")


def probe_shipping() -> None:
    log("\n" + "=" * 78)
    log("E. 운송모드 파싱률 & 실제 ETA/도착일 존재 여부  (/eu/shipping/containers)")
    log("=" * 78)
    try:
        rows = _get_json("/eu/shipping/containers", None)  # 리스트 응답, 기본 최근 3개월
    except Exception as exc:
        log(f"  [경고] shipping 조회 실패: {exc}")
        return
    if not isinstance(rows, list) or not rows:
        log("  (운송 데이터가 비어 있음)")
        return
    keys = list(rows[0].keys())
    log(f"  · 운송건수(최근 3개월): {len(rows):,}")
    log(f"  · 실제 제공 필드 ({len(keys)}개): " + ", ".join(keys))
    eta_fields = _scan_keys(keys, ETA_HINTS)
    if eta_fields:
        log(f"  · [발견] ETA/도착 관련 필드: {', '.join(eta_fields)}  (값이 실제로 채워지는지 아래 확인)")
        for f in eta_fields:
            filled = sum(1 for r in rows if str(r.get(f) or "").strip())
            log(f"      {f}: {filled:,}/{len(rows):,} 건에 값 있음")
    else:
        log("  · [없음] ETA/도착일 필드 없음 → ETA는 출고일+리드타임으로 '계산'해야 함 (계획값, 실제 도착 아님)")

    recognized = blank = 0
    unrec_samples: list[str] = []
    for r in rows:
        remark = str(r.get("remark") or r.get("Invoice 비고") or "").strip()
        if not remark:
            blank += 1
            continue
        if MODE_RE.search(remark):
            recognized += 1
        elif len(unrec_samples) < 8:
            unrec_samples.append(remark[:50])
    total = len(rows)
    rate = 100 * recognized / total if total else 0
    log("")
    log(f"  · remark 로 운송모드(해운/항공/철송/트럭) 인식: {recognized:,}/{total:,} ({rate:.1f}%)")
    log(f"  · remark 가 비어있는 건: {blank:,}")
    if unrec_samples:
        log("  · 인식 실패한 remark 예시 (이런 건 모드 계산에서 빠짐):")
        for s in unrec_samples:
            log(f"      - {s}")
    if rate >= 95:
        log("\n  판정 [PASS] 모드 파싱률 충분")
    elif rate >= 80:
        log("\n  판정 [WARN] 일부 누락 → 정규식/별칭 보강 또는 CMS에 모드 컬럼 요청 검토")
    else:
        log("\n  판정 [FAIL] 파싱률 낮음 → 모드별 계산 신뢰 어려움, 구조화 필드 필요")


def probe_stock_and_po(as_of: date) -> None:
    log("\n" + "=" * 78)
    log("F. 재고 / 미입고 실제 필드 확인  (/eu/stock/local, /eu/open-po)")
    log("=" * 78)
    # stock/local
    try:
        stock = _get_json("/eu/stock/local", {"as_of": as_of.isoformat()})
        if isinstance(stock, list) and stock:
            keys = list(stock[0].keys())
            has_3m = "sales_qty_3m" in keys
            null3m = sum(1 for r in stock if r.get("sales_qty_3m") in (None, "")) if has_3m else None
            log(f"  · stock/local 상품수: {len(stock):,}")
            log(f"    필드: " + ", ".join(keys))
            log(f"    최근3개월 판매수량(sales_qty_3m) 있음: {has_3m}"
                + (f"  (값 없는 상품 {null3m:,}개)" if null3m is not None else ""))
            log("    → 이 sales_qty_3m 은 90일 합계 '한 숫자'일 뿐, 월별 이력이 아님(그래서 별도 월별 적재 필요)")
        else:
            log("  · stock/local 비어 있음")
    except Exception as exc:
        log(f"  [경고] stock/local 조회 실패: {exc}")
    # open-po
    try:
        openpo = _get_json("/eu/open-po", {"date_from": month_start(as_of, 3).isoformat()})
        if isinstance(openpo, list) and openpo:
            keys = list(openpo[0].keys())
            date_fields = _scan_keys(keys, ("date", "dt", "order", "eta", "in_", "입고", "발주일", "expected"))
            log(f"  · open-po 건수: {len(openpo):,}")
            log(f"    필드: " + ", ".join(keys))
            if date_fields:
                log(f"    [발견] 날짜성 필드: {', '.join(date_fields)}")
            else:
                log("    [없음] 발주일/입고예정일/입고일 없음 → 브랜드 PO(Q2) 시간전개는 이 데이터만으론 불가")
        else:
            log("  · open-po 비어 있음")
    except Exception as exc:
        log(f"  [경고] open-po 조회 실패: {exc}")


def print_sales_row_shape(depth: dict) -> None:
    sample = depth.get("sample_row")
    if not sample:
        return
    log("\n  · 판매(sales/local) 한 줄의 실제 필드: " + ", ".join(sample.keys()))
    log("    (출고일 ship_dt, 거래유형 biz_type, 법인 site 가 있으면 월별·거래유형별 집계 가능)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 0 CMS 데이터 가용성 진단 (읽기 전용)")
    ap.add_argument("--as-of", default=date.today().isoformat(), help="기준일 YYYY-MM-DD (기본: 오늘)")
    ap.add_argument("--months", type=int, default=24, help="거슬러 확인할 개월 수 (기본 24)")
    ap.add_argument("--report", default=None, help="결과를 저장할 파일 경로 (선택)")
    args = ap.parse_args()

    try:
        as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    except ValueError:
        print("[에러] --as-of 는 YYYY-MM-DD 형식이어야 합니다.")
        return 2

    log("#" * 78)
    log("# Phase 0 진단 — CMS 데이터 가용성 실측 (읽기 전용: 조회만, 저장/수정 없음)")
    log("#" * 78)
    log(f"  기준일(as_of): {as_of}   |   확인 범위: 최근 {args.months}개월")
    log(f"  CMS base URL : {cms_base_url()}")
    log(f"  CMS_API_KEY  : {'설정됨' if os.environ.get('CMS_API_KEY', '').strip() else '없음 (401/403 나면 이 키부터 설정)'}")

    try:
        depth = probe_sales_depth(as_of, args.months)
        print_sales_row_shape(depth)
        probe_pull_speed(depth)
    except CmsAuthenticationError as exc:
        log(f"\n[중단] CMS 인증 실패: {exc}")
        log("       PowerShell 에서 다음처럼 키를 설정하고 다시 실행하세요:")
        log('       $env:CMS_API_KEY="<발급받은 키>"; py -3.14 tools/phase0_cms_diagnostic.py')
        return 1

    probe_products()
    probe_shipping()
    probe_stock_and_po(as_of)

    log("\n" + "#" * 78)
    log("# 진단 끝. 위 각 항목의 판정([PASS]/[WARN]/[FAIL]/[발견]/[없음])을 보고")
    log("#   1) 24개월 판매가 실제로 오는지  2) 얼마나 느린지  3) 유통기한/MOQ/alias 유무")
    log("#   4) 모드 파싱률  5) ETA/도착일 실존 여부 를 사실로 확정한 뒤 표(스키마) 설계로 넘어갑니다.")
    log("#" * 78)

    if args.report:
        try:
            with open(args.report, "w", encoding="utf-8") as f:
                f.write("\n".join(_REPORT_LINES))
            print(f"\n[저장됨] 결과를 파일로 저장했습니다: {args.report}")
        except Exception as exc:
            print(f"\n[경고] 리포트 저장 실패: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
