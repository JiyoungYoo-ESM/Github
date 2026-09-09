"""Persistent customer-support ticket models."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        Index("ix_support_tickets_status_created_at", "status", "created_at"),
        Index("ix_support_tickets_requester_created_at", "requester_name", "created_at"),
        Index("ix_support_tickets_owner_created_at", "owner_username", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    # Nullable only for tickets created before account ownership was introduced.
    # Legacy rows stay visible to administrators but are never guessed or
    # automatically assigned from the free-form requester name.
    owner_username: Mapped[str | None] = mapped_column(String(100))
    requester_name: Mapped[str] = mapped_column(String(100), nullable=False)
    requester_team: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="접수")
    assignee: Mapped[str | None] = mapped_column(String(100))
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    attachments: Mapped[list[SupportAttachment]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    status_events: Mapped[list[SupportStatusEvent]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )


class SupportAttachment(Base):
    __tablename__ = "support_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    ticket: Mapped[SupportTicket] = relationship(back_populates="attachments")


class SupportStatusEvent(Base):
    __tablename__ = "support_status_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    ticket: Mapped[SupportTicket] = relationship(back_populates="status_events")
