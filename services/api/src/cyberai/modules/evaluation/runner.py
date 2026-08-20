"""Evaluation runner and benchmark summary generation."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass
from statistics import quantiles

from cyberai.modules.evaluation.cases import EvaluationCase
from cyberai.modules.evaluation.evaluators import EvaluationResult, Evaluator
from cyberai.modules.evaluation.runner_types import EvaluationResponse

Responder = Callable[[EvaluationCase], Awaitable[EvaluationResponse]]

__all__ = [
    "BenchmarkSummary",
    "CaseEvaluation",
    "EvaluationReport",
    "EvaluationResponse",
    "EvaluationRunner",
]


@dataclass(frozen=True, slots=True)
class CaseEvaluation:
    case_id: str
    category: str
    model_key: str
    provider_key: str
    passed: bool
    score: float
    latency_ms: float
    input_tokens: int
    output_tokens: int
    evaluator_results: tuple[EvaluationResult, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    total_cases: int
    passed: int
    failed: int
    average_score: float
    p50_latency_ms: float
    p95_latency_ms: float
    input_tokens: int
    output_tokens: int
    results_by_category: dict[str, dict[str, int]]
    results_by_model: dict[str, dict[str, int]]


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    summary: BenchmarkSummary
    results: tuple[CaseEvaluation, ...]
    baseline: str | None = None
    candidate: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2)


class EvaluationRunner:
    def __init__(
        self,
        *,
        evaluators: Iterable[Evaluator],
        baseline: str | None = None,
        candidate: str | None = None,
    ) -> None:
        self.evaluators = tuple(evaluators)
        self.baseline = baseline
        self.candidate = candidate

    async def run(
        self, cases: Iterable[EvaluationCase], *, responder: Responder
    ) -> EvaluationReport:
        results: list[CaseEvaluation] = []
        for case in cases:
            response = await responder(case)
            evaluator_results = tuple(
                evaluator.evaluate(case, response) for evaluator in self.evaluators
            )
            score = _average(result.score for result in evaluator_results)
            passed = all(result.passed for result in evaluator_results)
            results.append(
                CaseEvaluation(
                    case_id=case.id,
                    category=case.category.value,
                    model_key=response.model_key,
                    provider_key=response.provider_key,
                    passed=passed,
                    score=score,
                    latency_ms=response.latency_ms,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    evaluator_results=evaluator_results,
                )
            )
        return EvaluationReport(
            summary=_summarize(results),
            results=tuple(results),
            baseline=self.baseline,
            candidate=self.candidate,
        )


def _average(values: Iterable[float]) -> float:
    items = tuple(values)
    if not items:
        return 1.0
    return sum(items) / len(items)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    if percentile == 50:
        return quantiles(values, n=100, method="inclusive")[49]
    if percentile == 95:
        return quantiles(values, n=100, method="inclusive")[94]
    raise ValueError("unsupported percentile")


def _bucket_increment(bucket: dict[str, int], passed: bool) -> None:
    bucket["total"] += 1
    if passed:
        bucket["passed"] += 1
    else:
        bucket["failed"] += 1


def _summarize(results: list[CaseEvaluation]) -> BenchmarkSummary:
    latencies = [result.latency_ms for result in results]
    by_category: dict[str, dict[str, int]] = {}
    by_model: dict[str, dict[str, int]] = {}
    for result in results:
        _bucket_increment(
            by_category.setdefault(result.category, {"total": 0, "passed": 0, "failed": 0}),
            result.passed,
        )
        _bucket_increment(
            by_model.setdefault(result.model_key, {"total": 0, "passed": 0, "failed": 0}),
            result.passed,
        )
    passed = sum(1 for result in results if result.passed)
    return BenchmarkSummary(
        total_cases=len(results),
        passed=passed,
        failed=len(results) - passed,
        average_score=_average(result.score for result in results),
        p50_latency_ms=_percentile(latencies, 50),
        p95_latency_ms=_percentile(latencies, 95),
        input_tokens=sum(result.input_tokens for result in results),
        output_tokens=sum(result.output_tokens for result in results),
        results_by_category=by_category,
        results_by_model=by_model,
    )
