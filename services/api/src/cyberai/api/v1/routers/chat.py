"""Chat completion endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cyberai.api.deps import OrchestratorServiceDep
from cyberai.core.context import current_context
from cyberai.modules.inference import Message as InferenceMessage
from cyberai.modules.inference import Role, TextDelta
from cyberai.modules.modelgw.types import (
    CompletionCompleted,
    CompletionStarted,
    RequestPrincipal,
)

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: Role
    content: str


class ChatCompletionRequestPayload(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None
    max_tokens: int = Field(default=1024, gt=0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)





@router.post("/chat/completions", summary="Stream a chat completion")
async def chat_completions(
    payload: ChatCompletionRequestPayload,
    orchestrator: OrchestratorServiceDep,
) -> StreamingResponse:
    """Stream a response via the AI Orchestrator boundary."""
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
                data = {
                    "event": "delta",
                    "text": event.text,
                }
                yield f"data: {json.dumps(data)}\n\n"
            elif isinstance(event, CompletionCompleted):
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

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
    )
