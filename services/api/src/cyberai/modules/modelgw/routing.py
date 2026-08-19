"""Routing policy: turning a request into an ordered list of candidates.

M0 routes on task support, availability and context size, using the configured
default and its fallbacks. The signature is what matters: tier, latency budget,
cost ceiling and provider health become additional inputs later without any
caller changing.
"""

from __future__ import annotations

from cyberai.core.config import ModelSettings
from cyberai.core.logging import get_logger
from cyberai.modules.modelgw.catalog import ModelCatalog
from cyberai.modules.modelgw.errors import ModelNotFoundError, NoModelAvailableError
from cyberai.modules.modelgw.types import ModelRoute, ModelSpec, TaskType

logger = get_logger(__name__)


class ModelRouter:
    """Decides which model answers, and in which order to try alternatives."""

    def __init__(self, catalog: ModelCatalog, settings: ModelSettings) -> None:
        self._catalog = catalog
        self._settings = settings
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        """Fail at startup, not on the first request, if routing is misconfigured."""
        if not self._catalog.has(self._settings.default_model):
            raise ModelNotFoundError(
                f"Configured default model '{self._settings.default_model}' "
                f"is not present in the catalog."
            )
        for key in self._settings.fallback_models:
            if not self._catalog.has(key):
                raise ModelNotFoundError(
                    f"Configured fallback model '{key}' is not present in the catalog."
                )

    def resolve(
        self,
        task: TaskType = TaskType.CHAT,
        *,
        requested_model: str | None = None,
        min_context_tokens: int | None = None,
    ) -> ModelRoute:
        """Return the primary model plus its usable fallbacks.

        Args:
            task: what the caller needs the model for.
            requested_model: an explicit choice. It is honoured only if the
                model exists, is available and supports the task.
            min_context_tokens: drop candidates whose context window is too small.

        Raises:
            ModelNotFoundError: the explicitly requested model cannot serve this request.
            NoModelAvailableError: nothing in the catalog can serve this request.
        """
        if requested_model is not None:
            primary = self._catalog.get(requested_model)
            self._assert_usable(primary, task, min_context_tokens)
        else:
            primary = self._catalog.get(self._settings.default_model)
            if not self._is_usable(primary, task, min_context_tokens):
                primary = self._first_usable(task, min_context_tokens)

        fallbacks = tuple(
            model
            for key in self._settings.fallback_models
            if (model := self._catalog.get(key)) is not primary
            and model.key != primary.key
            and self._is_usable(model, task, min_context_tokens)
        )
        return ModelRoute(primary=primary, fallbacks=fallbacks)

    # --- internals -----------------------------------------------------------

    def _is_usable(self, model: ModelSpec, task: TaskType, min_context_tokens: int | None) -> bool:
        if not model.is_available or not model.supports(task):
            return False
        return not (min_context_tokens is not None and model.context_window < min_context_tokens)

    def _assert_usable(
        self, model: ModelSpec, task: TaskType, min_context_tokens: int | None
    ) -> None:
        if not model.is_available:
            raise ModelNotFoundError(f"Model '{model.key}' is not available.")
        if not model.supports(task):
            raise ModelNotFoundError(
                f"Model '{model.key}' does not support the '{task.value}' task."
            )
        if min_context_tokens is not None and model.context_window < min_context_tokens:
            raise ModelNotFoundError(
                f"Model '{model.key}' has a context window of {model.context_window} tokens, "
                f"which is smaller than the required {min_context_tokens}."
            )

    def _first_usable(self, task: TaskType, min_context_tokens: int | None) -> ModelSpec:
        for model in self._catalog.list_for_task(task):
            if self._is_usable(model, task, min_context_tokens):
                logger.warning(
                    "modelgw.default_model_unusable",
                    task=task.value,
                    selected_model=model.key,
                    configured_default=self._settings.default_model,
                )
                return model
        raise NoModelAvailableError(
            f"No available model supports the '{task.value}' task with the required context."
        )
