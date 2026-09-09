"""Structured application events and lightweight process request metrics."""

from __future__ import annotations

import json
import logging
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_logger = logging.getLogger("esm_scm")


def configure_observability() -> None:
    """Attach one JSON stdout handler without taking over server loggers."""
    if _logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def log_event(level: int, event: str, **fields: object) -> None:
    _logger.log(level, event, extra={"event": event, "fields": fields})


def log_exception(event: str, **fields: object) -> None:
    _logger.exception(event, extra={"event": event, "fields": fields})


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = datetime.now(timezone.utc)
        self._requests_total = 0
        self._in_flight = 0
        self._slow_requests = 0
        self._status_counts: Counter[str] = Counter()
        self._duration_total_ms = 0.0
        self._duration_max_ms = 0.0

    def begin(self) -> None:
        with self._lock:
            self._in_flight += 1

    def complete(self, status_code: int, duration_ms: float, *, slow: bool) -> None:
        with self._lock:
            self._in_flight = max(self._in_flight - 1, 0)
            self._requests_total += 1
            self._status_counts[f"{status_code // 100}xx"] += 1
            self._duration_total_ms += duration_ms
            self._duration_max_ms = max(self._duration_max_ms, duration_ms)
            if slow:
                self._slow_requests += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            total = self._requests_total
            return {
                "scope": "process_local",
                "started_at": self._started_at.isoformat(),
                "requests_total": total,
                "in_flight": self._in_flight,
                "slow_requests_total": self._slow_requests,
                "status_counts": dict(self._status_counts),
                "duration_avg_ms": round(self._duration_total_ms / total, 2) if total else 0.0,
                "duration_max_ms": round(self._duration_max_ms, 2),
            }


request_metrics = RequestMetrics()


def request_metrics_snapshot() -> dict[str, object]:
    return request_metrics.snapshot()
