"""The model catalog.

An in-memory, config-driven catalog for M0. It moves to a database table once
models are administered at runtime; the entry shape (``ModelSpec``) is already
the one that table will hold, so that migration is data, not redesign.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from decimal import Decimal

from cyberai.modules.modelgw.errors import ModelNotFoundError
from cyberai.modules.modelgw.types import ModelSpec, TaskType

#: M0 ships only mock models. Real models are added in M4 (commercial provider)
#: and M11 (self-hosted GPU) without touching any consumer of the catalog.
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

    def list_all(self, *, include_unavailable: bool = False) -> tuple[ModelSpec, ...]:
        models = self._models.values()
        if include_unavailable:
            return tuple(models)
        return tuple(model for model in models if model.is_available)

    def list_for_task(self, task: TaskType) -> tuple[ModelSpec, ...]:
        return tuple(model for model in self.list_all() if model.supports(task))

    def __iter__(self) -> Iterator[ModelSpec]:
        return iter(self._models.values())

    def __len__(self) -> int:
        return len(self._models)


def default_catalog() -> ModelCatalog:
    return ModelCatalog(DEFAULT_MODELS)
