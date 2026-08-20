"""Token estimation boundary for conservative quota reservations."""

from __future__ import annotations

from typing import Protocol

from cyberai.modules.billing.types import TokenEstimate
from cyberai.modules.inference import InferenceGateway, Message
from cyberai.modules.modelgw import ModelCatalog


class TokenEstimator(Protocol):
    def estimate(
        self,
        *,
        messages: tuple[Message, ...],
        model_key: str,
        max_output_tokens: int,
    ) -> TokenEstimate: ...


class StaticTokenEstimator:
    def __init__(self, *, input_tokens: int) -> None:
        self._input_tokens = input_tokens

    def estimate(
        self,
        *,
        messages: tuple[Message, ...],
        model_key: str,
        max_output_tokens: int,
    ) -> TokenEstimate:
        return TokenEstimate(
            input_tokens=self._input_tokens,
            reserved_output_tokens=max_output_tokens,
            source="static_test_estimator",
            is_conservative=True,
        )


class ProviderTokenEstimator:
    """Uses provider token counting when available; reserves output conservatively."""

    def __init__(self, catalog: ModelCatalog, inference: InferenceGateway) -> None:
        self._catalog = catalog
        self._inference = inference

    def estimate(
        self,
        *,
        messages: tuple[Message, ...],
        model_key: str,
        max_output_tokens: int,
    ) -> TokenEstimate:
        model = self._catalog.get(model_key)
        input_tokens = sum(
            self._inference.count_tokens(model.provider, message.content) for message in messages
        )
        return TokenEstimate(
            input_tokens=input_tokens,
            reserved_output_tokens=max_output_tokens,
            source="provider_count_tokens",
            is_conservative=True,
        )
