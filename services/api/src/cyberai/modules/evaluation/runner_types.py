"""Shared evaluation runner types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationResponse:
    text: str
    latency_ms: float
    model_key: str
    provider_key: str
    input_tokens: int
    output_tokens: int
