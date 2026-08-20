"""Tests for deterministic AI evaluation and local benchmark runner."""

from __future__ import annotations

import json

import pytest

from cyberai.modules.evaluation.cases import EvaluationCase, EvaluationCategory
from cyberai.modules.evaluation.evaluators import (
    ExactMatchEvaluator,
    ForbiddenPatternEvaluator,
    KeywordPresenceEvaluator,
    LatencyThresholdEvaluator,
    RegexEvaluator,
    ResponseLengthEvaluator,
    SubstringEvaluator,
)
from cyberai.modules.evaluation.runner import (
    BenchmarkSummary,
    EvaluationResponse,
    EvaluationRunner,
)


def _case(category: EvaluationCategory = EvaluationCategory.REASONING) -> EvaluationCase:
    return EvaluationCase(
        id="case-1",
        version="1",
        category=category,
        input="Explain least privilege.",
        expected_criteria="Must mention minimal permissions.",
        expected_keywords=("least", "privilege"),
        forbidden_patterns=("password",),
        metadata={"suite": "unit"},
    )


def _response(text: str, *, latency_ms: float = 100.0) -> EvaluationResponse:
    return EvaluationResponse(
        text=text,
        latency_ms=latency_ms,
        model_key="mock-analyst-1",
        provider_key="mock",
        input_tokens=10,
        output_tokens=20,
    )


def test_deterministic_evaluators_score_expected_responses() -> None:
    case = _case()
    response = _response("Least privilege means granting minimal permissions.")

    evaluators = (
        ExactMatchEvaluator(expected="Least privilege means granting minimal permissions."),
        SubstringEvaluator(substring="minimal permissions"),
        KeywordPresenceEvaluator(),
        ForbiddenPatternEvaluator(),
        RegexEvaluator(pattern=r"Least privilege"),
        LatencyThresholdEvaluator(max_latency_ms=250),
        ResponseLengthEvaluator(min_chars=20, max_chars=100),
    )

    results = [evaluator.evaluate(case, response) for evaluator in evaluators]

    assert all(result.passed for result in results)
    assert all(result.score == 1.0 for result in results)


def test_forbidden_pattern_evaluator_fails_on_forbidden_content() -> None:
    result = ForbiddenPatternEvaluator().evaluate(_case(), _response("The password is visible."))

    assert result.passed is False
    assert result.score == 0.0
    assert result.evaluator == "forbidden_pattern"


@pytest.mark.asyncio
async def test_evaluation_runner_summarizes_results_by_category_and_model() -> None:
    async def responder(case: EvaluationCase) -> EvaluationResponse:
        return _response(f"Mock answer for {case.input}")

    cases = (
        _case(EvaluationCategory.CYBERSECURITY_KNOWLEDGE),
        _case(EvaluationCategory.PROGRAMMING),
    )
    runner = EvaluationRunner(evaluators=(ResponseLengthEvaluator(min_chars=5),))

    report = await runner.run(cases, responder=responder)

    assert report.summary == BenchmarkSummary(
        total_cases=2,
        passed=2,
        failed=0,
        average_score=1.0,
        p50_latency_ms=100.0,
        p95_latency_ms=100.0,
        input_tokens=20,
        output_tokens=40,
        results_by_category={
            "cybersecurity_knowledge": {"total": 1, "passed": 1, "failed": 0},
            "programming": {"total": 1, "passed": 1, "failed": 0},
        },
        results_by_model={"mock-analyst-1": {"total": 2, "passed": 2, "failed": 0}},
    )


@pytest.mark.asyncio
async def test_evaluation_report_exports_structured_json() -> None:
    async def responder(case: EvaluationCase) -> EvaluationResponse:
        return _response(f"Mock answer for {case.id}")

    runner = EvaluationRunner(evaluators=(ResponseLengthEvaluator(min_chars=5),))
    report = await runner.run((_case(),), responder=responder)

    payload = json.loads(report.to_json())

    assert payload["summary"]["total_cases"] == 1
    assert payload["results"][0]["case_id"] == "case-1"
    assert payload["results"][0]["model_key"] == "mock-analyst-1"


@pytest.mark.asyncio
async def test_mock_benchmark_runner_executes_without_external_services() -> None:
    from cyberai.modules.evaluation.benchmark import run_mock_benchmark

    report = await run_mock_benchmark(cases=(_case(),))

    assert report.summary.total_cases == 1
    assert report.summary.input_tokens > 0
    assert report.summary.output_tokens > 0
    assert report.results[0].provider_key == "mock"
