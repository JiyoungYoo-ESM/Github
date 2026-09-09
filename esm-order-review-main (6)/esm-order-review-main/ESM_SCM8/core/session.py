from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class SessionContext:
    uploaded_data: dict[str, pd.DataFrame] = field(default_factory=dict)
    uploaded_files: dict[str, str] = field(default_factory=dict)
    uploaded_file_metadata: dict[str, dict[str, object]] = field(default_factory=dict)
    uploaded_file_signatures: dict[str, object] = field(default_factory=dict)
    upload_errors: dict[str, object] = field(default_factory=dict)
    active_tab: str = "발주 검토 시트"
    shipping_read_debug: dict[str, object] = field(default_factory=dict)
    shipping_read_raw_df: pd.DataFrame | None = None
    shipping_read_cleaned_df: pd.DataFrame | None = None
    order_review_cache: dict[tuple, pd.DataFrame] = field(default_factory=dict)
    sales_detail_cache: dict[tuple, pd.DataFrame] = field(default_factory=dict)
    brand_options_cache: dict[tuple, list[str]] = field(default_factory=dict)
    order_review_manager_xlsx: bytes | None = None


def ensure_session_context(context: SessionContext | None = None) -> SessionContext:
    return context if context is not None else SessionContext()
