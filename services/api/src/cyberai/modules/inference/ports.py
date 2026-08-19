"""The provider port.

This protocol is the single seam between the platform and any model runtime.
Adding OpenAI, Anthropic, a self-hosted vLLM server or a local GGUF model means
writing one adapter that satisfies this interface - no other layer changes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from cyberai.modules.inference.types import (
    InferenceEvent,
    InferenceRequest,
    ModelCapabilities,
    ProviderHealth,
)


@runtime_checkable
class ModelProvider(Protocol):
    """A concrete way to reach a model runtime."""

    @property
    def name(self) -> str:
        """Stable provider identifier, e.g. ``mock``, ``commercial``, ``local_gpu``."""
        ...

    def supports(self, provider_model: str) -> bool:
        """Whether this provider can serve the given model identifier."""
        ...

    def capabilities(self, provider_model: str) -> ModelCapabilities:
        """Describe the limits of a model served by this provider."""
        ...

    def count_tokens(self, text: str) -> int:
        """Estimate the token count of a string.

        Used for budgeting before a call is made. Implementations should be
        cheap; an approximation that never *under*-counts is preferred to an
        exact count that costs a network round trip.
        """
        ...

    async def health(self) -> ProviderHealth:
        """Report reachability. Must not raise."""
        ...

    def generate(self, request: InferenceRequest) -> AsyncIterator[InferenceEvent]:
        """Stream a completion.

        Implementations are async generators yielding zero or more ``TextDelta``
        events followed by exactly one ``StreamCompleted``. Failures must be
        raised as ``InferenceError`` subclasses so the gateway can decide
        whether to fail over.
        """
        ...
