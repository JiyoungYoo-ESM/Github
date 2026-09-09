from __future__ import annotations

import asyncio
import threading

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from backend.routers import reports
from backend.services import report_resources


def reset_report_slots() -> None:
    report_resources._active_exports = 0


def test_report_request_size_is_rejected_before_generation(monkeypatch):
    monkeypatch.setattr(reports, "REPORT_MAX_REQUEST_BYTES", 10)
    request = reports.ReportExportRequest(title="large request")

    with pytest.raises(HTTPException) as error:
        asyncio.run(reports.export_report(request))

    assert error.value.status_code == 413


def test_report_output_is_streamed_and_directory_is_removed_after_response(tmp_path, monkeypatch):
    output_dir = tmp_path / "report_test"
    output_dir.mkdir()
    output_path = output_dir / "report.html"
    output_path.write_text("report", encoding="utf-8")
    monkeypatch.setattr(reports, "build_report_export", lambda **kwargs: output_path)
    reset_report_slots()

    async def scenario() -> None:
        response = await reports.export_report(reports.ReportExportRequest(format="html"))
        assert isinstance(response, FileResponse)
        assert report_resources.report_resource_snapshot()["active_exports"] == 0
        assert output_path.is_file()
        assert response.background is not None
        await response.background()
        assert not output_dir.exists()

    asyncio.run(scenario())


def test_oversized_report_output_is_rejected_and_removed(tmp_path, monkeypatch):
    output_dir = tmp_path / "report_oversized"
    output_dir.mkdir()
    output_path = output_dir / "report.pptx"
    output_path.write_bytes(b"oversized")
    monkeypatch.setattr(reports, "build_report_export", lambda **kwargs: output_path)
    monkeypatch.setattr(reports, "REPORT_MAX_OUTPUT_BYTES", 4)
    reset_report_slots()

    async def scenario() -> None:
        with pytest.raises(HTTPException) as error:
            await reports.export_report(reports.ReportExportRequest())

        assert error.value.status_code == 413
        assert report_resources.report_resource_snapshot()["active_exports"] == 0
        assert not output_dir.exists()

    asyncio.run(scenario())


def test_report_timeout_keeps_slot_until_generator_finishes(tmp_path, monkeypatch):
    output_dir = tmp_path / "report_timeout"
    output_path = output_dir / "report.html"
    worker_started = threading.Event()
    worker_release = threading.Event()

    def slow_export(**kwargs):
        output_dir.mkdir()
        worker_started.set()
        worker_release.wait(timeout=5)
        output_path.write_text("late report", encoding="utf-8")
        return output_path

    monkeypatch.setattr(reports, "build_report_export", slow_export)
    # Give the executor enough time to start even on a loaded CI runner. The
    # worker remains blocked on ``worker_release``, so the timeout behavior is
    # still exercised deterministically rather than racing thread startup.
    monkeypatch.setattr(reports, "REPORT_EXPORT_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(report_resources, "MAX_CONCURRENT_REPORT_EXPORTS", 1)
    reset_report_slots()

    async def scenario() -> None:
        try:
            with pytest.raises(HTTPException) as error:
                await reports.export_report(reports.ReportExportRequest(format="html"))
            assert error.value.status_code == 504
            assert worker_started.is_set()
            assert report_resources.report_resource_snapshot()["active_exports"] == 1
            assert await report_resources.acquire_report_slot() is False
        finally:
            worker_release.set()

        for _ in range(100):
            await asyncio.sleep(0.01)
            if report_resources.report_resource_snapshot()["timed_out_workers"] == 0:
                break

        assert report_resources.report_resource_snapshot()["active_exports"] == 0
        assert not output_dir.exists()

    asyncio.run(scenario())
