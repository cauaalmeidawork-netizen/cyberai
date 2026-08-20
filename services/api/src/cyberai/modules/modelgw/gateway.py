"""The Model Gateway.

Responsibility: *which* model answers, what happens when it cannot, and what
the call cost. It resolves a route, drives the fallback chain and emits exactly
one usage record per request.

One rule shapes the fallback logic: **failover is only safe before the first
token reaches the caller.** Once output has been streamed, switching models
would splice two different answers together, so a mid-stream failure is
surfaced as an error rather than silently retried. Getting this wrong produces
corrupted responses that are nearly impossible to reproduce.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from cyberai.core.logging import get_logger
from cyberai.modules.inference import (
    FinishReason,
    InferenceError,
    InferenceGateway,
    InferenceRequest,
    StreamCompleted,
    TextDelta,
    TokenUsage,
)
from cyberai.modules.modelgw.errors import NoModelAvailableError
from cyberai.modules.modelgw.routing import ModelRouter
from cyberai.modules.modelgw.types import (
    CompletionCompleted,
    CompletionRequest,
    CompletionStarted,
    GatewayEvent,
    ModelSpec,
    TaskType,
)
from cyberai.modules.modelgw.usage import (
    LoggingUsageSink,
    UsageRecord,
    UsageSink,
    UsageStatus,
    estimate_cost_usd,
)
from cyberai.observability.metrics import MetricsRecorder, NoopMetricsRecorder
from cyberai.observability.tracing import record_exception, start_span

logger = get_logger(__name__)


class ModelGateway:
    """Routes a completion request to a model and accounts for the result."""

    def __init__(
        self,
        router: ModelRouter,
        inference: InferenceGateway,
        usage_sink: UsageSink | None = None,
        *,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._router = router
        self._inference = inference
        self._usage_sink: UsageSink = usage_sink or LoggingUsageSink()
        self._metrics = metrics or NoopMetricsRecorder()

    async def stream(self, request: CompletionRequest) -> AsyncIterator[GatewayEvent]:
        """Stream a completion, failing over to the next candidate when safe.

        Yields:
            ``CompletionStarted`` once the answering model is known, then
            ``TextDelta`` events, then exactly one ``CompletionCompleted``.

        Raises:
            ModelNotFoundError: an explicitly requested model cannot serve this request.
            NoModelAvailableError: every candidate failed before producing output.
            InferenceError: a candidate failed after output had already been streamed.
        """
        routing_started = time.perf_counter()
        with start_span("model_gateway.route", {"ai.task": request.task.value}) as route_span:
            try:
                route = self._router.resolve(request.task, requested_model=request.model_key)
            except Exception as exc:
                self._metrics.counter(
                    "model_gateway_requests_total",
                    labels={
                        "task": request.task.value,
                        "model": "none",
                        "provider": "none",
                        "status": "routing_error",
                    },
                ).add()
                record_exception(route_span, exc, attributes={"error.type": type(exc).__name__})
                raise
            finally:
                routing_latency = time.perf_counter() - routing_started
                self._metrics.histogram(
                    "model_gateway_duration_seconds",
                    labels={
                        "task": request.task.value,
                        "model": "none",
                        "provider": "none",
                        "status": "success",
                        "phase": "routing",
                    },
                ).record(routing_latency)
            route_span.set_attribute("ai.model.selected", route.primary.key)
        last_error: InferenceError | None = None

        for attempt, model in enumerate(route.candidates, start=1):
            is_fallback = attempt > 1
            started = time.perf_counter()
            first_token_at: float | None = None
            emitted_output = False
            usage = TokenUsage()
            finish_reason = None

            inference_request = self._build_request(request, model)

            try:
                if is_fallback:
                    self._metrics.counter(
                        "model_gateway_fallbacks_total",
                        labels={
                            "task": request.task.value,
                            "model": model.key,
                            "provider": model.provider,
                        },
                    ).add()
                yield CompletionStarted(
                    model_key=model.key,
                    provider=model.provider,
                    attempt=attempt,
                    is_fallback=is_fallback,
                )

                async for event in self._inference.invoke(model.target, inference_request):
                    if isinstance(event, TextDelta):
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        emitted_output = True
                        yield event
                    elif isinstance(event, StreamCompleted):
                        usage = event.usage
                        finish_reason = event.finish_reason

            except InferenceError as exc:
                self._metrics.counter(
                    "model_gateway_requests_total",
                    labels={
                        "task": request.task.value,
                        "model": model.key,
                        "provider": model.provider,
                        "status": "failed",
                    },
                ).add()
                await self._emit_usage(
                    request,
                    model,
                    usage=usage,
                    started=started,
                    first_token_at=first_token_at,
                    attempt=attempt,
                    is_fallback=is_fallback,
                    status=UsageStatus.FAILED,
                    finish_reason=None,
                    error_code=exc.code,
                )
                if emitted_output:
                    # Output already reached the caller: splicing a second
                    # model's answer onto it would corrupt the response.
                    logger.error(
                        "modelgw.failure_after_output",
                        model_key=model.key,
                        provider=model.provider,
                        error_code=exc.code,
                        request_id=request.principal.request_id,
                    )
                    raise
                if not exc.can_failover:
                    raise
                last_error = exc
                logger.warning(
                    "modelgw.failover",
                    from_model=model.key,
                    provider=model.provider,
                    error_code=exc.code,
                    attempt=attempt,
                    remaining_candidates=len(route.candidates) - attempt,
                    request_id=request.principal.request_id,
                )
                continue

            record = await self._emit_usage(
                request,
                model,
                usage=usage,
                started=started,
                first_token_at=first_token_at,
                attempt=attempt,
                is_fallback=is_fallback,
                status=UsageStatus.SUCCESS,
                finish_reason=finish_reason.value if finish_reason else None,
                error_code=None,
            )
            yield CompletionCompleted(
                model_key=model.key,
                provider=model.provider,
                # The Inference Gateway guarantees a terminal event, so this
                # default is unreachable defence rather than a real fallback.
                finish_reason=finish_reason or FinishReason.STOP,
                usage=usage,
                record=record,
            )
            self._metrics.counter(
                "model_gateway_requests_total",
                labels={
                    "task": request.task.value,
                    "model": model.key,
                    "provider": model.provider,
                    "status": "success",
                },
            ).add()
            self._metrics.histogram(
                "model_gateway_duration_seconds",
                labels={
                    "task": request.task.value,
                    "model": model.key,
                    "provider": model.provider,
                    "status": "success",
                    "phase": "completion",
                },
            ).record(time.perf_counter() - started)
            return

        self._metrics.counter(
            "model_gateway_requests_total",
            labels={
                "task": request.task.value,
                "model": "none",
                "provider": "none",
                "status": "no_model_available",
            },
        ).add()
        raise NoModelAvailableError(
            "Every candidate model failed to serve this request."
        ) from last_error

    # --- internals -----------------------------------------------------------

    def _build_request(self, request: CompletionRequest, model: ModelSpec) -> InferenceRequest:
        """Clamp the request to what the chosen model can actually do."""
        return InferenceRequest(
            provider_model=model.provider_model,
            messages=request.messages,
            max_output_tokens=min(request.max_output_tokens, model.max_output_tokens),
            temperature=request.temperature,
            request_id=request.principal.request_id,
        )

    async def _emit_usage(
        self,
        request: CompletionRequest,
        model: ModelSpec,
        *,
        usage: TokenUsage,
        started: float,
        first_token_at: float | None,
        attempt: int,
        is_fallback: bool,
        status: UsageStatus,
        finish_reason: str | None,
        error_code: str | None,
    ) -> UsageRecord:
        now = time.perf_counter()
        record = UsageRecord(
            request_id=request.principal.request_id,
            organization_id=request.principal.org_id,
            user_id=request.principal.user_id,
            provider=model.provider,
            model_key=model.key,
            provider_model=model.provider_model,
            task=request.task.value if isinstance(request.task, TaskType) else str(request.task),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            latency_ms=(now - started) * 1000,
            time_to_first_token_ms=(
                (first_token_at - started) * 1000 if first_token_at is not None else None
            ),
            attempts=attempt,
            used_fallback=is_fallback,
            status=status,
            finish_reason=finish_reason,
            error_code=error_code,
            estimated_cost_usd=estimate_cost_usd(
                usage,
                input_cost_per_mtok=model.input_cost_per_mtok,
                output_cost_per_mtok=model.output_cost_per_mtok,
                cached_input_cost_per_mtok=model.cached_input_cost_per_mtok,
            ),
        )
        try:
            await self._usage_sink.record(record)
        except Exception:
            logger.exception("modelgw.usage_sink_failed", model_key=model.key)
        return record
