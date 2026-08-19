"""Model Gateway types: catalog entries, routes and the request contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from cyberai.modules.inference import (
    FinishReason,
    InferenceTarget,
    Message,
    TextDelta,
    TokenUsage,
)
from cyberai.modules.modelgw.usage import UsageRecord


class TaskType(StrEnum):
    """What the caller needs, not which model it wants.

    Routing by task is what keeps cost under control: summarisation and
    classification run on a cheap model while the expensive one is reserved for
    what the user actually reads.
    """

    CHAT = "chat"
    CODE = "code"
    REASONING = "reasoning"
    SUMMARIZE = "summarize"
    CLASSIFY = "classify"


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """A model the platform can route to.

    Prices are per million tokens in USD and are stored with the model rather
    than hardcoded in the billing code, so adding a model or repricing one is a
    catalog change. The catalog moves to the database in a later milestone;
    this shape is what it will hold.
    """

    key: str
    provider: str
    provider_model: str
    display_name: str
    description: str
    context_window: int
    max_output_tokens: int
    tasks: frozenset[TaskType]
    input_cost_per_mtok: Decimal = Decimal("0")
    output_cost_per_mtok: Decimal = Decimal("0")
    cached_input_cost_per_mtok: Decimal = Decimal("0")
    is_available: bool = True

    def __post_init__(self) -> None:
        if self.context_window <= 0:
            raise ValueError("context_window must be positive")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.max_output_tokens > self.context_window:
            raise ValueError("max_output_tokens cannot exceed context_window")
        if not self.tasks:
            raise ValueError("a model must support at least one task")

    def supports(self, task: TaskType) -> bool:
        return task in self.tasks

    @property
    def target(self) -> InferenceTarget:
        """The (provider, model) pair handed to the Inference Gateway."""
        return InferenceTarget(provider=self.provider, provider_model=self.provider_model)


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """An ordered list of candidates: the primary plus its fallbacks."""

    primary: ModelSpec
    fallbacks: tuple[ModelSpec, ...] = ()

    @property
    def candidates(self) -> tuple[ModelSpec, ...]:
        return (self.primary, *self.fallbacks)


@dataclass(frozen=True, slots=True)
class RequestPrincipal:
    """Who a request is attributed to, for the cost ledger and audit trail.

    All fields are optional in M0 because authentication arrives in M1; the
    ledger shape does not change when they start being populated.
    """

    org_id: str | None = None
    user_id: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    """What the caller asks of the Model Gateway."""

    messages: tuple[Message, ...]
    task: TaskType = TaskType.CHAT
    model_key: str | None = None
    max_output_tokens: int = 1_024
    temperature: float = 0.2
    principal: RequestPrincipal = field(default_factory=RequestPrincipal)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("CompletionRequest requires at least one message")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")


# --- Streaming events --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompletionStarted:
    """Emitted once the model that will actually answer has been chosen.

    After a fallback this is not the model that was requested, which is exactly
    why the caller is told.
    """

    model_key: str
    provider: str
    attempt: int
    is_fallback: bool


@dataclass(frozen=True, slots=True)
class CompletionCompleted:
    """Terminal event carrying the accounting for the call."""

    model_key: str
    provider: str
    finish_reason: FinishReason
    usage: TokenUsage
    record: UsageRecord


GatewayEvent = CompletionStarted | TextDelta | CompletionCompleted
