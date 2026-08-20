"""Tests for Documents API and RAG Ingestion (M3)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from cyberai.core.config import Settings
from cyberai.platform.db import Database
from cyberai.platform.db.models import Organization, Project, User


@pytest.mark.asyncio
@pytest.mark.integration
async def test_document_lifecycle(
    app_client: AsyncClient,
    test_user_token: str,
    test_project: Project,
) -> None:
    headers = {"Authorization": f"Bearer {test_user_token}"}
    project_id = test_project.id

    # 1. Create a document
    doc_payload = {
        "title": "Test Knowledge Base",
        "content": "CyberAI is an advanced autonomous agent platform.",
        "source_type": "text",
    }

    create_resp = await app_client.post(
        f"/api/v1/projects/{project_id}/documents",
        json=doc_payload,
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    doc_data = create_resp.json()
    assert doc_data["title"] == "Test Knowledge Base"
    assert doc_data["status"] == "completed"
    doc_id = doc_data["id"]

    # 2. Try duplicate document (should 409)
    dup_resp = await app_client.post(
        f"/api/v1/projects/{project_id}/documents",
        json=doc_payload,
        headers=headers,
    )
    assert dup_resp.status_code == 409

    # 3. List documents
    list_resp = await app_client.get(
        f"/api/v1/projects/{project_id}/documents",
        headers=headers,
    )
    assert list_resp.status_code == 200
    docs = list_resp.json()
    assert len(docs) >= 1
    assert any(d["id"] == doc_id for d in docs)

    # 4. Get specific document
    get_resp = await app_client.get(
        f"/api/v1/projects/{project_id}/documents/{doc_id}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == doc_id

    # 5. Retrieve from RAG (MockEmbeddingProvider will find the chunks)
    retrieve_resp = await app_client.post(
        f"/api/v1/projects/{project_id}/rag/retrieve",
        json={"query": "What is CyberAI?", "top_k": 3},
        headers=headers,
    )
    assert retrieve_resp.status_code == 200
    chunks = retrieve_resp.json()
    assert isinstance(chunks, list)
    if chunks:
        assert "CyberAI" in chunks[0]["content"]

    # 6. Delete document
    del_resp = await app_client.delete(
        f"/api/v1/projects/{project_id}/documents/{doc_id}",
        headers=headers,
    )
    assert del_resp.status_code == 204

    # 7. Ensure it's deleted
    get_again = await app_client.get(
        f"/api/v1/projects/{project_id}/documents/{doc_id}",
        headers=headers,
    )
    assert get_again.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
async def test_document_rag_endpoints_do_not_cross_tenants(
    app_client: AsyncClient,
    db: Database,
    settings: Settings,
    test_user_token: str,
    test_project: Project,
) -> None:
    """A user from org B must not observe or mutate org A documents/chunks."""
    suffix = uuid4().hex[:8]
    org_b = Organization(slug=f"tenant-b-docs-{suffix}", display_name="Tenant B")
    async with db.session() as session:
        session.add(org_b)
        await session.flush()
        user_b = User(
            org_id=org_b.id,
            identity_provider_id=f"test-idp|tenant-b-docs-{suffix}",
            email=f"tenant-b-docs-{suffix}@cyberai.dev",
            display_name="Tenant B User",
        )
        session.add(user_b)
        await session.flush()

    token_b = jwt.encode(
        {
            "sub": str(user_b.id),
            "exp": int(datetime.now(UTC).timestamp()) + 3600,
        },
        settings.auth.jwt_secret,
        algorithm="HS256",
    )
    headers_a = {"Authorization": f"Bearer {test_user_token}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    create_resp = await app_client.post(
        f"/api/v1/projects/{test_project.id}/documents",
        json={
            "title": "Tenant A Knowledge",
            "content": "Tenant A confidential RAG content about project Alpha.",
            "source_type": "text",
        },
        headers=headers_a,
    )
    assert create_resp.status_code == 200, create_resp.text
    doc_id = create_resp.json()["id"]

    list_resp = await app_client.get(
        f"/api/v1/projects/{test_project.id}/documents",
        headers=headers_b,
    )
    assert list_resp.status_code == 404

    get_resp = await app_client.get(
        f"/api/v1/projects/{test_project.id}/documents/{doc_id}",
        headers=headers_b,
    )
    assert get_resp.status_code == 404

    retrieve_resp = await app_client.post(
        f"/api/v1/projects/{test_project.id}/rag/retrieve",
        json={"query": "project Alpha", "top_k": 3},
        headers=headers_b,
    )
    assert retrieve_resp.status_code == 404

    delete_resp = await app_client.delete(
        f"/api/v1/projects/{test_project.id}/documents/{doc_id}",
        headers=headers_b,
    )
    assert delete_resp.status_code == 404

    still_exists_resp = await app_client.get(
        f"/api/v1/projects/{test_project.id}/documents/{doc_id}",
        headers=headers_a,
    )
    assert still_exists_resp.status_code == 200

    cleanup_resp = await app_client.delete(
        f"/api/v1/projects/{test_project.id}/documents/{doc_id}",
        headers=headers_a,
    )
    assert cleanup_resp.status_code == 204

    async with db.session() as session:
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_b.id})
        await session.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_b.id})
