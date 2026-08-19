"""A deterministic in-process provider.

The mock provider is not scaffolding to be deleted later: it is the reason the
whole platform can be built, tested and demonstrated on a laptop with no GPU
and no vendor account, and it keeps the test suite fast, offline and
deterministic permanently.

It also simulates the failure modes the gateways must survive. A test triggers
one by embedding a directive in the user message:

    ``[[mock:timeout]]``          - stall past the first-token timeout
    ``[[mock:unavailable]]``      - fail as an unavailable provider
    ``[[mock:rate_limit]]``       - fail as a rate-limited provider
    ``[[mock:error]]``            - raise an unexpected adapter error
    ``[[mock:truncated]]``        - end the stream without a completion event
    ``[[mock:fail_midstream]]``   - fail *after* emitting output

Directives are only honoured for the mock provider and never leave this file.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Final

from cyberai.core.config import MockProviderSettings
from cyberai.modules.inference.errors import (
    ProviderRateLimitedError,
    ProviderUnavailableError,
    UnsupportedModelError,
)
from cyberai.modules.inference.types import (
    FinishReason,
    InferenceEvent,
    InferenceRequest,
    ModelCapabilities,
    ProviderHealth,
    Role,
    StreamCompleted,
    TextDelta,
    TokenUsage,
)

PROVIDER_NAME: Final = "mock"

#: Models this provider pretends to serve, and their limits.
MOCK_MODELS: Final[dict[str, ModelCapabilities]] = {
    "mock-analyst-1": ModelCapabilities(
        context_window=32_768, max_output_tokens=4_096, supports_streaming=True
    ),
    "mock-analyst-mini": ModelCapabilities(
        context_window=16_384, max_output_tokens=2_048, supports_streaming=True
    ),
}

_DIRECTIVE = re.compile(r"\[\[mock:(?P<name>[a-z_]+)\]\]")

#: Rough characters-per-token ratio. Deliberately conservative: a budget built
#: on an under-count is a budget that overflows the context window.
_CHARS_PER_TOKEN: Final = 4


class MockModelProvider:
    """Deterministic provider used for development, tests and CI."""

    def __init__(self, settings: MockProviderSettings | None = None) -> None:
        self._settings = settings or MockProviderSettings()

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def supports(self, provider_model: str) -> bool:
        return provider_model in MOCK_MODELS

    def capabilities(self, provider_model: str) -> ModelCapabilities:
        try:
            return MOCK_MODELS[provider_model]
        except KeyError as exc:
            raise UnsupportedModelError(
                f"Unknown mock model '{provider_model}'.", provider=PROVIDER_NAME
            ) from exc

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, -(-len(text) // _CHARS_PER_TOKEN))

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=PROVIDER_NAME, healthy=True, detail="in-process mock")

    async def generate(self, request: InferenceRequest) -> AsyncIterator[InferenceEvent]:
        capabilities = self.capabilities(request.provider_model)
        directive = self._directive(request)

        if directive == "unavailable":
            raise ProviderUnavailableError(provider=PROVIDER_NAME)
        if directive == "rate_limit":
            raise ProviderRateLimitedError(provider=PROVIDER_NAME)
        if directive == "error":
            raise RuntimeError("simulated adapter failure")
        if directive == "timeout":
            await asyncio.sleep(3_600)

        prompt_tokens = sum(self.count_tokens(message.content) for message in request.messages)
        answer = self._compose_answer(request)
        chunks = self._chunk(answer)

        emitted: list[str] = []
        for index, chunk in enumerate(chunks):
            if directive == "fail_midstream" and index == 1:
                raise ProviderUnavailableError(
                    "Simulated mid-stream provider failure.", provider=PROVIDER_NAME
                )
            if self._settings.chunk_delay_ms:
                await asyncio.sleep(self._settings.chunk_delay_ms / 1000)
            emitted.append(chunk)
            yield TextDelta(text=chunk)

        if directive == "truncated":
            return

        output_text = "".join(emitted)
        output_tokens = self.count_tokens(output_text)
        finish_reason = (
            FinishReason.LENGTH
            if output_tokens >= min(request.max_output_tokens, capabilities.max_output_tokens)
            else FinishReason.STOP
        )
        yield StreamCompleted(
            finish_reason=finish_reason,
            usage=TokenUsage(input_tokens=prompt_tokens, output_tokens=output_tokens),
        )

    # --- internals -----------------------------------------------------------

    def _directive(self, request: InferenceRequest) -> str | None:
        for message in reversed(request.messages):
            if message.role is not Role.USER:
                continue
            match = _DIRECTIVE.search(message.content)
            if match:
                return match.group("name")
        return None

    def _compose_answer(self, request: InferenceRequest) -> str:
        last_user = next(
            (m.content for m in reversed(request.messages) if m.role is Role.USER),
            "",
        )
        prompt = _DIRECTIVE.sub("", last_user).strip()
        preview = prompt[:200] if prompt else "(empty prompt)"
        return (
            f"[{request.provider_model}] MockModelProvider response. "
            f"This deterministic fixture confirms the Model Gateway and Inference Gateway "
            f"are wired end to end; no language model was invoked. "
            f"Received {len(request.messages)} message(s). "
            f"Prompt preview: {preview}"
        )

    def _chunk(self, text: str) -> list[str]:
        words = text.split(" ")
        size = self._settings.words_per_chunk
        groups = [words[i : i + size] for i in range(0, len(words), size)]
        return [(" " if index else "") + " ".join(group) for index, group in enumerate(groups)]
