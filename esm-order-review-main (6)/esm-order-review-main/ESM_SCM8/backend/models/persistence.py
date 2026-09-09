"""Database-backed state that must survive a web-process restart.

Large workbooks remain files (and need a persistent volume or object storage),
but the metadata used to authenticate users, poll jobs, and reopen the latest
analysis is kept in the application database.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_kind_scope_updated", "kind", "security_scope", "updated_at"),
        Index("ix_analysis_jobs_kind_client_updated", "kind", "client_id", "updated_at"),
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(160))
    security_scope: Mapped[str | None] = mapped_column(String(160))
    is_latest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    result_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    status_code: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class LatestAnalysisSnapshot(Base):
    __tablename__ = "latest_analysis_snapshots"

    snapshot_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
