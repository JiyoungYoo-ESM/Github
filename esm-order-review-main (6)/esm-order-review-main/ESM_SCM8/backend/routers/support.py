"""Customer-support ticket API backed by PostgreSQL."""

from __future__ import annotations

import re
import shutil
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.auth.models import UserAccount
from backend.config import SUPPORT_ATTACHMENT_DIR, SUPPORT_MAX_ATTACHMENT_BYTES
from backend.database import get_db_session
from backend.models.support import SupportAttachment, SupportStatusEvent, SupportTicket
from backend.services.auth import require_authenticated_user
from backend.services import object_storage
from backend.support_schemas import (
    SupportTicketListResponse,
    SupportTicketResponse,
    SupportTicketUpdateRequest,
)

router = APIRouter(prefix="/api/support", tags=["support"])

ALLOWED_CATEGORIES = {"데이터 오류", "기능 문의", "권한·계정"}
ALLOWED_STATUSES = {"접수", "처리중", "완료", "지연"}


def _clean_file_name(file_name: str) -> str:
    base = Path(file_name or "attachment").name
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._ -]", "_", base).strip(" .")
    return cleaned[:180] or "attachment"


def _ticket_number() -> str:
    now = datetime.now(timezone.utc)
    return f"SC-{now:%y%m}-{uuid4().hex[:6].upper()}"


def _serialize(ticket: SupportTicket) -> SupportTicketResponse:
    return SupportTicketResponse.model_validate(ticket)


@router.get("/tickets", response_model=SupportTicketListResponse)
def list_support_tickets(
    db: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[UserAccount, Depends(require_authenticated_user)],
) -> SupportTicketListResponse:
    statement = select(SupportTicket).options(selectinload(SupportTicket.attachments))
    if not current_user.is_admin:
        statement = statement.where(SupportTicket.owner_username == current_user.username)
    tickets = list(
        db.scalars(
            statement.order_by(SupportTicket.created_at.desc()).limit(200)
        )
    )
    counts = Counter(ticket.status for ticket in tickets)
    return SupportTicketListResponse(
        items=[_serialize(ticket) for ticket in tickets],
        summary={
            "total": len(tickets),
            "received": counts["접수"],
            "in_progress": counts["처리중"],
            "completed": counts["완료"],
            "delayed": counts["지연"],
        },
    )


@router.post("/tickets", response_model=SupportTicketResponse, status_code=201)
async def create_support_ticket(
    db: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[UserAccount, Depends(require_authenticated_user)],
    requester_name: Annotated[str, Form(min_length=1, max_length=100)],
    category: Annotated[str, Form(min_length=1, max_length=40)],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    content: Annotated[str, Form(min_length=1, max_length=10000)],
    requester_team: Annotated[str | None, Form(max_length=100)] = None,
    attachment: Annotated[UploadFile | None, File()] = None,
) -> SupportTicketResponse:
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=422, detail="지원하지 않는 문의 유형입니다.")

    ticket = SupportTicket(
        ticket_number=_ticket_number(),
        owner_username=current_user.username,
        requester_name=requester_name.strip(),
        requester_team=requester_team.strip() if requester_team else None,
        category=category,
        title=title.strip(),
        content=content.strip(),
        status="접수",
        due_date=(datetime.now(timezone.utc) + timedelta(days=3)).date(),
    )
    ticket.status_events.append(
        SupportStatusEvent(
            from_status=None,
            to_status="접수",
            changed_by=current_user.username,
            note="문의 등록",
        )
    )
    db.add(ticket)
    db.flush()

    saved_path: Path | None = None
    uploaded_object_name: str | None = None
    try:
        if attachment and attachment.filename:
            SUPPORT_ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
            ticket_dir = SUPPORT_ATTACHMENT_DIR / ticket.id
            ticket_dir.mkdir(parents=True, exist_ok=True)
            safe_name = _clean_file_name(attachment.filename)
            storage_name = f"{uuid4().hex}_{safe_name}"
            saved_path = ticket_dir / storage_name
            size = 0
            with saved_path.open("wb") as target:
                while chunk := await attachment.read(1024 * 1024):
                    size += len(chunk)
                    if size > SUPPORT_MAX_ATTACHMENT_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"첨부파일은 최대 {SUPPORT_MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB까지 가능합니다.",
                        )
                    target.write(chunk)
            storage_key = str(saved_path.relative_to(SUPPORT_ATTACHMENT_DIR))
            if object_storage.enabled():
                uploaded_object_name = f"support/{ticket.id}/{storage_name}"
                storage_key = object_storage.upload_file(
                    saved_path,
                    uploaded_object_name,
                    content_type=attachment.content_type or "application/octet-stream",
                )
                saved_path.unlink(missing_ok=True)
            ticket.attachments.append(
                SupportAttachment(
                    original_name=safe_name,
                    storage_key=storage_key,
                    content_type=attachment.content_type,
                    size_bytes=size,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        if uploaded_object_name is not None:
            try:
                object_storage.delete_object(uploaded_object_name)
            except Exception:
                pass
        if saved_path is not None:
            shutil.rmtree(saved_path.parent, ignore_errors=True)
        raise

    db.refresh(ticket)
    return _serialize(ticket)


@router.patch("/tickets/{ticket_id}", response_model=SupportTicketResponse)
def update_support_ticket(
    ticket_id: str,
    body: SupportTicketUpdateRequest,
    db: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[UserAccount, Depends(require_authenticated_user)],
) -> SupportTicketResponse:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="문의 관리 권한이 없습니다.")

    ticket = db.scalar(
        select(SupportTicket)
        .options(selectinload(SupportTicket.attachments))
        .where(SupportTicket.id == ticket_id)
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    if body.status is not None and body.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail="지원하지 않는 처리 상태입니다.")

    previous_status = ticket.status
    if body.status is not None:
        ticket.status = body.status
    if body.assignee is not None:
        ticket.assignee = body.assignee.strip() or None
    if body.due_date is not None:
        ticket.due_date = body.due_date
    if ticket.status != previous_status:
        ticket.status_events.append(
            SupportStatusEvent(
                from_status=previous_status,
                to_status=ticket.status,
                changed_by=current_user.username,
                note=body.note,
            )
        )
    db.commit()
    db.refresh(ticket)
    return _serialize(ticket)
