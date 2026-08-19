"""Provider-neutral inference types.

These are the only shapes that cross the boundary between the application and
a model provider. Nothing here mentions a vendor, a wire format or an SDK: an
OpenAI-compatible server, an Anthropic endpoint, a local vLLM deployment and
the mock provider all adapt onto this same contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self


class Role(StrEnum):
    """Author of a message in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Message:
    """A single message handed to a provider.

    By the time a message reaches this layer it is already assembled: trust
    classification and untrusted-context isolation happen upstream, in the AI
    Orchestrator (M2), never here.
    """

    role: Role
    content: str


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    TIMEOUT = "timeout"
    ERROR = "error"
    CONTENT_FILTERED = "content_filtered"


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token accounting for one inference call.

    ``cached_input_tokens`` is tracked separately from the first request:
    prompt caching changes the real cost of a call by an order of magnitude,
    and a ledger that ignores it reports a margin that does not exist.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def billable_input_tokens(self) -> int:
        return max(self.input_tokens - self.cached_input_tokens, 0)

    def merge(self, other: TokenUsage) -> Self:
        return type(self)(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
        )


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """What a provider can do with a given model."""

    context_window: int
    max_output_tokens: int
    supports_streaming: bool = True
    supports_tools: bool = False


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    provider: str
    healthy: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    """A fully resolved call to one concrete model on one concrete provider."""

    provider_model: str
    messages: tuple[Message, ...]
    max_output_tokens: int
    temperature: float = 0.2
    top_p: float = 1.0
    stop: tuple[str, ...] = field(default_factory=tuple)
    request_id: str | None = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("InferenceRequest requires at least one message")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be within [0.0, 2.0]")
        if not 0.0 < self.top_p <= 1.0:
            raise ValueError("top_p must be within (0.0, 1.0]")


# --- Streaming events --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextDelta:
    """An incremental piece of assistant output."""

    text: str


@dataclass(frozen=True, slots=True)
class StreamCompleted:
    """Terminal event of a successful stream."""

    finish_reason: FinishReason
    usage: TokenUsage


InferenceEvent = TextDelta | StreamCompleted
