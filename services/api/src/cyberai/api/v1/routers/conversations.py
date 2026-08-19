"""Conversations and Messages CRUD."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from cyberai.api.auth import CurrentUserDep
from cyberai.api.deps import DatabaseDep, OrchestratorServiceDep
from cyberai.core.context import current_context
from cyberai.modules.inference import Message as InferenceMessage
from cyberai.modules.inference import Role, TextDelta
from cyberai.modules.modelgw.types import (
    CompletionCompleted,
    CompletionStarted,
    RequestPrincipal,
)
from cyberai.platform.db.models import Conversation
from cyberai.platform.db.models import Message as DBMessage
from cyberai.platform.db.tenant import TenantContext

router = APIRouter(tags=["conversations"], prefix="/projects/{project_id}/conversations")


class ConversationOut(BaseModel):
    id: str
    project_id: str
    title: str


class ConversationCreate(BaseModel):
    title: str


class ChatMessagePayload(BaseModel):
    role: Role
    content: str


class ChatCompletionRequestPayload(BaseModel):
    messages: list[ChatMessagePayload] = Field(min_length=1)
    model: str | None = None
    max_tokens: int = Field(default=1024, gt=0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


@router.post("", response_model=ConversationOut)
async def create_conversation(
    project_id: uuid.UUID,
    payload: ConversationCreate,
    user: CurrentUserDep,
    db: DatabaseDep,
) -> Any:
    """Create a new conversation thread within a project."""
    conv = Conversation(
        org_id=user.org_id,
        project_id=project_id,
        title=payload.title,
        created_by_user_id=user.id,
    )
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
    return ConversationOut(
        id=str(conv.id),
        project_id=str(conv.project_id),
        title=conv.title,
    )


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    project_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep,
) -> Any:
    """List all conversations within a project."""
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.project_id == project_id)
            .order_by(Conversation.created_at.desc())
        )
        return [
            ConversationOut(
                id=str(c.id),
                project_id=str(c.project_id),
                title=c.title,
            )
            for c in result.scalars()
        ]


@router.post("/{conversation_id}/messages", summary="Stream a chat response within a conversation")
async def stream_conversation_messages(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatCompletionRequestPayload,
    user: CurrentUserDep,
    db: DatabaseDep,
    orchestrator: OrchestratorServiceDep,
) -> StreamingResponse:
    """Send a message to a conversation and stream the AI response."""
    ctx = current_context()
    principal = RequestPrincipal(
        org_id=ctx.org_id,
        user_id=ctx.user_id,
        request_id=ctx.request_id,
    )

    messages = tuple(
        InferenceMessage(role=m.role, content=m.content) for m in payload.messages
    )

    async def _stream() -> AsyncIterator[str]:
        assistant_content = ""
        output_tokens = 0

        async for event in orchestrator.stream_chat(
            messages=messages,
            model=payload.model,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
            principal=principal,
        ):
            if isinstance(event, CompletionStarted):
                data = {
                    "event": "started",
                    "model": event.model_key,
                    "is_fallback": event.is_fallback,
                }
                yield f"data: {json.dumps(data)}\n\n"
            elif isinstance(event, TextDelta):
                assistant_content += event.text
                data = {
                    "event": "delta",
                    "text": event.text,
                }
                yield f"data: {json.dumps(data)}\n\n"
            elif isinstance(event, CompletionCompleted):
                output_tokens = event.usage.output_tokens
                data = {
                    "event": "completed",
                    "finish_reason": event.finish_reason.value,
                    "usage": {
                        "input_tokens": event.usage.input_tokens,
                        "output_tokens": event.usage.output_tokens,
                    },
                }
                yield f"data: {json.dumps(data)}\n\n"

        yield "data: [DONE]\n\n"

        # Persist messages after streaming ends
        async with db.session(TenantContext(org_id=user.org_id)) as session:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            if result.scalar_one_or_none():
                # Save the last user message
                last_user = payload.messages[-1]
                db_user_msg = DBMessage(
                    org_id=user.org_id,
                    conversation_id=conversation_id,
                    role=last_user.role.value,
                    content=last_user.content,
                )
                db_asst_msg = DBMessage(
                    org_id=user.org_id,
                    conversation_id=conversation_id,
                    role=Role.ASSISTANT.value,
                    content=assistant_content,
                    tokens_used=output_tokens,
                )
                session.add_all([db_user_msg, db_asst_msg])
                await session.commit()

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
    )
