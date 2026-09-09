"""Request and response contracts for customer-support tickets."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SupportAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    content_type: str | None
    size_bytes: int


class SupportTicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticket_number: str
    requester_name: str
    requester_team: str | None
    category: str
    title: str
    content: str
    status: str
    assignee: str | None
    due_date: date | None
    created_at: datetime
    updated_at: datetime
    attachments: list[SupportAttachmentResponse] = Field(default_factory=list)


class SupportTicketSummary(BaseModel):
    total: int
    received: int
    in_progress: int
    completed: int
    delayed: int


class SupportTicketListResponse(BaseModel):
    items: list[SupportTicketResponse]
    summary: SupportTicketSummary


class SupportTicketUpdateRequest(BaseModel):
    status: str | None = None
    assignee: str | None = Field(default=None, max_length=100)
    due_date: date | None = None
    changed_by: str = Field(default="SCM 관리자", min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)
