"""Persistence for the most recent order-review result per client, plus a
fallback that reconstructs rows from the latest generated output workbook."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backend.config import LATEST_ORDER_REVIEW_DIR, OUTPUT_DIR
from backend.services import persistent_state


def _safe_client_id(client_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", client_id)[:80] or "default"


def latest_order_review_path(client_id: str) -> Path:
    return LATEST_ORDER_REVIEW_DIR / f"{_safe_client_id(client_id)}.json"


def latest_order_review_workbook_path(client_id: str) -> Path:
    return LATEST_ORDER_REVIEW_DIR / f"{_safe_client_id(client_id)}.xlsx"


def latest_order_review_entry() -> tuple[str, dict[str, object]] | None:
    """Return the newest saved order-review payload across all local clients."""
    if persistent_state.enabled():
        entry = persistent_state.newest_snapshot("order_review")
        if entry is None:
            return None
        snapshot_key, payload = entry
        return snapshot_key.removeprefix("order_review:"), payload
    candidates: list[tuple[datetime, float, str, dict[str, object]]] = []
    for path in LATEST_ORDER_REVIEW_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            continue
        saved_at_raw = str(payload.get("saved_at") or "")
        try:
            saved_at = datetime.fromisoformat(saved_at_raw)
            if saved_at.tzinfo is None:
                saved_at = saved_at.replace(tzinfo=timezone.utc)
        except ValueError:
            saved_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        candidates.append((saved_at, path.stat().st_mtime, path.stem, payload))
    if not candidates:
        return None
    _, _, client_id, payload = max(candidates, key=lambda item: (item[0], item[1]))
    return client_id, payload


def load_latest_order_review_result(client_id: str) -> dict[str, object] | None:
    """Load only the requesting account/entity/browser scope."""
    if persistent_state.enabled():
        return persistent_state.load_snapshot(f"order_review:{_safe_client_id(client_id)}")

    path = latest_order_review_path(client_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def save_latest_order_review_workbook(client_id: str, source_path: Path) -> Path | None:
    """Keep the latest full multi-sheet ESM workbook beyond transient job cleanup."""
    source = Path(source_path)
    if not source.is_file():
        return None
    LATEST_ORDER_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    target = latest_order_review_workbook_path(client_id)
    temporary = target.with_suffix(".xlsx.tmp")
    shutil.copy2(source, temporary)
    temporary.replace(target)
    return target


def order_review_rows_from_result(result: dict[str, object]) -> list[dict[str, object]]:
    tables = result.get("tables")
    if not isinstance(tables, dict):
        return []
    rows = tables.get("stock_gap_order_review") or tables.get("order_review") or []
    return rows if isinstance(rows, list) else []


def order_review_eta_rows_from_result(result: dict[str, object]) -> list[dict[str, object]]:
    """도착 캘린더(운송수단·B/L 단위 입고 예정) 행.

    발주검토 행에는 SKU별 '최초 ETA' 한 건만 남아서, 이 표가 없으면 세션을 복구한 재고공백
    화면이 ETA 상세 목록과 타임라인의 입고 지점을 그리지 못한다.
    """
    tables = result.get("tables")
    if not isinstance(tables, dict):
        return []
    rows = tables.get("stock_gap_eta") or []
    return rows if isinstance(rows, list) else []


def save_latest_order_review_result(client_id: str, job_id: str, result: dict[str, object], source: str) -> None:
    rows = order_review_rows_from_result(result)
    eta_rows = order_review_eta_rows_from_result(result)
    payload = {
        "job_id": job_id,
        "source": source,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "rows": rows,
        "eta_row_count": len(eta_rows),
        "eta_rows": eta_rows,
    }
    if persistent_state.enabled():
        persistent_state.save_snapshot(
            f"order_review:{_safe_client_id(client_id)}", "order_review", payload
        )
        return
    try:
        LATEST_ORDER_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        latest_order_review_path(client_id).write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception:
        return


def latest_order_review_from_output_excel() -> dict[str, object] | None:
    candidates = sorted(
        OUTPUT_DIR.glob("*/ESM_order_review_*.xlsx"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for output_path in candidates:
        try:
            workbook = pd.ExcelFile(output_path)
            sheet_name = next((name for name in workbook.sheet_names if "보고서원본" in name), None)
            if sheet_name is None:
                continue
            df = pd.read_excel(output_path, sheet_name=sheet_name)
            if df.empty:
                continue
            rows: list[dict[str, object]] = []
            for record in df.where(pd.notna(df), None).to_dict(orient="records"):
                code = record.get("코드")
                if not code:
                    continue
                order_qty = record.get("발주 필요수량") or 0
                order_amount_krw = record.get("=발주 금액(KRW)") or 0
                rows.append(
                    {
                        "sku": code,
                        "productName": record.get("SKU") or "-",
                        "brand": record.get("브랜드") or "-",
                        "euAvailableStock": record.get("현지 창고재고") or record.get("EU 창고재고") or 0,
                        "inboundQty": record.get("미입고현황") or 0,
                        "requiredOrderQty": order_qty,
                        "requiredOrderAmount": order_amount_krw,
                        "priorityAction": "발주필요"
                        if float(order_qty or 0) > 0 or float(order_amount_krw or 0) > 0
                        else "발주불필요",
                        "상품코드": code,
                        "상품명": record.get("SKU") or "-",
                        "브랜드": record.get("브랜드") or "-",
                        "EU 현지 재고": record.get("현지 창고재고") or record.get("EU 창고재고") or 0,
                        "미입고수량": record.get("미입고현황") or 0,
                        "발주필요수량": order_qty,
                        "발주필요금액(KRW)": order_amount_krw,
                        "우선 액션": "발주필요" if float(order_qty or 0) > 0 or float(order_amount_krw or 0) > 0 else "발주불필요",
                    }
                )
            job_id = output_path.stem.replace("ESM_order_review_", "")
            return {
                "job_id": job_id,
                "source": "latest_output_excel",
                "saved_at": datetime.fromtimestamp(output_path.stat().st_mtime, timezone.utc).isoformat(),
                "row_count": len(rows),
                "rows": rows,
            }
        except Exception:
            continue
    return None
