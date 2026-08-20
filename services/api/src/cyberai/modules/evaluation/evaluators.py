"""Deterministic evaluators for benchmark cases."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from cyberai.modules.evaluation.cases import EvaluationCase
from cyberai.modules.evaluation.runner_types import EvaluationResponse


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    evaluator: str
    passed: bool
    score: float
    detail: str


class Evaluator(Protocol):
    name: str

    def evaluate(self, case: EvaluationCase, response: EvaluationResponse) -> EvaluationResult:
        """Evaluate a response deterministically."""


class ExactMatchEvaluator:
    name = "exact_match"

    def __init__(self, expected: str | None = None) -> None:
        self.expected = expected

    def evaluate(self, case: EvaluationCase, response: EvaluationResponse) -> EvaluationResult:
        expected = self.expected if self.expected is not None else case.reference_answer
        passed = expected is not None and response.text.strip() == expected.strip()
        return EvaluationResult(self.name, passed, 1.0 if passed else 0.0, "exact match")


class SubstringEvaluator:
    name = "substring"

    def __init__(self, substring: str | None = None) -> None:
        self.substring = substring

    def evaluate(self, case: EvaluationCase, response: EvaluationResponse) -> EvaluationResult:
        expected = self.substring or case.expected_criteria
        passed = expected.lower() in response.text.lower()
        return EvaluationResult(self.name, passed, 1.0 if passed else 0.0, "substring present")


class KeywordPresenceEvaluator:
    name = "keyword_presence"

    def evaluate(self, case: EvaluationCase, response: EvaluationResponse) -> EvaluationResult:
        if not case.expected_keywords:
            return EvaluationResult(self.name, True, 1.0, "no keywords required")
        lowered = response.text.lower()
        matches = sum(1 for keyword in case.expected_keywords if keyword.lower() in lowered)
        score = matches / len(case.expected_keywords)
        return EvaluationResult(self.name, score == 1.0, score, f"{matches} keywords matched")


class ForbiddenPatternEvaluator:
    name = "forbidden_pattern"

    def evaluate(self, case: EvaluationCase, response: EvaluationResponse) -> EvaluationResult:
        for pattern in case.forbidden_patterns:
            if re.search(pattern, response.text, flags=re.IGNORECASE):
                return EvaluationResult(
                    self.name, False, 0.0, f"forbidden pattern matched: {pattern}"
                )
        return EvaluationResult(self.name, True, 1.0, "no forbidden patterns matched")


class RegexEvaluator:
    name = "regex"

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern

    def evaluate(self, case: EvaluationCase, response: EvaluationResponse) -> EvaluationResult:
        passed = re.search(self.pattern, response.text) is not None
        return EvaluationResult(self.name, passed, 1.0 if passed else 0.0, "regex match")


class LatencyThresholdEvaluator:
    name = "latency_threshold"

    def __init__(self, max_latency_ms: float) -> None:
        self.max_latency_ms = max_latency_ms

    def evaluate(self, case: EvaluationCase, response: EvaluationResponse) -> EvaluationResult:
        passed = response.latency_ms <= self.max_latency_ms
        return EvaluationResult(
            self.name,
            passed,
            1.0 if passed else 0.0,
            f"latency_ms={response.latency_ms:.2f}",
        )


class ResponseLengthEvaluator:
    name = "response_length"

    def __init__(self, *, min_chars: int = 0, max_chars: int | None = None) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars

    def evaluate(self, case: EvaluationCase, response: EvaluationResponse) -> EvaluationResult:
        length = len(response.text)
        above_min = length >= self.min_chars
        below_max = self.max_chars is None or length <= self.max_chars
        passed = above_min and below_max
        return EvaluationResult(self.name, passed, 1.0 if passed else 0.0, f"chars={length}")
