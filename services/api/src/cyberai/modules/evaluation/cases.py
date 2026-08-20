"""Evaluation case definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EvaluationCategory(StrEnum):
    CYBERSECURITY_KNOWLEDGE = "cybersecurity_knowledge"
    REASONING = "reasoning"
    PROGRAMMING = "programming"
    CODE_GENERATION = "code_generation"
    CODE_ANALYSIS = "code_analysis"
    HALLUCINATION = "hallucination"
    RAG_QUALITY = "rag_quality"
    POLICY_BEHAVIOR = "policy_behavior"
    LATENCY = "latency"


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    id: str
    version: str
    category: EvaluationCategory
    input: str
    expected_criteria: str
    expected_keywords: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()
    reference_answer: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
