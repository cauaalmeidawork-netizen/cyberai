"""Tests for the OpenAI-compatible real model provider."""

from __future__ import annotations

import json

import httpx
import pytest

from cyberai.container import build_services, shutdown_services
from cyberai.core.config import InferenceSettings, OpenAICompatibleProviderSettings, load_settings
from cyberai.modules.inference import (
    FinishReason,
    InferenceRequest,
    Message,
    Role,
    StreamCompleted,
    TextDelta,
)
from cyberai.modules.inference.errors import (
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from cyberai.modules.inference.providers.openai_compatible import OpenAICompatibleModelProvider
from cyberai.modules.modelgw.catalog import default_catalog


def _settings() -> OpenAICompatibleProviderSettings:
    return OpenAICompatibleProviderSettings(
        enabled=True,
        api_key="test-key",
        base_url="https://models.example.test/v1",
        model="gpt-test",
        model_key="real-chat",
        display_name="Real Chat",
        context_window=8192,
        max_output_tokens=1024,
    )


def _request() -> InferenceRequest:
    return InferenceRequest(
        provider_model="gpt-test",
        messages=(Message(role=Role.USER, content="hello"),),
        max_output_tokens=128,
        temperature=0.3,
    )


async def _collect(provider: OpenAICompatibleModelProvider) -> list[object]:
    return [event async for event in provider.generate(_request())]


@pytest.mark.asyncio
async def test_openai_compatible_provider_streams_sse_events() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        chunks = [
            {"choices": [{"delta": {"content": "hel"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "lo"}, "finish_reason": None}]},
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        ]
        body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx.Response(
            200,
            content=body.encode(),
            headers={"content-type": "text/event-stream"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleModelProvider(_settings(), client=client)
        events = await _collect(provider)

    assert captured_request is not None
    assert captured_request.url == "https://models.example.test/v1/chat/completions"
    assert captured_request.headers["authorization"] == "Bearer test-key"
    payload = json.loads(captured_request.content)
    assert payload["model"] == "gpt-test"
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert events[:2] == [TextDelta(text="hel"), TextDelta(text="lo")]
    assert isinstance(events[-1], StreamCompleted)
    assert events[-1].finish_reason is FinishReason.STOP
    assert events[-1].usage.input_tokens == 3
    assert events[-1].usage.output_tokens == 2


@pytest.mark.asyncio
async def test_openai_compatible_provider_maps_http_errors() -> None:
    async def rate_limited(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    async def unavailable(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "try later"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(rate_limited)) as client:
        provider = OpenAICompatibleModelProvider(_settings(), client=client)
        with pytest.raises(ProviderRateLimitedError):
            await _collect(provider)

    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        provider = OpenAICompatibleModelProvider(_settings(), client=client)
        with pytest.raises(ProviderUnavailableError):
            await _collect(provider)


@pytest.mark.asyncio
async def test_openai_compatible_provider_maps_timeout_and_invalid_stream() -> None:
    async def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    async def invalid(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"data: not-json\n\n")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        provider = OpenAICompatibleModelProvider(_settings(), client=client)
        with pytest.raises(ProviderTimeoutError):
            await _collect(provider)

    async with httpx.AsyncClient(transport=httpx.MockTransport(invalid)) as client:
        provider = OpenAICompatibleModelProvider(_settings(), client=client)
        with pytest.raises(ProviderResponseError):
            await _collect(provider)


def test_catalog_includes_real_model_only_when_enabled() -> None:
    mock_only = default_catalog()
    assert mock_only.has("mock-analyst-1")
    assert not mock_only.has("real-chat")

    catalog = default_catalog(openai_compatible=_settings())
    real_model = catalog.get("real-chat")
    assert real_model.provider == "openai-compatible"
    assert real_model.provider_model == "gpt-test"


@pytest.mark.asyncio
async def test_container_selects_real_provider_from_configuration() -> None:
    settings = load_settings(
        openai_compatible={
            "enabled": True,
            "api_key": "test-key",
            "base_url": "https://models.example.test/v1",
            "model": "gpt-test",
            "model_key": "real-chat",
        },
        models={"default_model": "real-chat", "fallback_models": ["mock-analyst-1"]},
        inference=InferenceSettings(request_timeout_seconds=5.0, first_token_timeout_seconds=1.0),
    )
    services = build_services(settings)
    try:
        assert services.providers.has("mock")
        assert services.providers.has("openai-compatible")
        assert services.catalog.get("real-chat").provider == "openai-compatible"
    finally:
        await shutdown_services(services)
