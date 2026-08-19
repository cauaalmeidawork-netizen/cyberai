"""AI Orchestrator Service.

M0 boundary: forwards requests to the Model Gateway.
Future M2+: Memory, RAG, Policy, Prompt Injection Defense will be hooked here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from cyberai.modules.inference.types import Message, Role
from cyberai.modules.modelgw.gateway import ModelGateway
from cyberai.modules.modelgw.types import (
    CompletionRequest,
    GatewayEvent,
    RequestPrincipal,
    TaskType,
)
from cyberai.modules.rag.abstractions import Retriever


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
        retriever: Retriever | None = None,
    ) -> AsyncIterator[GatewayEvent]:
        """Stream a chat completion, potentially augmented by RAG."""
        messages_list = list(messages)

        if retriever and messages_list:
            # We assume the last user message is the query for RAG
            last_msg = messages_list[-1]
            if last_msg.role == Role.USER and last_msg.content:
                # Retrieve relevant chunks
                chunks = await retriever.retrieve(query=last_msg.content, top_k=3)
                if chunks:
                    context_blocks = [f"- {c.content}" for c in chunks]
                    context_str = "\n".join(context_blocks)
                    rag_prompt = (
                        "=== KNOWLEDGE BASE ===\n"
                        "Use the following retrieved context to answer the user's question.\n"
                        f"{context_str}\n"
                        "======================"
                    )

                    # Prepend RAG context to the system message or first user message
                    if messages_list[0].role == Role.SYSTEM:
                        messages_list[0] = Message(
                            role=Role.SYSTEM,
                            content=f"{messages_list[0].content}\n\n{rag_prompt}",
                        )
                    else:
                        messages_list.insert(0, Message(role=Role.SYSTEM, content=rag_prompt))

        request = CompletionRequest(
            messages=tuple(messages_list),
            task=TaskType.CHAT,
            model_key=model,
            max_output_tokens=max_tokens,
            temperature=temperature,
            principal=principal,
        )
        async for event in self._model_gateway.stream(request):
            yield event
