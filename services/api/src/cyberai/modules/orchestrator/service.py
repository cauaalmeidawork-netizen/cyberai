"""AI Orchestrator Service.

M0 boundary: forwards requests to the Model Gateway.
Future M2+: Memory, RAG, Policy, Prompt Injection Defense will be hooked here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from cyberai.modules.inference.types import Message
from cyberai.modules.modelgw.gateway import ModelGateway
from cyberai.modules.modelgw.types import (
    CompletionRequest,
    GatewayEvent,
    RequestPrincipal,
    TaskType,
)


class OrchestratorService:
    """The central brain for AI operations."""

    def __init__(self, model_gateway: ModelGateway) -> None:
        self._model_gateway = model_gateway

    async def stream_chat(
        self,
        messages: tuple[Message, ...],
        model: str | None,
        max_tokens: int,
        temperature: float,
        principal: RequestPrincipal,
    ) -> AsyncIterator[GatewayEvent]:
        """Stream a chat completion."""
        request = CompletionRequest(
            messages=messages,
            task=TaskType.CHAT,
            model_key=model,
            max_output_tokens=max_tokens,
            temperature=temperature,
            principal=principal,
        )
        async for event in self._model_gateway.stream(request):
            yield event
