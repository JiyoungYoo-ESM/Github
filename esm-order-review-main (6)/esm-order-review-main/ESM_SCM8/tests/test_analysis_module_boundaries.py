from __future__ import annotations

import ast
from pathlib import Path

import backend.analysis as analysis
from backend.routers import season as season_router
from backend.services import (
    category_corrections,
    ingredient_analysis_pipeline,
    order_analysis_workflow,
    order_review_metrics,
    season_analysis_options,
    season_api_analysis_service,
    season_analysis_common,
    season_cache_service,
    season_detail_pipeline,
    season_ingredient_analysis,
    upload_classification,
)
from backend.services.reports import (
    pptx_dynamic_cards,
    pptx_template_common,
    pptx_template_rankings,
    pptx_template_sections,
    report_pptx,
)
from backend.services.upload_models import SavedUpload


ANALYSIS_SOURCE = Path(analysis.__file__).read_text(encoding="utf-8")
SEASON_ORCHESTRATOR_SOURCE = Path(season_ingredient_analysis.__file__).read_text(encoding="utf-8")
SEASON_ROUTER_SOURCE = Path(season_router.__file__).read_text(encoding="utf-8")
REPORT_PPTX_SOURCE = Path(report_pptx.__file__).read_text(encoding="utf-8")


def test_analysis_does_not_redefine_extracted_upload_responsibilities() -> None:
    module = ast.parse(ANALYSIS_SOURCE)
    definitions = {
        node.name
        for node in module.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "SavedUpload" not in definitions
    assert "classify_uploads_for_preview" not in definitions
    assert "prepare_uploaded_data" not in definitions
    assert "save_user_category_corrections" not in definitions
    assert "build_season_ingredient_analysis" not in definitions
    assert "dataframe_records" not in definitions
    assert "build_sku_concentration_df" not in definitions
    assert "run_core_analysis_from_uploaded_data" not in definitions


def test_analysis_compatibility_exports_point_to_service_modules() -> None:
    assert analysis.SavedUpload is SavedUpload
    assert analysis.classify_uploads_for_preview is upload_classification.classify_uploads_for_preview
    assert analysis.prepare_uploaded_data is upload_classification.prepare_uploaded_data
    assert analysis.apply_category_corrections_to_merged is category_corrections.apply_category_corrections_to_merged
    assert analysis.build_season_ingredient_analysis is season_ingredient_analysis.build_season_ingredient_analysis
    assert analysis.build_sku_concentration_df is order_review_metrics.build_sku_concentration_df
    assert analysis.run_core_analysis is order_analysis_workflow.run_core_analysis


def test_season_orchestrator_does_not_redefine_extracted_pipeline_responsibilities() -> None:
    module = ast.parse(SEASON_ORCHESTRATOR_SOURCE)
    definitions = {
        node.name
        for node in module.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "top_rows_per_group" not in definitions
    assert "filter_rows_by_values" not in definitions
    assert "empty_season_ingredient_analysis" not in definitions
    assert "build_ingredient_analysis" not in definitions
    assert "build_season_detail_tables" not in definitions


def test_season_pipeline_exports_point_to_focused_modules() -> None:
    assert season_ingredient_analysis.build_month_coverage is season_analysis_common.build_month_coverage
    assert callable(ingredient_analysis_pipeline.build_ingredient_analysis)
    assert callable(season_detail_pipeline.build_season_detail_tables)


def test_season_router_does_not_own_extracted_cache_or_cms_algorithms() -> None:
    module = ast.parse(SEASON_ROUTER_SOURCE)
    definitions = {
        node.name
        for node in module.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "_summary_records" not in definitions
    assert "_country_summary_records" not in definitions
    assert "_monthly_records" not in definitions
    assert "_season_source_classifications" not in definitions
    assert "add_months" not in definitions


def test_season_router_reexports_service_policy_versions() -> None:
    assert season_router.SEASON_ANALYSIS_SCHEMA_VERSION == season_cache_service.SEASON_ANALYSIS_SCHEMA_VERSION
    assert season_router.API_ANALYSIS_CACHE_KEYS == season_cache_service.API_ANALYSIS_CACHE_KEYS
    assert season_router.SEASON_DATA_MIN_DATE == season_analysis_options.SEASON_DATA_MIN_DATE
    assert callable(season_api_analysis_service.run_api_analysis_with_options)


def test_report_pptx_orchestrator_does_not_redefine_extracted_renderers() -> None:
    module = ast.parse(REPORT_PPTX_SOURCE)
    definitions = {
        node.name
        for node in module.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "build_region_table_rows" not in definitions
    assert "fill_template_brand" not in definitions
    assert "fill_template_sku" not in definitions
    assert "replace_cross_matrix_content" not in definitions
    assert "add_report_card_season_calendar" not in definitions
    assert "add_report_card_cross_matrix" not in definitions


def test_report_pptx_compatibility_exports_point_to_focused_modules() -> None:
    assert report_pptx.set_template_badge is pptx_template_common.set_template_badge
    assert report_pptx.build_region_table_rows is pptx_template_rankings.build_region_table_rows
    assert report_pptx.fill_template_sku is pptx_template_sections.fill_template_sku
    assert report_pptx.add_report_card_cross_matrix is pptx_dynamic_cards.add_report_card_cross_matrix
