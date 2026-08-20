"""AI Orchestrator Service.

M0 boundary: forwards requests to the Model Gateway.
Future M2+: Memory, RAG, Policy, Prompt Injection Defense will be hooked here.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from cyberai.core.logging import get_logger
from cyberai.modules.inference.types import Message, Role
from cyberai.modules.modelgw.gateway import ModelGateway
from cyberai.modules.modelgw.types import (
    CompletionRequest,
    GatewayEvent,
    RequestPrincipal,
    TaskType,
)
from cyberai.modules.rag.abstractions import Retriever
from cyberai.observability.metrics import MetricsRecorder, NoopMetricsRecorder
from cyberai.observability.tracing import record_exception, start_span

logger = get_logger(__name__)


class OrchestratorService:
    """The central brain for AI operations."""

    def __init__(
        self,
        model_gateway: ModelGateway,
        *,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._model_gateway = model_gateway
        self._metrics = metrics or NoopMetricsRecorder()

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
        started = time.perf_counter()
        messages_list = list(messages)
        rag_enabled = retriever is not None
        retrieved_chunks = 0
        retrieval_latency_seconds = 0.0
        status = "success"

        with start_span(
            "ai.orchestrator",
            {"ai.rag_enabled": rag_enabled},
        ) as span:
            try:
                if retriever and messages_list:
                    # We assume the last user message is the query for RAG
                    last_msg = messages_list[-1]
                    if last_msg.role == Role.USER and last_msg.content:
                        retrieval_started = time.perf_counter()
                        chunks = await retriever.retrieve(query=last_msg.content, top_k=3)
                        retrieval_latency_seconds = time.perf_counter() - retrieval_started
                        retrieved_chunks = len(chunks)
                        span.set_attribute("ai.rag_chunks", retrieved_chunks)
                        if chunks:
                            context_blocks = [f"- {c.content}" for c in chunks]
                            context_str = "\n".join(context_blocks)
                            rag_prompt = (
                                "=== KNOWLEDGE BASE ===\n"
                                "Use the following retrieved context to answer "
                                "the user's question.\n"
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
                                messages_list.insert(
                                    0, Message(role=Role.SYSTEM, content=rag_prompt)
                                )

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
            except Exception as exc:
                status = "error"
                logger.exception("orchestrator.stream_failed", error=type(exc).__name__)
                record_exception(span, exc, attributes={"error.type": type(exc).__name__})
                raise
            finally:
                duration_seconds = time.perf_counter() - started
                labels = {"task": "chat", "rag_enabled": str(rag_enabled).lower(), "status": status}
                self._metrics.counter("ai_orchestrator_requests_total", labels=labels).add()
                self._metrics.histogram("ai_orchestrator_duration_seconds", labels=labels).record(
                    duration_seconds
                )
                if rag_enabled:
                    self._metrics.histogram(
                        "rag_retrieval_duration_seconds",
                        labels={"top_k": "3", "status": status},
                    ).record(retrieval_latency_seconds)
                    self._metrics.gauge(
                        "rag_chunks_returned",
                        labels={"top_k": "3", "status": status},
                    ).set(retrieved_chunks)
