"""Tests for Documents API and RAG Ingestion (M3)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from cyberai.platform.db.models import Project


@pytest.mark.asyncio
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
        "source_type": "text"
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
