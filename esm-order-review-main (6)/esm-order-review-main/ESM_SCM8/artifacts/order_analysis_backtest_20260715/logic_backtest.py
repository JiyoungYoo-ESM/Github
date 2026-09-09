from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).with_name("logic_results.json")
sys.path.insert(0, str(ROOT))

from backend.analysis import build_sku_concentration_df  # noqa: E402


def stock_gap_historical_result() -> dict[str, object]:
    script = r"""
import { computeStockGapItem } from './lib/stock-gap.ts';
const result = computeStockGapItem({
  sku:'HIST-001', productName:'Historical', brand:'TEST', availableQty:1000,
  recent3mSalesQty:900, avgDailySalesQty:null, stockoutDate:null, earliestEtaDate:null,
  etaItems:[], riskScore:0, backendStatus:'', priorityAction:'', riskReason:'',
  preArrivalStockoutRisk:false, etaDelayFlag:false, urgentReplenishmentQty:0,
  urgentAction:'', shortageQty:0, baseDate:'2026-01-01'
}, new Date('2026-01-01'));
console.log(JSON.stringify({
  baseDate: result.baseDate,
  stockoutDate: result.stockoutDate?.toISOString().slice(0,10),
  observedStatus: result.status,
  expectedStatusUsingBaseDate: 'sufficient'
}));
"""
    completed = subprocess.run(
        [
            "node",
            "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON",
            "--experimental-strip-types",
            "--input-type=module",
            "-",
        ],
        input=script,
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT / "frontend",
    )
    return json.loads(completed.stdout)


def sku_window_result() -> dict[str, object]:
    sales = pd.DataFrame(
        {
            "sku": ["SKU-1", "SKU-1"],
            "date": ["2026-04-01", "2025-01-01"],
            "qty": [1, 9],
            "amount_krw": [100, 900],
        }
    )
    stock = pd.DataFrame({"sku": ["SKU-1"], "euAvailableStock": [5], "unitPrice": [2]})
    output = build_sku_concentration_df({"sales_detail": sales, "eu_stock": stock}, 1500)
    row = output.iloc[0]
    return {
        "declared_window": "2026-02-01 through 2026-04-30",
        "expected_in_window_qty": 1.0,
        "expected_in_window_amount_krw": 100.0,
        "observed_qty": float(row["최근 3개월 판매수량"]),
        "observed_amount_krw": float(row["최근 3개월 판매금액(KRW)"]),
        "out_of_window_row_included": float(row["최근 3개월 판매금액(KRW)"]) == 1000.0,
    }


def missing_identity_result() -> dict[str, object]:
    sales = pd.DataFrame({"sku": ["SKU-NAN"], "qty": [1], "amount_krw": [100]})
    stock = pd.DataFrame(
        {
            "sku": ["SKU-NAN"],
            "productName": [float("nan")],
            "brand": [float("nan")],
            "euAvailableStock": [1],
            "unitPrice": [1],
        }
    )
    output = build_sku_concentration_df({"sales_detail": sales, "eu_stock": stock}, 1500)
    row = output.iloc[0]
    return {
        "observed_product_name": str(row["상품명"]),
        "observed_brand": str(row["브랜드"]),
        "nan_rendered_as_identity": str(row["상품명"]).lower() == "nan" or str(row["브랜드"]).lower() == "nan",
    }


def main() -> None:
    result = {
        "stock_gap_historical_base_date": stock_gap_historical_result(),
        "sku_concentration_window": sku_window_result(),
        "sku_concentration_missing_identity": missing_identity_result(),
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
