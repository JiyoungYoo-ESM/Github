# Report source notes

- Audience: product stakeholders.
- Required structure mapping: title, Executive Summary, findings, recommended next steps, further questions, and caveats are all visible report sections.
- Chart map: the findings section uses a three-row bar chart of affected SKU counts. The canonical artifact passed schema/package validation, but portable-reader verification repeatedly reported desktop horizontal overflow; a control run against an existing report also failed in the same shared reader (loading timeout). No HTML file is claimed as delivered. The exact counts and denominators remain in the adjacent findings narrative and `risk_impact` snapshot dataset.
- Primary evidence: `sku_tab_backtest_20260715.ipynb`, `metric_reconciliation.csv`, `interpretation_risk_summary.csv`.
- Delivery mode: portable HTML only.
