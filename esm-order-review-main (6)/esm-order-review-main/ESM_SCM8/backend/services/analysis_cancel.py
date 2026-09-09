"""Cooperative cancellation for long-running CMS analysis fetches.

A CMS fetch runs in a worker thread and cannot be killed safely, but every
fetch is a page loop. Checking a token between pages stops it within roughly
one page instead of letting an abandoned fetch keep competing with the user's
restarted analysis for CMS bandwidth, threads and memory.

The token travels by ``contextvars`` so no fetch signature has to change: the
async job sets it, ``run_in_threadpool`` copies the context into the worker
thread, and the nested page ``ThreadPoolExecutor`` reads it through closure
capture.

Cancellation always raises. A cancelled fetch must never return the pages it
already has, or partial data would reach the analysis and the fetch cache.
"""

from __future__ import annotations

import contextvars
import threading


class AnalysisCancelled(Exception):
    """Raised inside a fetch once the user has cancelled the analysis."""


class CancelToken:
    """A one-way flag shared between the request handler and worker threads."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


_CURRENT_TOKEN: contextvars.ContextVar[CancelToken | None] = contextvars.ContextVar(
    "analysis_cancel_token",
    default=None,
)
_TOKENS_LOCK = threading.Lock()
_TOKENS: dict[str, CancelToken] = {}


def register(job_id: str) -> CancelToken:
    """Bind a fresh token to ``job_id`` and to the calling task's context."""
    token = CancelToken()
    with _TOKENS_LOCK:
        _TOKENS[job_id] = token
    _CURRENT_TOKEN.set(token)
    return token


def unregister(job_id: str) -> None:
    with _TOKENS_LOCK:
        _TOKENS.pop(job_id, None)


def cancel(job_id: str) -> bool:
    """Signal the fetch for ``job_id``; False when no fetch is registered."""
    with _TOKENS_LOCK:
        token = _TOKENS.get(job_id)
    if token is None:
        return False
    token.cancel()
    return True


def current_token() -> CancelToken | None:
    """Read the bound token.

    Call this from the thread that owns the context and capture the result in a
    closure. A ``ThreadPoolExecutor`` child thread does NOT inherit contextvars,
    so calling :func:`is_cancelled` inside a page worker would always say False.
    """
    return _CURRENT_TOKEN.get()


def is_cancelled() -> bool:
    token = _CURRENT_TOKEN.get()
    return token is not None and token.cancelled


def raise_if_cancelled() -> None:
    if is_cancelled():
        raise AnalysisCancelled("사용자가 분석을 중단했습니다.")


def active_token_count() -> int:
    """Exposed for tests and health checks; must return to 0 between jobs."""
    with _TOKENS_LOCK:
        return len(_TOKENS)
