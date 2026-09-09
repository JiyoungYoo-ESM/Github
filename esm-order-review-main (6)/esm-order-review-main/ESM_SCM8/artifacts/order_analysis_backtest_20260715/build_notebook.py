from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


OUTPUT = Path(__file__).with_name("order_analysis_data_integrity_backtest.ipynb")


notebook = nbf.v4.new_notebook()
notebook["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.11"},
}
notebook["cells"] = [
    nbf.v4.new_markdown_cell(
        """## tl;dr

- **Overall assessment: Needs revision.** The order-review export reconciles cleanly, but the stock-gap shortage definition and SKU-concentration window are not stable enough for decision use.
- **Order review passed its arithmetic backtest:** 2,571 rows, no duplicate product keys, and exact agreement between hidden calculations, displayed values, and summary totals.
- **Stock-gap shortage is not reproducible from the screen definition for 30 of 75 gap rows.** Those rows show 319,995 units versus 149,065 units from displayed gap days × displayed sales speed, a +170,930 unit difference.
- **Historical backtests are not deterministic** because one no-ETA status branch references the execution date instead of the analysis base date.
- **SKU concentration includes out-of-window sales rows** and can render missing identity values as the literal text `nan`.
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Context & Methods

This diagnostic notebook validates the full order-analysis area: order review, stock gap, SKU concentration, shared summaries, and Excel exports. It uses aggregate-only evidence from the latest available local exports and synthetic boundary cases; no product-level identifiers are displayed.

### Key Assumptions

- The latest matching local export is representative of the current screen implementation.
- `발주필요수량`, `권장 발주 금액`, scenario stock, and MOI must reconcile to the hidden calculation sheet.
- The stock-gap help text defines shortage as `gap days × daily sales speed`; one-decimal display rounding is allowed in the tolerance band.
- Historical status decisions should be a pure function of the supplied analysis base date.
"""
    ),
    nbf.v4.new_markdown_cell("## Data"),
    nbf.v4.new_code_cell(
        """import json
from pathlib import Path
import pandas as pd

HERE = Path.cwd()
export_results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
logic_results = json.loads((HERE / "logic_results.json").read_text(encoding="utf-8"))
export_results["as_of"]
"""
    ),
    nbf.v4.new_markdown_cell("## Results"),
    nbf.v4.new_code_cell(
        """order = export_results["order_export"]
stock = export_results["stock_gap_export"]

summary = pd.DataFrame([
    {"area": "Order review", "population": order["row_count"], "check": "Scenario formulas / summaries", "result": "PASS" if all([order["scenario_stock_failures"] == 0, order["scenario_qty_failures"] == 0, order["scenario_amount_failures"] == 0, order["moi_failures"] == 0, order["summary_qty_matches"], order["summary_amount_matches"]]) else "FAIL"},
    {"area": "Stock gap", "population": stock["row_count"], "check": "Summary cards", "result": "PASS" if all(stock["summary_matches"].values()) else "FAIL"},
    {"area": "Stock gap", "population": stock["computed_risk"], "check": "Shortage formula reproducibility", "result": f'FAIL ({stock["shortage_reconciliation_exceptions"]} rows)'},
    {"area": "SKU concentration", "population": 2, "check": "Three-month date window boundary", "result": "FAIL" if logic_results["sku_concentration_window"]["out_of_window_row_included"] else "PASS"},
])
summary
"""
    ),
    nbf.v4.new_code_cell(
        """pd.DataFrame([
    {"metric": "Order rows", "observed": order["row_count"], "expected": order["target_count"], "status": order["target_count_matches"]},
    {"metric": "Before-scenario order qty", "observed": order["before_qty_sum"], "expected": order["summary_qty"], "status": order["summary_qty_matches"]},
    {"metric": "Before-scenario order amount (KRW)", "observed": order["before_amount_sum_krw"], "expected": order["summary_amount_krw"], "status": order["summary_amount_matches"]},
    {"metric": "Duplicate product-code rows", "observed": order["duplicate_product_code_rows"], "expected": 0, "status": order["duplicate_product_code_rows"] == 0},
    {"metric": "Formula/cache mismatches", "observed": order["visible_cache_failures"] + order["formula_pattern_failures"], "expected": 0, "status": order["visible_cache_failures"] + order["formula_pattern_failures"] == 0},
])
"""
    ),
    nbf.v4.new_code_cell(
        """pd.DataFrame([
    {"metric": "Gap-risk rows", "displayed": stock["summary_risk"], "recomputed": stock["computed_risk"], "difference": stock["summary_risk"] - stock["computed_risk"]},
    {"metric": "7+ day gap rows", "displayed": stock["summary_long_gap"], "recomputed": stock["computed_long_gap"], "difference": stock["summary_long_gap"] - stock["computed_long_gap"]},
    {"metric": "Shortage units on 30 exceptions", "displayed": stock["shortage_exception_displayed_total"], "recomputed": stock["shortage_exception_visible_formula_total"], "difference": stock["shortage_exception_delta"]},
    {"metric": "Year-ambiguous date rows", "displayed": stock["gap_date_ambiguous_rows"], "recomputed": None, "difference": None},
])
"""
    ),
    nbf.v4.new_code_cell(
        """pd.DataFrame([
    {"case": "Historical no-ETA status", **logic_results["stock_gap_historical_base_date"]},
    {"case": "SKU three-month window", **logic_results["sku_concentration_window"]},
    {"case": "Missing SKU identity", **logic_results["sku_concentration_missing_identity"]},
])
"""
    ),
    nbf.v4.new_code_cell(
        """# Reconciliation assertions that are expected to pass.
assert order["row_count"] == order["target_count"]
assert order["duplicate_product_code_rows"] == 0
assert order["scenario_stock_failures"] == 0
assert order["scenario_qty_failures"] == 0
assert order["scenario_amount_failures"] == 0
assert order["moi_failures"] == 0
assert order["summary_qty_matches"] and order["summary_amount_matches"]
assert all(stock["summary_matches"].values())
assert stock["gap_date_failures"] == 0
print("All expected-pass reconciliation assertions succeeded.")
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Takeaways

1. **Keep the order-review arithmetic.** Its row grain, scenario formulas, cached values, and totals are internally consistent on the reviewed export.
2. **Choose one canonical stock-gap shortage definition.** Either display the explicit order-model shortage and rename/explain it, or calculate the displayed shortage strictly from gap days × daily sales speed. Do not mix the two silently.
3. **Make status calculations base-date pure.** Pass the analysis base date into the no-ETA branch instead of reading the machine clock.
4. **Filter SKU concentration by the requested analysis window before grouping.** Record the applied start/end dates in result metadata.
5. **Normalize missing identity fields.** Treat null, NaN, blank, `none`, and `-` as missing and fall back to the product master.
6. **Use full dates in stock-gap exports.** Seventy rows cannot be temporally interpreted from `MM/DD` alone because the year is omitted.
7. **Fix Excel validation XML.** Replace the non-standard validation error style with a standards-compliant value so external parsers can open the workbook.
"""
    ),
]

client = NotebookClient(
    notebook,
    timeout=120,
    kernel_name="python3",
    resources={"metadata": {"path": str(OUTPUT.parent)}},
)
client.execute()
nbf.write(notebook, OUTPUT)
print(OUTPUT)
