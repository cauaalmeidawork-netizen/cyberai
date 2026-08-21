"""Conversations, message history and chat streaming."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cyberai.api.auth import CurrentUserDep, Permission, require_csrf, require_permission
from cyberai.api.deps import DatabaseDep, MetricsDep, OrchestratorServiceDep, SettingsDep
from cyberai.api.v1.routers.documents import build_rag_service
from cyberai.core.context import current_context
from cyberai.modules.inference import Message as InferenceMessage
from cyberai.modules.inference import Role, TextDelta
from cyberai.modules.modelgw.types import (
    CompletionCompleted,
    CompletionStarted,
    RequestPrincipal,
)
from cyberai.modules.rag.abstractions import RetrievedChunk
from cyberai.observability.metrics import MetricsRecorder
from cyberai.platform.db import Database
from cyberai.platform.db.models import ChatIdempotencyKey, Conversation, Project
from cyberai.platform.db.models import Message as DBMessage
from cyberai.platform.db.tenant import TenantContext

router = APIRouter(tags=["conversations"], prefix="/projects/{project_id}/conversations")

_IDEMPOTENCY_COMPLETED = "completed"
_IDEMPOTENCY_FAILED = "failed"
_IDEMPOTENCY_IN_PROGRESS = "in_progress"


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
    rag_enabled: bool = False


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    tokens_used: int | None
    created_at: datetime


class PaginationOut(BaseModel):
    limit: int
    offset: int
    next_offset: int | None


class MessagePageOut(BaseModel):
    messages: list[MessageOut]
    pagination: PaginationOut


class ChatCompletionResult(BaseModel):
    started: dict[str, Any] | None = None
    assistant_content: str
    completed: dict[str, Any]


class ProjectRagRetriever:
    """Opens a tenant-scoped RAG session only for retrieval."""

    def __init__(
        self,
        db: Database,
        *,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        metrics: MetricsRecorder,
    ) -> None:
        self._db = db
        self._org_id = org_id
        self._project_id = project_id
        self._metrics = metrics

    async def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        async with self._db.session(TenantContext(org_id=self._org_id)) as session:
            rag_service = build_rag_service(
                session,
                org_id=self._org_id,
                project_id=self._project_id,
                metrics=self._metrics,
            )
            return await rag_service.retrieve(query, top_k=top_k)


@router.post("", response_model=ConversationOut)
async def create_conversation(
    project_id: uuid.UUID,
    payload: ConversationCreate,
    user: CurrentUserDep,
    db: DatabaseDep,
    request: Request,
    settings: SettingsDep,
) -> ConversationOut:
    """Create a new conversation thread within a project."""
    require_permission(user, Permission.CONVERSATION_WRITE)
    await require_csrf(request=request, db=db, settings=settings)
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        await _project_or_404(session, project_id=project_id, org_id=user.org_id)
        conv = Conversation(
            org_id=user.org_id,
            project_id=project_id,
            title=payload.title,
            created_by_user_id=user.id,
        )
        session.add(conv)
        await session.flush()
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
) -> list[ConversationOut]:
    """List all conversations within a project."""
    require_permission(user, Permission.CONVERSATION_READ)
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        await _project_or_404(session, project_id=project_id, org_id=user.org_id)
        result = await session.execute(
            select(Conversation)
            .where(Conversation.project_id == project_id, Conversation.org_id == user.org_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        )
        return [
            ConversationOut(
                id=str(c.id),
                project_id=str(c.project_id),
                title=c.title,
            )
            for c in result.scalars()
        ]


@router.get("/{conversation_id}/messages", response_model=MessagePageOut)
async def list_messages(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MessagePageOut:
    """List persisted messages in deterministic order."""
    require_permission(user, Permission.CONVERSATION_READ)
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        await _conversation_or_404(
            session,
            project_id=project_id,
            conversation_id=conversation_id,
            org_id=user.org_id,
        )
        result = await session.execute(
            select(DBMessage)
            .where(DBMessage.conversation_id == conversation_id, DBMessage.org_id == user.org_id)
            .order_by(DBMessage.created_at.asc(), DBMessage.id.asc())
            .limit(limit + 1)
            .offset(offset)
        )
        rows = list(result.scalars())
    page_rows = rows[:limit]
    return MessagePageOut(
        messages=[
            MessageOut(
                id=str(message.id),
                conversation_id=str(message.conversation_id),
                role=message.role,
                content=message.content,
                tokens_used=message.tokens_used,
                created_at=message.created_at,
            )
            for message in page_rows
        ],
        pagination=PaginationOut(
            limit=limit,
            offset=offset,
            next_offset=offset + limit if len(rows) > limit else None,
        ),
    )


@router.post("/{conversation_id}/messages", summary="Stream a chat response within a conversation")
async def stream_conversation_messages(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatCompletionRequestPayload,
    user: CurrentUserDep,
    db: DatabaseDep,
    orchestrator: OrchestratorServiceDep,
    metrics: MetricsDep,
    request: Request,
    settings: SettingsDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> StreamingResponse:
    """Send a message to a conversation and stream the AI response."""
    require_permission(user, Permission.CONVERSATION_WRITE)
    await require_csrf(request=request, db=db, settings=settings)
    normalized_key = _normalize_idempotency_key(idempotency_key)
    request_hash = _request_hash(payload)
    replay = await _prepare_or_replay_idempotency(
        db=db,
        org_id=user.org_id,
        project_id=project_id,
        conversation_id=conversation_id,
        key=normalized_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return _streaming_response(replay)

    ctx = current_context()
    principal = RequestPrincipal(
        org_id=ctx.org_id,
        user_id=ctx.user_id,
        request_id=ctx.request_id,
    )
    messages = tuple(InferenceMessage(role=m.role, content=m.content) for m in payload.messages)
    retriever = (
        ProjectRagRetriever(db, org_id=user.org_id, project_id=project_id, metrics=metrics)
        if payload.rag_enabled
        else None
    )

    try:
        result = await _collect_completion(
            orchestrator=orchestrator,
            messages=messages,
            payload=payload,
            principal=principal,
            retriever=retriever,
        )
        await _persist_chat_result(
            db=db,
            org_id=user.org_id,
            project_id=project_id,
            conversation_id=conversation_id,
            payload=payload,
            idempotency_key=normalized_key,
            request_hash=request_hash,
            result=result,
        )
    except Exception:
        if normalized_key is not None:
            await _mark_idempotency_failed(
                db=db,
                org_id=user.org_id,
                conversation_id=conversation_id,
                key=normalized_key,
                request_hash=request_hash,
            )
        raise

    return _streaming_response(result)


async def _project_or_404(
    session: AsyncSession, *, project_id: uuid.UUID, org_id: uuid.UUID
) -> Project:
    project = cast(
        Project | None,
        await session.scalar(
            select(Project).where(Project.id == project_id, Project.org_id == org_id)
        ),
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _conversation_or_404(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Conversation:
    conversation = cast(
        Conversation | None,
        await session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.project_id == project_id,
                Conversation.org_id == org_id,
            )
        ),
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _normalize_idempotency_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Idempotency-Key must not be empty")
    if len(value) > 128:
        raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
    return value


def _request_hash(payload: ChatCompletionRequestPayload) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _prepare_or_replay_idempotency(
    *,
    db: Database,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    key: str | None,
    request_hash: str,
) -> ChatCompletionResult | None:
    async with db.session(TenantContext(org_id=org_id)) as session:
        await _conversation_or_404(
            session,
            project_id=project_id,
            conversation_id=conversation_id,
            org_id=org_id,
        )
        if key is None:
            return None

        record = await session.scalar(
            select(ChatIdempotencyKey)
            .where(
                ChatIdempotencyKey.org_id == org_id,
                ChatIdempotencyKey.conversation_id == conversation_id,
                ChatIdempotencyKey.idempotency_key == key,
            )
            .with_for_update()
        )
        if record is None:
            session.add(
                ChatIdempotencyKey(
                    org_id=org_id,
                    conversation_id=conversation_id,
                    idempotency_key=key,
                    request_hash=request_hash,
                    status=_IDEMPOTENCY_IN_PROGRESS,
                    input_tokens=0,
                    output_tokens=0,
                    is_fallback=False,
                )
            )
            return None

        if record.request_hash != request_hash:
            raise HTTPException(status_code=409, detail="Idempotency-Key payload conflict")
        if record.status == _IDEMPOTENCY_COMPLETED:
            return await _replay_completed(session, record)
        if record.status == _IDEMPOTENCY_IN_PROGRESS:
            raise HTTPException(status_code=409, detail="Idempotent operation is still in progress")

        record.status = _IDEMPOTENCY_IN_PROGRESS
        record.user_message_id = None
        record.assistant_message_id = None
        record.model_key = None
        record.provider = None
        record.finish_reason = None
        record.input_tokens = 0
        record.output_tokens = 0
        record.is_fallback = False
        record.completed_at = None
        session.add(record)
        return None


async def _replay_completed(session: Any, record: ChatIdempotencyKey) -> ChatCompletionResult:
    if record.assistant_message_id is None:
        raise HTTPException(status_code=409, detail="Idempotency replay is unavailable")
    assistant_message = await session.scalar(
        select(DBMessage).where(
            DBMessage.id == record.assistant_message_id,
            DBMessage.org_id == record.org_id,
            DBMessage.conversation_id == record.conversation_id,
        )
    )
    if assistant_message is None:
        raise HTTPException(status_code=409, detail="Idempotency replay is unavailable")
    return ChatCompletionResult(
        started={
            "event": "started",
            "model": record.model_key or "unknown",
            "is_fallback": record.is_fallback,
        },
        assistant_content=assistant_message.content,
        completed={
            "event": "completed",
            "finish_reason": record.finish_reason or "stop",
            "usage": {
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
            },
        },
    )


async def _collect_completion(
    *,
    orchestrator: Any,
    messages: tuple[InferenceMessage, ...],
    payload: ChatCompletionRequestPayload,
    principal: RequestPrincipal,
    retriever: ProjectRagRetriever | None,
) -> ChatCompletionResult:
    started: dict[str, Any] | None = None
    completed: dict[str, Any] | None = None
    assistant_parts: list[str] = []

    async for event in orchestrator.stream_chat(
        messages=messages,
        model=payload.model,
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
        principal=principal,
        retriever=retriever,
    ):
        if isinstance(event, CompletionStarted):
            started = {
                "event": "started",
                "model": event.model_key,
                "is_fallback": event.is_fallback,
            }
        elif isinstance(event, TextDelta):
            assistant_parts.append(event.text)
        elif isinstance(event, CompletionCompleted):
            completed = {
                "event": "completed",
                "finish_reason": event.finish_reason.value,
                "usage": {
                    "input_tokens": event.usage.input_tokens,
                    "output_tokens": event.usage.output_tokens,
                },
                "model": event.model_key,
                "provider": event.provider,
            }

    if completed is None:
        raise HTTPException(status_code=503, detail="Provider did not complete the response")
    return ChatCompletionResult(
        started=started,
        assistant_content="".join(assistant_parts),
        completed=completed,
    )


async def _persist_chat_result(
    *,
    db: Database,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatCompletionRequestPayload,
    idempotency_key: str | None,
    request_hash: str,
    result: ChatCompletionResult,
) -> None:
    # The provider call and database commit are intentionally not a distributed
    # transaction. A client only receives completed/[DONE] after this commit;
    # retries after a committed result are replayed by Idempotency-Key.
    try:
        async with db.session(TenantContext(org_id=org_id)) as session:
            await _conversation_or_404(
                session,
                project_id=project_id,
                conversation_id=conversation_id,
                org_id=org_id,
            )
            last_user = payload.messages[-1]
            user_message = DBMessage(
                org_id=org_id,
                conversation_id=conversation_id,
                role=last_user.role.value,
                content=last_user.content,
            )
            assistant_message = DBMessage(
                org_id=org_id,
                conversation_id=conversation_id,
                role=Role.ASSISTANT.value,
                content=result.assistant_content,
                tokens_used=int(result.completed["usage"]["output_tokens"]),
            )
            session.add_all([user_message, assistant_message])
            await session.flush()

            if idempotency_key is not None:
                record = await session.scalar(
                    select(ChatIdempotencyKey)
                    .where(
                        ChatIdempotencyKey.org_id == org_id,
                        ChatIdempotencyKey.conversation_id == conversation_id,
                        ChatIdempotencyKey.idempotency_key == idempotency_key,
                    )
                    .with_for_update()
                )
                if record is None:
                    record = ChatIdempotencyKey(
                        org_id=org_id,
                        conversation_id=conversation_id,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        status=_IDEMPOTENCY_IN_PROGRESS,
                    )
                if record.request_hash != request_hash:
                    raise HTTPException(status_code=409, detail="Idempotency-Key payload conflict")
                if record.status == _IDEMPOTENCY_COMPLETED:
                    raise HTTPException(status_code=409, detail="Idempotency-Key already completed")

                record.status = _IDEMPOTENCY_COMPLETED
                record.user_message_id = user_message.id
                record.assistant_message_id = assistant_message.id
                record.model_key = str(result.completed.get("model") or "")
                record.provider = str(result.completed.get("provider") or "")
                record.finish_reason = str(result.completed["finish_reason"])
                record.input_tokens = int(result.completed["usage"]["input_tokens"])
                record.output_tokens = int(result.completed["usage"]["output_tokens"])
                record.is_fallback = bool((result.started or {}).get("is_fallback", False))
                record.completed_at = datetime.now(UTC)
                session.add(record)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Idempotency-Key conflict") from exc


async def _mark_idempotency_failed(
    *,
    db: Database,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    key: str,
    request_hash: str,
) -> None:
    async with db.session(TenantContext(org_id=org_id)) as session:
        record = await session.scalar(
            select(ChatIdempotencyKey).where(
                ChatIdempotencyKey.org_id == org_id,
                ChatIdempotencyKey.conversation_id == conversation_id,
                ChatIdempotencyKey.idempotency_key == key,
                ChatIdempotencyKey.request_hash == request_hash,
            )
        )
        if record is not None and record.status == _IDEMPOTENCY_IN_PROGRESS:
            record.status = _IDEMPOTENCY_FAILED
            session.add(record)


def _streaming_response(result: ChatCompletionResult) -> StreamingResponse:
    async def _stream() -> AsyncIterator[str]:
        if result.started is not None:
            yield _sse(result.started)
        if result.assistant_content:
            yield _sse({"event": "delta", "text": result.assistant_content})
        completed = {
            "event": "completed",
            "finish_reason": result.completed["finish_reason"],
            "usage": result.completed["usage"],
        }
        yield _sse(completed)
        yield "data: [DONE]\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"
