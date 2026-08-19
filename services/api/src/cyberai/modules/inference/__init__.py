"""Inference Gateway - *how* inference is reached.

This module owns transport concerns and nothing else: provider adapters,
timeouts, concurrency limits, circuit breaking and health. It has no opinion on
which model should answer a request; that is the Model Gateway's job
(``cyberai.modules.modelgw``), which sits one layer above.

The application never imports a vendor SDK. It depends on the
``ModelProvider`` protocol, and providers are wired in the composition root.
"""

from cyberai.modules.inference.errors import (
    CircuitOpenError,
    InferenceError,
    ProviderNotRegisteredError,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from cyberai.modules.inference.gateway import InferenceGateway, InferenceTarget
from cyberai.modules.inference.ports import ModelProvider
from cyberai.modules.inference.registry import ProviderRegistry
from cyberai.modules.inference.types import (
    FinishReason,
    InferenceEvent,
    InferenceRequest,
    Message,
    ModelCapabilities,
    ProviderHealth,
    Role,
    StreamCompleted,
    TextDelta,
    TokenUsage,
)

__all__ = [
    "CircuitOpenError",
    "FinishReason",
    "InferenceError",
    "InferenceEvent",
    "InferenceGateway",
    "InferenceRequest",
    "InferenceTarget",
    "Message",
    "ModelCapabilities",
    "ModelProvider",
    "ProviderHealth",
    "ProviderNotRegisteredError",
    "ProviderRateLimitedError",
    "ProviderRegistry",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "Role",
    "StreamCompleted",
    "TextDelta",
    "TokenUsage",
]
