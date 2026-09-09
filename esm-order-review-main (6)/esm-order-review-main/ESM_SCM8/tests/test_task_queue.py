from __future__ import annotations

import sys
from types import SimpleNamespace

from backend.services import task_queue


class _FakeTask:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def apply_async(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_enqueue_cms_submits_json_safe_job_arguments(monkeypatch):
    fake_task = _FakeTask()
    monkeypatch.setattr(task_queue, "CELERY_BROKER_URL", "redis://queue.example/0")
    monkeypatch.setitem(sys.modules, "backend.worker.tasks", SimpleNamespace(run_cms_analysis_task=fake_task))

    task_queue.enqueue_cms("job-1", {"as_of": "2026-07-23"}, "client-1", "admin", "PL")

    assert fake_task.calls[0]["args"] == ["job-1", {"as_of": "2026-07-23"}, "client-1", "admin", "PL"]
    assert fake_task.calls[0]["task_id"] == "cms:job-1"
    assert fake_task.calls[0]["queue"] == "analysis"
    assert fake_task.calls[0]["retry"] is True
    assert fake_task.calls[0]["retry_policy"]["max_retries"] == task_queue.CELERY_TASK_MAX_RETRIES


def test_enqueue_season_submits_worker_release_context(monkeypatch):
    fake_task = _FakeTask()
    monkeypatch.setattr(task_queue, "CELERY_BROKER_URL", "redis://queue.example/0")
    monkeypatch.setitem(sys.modules, "backend.worker.tasks", SimpleNamespace(run_season_analysis_task=fake_task))

    task_queue.enqueue_season("job-2", {"security_scope": "admin__PL"}, "client-1")

    assert fake_task.calls[0]["args"] == ["job-2", {"security_scope": "admin__PL"}, "client-1"]
    assert fake_task.calls[0]["task_id"] == "season:job-2"
    assert fake_task.calls[0]["retry"] is True


def test_enqueue_order_logic_v3_submits_only_durable_identifiers(monkeypatch):
    fake_task = _FakeTask()
    monkeypatch.setattr(task_queue, "CELERY_BROKER_URL", "redis://queue.example/0")
    monkeypatch.setitem(
        sys.modules,
        "backend.worker.tasks",
        SimpleNamespace(run_order_logic_v3_task=fake_task),
    )

    body = {"as_of": "2026-08-31", "entity_code": "HQ", "preview": True}
    task_queue.enqueue_order_logic_v3("job-3", body, "client-3")

    assert fake_task.calls[0]["args"] == ["job-3", body, "client-3"]
    assert fake_task.calls[0]["task_id"] == "order-v3:job-3"
    assert fake_task.calls[0]["queue"] == "order-v3"
    assert fake_task.calls[0]["retry"] is True
