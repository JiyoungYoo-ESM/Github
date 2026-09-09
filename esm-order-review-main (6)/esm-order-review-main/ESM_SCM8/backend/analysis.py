"""Backward-compatible facade for backend analysis services.

New code should import the focused modules under ``backend.services``.  This
module keeps the historical public import path stable for scripts and tests.
"""

from __future__ import annotations

import pandas as pd

from core.inbound import build_master_unregistered_sku_df
from core.order_review_report import (
    _strip_check_required_internal_columns,
    build_check_required_sheet_df,
    build_excluded_order_review_df,
    build_human_data_issue_df,
)
from core.session import SessionContext
from core.transport import unrecognized_transport_report_df

from backend.services.category_corrections import (
    apply_category_corrections_to_merged,
    merge_default_category_corrections,
    normalize_sku_key,
    read_category_correction_excel,
    read_category_correction_upload,
    read_default_category_corrections,
    read_user_category_corrections,
    save_user_category_corrections,
)
from backend.services.dataframe_utils import (
    dataframe_preview,
    dataframe_records,
    date_range_label,
    first_existing_column,
    jsonable_value,
)
from backend.services.order_analysis_workflow import (
    DeferredExcelExport,
    apply_analysis_setting_overrides,
    apply_eur_krw_rate_setting,
    response_analysis_settings,
    run_core_analysis,
    run_core_analysis_from_uploaded_data,
)
from backend.services.order_review_metrics import (
    build_sku_concentration_df,
    check_required_sku_count,
    enrich_order_review_amounts,
    order_template_review_basis,
)
from backend.services.season_ingredient_analysis import (
    build_month_coverage,
    build_season_ingredient_analysis,
)
from backend.services.upload_classification import (
    ALLOWED_UPLOAD_ROLES,
    UPLOAD_KEY_TO_RESPONSE_ROLE,
    classify_uploads_for_preview,
    column_names_for_preview,
    file_mapping_from_classifications,
    matched_required_columns,
    missing_required_columns,
    normalize_upload_role,
    prepare_explicit_role_uploaded_data,
    prepare_uploaded_data,
    response_role_for_upload_key,
    upload_key_for_role,
)
from backend.services.upload_models import SavedUpload, UploadedFileAdapter


def build_check_required_df(
    settings: dict[str, object],
    review: pd.DataFrame,
    excluded_review: pd.DataFrame,
    context: SessionContext | None = None,
) -> pd.DataFrame:
    """Legacy wrapper retaining the historical monkeypatch seam."""

    excluded_df = build_excluded_order_review_df(excluded_review, settings)
    master_unregistered_df = build_master_unregistered_sku_df(settings, context)
    return _strip_check_required_internal_columns(
        build_check_required_sheet_df(
            pd.DataFrame(),
            unrecognized_transport_report_df(settings, context),
            excluded_df,
            master_unregistered_df,
            pd.DataFrame(),
            build_human_data_issue_df(settings, context),
        )
    )


__all__ = [
    "ALLOWED_UPLOAD_ROLES",
    "DeferredExcelExport",
    "SavedUpload",
    "UPLOAD_KEY_TO_RESPONSE_ROLE",
    "UploadedFileAdapter",
    "apply_analysis_setting_overrides",
    "apply_category_corrections_to_merged",
    "apply_eur_krw_rate_setting",
    "build_check_required_df",
    "build_month_coverage",
    "build_season_ingredient_analysis",
    "build_sku_concentration_df",
    "check_required_sku_count",
    "classify_uploads_for_preview",
    "column_names_for_preview",
    "dataframe_preview",
    "dataframe_records",
    "date_range_label",
    "enrich_order_review_amounts",
    "file_mapping_from_classifications",
    "first_existing_column",
    "jsonable_value",
    "matched_required_columns",
    "merge_default_category_corrections",
    "missing_required_columns",
    "normalize_sku_key",
    "normalize_upload_role",
    "order_template_review_basis",
    "prepare_explicit_role_uploaded_data",
    "prepare_uploaded_data",
    "read_category_correction_excel",
    "read_category_correction_upload",
    "read_default_category_corrections",
    "read_user_category_corrections",
    "response_analysis_settings",
    "response_role_for_upload_key",
    "run_core_analysis",
    "run_core_analysis_from_uploaded_data",
    "save_user_category_corrections",
    "upload_key_for_role",
]
