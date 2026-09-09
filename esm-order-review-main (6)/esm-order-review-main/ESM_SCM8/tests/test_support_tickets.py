from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.models import UserAccount
from backend.database import Base, get_db_session
from backend.main import app
from backend.models.support import SupportStatusEvent, SupportTicket
from backend.routers.support import ALLOWED_CATEGORIES, ALLOWED_STATUSES
from backend.services.auth import require_authenticated_user


def _account(username: str, *, is_admin: bool = False) -> UserAccount:
    return UserAccount(
        username=username,
        password_hash="test-only",
        role="MASTER" if is_admin else "TEAM",
        allowed_entities=("HQ",),
        is_active=True,
        display_name=username,
        account_type="TEST",
        is_admin=is_admin,
    )


@pytest.fixture()
def support_context(tmp_path, monkeypatch):
    database_path = tmp_path / "support-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    current_user = {"value": _account("bm1")}

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_user() -> UserAccount:
        return current_user["value"]

    app.dependency_overrides[require_authenticated_user] = override_user
    app.dependency_overrides[get_db_session] = override_session
    # TestClient enters the application lifespan.  Do not start the production
    # CMS cache warmer here: its blocking HTTP worker can outlive cancellation
    # and make the isolated support-ticket tests wait for the network.
    monkeypatch.setattr("backend.main.start_cms_prefetch_task", lambda: None)
    try:
        with TestClient(app) as client:
            yield client, session_factory, current_user
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _create_ticket(client: TestClient, label: str):
    return client.post(
        "/api/support/tickets",
        data={
            "requester_name": label,
            "requester_team": "SCM",
            "category": next(iter(ALLOWED_CATEGORIES)),
            "title": f"{label} ticket",
            "content": f"{label} content",
        },
        headers={"X-Requested-With": "fetch"},
    )


def test_regular_accounts_create_and_list_only_their_own_tickets(support_context) -> None:
    client, session_factory, current_user = support_context

    bm1_created = _create_ticket(client, "BM1")
    assert bm1_created.status_code == 201
    bm1_id = bm1_created.json()["id"]

    current_user["value"] = _account("bm2")
    bm2_created = _create_ticket(client, "BM2")
    assert bm2_created.status_code == 201

    current_user["value"] = _account("bm1")
    bm1_list = client.get("/api/support/tickets")
    assert bm1_list.status_code == 200
    assert [item["id"] for item in bm1_list.json()["items"]] == [bm1_id]
    assert bm1_list.json()["summary"]["total"] == 1

    current_user["value"] = _account("adminmaster", is_admin=True)
    admin_list = client.get("/api/support/tickets")
    assert admin_list.status_code == 200
    assert {item["id"] for item in admin_list.json()["items"]} == {
        bm1_id,
        bm2_created.json()["id"],
    }
    assert admin_list.json()["summary"]["total"] == 2

    with session_factory() as session:
        owners = {
            ticket.id: ticket.owner_username
            for ticket in session.scalars(select(SupportTicket))
        }
    assert owners[bm1_id] == "bm1"
    assert owners[bm2_created.json()["id"]] == "bm2"


def test_only_admin_can_manage_ticket_and_actor_cannot_be_spoofed(support_context) -> None:
    client, session_factory, current_user = support_context
    created = _create_ticket(client, "BM1")
    assert created.status_code == 201
    ticket_id = created.json()["id"]
    next_status = next(status for status in ALLOWED_STATUSES if status != created.json()["status"])
    update = {
        "status": next_status,
        "assignee": "support-owner",
        "due_date": "2026-08-01",
        "changed_by": "spoofed-user",
        "note": "admin update",
    }

    own_update = client.patch(
        f"/api/support/tickets/{ticket_id}",
        json=update,
        headers={"X-Requested-With": "fetch"},
    )
    assert own_update.status_code == 403

    current_user["value"] = _account("bm2")
    other_update = client.patch(
        f"/api/support/tickets/{ticket_id}",
        json=update,
        headers={"X-Requested-With": "fetch"},
    )
    assert other_update.status_code == 403

    current_user["value"] = _account("adminmaster", is_admin=True)
    admin_update = client.patch(
        f"/api/support/tickets/{ticket_id}",
        json=update,
        headers={"X-Requested-With": "fetch"},
    )
    assert admin_update.status_code == 200
    assert admin_update.json()["status"] == next_status
    assert admin_update.json()["assignee"] == "support-owner"
    assert admin_update.json()["due_date"] == "2026-08-01"

    with session_factory() as session:
        events = list(
            session.scalars(
                select(SupportStatusEvent)
                .where(SupportStatusEvent.ticket_id == ticket_id)
                .order_by(SupportStatusEvent.created_at)
            )
        )
    assert events[-1].changed_by == "adminmaster"


def test_legacy_ticket_without_owner_is_visible_and_manageable_only_by_admin(
    support_context,
) -> None:
    client, session_factory, current_user = support_context
    with session_factory() as session:
        legacy = SupportTicket(
            ticket_number="SC-LEGACY-001",
            owner_username=None,
            requester_name="Legacy requester",
            requester_team="SCM",
            category=next(iter(ALLOWED_CATEGORIES)),
            title="Legacy ticket",
            content="Created before authenticated ownership",
            status=next(iter(ALLOWED_STATUSES)),
        )
        session.add(legacy)
        session.commit()
        legacy_id = legacy.id

    regular_list = client.get("/api/support/tickets")
    assert regular_list.status_code == 200
    assert regular_list.json()["items"] == []
    assert regular_list.json()["summary"]["total"] == 0

    regular_update = client.patch(
        f"/api/support/tickets/{legacy_id}",
        json={"assignee": "regular-user"},
        headers={"X-Requested-With": "fetch"},
    )
    assert regular_update.status_code == 403

    current_user["value"] = _account("adminmaster", is_admin=True)
    admin_list = client.get("/api/support/tickets")
    assert [item["id"] for item in admin_list.json()["items"]] == [legacy_id]

    admin_update = client.patch(
        f"/api/support/tickets/{legacy_id}",
        json={"assignee": "admin-owner"},
        headers={"X-Requested-With": "fetch"},
    )
    assert admin_update.status_code == 200
    assert admin_update.json()["assignee"] == "admin-owner"
