"""OpenAI-compatible chat completions provider."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

import httpx

from cyberai.core.config import OpenAICompatibleProviderSettings
from cyberai.modules.inference.errors import (
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnsupportedModelError,
)
from cyberai.modules.inference.types import (
    FinishReason,
    InferenceEvent,
    InferenceRequest,
    ModelCapabilities,
    ProviderHealth,
    StreamCompleted,
    TextDelta,
    TokenUsage,
)

PROVIDER_NAME: Final = "openai-compatible"
_CHARS_PER_TOKEN: Final = 4


class OpenAICompatibleModelProvider:
    """Adapter for hosted APIs that implement OpenAI chat-completions streaming."""

    def __init__(
        self,
        settings: OpenAICompatibleProviderSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._timeout = httpx.Timeout(
            settings.request_timeout_seconds,
            connect=settings.connect_timeout_seconds,
        )

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def supports(self, provider_model: str) -> bool:
        return self._settings.enabled and provider_model == self._settings.model

    def capabilities(self, provider_model: str) -> ModelCapabilities:
        if not self.supports(provider_model):
            raise UnsupportedModelError(
                f"Unknown OpenAI-compatible model '{provider_model}'.", provider=PROVIDER_NAME
            )
        return ModelCapabilities(
            context_window=self._settings.context_window,
            max_output_tokens=self._settings.max_output_tokens,
            supports_streaming=True,
        )

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, -(-len(text) // _CHARS_PER_TOKEN))

    async def health(self) -> ProviderHealth:
        if self._settings.api_key is None:
            return ProviderHealth(provider=PROVIDER_NAME, healthy=False, detail="api key missing")
        try:
            async with self._client_context() as client:
                response = await client.get(self._url("/models"), headers=self._headers())
            if response.status_code < 400:
                return ProviderHealth(provider=PROVIDER_NAME, healthy=True, detail="reachable")
            return ProviderHealth(
                provider=PROVIDER_NAME,
                healthy=False,
                detail=f"http_{response.status_code}",
            )
        except Exception as exc:
            return ProviderHealth(provider=PROVIDER_NAME, healthy=False, detail=type(exc).__name__)

    async def generate(self, request: InferenceRequest) -> AsyncIterator[InferenceEvent]:
        self.capabilities(request.provider_model)
        payload = self._payload(request)
        output_parts: list[str] = []
        usage: TokenUsage | None = None
        finish_reason: FinishReason | None = None
        saw_stream_event = False

        try:
            async with (
                self._client_context() as client,
                client.stream(
                    "POST",
                    self._url("/chat/completions"),
                    headers=self._headers(),
                    json=payload,
                    timeout=self._timeout,
                ) as response,
            ):
                await self._raise_for_status(response)
                async for line in response.aiter_lines():
                    parsed = self._parse_sse_line(line)
                    if parsed is None:
                        continue
                    if parsed == "[DONE]":
                        break
                    saw_stream_event = True
                    chunk = self._decode_chunk(parsed)
                    delta = self._extract_delta(chunk)
                    if delta:
                        output_parts.append(delta)
                        yield TextDelta(text=delta)
                    usage = self._extract_usage(chunk) or usage
                    finish_reason = self._extract_finish_reason(chunk) or finish_reason
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(provider=PROVIDER_NAME) from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(provider=PROVIDER_NAME) from exc

        if not saw_stream_event:
            raise ProviderResponseError(
                "The provider returned an empty streaming response.", provider=PROVIDER_NAME
            )

        yield StreamCompleted(
            finish_reason=finish_reason or FinishReason.STOP,
            usage=usage or self._estimated_usage(request, "".join(output_parts)),
        )

    def _payload(self, request: InferenceRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.provider_model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.stop:
            payload["stop"] = list(request.stop)
        if self._settings.keep_alive:
            payload["keep_alive"] = self._settings.keep_alive
        return payload

    def _headers(self) -> dict[str, str]:
        if self._settings.api_key is None:
            raise ProviderUnavailableError(
                "Provider API key is not configured.", provider=PROVIDER_NAME
            )
        return {
            "authorization": f"Bearer {self._settings.api_key.get_secret_value()}",
            "content-type": "application/json",
            "accept": "text/event-stream",
        }

    def _url(self, path: str) -> str:
        return f"{self._settings.base_url}{path}"

    @asynccontextmanager
    async def _client_context(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(
            base_url=self._settings.base_url,
            timeout=self._timeout,
        ) as client:
            yield client

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail = await self._safe_error_detail(response)
        if response.status_code == 429:
            raise ProviderRateLimitedError(detail, provider=PROVIDER_NAME)
        if response.status_code in {408, 504}:
            raise ProviderTimeoutError(detail, provider=PROVIDER_NAME)
        if response.status_code >= 500:
            raise ProviderUnavailableError(detail, provider=PROVIDER_NAME)
        raise ProviderResponseError(detail, provider=PROVIDER_NAME)

    async def _safe_error_detail(self, response: httpx.Response) -> str:
        content = await response.aread()
        if not content:
            return f"Provider returned HTTP {response.status_code}."
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return f"Provider returned HTTP {response.status_code}."
        message = data.get("error", {}).get("message") if isinstance(data, dict) else None
        if isinstance(message, str) and message:
            return message[:300]
        return f"Provider returned HTTP {response.status_code}."

    def _parse_sse_line(self, line: str) -> str | None:
        stripped = line.strip()
        if not stripped or stripped.startswith(":"):
            return None
        if not stripped.startswith("data:"):
            return None
        return stripped.removeprefix("data:").strip()

    def _decode_chunk(self, payload: str) -> dict[str, Any]:
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(
                "Provider emitted invalid JSON.", provider=PROVIDER_NAME
            ) from exc
        if not isinstance(decoded, dict):
            raise ProviderResponseError(
                "Provider emitted a non-object chunk.", provider=PROVIDER_NAME
            )
        return decoded

    def _extract_delta(self, chunk: dict[str, Any]) -> str | None:
        choice = self._first_choice(chunk)
        delta = choice.get("delta") if choice is not None else None
        content = delta.get("content") if isinstance(delta, dict) else None
        return content if isinstance(content, str) else None

    def _extract_finish_reason(self, chunk: dict[str, Any]) -> FinishReason | None:
        choice = self._first_choice(chunk)
        reason = choice.get("finish_reason") if choice is not None else None
        if reason is None:
            return None
        if reason == "stop":
            return FinishReason.STOP
        if reason == "length":
            return FinishReason.LENGTH
        if reason == "content_filter":
            return FinishReason.CONTENT_FILTERED
        return FinishReason.ERROR

    def _extract_usage(self, chunk: dict[str, Any]) -> TokenUsage | None:
        usage = chunk.get("usage")
        if not isinstance(usage, dict):
            return None
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        details = usage.get("prompt_tokens_details", {})
        cached_tokens = details.get("cached_tokens", 0) if isinstance(details, dict) else 0
        return TokenUsage(
            input_tokens=prompt_tokens if isinstance(prompt_tokens, int) else 0,
            output_tokens=completion_tokens if isinstance(completion_tokens, int) else 0,
            cached_input_tokens=cached_tokens if isinstance(cached_tokens, int) else 0,
        )

    def _first_choice(self, chunk: dict[str, Any]) -> dict[str, Any] | None:
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        return first if isinstance(first, dict) else None

    def _estimated_usage(self, request: InferenceRequest, output_text: str) -> TokenUsage:
        return TokenUsage(
            input_tokens=sum(self.count_tokens(message.content) for message in request.messages),
            output_tokens=self.count_tokens(output_text),
        )
