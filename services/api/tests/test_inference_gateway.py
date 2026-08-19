"""Tests for the Inference Gateway."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from cyberai.core.config import InferenceSettings, MockProviderSettings
from cyberai.modules.inference import (
    FinishReason,
    InferenceEvent,
    InferenceGateway,
    InferenceRequest,
    InferenceTarget,
    Message,
    ProviderRegistry,
    Role,
    StreamCompleted,
)
from cyberai.modules.inference.errors import (
    CircuitOpenError,
    ProviderNotRegisteredError,
    ProviderResponseError,
    ProviderTimeoutError,
    UnsupportedModelError,
)
from cyberai.modules.inference.providers import MockModelProvider


@pytest.fixture
def mock_settings() -> MockProviderSettings:
    return MockProviderSettings(chunk_delay_ms=0)


@pytest.fixture
def registry(mock_settings: MockProviderSettings) -> ProviderRegistry:
    return ProviderRegistry([MockModelProvider(mock_settings)])


@pytest.fixture
def gateway(registry: ProviderRegistry) -> InferenceGateway:
    return InferenceGateway(
        registry,
        InferenceSettings(
            request_timeout_seconds=5.0,
            first_token_timeout_seconds=1.0,
            max_concurrent_requests_per_provider=2,
            circuit_breaker_failure_threshold=2,
            circuit_breaker_reset_seconds=0.1,
        ),
    )


def _request(content: str, max_tokens: int = 256) -> InferenceRequest:
    return InferenceRequest(
        provider_model="mock-analyst-1",
        messages=(Message(role=Role.USER, content=content),),
        max_output_tokens=max_tokens,
    )


async def _collect(stream: AsyncIterator[InferenceEvent]) -> list[InferenceEvent]:
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_successful_stream(gateway: InferenceGateway) -> None:
    request = _request("hello")
    events = await _collect(
        gateway.invoke(
            target=InferenceTarget(provider="mock", provider_model="mock-analyst-1"),
            request=request,
        )
    )
    assert len(events) >= 1
    assert isinstance(events[-1], StreamCompleted)
    assert events[-1].finish_reason is FinishReason.STOP


@pytest.mark.asyncio
async def test_unregistered_provider(gateway: InferenceGateway) -> None:
    request = _request("hello")
    with pytest.raises(ProviderNotRegisteredError):
        async for _event in gateway.invoke(
            target=InferenceTarget(provider="unknown", provider_model="x"),
            request=request,
        ):
            pass


@pytest.mark.asyncio
async def test_unsupported_model(gateway: InferenceGateway) -> None:
    request = _request("hello")
    with pytest.raises(UnsupportedModelError):
        async for _event in gateway.invoke(
            target=InferenceTarget(provider="mock", provider_model="not-a-model"),
            request=request,
        ):
            pass


@pytest.mark.asyncio
async def test_timeout_opens_circuit(gateway: InferenceGateway) -> None:
    request = _request("[[mock:timeout]]")
    for _ in range(2):
        with pytest.raises(ProviderTimeoutError):
            async for _event in gateway.invoke(
                target=InferenceTarget(provider="mock", provider_model="mock-analyst-1"),
                request=request,
            ):
                pass

    assert gateway.circuit_state("mock") == "open"
    # The next call should fail fast.
    with pytest.raises(CircuitOpenError):
        async for _event in gateway.invoke(
            target=InferenceTarget(provider="mock", provider_model="mock-analyst-1"),
            request=request,
        ):
            pass


@pytest.mark.asyncio
async def test_truncated_stream_raises(gateway: InferenceGateway) -> None:
    request = _request("[[mock:truncated]]")
    with pytest.raises(ProviderResponseError):
        async for _event in gateway.invoke(
            target=InferenceTarget(provider="mock", provider_model="mock-analyst-1"),
            request=request,
        ):
            pass


@pytest.mark.asyncio
async def test_circuit_recovers_after_cooldown(gateway: InferenceGateway) -> None:
    request = _request("[[mock:timeout]]")
    for _ in range(2):
        with pytest.raises(ProviderTimeoutError):
            async for _event in gateway.invoke(
                target=InferenceTarget(provider="mock", provider_model="mock-analyst-1"),
                request=request,
            ):
                pass

    import asyncio

    await asyncio.sleep(0.15)
    # Half-open state allows one request through.
    assert gateway.circuit_state("mock") in {"half_open", "closed"}


@pytest.mark.asyncio
async def test_token_counting(gateway: InferenceGateway) -> None:
    # Mock uses ~4 chars per token.
    assert gateway.count_tokens("mock", "123456789") == 3
    assert gateway.count_tokens("mock", "abcd") == 1


@pytest.mark.asyncio
async def test_health(registry: ProviderRegistry) -> None:
    gateway = InferenceGateway(
        registry,
        InferenceSettings(request_timeout_seconds=5.0, first_token_timeout_seconds=1.0),
    )
    health = await gateway.health()
    assert health["mock"].healthy is True
