"""M10 chat hardening integration tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from cyberai.core.config import Settings
from cyberai.platform.db import Database
from cyberai.platform.db.models import Organization, Project, SubscriptionModel, User

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class ChatCase:
    org: Organization
    user: User
    project: Project
    token: str


@pytest.fixture
async def chat_case(db: Database, settings: Settings) -> AsyncIterator[ChatCase]:
    suffix = uuid4().hex[:8]
    org = Organization(slug=f"chat-m10-{suffix}", display_name="Chat M10 Org")
    async with db.session() as session:
        session.add(org)
        await session.flush()
        user = User(
            org_id=org.id,
            identity_provider_id=f"test-idp|chat-m10-{suffix}",
            email=f"chat-m10-{suffix}@cyberai.dev",
            display_name="Chat M10 User",
        )
        session.add(user)
        await session.flush()
        project = Project(
            org_id=org.id,
            name=f"Chat M10 Project {suffix}",
            description="M10 chat hardening test project",
        )
        session.add(project)
        await session.flush()

    token = jwt.encode(
        {"sub": str(user.id), "exp": int(datetime.now(UTC).timestamp()) + 3600},
        settings.auth.jwt_secret,
        algorithm="HS256",
    )
    try:
        yield ChatCase(org=org, user=user, project=project, token=token)
    finally:
        async with db.session() as session:
            idempotency_exists = await session.scalar(
                text("SELECT to_regclass('public.chat_idempotency_keys')")
            )
            if idempotency_exists is not None:
                await session.execute(
                    text("DELETE FROM chat_idempotency_keys WHERE org_id = :org_id"),
                    {"org_id": org.id},
                )
            await session.execute(
                text("DELETE FROM messages WHERE org_id = :org_id"), {"org_id": org.id}
            )
            await session.execute(
                text("DELETE FROM conversations WHERE org_id = :org_id"), {"org_id": org.id}
            )
            await session.execute(
                text("DELETE FROM chunks WHERE org_id = :org_id"), {"org_id": org.id}
            )
            await session.execute(
                text("DELETE FROM documents WHERE org_id = :org_id"), {"org_id": org.id}
            )
            await session.execute(
                text("DELETE FROM subscriptions WHERE org_id = :org_id"), {"org_id": org.id}
            )
            await session.execute(
                text("DELETE FROM usage_reservations WHERE org_id = :org_id"), {"org_id": org.id}
            )
            await session.execute(
                text("DELETE FROM usage_records WHERE org_id = :org_id"), {"org_id": org.id}
            )
            await session.execute(
                text("DELETE FROM usage_aggregates WHERE org_id = :org_id"), {"org_id": org.id}
            )
            await session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project.id})
            await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
            await session.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org.id})


def _headers(token: str, *, request_id: str, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Request-ID": request_id,
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _chat_payload(content: str, *, rag_enabled: bool = False) -> dict[str, object]:
    return {
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 128,
        "temperature": 0.2,
        "rag_enabled": rag_enabled,
    }


def _sse_payloads(response_text: str) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for line in response_text.splitlines():
        if not line.startswith("data: "):
            continue
        raw = line.removeprefix("data: ")
        if raw == "[DONE]":
            continue
        payloads.append(json.loads(raw))
    return payloads


def _assistant_text(response_text: str) -> str:
    return "".join(
        str(event["text"]) for event in _sse_payloads(response_text) if event["event"] == "delta"
    )


async def _create_conversation(app_client: AsyncClient, case: ChatCase) -> str:
    response = await app_client.post(
        f"/api/v1/projects/{case.project.id}/conversations",
        json={"title": "M10 test conversation"},
        headers=_headers(case.token, request_id=f"create-{uuid4()}"),
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _usage_count(db: Database, org_id: UUID) -> int:
    async with db.session() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM usage_records WHERE org_id = :org_id"),
            {"org_id": org_id},
        )
    return int(count or 0)


async def _message_count(db: Database, org_id: UUID) -> int:
    async with db.session() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM messages WHERE org_id = :org_id"),
            {"org_id": org_id},
        )
    return int(count or 0)


@pytest.mark.asyncio
async def test_conversation_messages_are_listed_in_stable_paginated_order(
    app_client: AsyncClient,
    chat_case: ChatCase,
) -> None:
    conversation_id = await _create_conversation(app_client, chat_case)

    chat_response = await app_client.post(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        json=_chat_payload("Persist this M10 history turn."),
        headers=_headers(chat_case.token, request_id="history-req-1", idempotency_key="history-1"),
    )
    assert chat_response.status_code == 200, chat_response.text
    assert "data: [DONE]" in chat_response.text

    first_page = await app_client.get(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        params={"limit": 1, "offset": 0},
        headers=_headers(chat_case.token, request_id="history-list-1"),
    )
    assert first_page.status_code == 200, first_page.text
    assert first_page.json()["messages"] == [
        {
            "id": first_page.json()["messages"][0]["id"],
            "conversation_id": conversation_id,
            "role": "user",
            "content": "Persist this M10 history turn.",
            "tokens_used": None,
            "created_at": first_page.json()["messages"][0]["created_at"],
        }
    ]
    assert first_page.json()["pagination"]["next_offset"] == 1

    second_page = await app_client.get(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        params={"limit": 1, "offset": 1},
        headers=_headers(chat_case.token, request_id="history-list-2"),
    )
    assert second_page.status_code == 200, second_page.text
    assert second_page.json()["messages"][0]["conversation_id"] == conversation_id
    assert second_page.json()["messages"][0]["role"] == "assistant"
    assert "MockModelProvider response" in second_page.json()["messages"][0]["content"]
    assert second_page.json()["pagination"]["next_offset"] is None


@pytest.mark.asyncio
async def test_completed_idempotency_key_replays_without_duplicate_messages_or_usage(
    app_client: AsyncClient,
    db: Database,
    chat_case: ChatCase,
) -> None:
    conversation_id = await _create_conversation(app_client, chat_case)
    before_usage = await _usage_count(db, chat_case.org.id)
    payload = _chat_payload("Replay this completed operation.")

    first_response = await app_client.post(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        json=payload,
        headers=_headers(chat_case.token, request_id="idem-req-1", idempotency_key="same-key"),
    )
    second_response = await app_client.post(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        json=payload,
        headers=_headers(chat_case.token, request_id="idem-req-2", idempotency_key="same-key"),
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    assert _assistant_text(second_response.text) == _assistant_text(first_response.text)
    assert await _message_count(db, chat_case.org.id) == 2
    assert await _usage_count(db, chat_case.org.id) == before_usage + 1


@pytest.mark.asyncio
async def test_idempotency_key_reuse_with_different_payload_returns_conflict(
    app_client: AsyncClient,
    chat_case: ChatCase,
) -> None:
    conversation_id = await _create_conversation(app_client, chat_case)

    first_response = await app_client.post(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        json=_chat_payload("The original semantic payload."),
        headers=_headers(
            chat_case.token,
            request_id="conflict-req-1",
            idempotency_key="conflict-key",
        ),
    )
    second_response = await app_client.post(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        json=_chat_payload("A different semantic payload."),
        headers=_headers(
            chat_case.token,
            request_id="conflict-req-2",
            idempotency_key="conflict-key",
        ),
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 409


@pytest.mark.asyncio
async def test_chat_validates_conversation_before_provider_is_called(
    app_client: AsyncClient,
    chat_case: ChatCase,
) -> None:
    missing_conversation_id = uuid4()

    response = await app_client.post(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{missing_conversation_id}/messages",
        json=_chat_payload("[[mock:unavailable]]"),
        headers=_headers(
            chat_case.token,
            request_id="missing-conv-req",
            idempotency_key="missing-conv",
        ),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_message_history_does_not_cross_tenants(
    app_client: AsyncClient,
    db: Database,
    settings: Settings,
    chat_case: ChatCase,
) -> None:
    conversation_id = await _create_conversation(app_client, chat_case)
    chat_response = await app_client.post(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        json=_chat_payload("Tenant A history must stay private."),
        headers=_headers(
            chat_case.token,
            request_id="tenant-a-chat",
            idempotency_key="tenant-a-chat",
        ),
    )
    assert chat_response.status_code == 200, chat_response.text

    suffix = uuid4().hex[:8]
    org_b = Organization(slug=f"chat-m10-b-{suffix}", display_name="Chat M10 Org B")
    async with db.session() as session:
        session.add(org_b)
        await session.flush()
        user_b = User(
            org_id=org_b.id,
            identity_provider_id=f"test-idp|chat-m10-b-{suffix}",
            email=f"chat-m10-b-{suffix}@cyberai.dev",
            display_name="Chat M10 User B",
        )
        session.add(user_b)
        await session.flush()
    token_b = jwt.encode(
        {"sub": str(user_b.id), "exp": int(datetime.now(UTC).timestamp()) + 3600},
        settings.auth.jwt_secret,
        algorithm="HS256",
    )

    response = await app_client.get(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        headers=_headers(token_b, request_id="tenant-b-history"),
    )

    assert response.status_code == 404
    async with db.session() as session:
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_b.id})
        await session.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_b.id})


@pytest.mark.asyncio
async def test_chat_rag_uses_project_scoped_retriever(
    app_client: AsyncClient,
    db: Database,
    chat_case: ChatCase,
) -> None:
    async with db.session() as session:
        session.add(SubscriptionModel(org_id=chat_case.org.id, plan_key="pro", status="active"))

    document_response = await app_client.post(
        f"/api/v1/projects/{chat_case.project.id}/documents",
        json={
            "title": "Alpha runbook",
            "content": "Alpha incident runbook says rotate credentials and isolate hosts.",
            "source_type": "text",
        },
        headers=_headers(chat_case.token, request_id="rag-doc-create"),
    )
    assert document_response.status_code == 200, document_response.text
    conversation_id = await _create_conversation(app_client, chat_case)

    chat_response = await app_client.post(
        f"/api/v1/projects/{chat_case.project.id}/conversations/{conversation_id}/messages",
        json=_chat_payload("What does the Alpha runbook say?", rag_enabled=True),
        headers=_headers(chat_case.token, request_id="rag-chat-req", idempotency_key="rag-chat"),
    )

    assert chat_response.status_code == 200, chat_response.text
    assert "Received 2 message(s)" in _assistant_text(chat_response.text)
