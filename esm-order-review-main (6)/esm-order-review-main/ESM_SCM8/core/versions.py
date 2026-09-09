from __future__ import annotations

ORDER_REVIEW_LOGIC_VERSION = 30
ORDER_REVIEW_EXPORT_VERSION = 61

LOGIC_VERSION_HISTORY = {
    27: "Initial refactor baseline carried into core modules.",
    28: "Pass SessionContext into cached_order_review_df calculations so cached review data matches uploaded inputs.",
    29: "Use editable safety months as the single target for order quantities and derived statuses.",
    30: "Limit PL V1 shipping quantities, amounts, and ETAs to SKO Sp. z o.o. customer rows.",
}

EXPORT_VERSION_HISTORY = {
    58: "Initial refactor baseline for generated order review Excel workbooks.",
    59: "Remove local and transport target parameters from order review Excel exports.",
    60: "Trim the order-sheet parameter title band to the six remaining parameter columns.",
    61: "Use the editable-input fill for sea, rail, and truck lead-time values in the report sheet.",
}
