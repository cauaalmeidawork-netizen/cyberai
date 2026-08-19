"""The Inference Gateway.

Responsibility: *how* a model is reached. It resolves the provider adapter,
enforces the transport policy (concurrency, first-token and total timeouts,
circuit breaking) and normalises failures into ``InferenceError`` subclasses.

Explicit non-responsibilities: choosing a model, applying fallback across
models, pricing, quotas, prompts, policy. Those belong to the Model Gateway and
the AI Orchestrator above it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from cyberai.core.config import InferenceSettings
from cyberai.core.logging import get_logger
from cyberai.modules.inference.circuit import CircuitBreaker
from cyberai.modules.inference.errors import (
    CircuitOpenError,
    InferenceError,
    ProviderResponseError,
    ProviderTimeoutError,
    UnsupportedModelError,
)
from cyberai.modules.inference.ports import ModelProvider
from cyberai.modules.inference.registry import ProviderRegistry
from cyberai.modules.inference.types import (
    InferenceEvent,
    InferenceRequest,
    ModelCapabilities,
    ProviderHealth,
    StreamCompleted,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class InferenceTarget:
    """One concrete (provider, model) pair, decided by the Model Gateway."""

    provider: str
    provider_model: str


class InferenceGateway:
    """Executes inference requests against registered providers."""

    def __init__(self, registry: ProviderRegistry, settings: InferenceSettings) -> None:
        self._registry = registry
        self._settings = settings
        self._breakers: dict[str, CircuitBreaker] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    # --- introspection -------------------------------------------------------

    def capabilities(self, target: InferenceTarget) -> ModelCapabilities:
        provider = self._resolve(target)
        return provider.capabilities(target.provider_model)

    def count_tokens(self, provider_name: str, text: str) -> int:
        return self._registry.get(provider_name).count_tokens(text)

    async def health(self) -> dict[str, ProviderHealth]:
        """Probe every registered provider. Never raises."""
        results: dict[str, ProviderHealth] = {}
        for provider in self._registry:
            try:
                results[provider.name] = await provider.health()
            except Exception as exc:
                results[provider.name] = ProviderHealth(
                    provider=provider.name, healthy=False, detail=type(exc).__name__
                )
        return results

    def circuit_state(self, provider_name: str) -> str:
        return self._breaker(provider_name).state.value

    # --- execution -----------------------------------------------------------

    async def invoke(
        self, target: InferenceTarget, request: InferenceRequest
    ) -> AsyncIterator[InferenceEvent]:
        """Stream a completion from one target, applying the transport policy.

        Raises:
            InferenceError: a normalised transport or provider failure. Its
                ``can_failover`` attribute tells the caller whether trying
                another model is worthwhile.
        """
        provider = self._resolve(target)
        breaker = self._breaker(target.provider)
        if not breaker.allows_request():
            raise CircuitOpenError(provider=target.provider)

        settings = self._settings
        saw_completion = False

        async with self._semaphore(target.provider):
            try:
                loop = asyncio.get_running_loop()
                # The wait for the first token is budgeted separately: a provider
                # that accepts the connection and then stalls is the common
                # failure mode, and a single end-to-end timeout hides it behind
                # a legitimately long stream.
                async with asyncio.timeout(settings.first_token_timeout_seconds) as timeout:
                    first = True
                    async for event in provider.generate(request):
                        if first:
                            timeout.reschedule(loop.time() + settings.request_timeout_seconds)
                            first = False
                        if isinstance(event, StreamCompleted):
                            saw_completion = True
                        yield event
            except TimeoutError as exc:
                breaker.record_failure()
                logger.warning(
                    "inference.timeout",
                    provider=target.provider,
                    provider_model=target.provider_model,
                    request_id=request.request_id,
                )
                raise ProviderTimeoutError(provider=target.provider) from exc
            except InferenceError:
                breaker.record_failure()
                raise
            except asyncio.CancelledError:
                # A client disconnect is not a provider failure.
                raise
            except Exception as exc:
                breaker.record_failure()
                logger.exception(
                    "inference.provider_error",
                    provider=target.provider,
                    provider_model=target.provider_model,
                    error=type(exc).__name__,
                )
                raise ProviderResponseError(provider=target.provider) from exc

        if not saw_completion:
            breaker.record_failure()
            raise ProviderResponseError(
                "The inference provider ended the stream without a completion event.",
                provider=target.provider,
            )
        breaker.record_success()

    # --- internals -----------------------------------------------------------

    def _resolve(self, target: InferenceTarget) -> ModelProvider:
        provider = self._registry.get(target.provider)
        if not provider.supports(target.provider_model):
            raise UnsupportedModelError(
                f"Provider '{target.provider}' does not serve the requested model.",
                provider=target.provider,
            )
        return provider

    def _breaker(self, provider_name: str) -> CircuitBreaker:
        breaker = self._breakers.get(provider_name)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=self._settings.circuit_breaker_failure_threshold,
                reset_seconds=self._settings.circuit_breaker_reset_seconds,
            )
            self._breakers[provider_name] = breaker
        return breaker

    def _semaphore(self, provider_name: str) -> asyncio.Semaphore:
        semaphore = self._semaphores.get(provider_name)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self._settings.max_concurrent_requests_per_provider)
            self._semaphores[provider_name] = semaphore
        return semaphore
