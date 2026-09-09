"""Order analysis execution workflow and deferred workbook export."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import pandas as pd

from core.eta import build_arrival_calendar_report_df
from core.exchange_rate import fallback_rate_metadata
from core.export_excel import (
    build_order_review_report_summary,
    build_stock_eta_sheet_df,
    generate_order_review_excel_fast,
)
from core.kpi import get_currency_krw_rate
from core.lead_times import analysis_lead_time_settings
from core.order_review import order_review_df
from core.order_review_report import (
    build_order_review_report_df,
    order_review_dashboard_kpi_values,
)
from core.session import SessionContext
from core.transport import applied_lead_times
from core.validation import apply_order_review_filters, default_settings_for_validation

from backend.services.dataframe_utils import dataframe_preview, dataframe_records
from backend.services.order_review_metrics import (
    build_check_required_df,
    build_sku_concentration_df,
    check_required_sku_count,
    enrich_order_review_amounts,
    order_template_review_basis,
)
from backend.services.season_ingredient_analysis import build_season_ingredient_analysis
from backend.services.upload_classification import file_mapping_from_classifications, prepare_uploaded_data
from backend.services.upload_models import SavedUpload


@dataclass(frozen=True)
class DeferredExcelExport:
    output_path: Path
    settings: dict[str, object]
    review: pd.DataFrame
    excluded_review: pd.DataFrame
    report_df: pd.DataFrame
    check_required_df: pd.DataFrame
    calendar_df: pd.DataFrame
    stock_eta_df: pd.DataFrame
    context: SessionContext

    def write(self) -> None:
        excel_bytes = generate_order_review_excel_fast(
            self.settings,
            self.review,
            excluded_review=self.excluded_review,
            report_df=self.report_df,
            check_required_df=self.check_required_df,
            calendar_df=self.calendar_df,
            stock_eta_df=self.stock_eta_df,
            context=self.context,
        )
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_bytes(excel_bytes)


def apply_eur_krw_rate_setting(settings: dict[str, object], eur_krw_rate: float | None) -> dict[str, object]:
    entity_code = str(settings.get("entity_code") or "PL").strip().upper()
    currency_code = "USD" if entity_code == "USA" else "EUR"
    settings["currency_code"] = currency_code
    if eur_krw_rate is not None:
        settings["eur_krw_rate"] = float(eur_krw_rate)
        settings["currency_krw_rate"] = float(eur_krw_rate)
        return {
            "eur_krw_rate": float(eur_krw_rate),
            "currency_code": currency_code,
            "currency_krw_rate": float(eur_krw_rate),
            "rate_source": "manual",
        }

    default_rate = float(settings.get("eur_krw_rate", 0)) if currency_code == "EUR" else 0.0
    rate, rate_date, success = get_currency_krw_rate(currency_code, default_rate=default_rate)
    settings["eur_krw_rate"] = float(rate)
    settings["currency_krw_rate"] = float(rate)
    result = {
        "eur_krw_rate": float(rate),
        "currency_code": currency_code,
        "currency_krw_rate": float(rate),
        "rate_source": "api" if success else ("default" if currency_code == "EUR" else "unavailable"),
        "rate_date": rate_date,
    }
    if not success and currency_code == "EUR":
        result.update(fallback_rate_metadata())
    return result


def apply_analysis_setting_overrides(
    settings: dict[str, object],
    settings_overrides: dict[str, object] | None,
) -> None:
    settings_overrides = settings_overrides or {}

    for key in ("base_date", "period_start", "period_end"):
        if key in settings_overrides:
            settings[key] = settings_overrides[key]

    for key in (
        "safety_months",
        "sku_shortage_threshold_pct",
        "sku_overstock_threshold_pct",
    ):
        if key in settings_overrides:
            settings[key] = float(settings_overrides[key])

    entity_code = str(
        settings_overrides.get("entity_code")
        or settings.get("entity_code")
        or "PL"
    ).strip().upper()
    lead_time_fields = {
        "lead_time_air": "AIR",
        "lead_time_sea": "OCEAN",
        "lead_time_rail": "RAIL",
        "lead_time_truck": "TRUCKING",
    }
    lead_time_overrides = dict(settings_overrides.get("lead_time_overrides") or {})
    legacy_overrides = {
        transport_code: int(settings_overrides[field_name])
        for field_name, transport_code in lead_time_fields.items()
        if field_name in settings_overrides
    }
    if legacy_overrides and entity_code != "PL":
        raise ValueError(
            "lead_time_air/sea/rail/truck are legacy PL-only fields; "
            "use lead_time_overrides with entity transport codes"
        )
    # The dynamic map is the canonical request shape and wins if both request
    # forms are supplied during the PL compatibility window.
    combined_overrides = {**legacy_overrides, **lead_time_overrides}
    entity_lead_time_settings = analysis_lead_time_settings(
        entity_code,
        combined_overrides,
    )
    settings.update(entity_lead_time_settings)
    settings["applied_lead_times"] = applied_lead_times(entity_lead_time_settings)


def response_analysis_settings(settings: dict[str, object]) -> dict[str, object]:
    lead_times = dict(settings.get("lead_times") or {})
    return {
        "safety_months": float(settings.get("safety_months", 3.0)),
        "sku_shortage_threshold_pct": float(settings.get("sku_shortage_threshold_pct", 2.5)),
        "sku_overstock_threshold_pct": float(settings.get("sku_overstock_threshold_pct", 3.0)),
        "lead_times": {
            mode: int(days)
            for mode, days in lead_times.items()
        },
        "entity_code": str(settings.get("entity_code") or ""),
        "lead_time_effective_date": settings.get("lead_time_effective_date"),
        "lead_time_source": settings.get("lead_time_source"),
        "lead_time_overrides": dict(settings.get("lead_time_overrides") or {}),
        "lead_times_by_code": dict(settings.get("lead_times_by_code") or {}),
        "lead_time_methods": list(settings.get("lead_time_methods") or []),
    }


def run_core_analysis(
    saved_uploads: list[SavedUpload],
    output_path: Path,
    eur_krw_rate: float | None = None,
    settings_overrides: dict[str, object] | None = None,
    entity_code: str = "PL",
) -> dict[str, object]:
    context = SessionContext()
    uploaded_data, _uploaded_files, classifications = prepare_uploaded_data(saved_uploads, context)
    size_by_saved_name = {upload.saved_name: upload.size_bytes for upload in saved_uploads}
    return run_core_analysis_from_uploaded_data(
        uploaded_data,
        classifications,
        output_path,
        eur_krw_rate=eur_krw_rate,
        settings_overrides=settings_overrides,
        entity_code=entity_code,
        context=context,
        size_by_saved_name=size_by_saved_name,
    )


def run_core_analysis_from_uploaded_data(
    uploaded_data: dict[str, pd.DataFrame],
    classifications: list[dict[str, object]],
    output_path: Path,
    eur_krw_rate: float | None = None,
    settings_overrides: dict[str, object] | None = None,
    context: SessionContext | None = None,
    size_by_saved_name: dict[str, int] | None = None,
    defer_excel: bool = False,
    entity_code: str = "PL",
) -> dict[str, object]:
    started_at = time.perf_counter()

    def log_stage(stage: str) -> None:
        print(f"[analysis] {stage}: {time.perf_counter() - started_at:.2f}s", flush=True)

    def timed_stage(stage: str, fn):
        stage_started_at = time.perf_counter()
        value = fn()
        print(
            f"[perf][analysis] {stage} seconds={time.perf_counter() - stage_started_at:.3f} total_seconds={time.perf_counter() - started_at:.3f}",
            flush=True,
        )
        return value

    context = context or SessionContext()
    log_stage("uploads prepared")
    context.uploaded_data = uploaded_data
    context.uploaded_files = {str(item["key"]): str(item["original_name"]) for item in classifications}
    context.uploaded_file_metadata = {
        item["key"]: {
            "file_name": item["original_name"],
            "size": (size_by_saved_name or {}).get(str(item.get("saved_name", "")), 0),
            "shape": (item["rows"], item["columns"]),
        }
        for item in classifications
    }

    settings = timed_stage(
        "default_settings",
        lambda: default_settings_for_validation(entity_code),
    )
    timed_stage("apply_setting_overrides", lambda: apply_analysis_setting_overrides(settings, settings_overrides))
    response_settings = timed_stage("eur_krw_rate", lambda: apply_eur_krw_rate_setting(settings, eur_krw_rate))
    response_settings.update(response_analysis_settings(settings))
    settings["include_excel_debug_sheets"] = False
    settings["include_season_sheets"] = "sales_history" in uploaded_data

    combined_review = timed_stage("order_review_df", lambda: order_review_df(settings, excluded_only=None, context=context))
    excluded_mask = combined_review["제외 SKU"].astype(bool) if "제외 SKU" in combined_review.columns else pd.Series(False, index=combined_review.index)
    review_all = combined_review[~excluded_mask].copy()
    excluded_all = combined_review[excluded_mask].copy()
    review = timed_stage("apply_order_review_filters", lambda: apply_order_review_filters(review_all, settings))
    excluded_review = timed_stage("apply_excluded_order_review_filters", lambda: apply_order_review_filters(excluded_all, settings))
    template_review = timed_stage(
        "order_template_review_basis",
        lambda: order_template_review_basis(combined_review, review, settings),
    )
    log_stage("review calculated")

    report_df = timed_stage("build_order_review_report_df", lambda: build_order_review_report_df(template_review, settings))
    report_df = timed_stage(
        "enrich_order_review_amounts",
        lambda: enrich_order_review_amounts(
            report_df,
            uploaded_data,
            response_settings.get("eur_krw_rate"),
            settings=settings,
        ),
    )
    sku_concentration_df = timed_stage(
        "build_sku_concentration_df",
        lambda: build_sku_concentration_df(
            uploaded_data,
            response_settings.get("eur_krw_rate"),
            settings=settings,
        ),
    )
    check_required_df = timed_stage("build_check_required_df", lambda: build_check_required_df(settings, review, excluded_review, context))
    calendar_df = timed_stage("build_arrival_calendar_report_df", lambda: build_arrival_calendar_report_df(settings, context))
    stock_eta_df = timed_stage("build_stock_eta_sheet_df", lambda: build_stock_eta_sheet_df(template_review, calendar_df, settings))
    season_ingredient_analysis = timed_stage(
        "build_season_ingredient_analysis",
        lambda: build_season_ingredient_analysis(uploaded_data),
    )
    log_stage("report tables built")

    deferred_excel_export = DeferredExcelExport(
        output_path=output_path,
        settings=settings,
        review=review,
        excluded_review=excluded_review,
        report_df=report_df,
        check_required_df=check_required_df,
        calendar_df=calendar_df,
        stock_eta_df=stock_eta_df,
        context=context,
    )
    if defer_excel:
        log_stage("excel deferred")
    else:
        timed_stage("excel_write", deferred_excel_export.write)
        log_stage("excel written")

    dashboard_kpi = timed_stage("order_review_dashboard_kpi_values", lambda: order_review_dashboard_kpi_values(report_df))
    report_summary = timed_stage("build_order_review_report_summary", lambda: build_order_review_report_summary(report_df, settings))
    log_stage("summary ready")

    tables_started_at = time.perf_counter()
    tables = {
        "order_review": timed_stage("records.order_review_preview", lambda: dataframe_preview(report_df)),
        "check_required": timed_stage("records.check_required_preview", lambda: dataframe_preview(check_required_df)),
        "stock_eta": timed_stage("records.stock_eta_preview", lambda: dataframe_preview(stock_eta_df)),
        "stock_gap_order_review": timed_stage("records.stock_gap_order_review", lambda: dataframe_records(report_df)),
        "stock_gap_eta": timed_stage("records.stock_gap_eta", lambda: dataframe_records(calendar_df)),
        "sku_concentration": timed_stage("records.sku_concentration", lambda: dataframe_records(sku_concentration_df)),
    }
    print(
        f"[perf][analysis] records.all seconds={time.perf_counter() - tables_started_at:.3f} total_seconds={time.perf_counter() - started_at:.3f}",
        flush=True,
    )

    result = {
        "summary": {
            "total_sku": int(len(report_df)),
            "order_required_sku": int(dashboard_kpi["order_needed_sku"]),
            "check_required_sku": check_required_sku_count(check_required_df),
            "order_required_qty": float(report_summary["total_order_qty"]),
            "order_amount_eur": float(report_summary["total_order_eur"]),
        },
        "tables": tables,
        **season_ingredient_analysis,
        "uploaded_files": classifications,
        "file_mapping": file_mapping_from_classifications(classifications),
        "settings": response_settings,
    }
    if defer_excel:
        result["_deferred_excel_export"] = deferred_excel_export
    return result

__all__ = [
    "DeferredExcelExport",
    "apply_analysis_setting_overrides",
    "apply_eur_krw_rate_setting",
    "response_analysis_settings",
    "run_core_analysis",
    "run_core_analysis_from_uploaded_data",
]
