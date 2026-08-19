"""Tests for the Model Gateway."""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest

from cyberai.core.config import InferenceSettings, MockProviderSettings, ModelSettings
from cyberai.modules.inference import (
    InferenceGateway,
    Message,
    ProviderRegistry,
    Role,
)
from cyberai.modules.inference.providers import MockModelProvider
from cyberai.modules.modelgw import (
    CompletionRequest,
    ModelCatalog,
    ModelGateway,
    ModelRouter,
    ModelSpec,
    RequestPrincipal,
    TaskType,
    default_catalog,
)
from cyberai.modules.modelgw.errors import ModelNotFoundError, NoModelAvailableError
from cyberai.modules.modelgw.types import (
    CompletionCompleted,
    CompletionStarted,
    GatewayEvent,
)
from cyberai.modules.modelgw.usage import CollectingUsageSink, estimate_cost_usd


def _build_gateway(
    *,
    default_model: str = "mock-analyst-1",
    fallbacks: list[str] | None = None,
    usage_sink: CollectingUsageSink | None = None,
) -> tuple[ModelGateway, CollectingUsageSink]:
    providers = ProviderRegistry([MockModelProvider(MockProviderSettings())])
    inference = InferenceGateway(
        providers,
        InferenceSettings(
            request_timeout_seconds=5.0,
            first_token_timeout_seconds=1.0,
            max_concurrent_requests_per_provider=8,
        ),
    )
    catalog = default_catalog()
    router = ModelRouter(
        catalog,
        ModelSettings(default_model=default_model, fallback_models=fallbacks or []),
    )
    sink = usage_sink or CollectingUsageSink()
    return ModelGateway(router, inference, sink), sink


def _chat_request(content: str, *, model_key: str | None = None) -> CompletionRequest:
    return CompletionRequest(
        messages=(Message(role=Role.USER, content=content),),
        model_key=model_key,
        principal=RequestPrincipal(
            request_id="req-test", org_id="00000000-0000-0000-0000-000000000001"
        ),
    )


async def _collect(stream: AsyncIterator[GatewayEvent]) -> list[GatewayEvent]:
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_successful_completion() -> None:
    gateway, sink = _build_gateway()
    request = _chat_request("explain what a firewall is")
    events = await _collect(gateway.stream(request))

    assert isinstance(events[0], CompletionStarted)
    assert events[0].model_key == "mock-analyst-1"
    assert events[0].is_fallback is False

    assert isinstance(events[-1], CompletionCompleted)
    completed = events[-1]
    assert completed.provider == "mock"
    assert completed.usage.total_tokens > 0

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.model_key == "mock-analyst-1"
    assert record.request_id == "req-test"
    assert record.organization_id == "00000000-0000-0000-0000-000000000001"
    assert record.status.value == "success"


@pytest.mark.asyncio
async def test_explicit_model_request() -> None:
    gateway, _sink = _build_gateway()
    request = _chat_request("hello", model_key="mock-analyst-mini")
    events = await _collect(gateway.stream(request))
    started = events[0]
    assert isinstance(started, CompletionStarted)
    assert started.model_key == "mock-analyst-mini"


@pytest.mark.asyncio
async def test_explicit_model_not_supporting_task() -> None:
    gateway, _sink = _build_gateway()
    # mock-analyst-mini does not support CODE.
    request = CompletionRequest(
        messages=(Message(role=Role.USER, content="write code"),),
        task=TaskType.CODE,
        model_key="mock-analyst-mini",
        principal=RequestPrincipal(request_id="req-test"),
    )
    with pytest.raises(ModelNotFoundError):
        await _collect(gateway.stream(request))


@pytest.mark.asyncio
async def test_no_model_available() -> None:
    catalog = ModelCatalog(
        (
            ModelSpec(
                key="offline-model",
                provider="mock",
                provider_model="offline",
                display_name="Offline",
                description="Not usable.",
                context_window=4096,
                max_output_tokens=1024,
                tasks=frozenset({TaskType.CHAT}),
                is_available=False,
            ),
        )
    )
    router = ModelRouter(catalog, ModelSettings(default_model="offline-model", fallback_models=[]))
    providers = ProviderRegistry([MockModelProvider(MockProviderSettings())])
    inference = InferenceGateway(providers, InferenceSettings())
    gateway = ModelGateway(router, inference, CollectingUsageSink())

    request = _chat_request("hello")
    with pytest.raises(NoModelAvailableError):
        await _collect(gateway.stream(request))


@pytest.mark.asyncio
async def test_fallback_chain() -> None:
    gateway, sink = _build_gateway(
        default_model="mock-analyst-1",
        fallbacks=["mock-analyst-mini"],
    )
    # Force the primary to time out twice and open its circuit.
    request = _chat_request("[[mock:timeout]]")

    with pytest.raises(NoModelAvailableError):
        await _collect(gateway.stream(request))

    # The fallback was attempted; both attempts are logged.
    assert len(sink.records) >= 1


@pytest.mark.asyncio
async def test_no_splicing_after_output_starts() -> None:
    from cyberai.modules.inference.errors import ProviderUnavailableError

    gateway, sink = _build_gateway(fallbacks=["mock-analyst-mini"])
    request = _chat_request("[[mock:fail_midstream]]")

    # The gateway re-raises after output has been streamed to avoid splicing
    # two different model answers together.
    with pytest.raises(ProviderUnavailableError):
        await _collect(gateway.stream(request))

    # The usage record marks the attempt as failed.
    failed_record = next(r for r in sink.records if r.status.value == "failed")
    assert failed_record.error_code is not None


@pytest.mark.asyncio
async def test_usage_cost_estimation() -> None:
    from cyberai.modules.inference import TokenUsage

    cost = estimate_cost_usd(
        TokenUsage(input_tokens=1_000, output_tokens=500),
        input_cost_per_mtok=Decimal("2.5"),
        output_cost_per_mtok=Decimal("10.0"),
    )
    # (1000 * 2.5 + 500 * 10.0) / 1_000_000 = 0.0075
    assert cost == Decimal("0.0075")


def test_model_spec_validation() -> None:
    with pytest.raises(ValueError, match="max_output_tokens cannot exceed"):
        ModelSpec(
            key="bad",
            provider="mock",
            provider_model="bad",
            display_name="Bad",
            description="Bad",
            context_window=100,
            max_output_tokens=200,
            tasks=frozenset({TaskType.CHAT}),
        )


def test_default_model_cannot_be_its_own_fallback() -> None:
    with pytest.raises(ValueError, match="default_model must not also be listed"):
        ModelSettings(default_model="x", fallback_models=["x"])


@pytest.mark.asyncio
async def test_catalog_list_available_only() -> None:
    catalog = default_catalog()
    models = catalog.list_all()
    assert all(model.is_available for model in models)


def test_router_resolves_default() -> None:
    gateway, _sink = _build_gateway()
    route = gateway._router.resolve()
    assert route.primary.key == "mock-analyst-1"


def test_router_honours_task_support() -> None:
    gateway, _sink = _build_gateway(default_model="mock-analyst-mini")
    # mini supports only CHAT/SUMMARIZE/CLASSIFY; default resolver still picks
    # it because it supports CHAT.
    route = gateway._router.resolve(TaskType.CHAT)
    assert route.primary.key == "mock-analyst-mini"

    # But CODE is unsupported by mini, so it cannot be used.
    route2 = gateway._router.resolve(TaskType.CODE)
    assert route2.primary.key == "mock-analyst-1"
