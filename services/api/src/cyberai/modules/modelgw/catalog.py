"""The model catalog.

An in-memory, config-driven catalog for M0. It moves to a database table once
models are administered at runtime; the entry shape (``ModelSpec``) is already
the one that table will hold, so that migration is data, not redesign.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from decimal import Decimal

from cyberai.core.config import OpenAICompatibleProviderSettings
from cyberai.modules.modelgw.errors import ModelNotFoundError
from cyberai.modules.modelgw.types import ModelSpec, TaskType

#: Mock models are always present so development and CI remain offline.
DEFAULT_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        key="mock-analyst-1",
        provider="mock",
        provider_model="mock-analyst-1",
        display_name="Mock Analyst 1",
        description=(
            "Deterministic development model. Produces fixture responses so the "
            "platform can be built and tested without a GPU or a vendor account."
        ),
        context_window=32_768,
        max_output_tokens=4_096,
        tasks=frozenset(
            {
                TaskType.CHAT,
                TaskType.CODE,
                TaskType.REASONING,
                TaskType.SUMMARIZE,
                TaskType.CLASSIFY,
            }
        ),
        input_cost_per_mtok=Decimal("0"),
        output_cost_per_mtok=Decimal("0"),
    ),
    ModelSpec(
        key="mock-analyst-mini",
        provider="mock",
        provider_model="mock-analyst-mini",
        display_name="Mock Analyst Mini",
        description=(
            "Smaller deterministic development model. Stands in for the cheap "
            "route used by summarisation, classification and fallback."
        ),
        context_window=16_384,
        max_output_tokens=2_048,
        tasks=frozenset({TaskType.CHAT, TaskType.SUMMARIZE, TaskType.CLASSIFY}),
        input_cost_per_mtok=Decimal("0"),
        output_cost_per_mtok=Decimal("0"),
    ),
)


def _openai_compatible_model(settings: OpenAICompatibleProviderSettings) -> ModelSpec | None:
    if not settings.enabled:
        return None
    return ModelSpec(
        key=settings.model_key,
        provider="openai-compatible",
        provider_model=settings.model,
        display_name=settings.display_name,
        description="Environment-configured OpenAI-compatible hosted chat model.",
        context_window=settings.context_window,
        max_output_tokens=settings.max_output_tokens,
        tasks=frozenset(
            {
                TaskType.CHAT,
                TaskType.CODE,
                TaskType.REASONING,
                TaskType.SUMMARIZE,
                TaskType.CLASSIFY,
            }
        ),
        input_cost_per_mtok=Decimal("0"),
        output_cost_per_mtok=Decimal("0"),
    )


class ModelCatalog:
    """Lookup of the models this deployment can route to."""

    def __init__(self, models: Iterable[ModelSpec]) -> None:
        self._models: dict[str, ModelSpec] = {}
        for model in models:
            if model.key in self._models:
                raise ValueError(f"duplicate model key '{model.key}' in catalog")
            self._models[model.key] = model
        if not self._models:
            raise ValueError("the model catalog cannot be empty")

    def get(self, key: str) -> ModelSpec:
        try:
            return self._models[key]
        except KeyError as exc:
            raise ModelNotFoundError(f"Unknown model '{key}'.") from exc

    def has(self, key: str) -> bool:
        return key in self._models

    def list_all(
        self, *, include_unavailable: bool = False, include_internal: bool = True
    ) -> tuple[ModelSpec, ...]:
        """List catalog models.

        Internal/test providers (mock) are part of the catalog by default —
        internal routing depends on them in local and CI environments. Public
        surfaces (the client-facing model list) must pass ``include_internal=False``.
        """
        models: Iterator[ModelSpec] = iter(self._models.values())

        # Filter by availability
        if not include_unavailable:
            models = (model for model in models if model.is_available)

        # Filter out internal/test providers (mock) when explicitly requested
        if not include_internal:
            models = (model for model in models if model.provider != "mock")

        return tuple(models)

    def list_for_task(self, task: TaskType) -> tuple[ModelSpec, ...]:
        return tuple(model for model in self.list_all() if model.supports(task))

    def __iter__(self) -> Iterator[ModelSpec]:
        return iter(self._models.values())

    def __len__(self) -> int:
        return len(self._models)


def default_catalog(
    *,
    openai_compatible: OpenAICompatibleProviderSettings | None = None,
    include_mock: bool = True,
) -> ModelCatalog:
    models = list(DEFAULT_MODELS) if include_mock else []
    if openai_compatible is not None:
        real_model = _openai_compatible_model(openai_compatible)
        if real_model is not None:
            models.append(real_model)
    return ModelCatalog(models)
