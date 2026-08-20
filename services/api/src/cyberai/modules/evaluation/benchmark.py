"""Local benchmark runner backed by MockModelProvider."""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import Iterable

from cyberai.core.config import InferenceSettings, MockProviderSettings, ModelSettings
from cyberai.modules.evaluation.cases import EvaluationCase, EvaluationCategory
from cyberai.modules.evaluation.evaluators import (
    ForbiddenPatternEvaluator,
    KeywordPresenceEvaluator,
    ResponseLengthEvaluator,
)
from cyberai.modules.evaluation.runner import EvaluationReport, EvaluationRunner
from cyberai.modules.evaluation.runner_types import EvaluationResponse
from cyberai.modules.inference import InferenceGateway, Message, ProviderRegistry, Role, TextDelta
from cyberai.modules.inference.providers import MockModelProvider
from cyberai.modules.modelgw import (
    CompletionRequest,
    ModelGateway,
    ModelRouter,
    RequestPrincipal,
    default_catalog,
)
from cyberai.modules.modelgw.types import CompletionCompleted
from cyberai.modules.modelgw.usage import CollectingUsageSink


def default_cases() -> tuple[EvaluationCase, ...]:
    return (
        EvaluationCase(
            id="cyber-knowledge-001",
            version="1",
            category=EvaluationCategory.CYBERSECURITY_KNOWLEDGE,
            input="Explain least privilege in one sentence.",
            expected_criteria="Answer should describe limiting permissions.",
            expected_keywords=("Prompt preview",),
            forbidden_patterns=("api_key", "password"),
        ),
    )


async def run_mock_benchmark(cases: Iterable[EvaluationCase] | None = None) -> EvaluationReport:
    provider = MockModelProvider(MockProviderSettings())
    inference = InferenceGateway(
        ProviderRegistry([provider]),
        InferenceSettings(request_timeout_seconds=5.0, first_token_timeout_seconds=1.0),
    )
    gateway = ModelGateway(
        ModelRouter(default_catalog(), ModelSettings()),
        inference,
        CollectingUsageSink(),
    )

    async def responder(case: EvaluationCase) -> EvaluationResponse:
        started = time.perf_counter()
        request = CompletionRequest(
            messages=(Message(role=Role.USER, content=case.input),),
            principal=RequestPrincipal(request_id=f"eval-{case.id}"),
        )
        chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0
        model_key = "unknown"
        provider_key = "unknown"
        async for event in gateway.stream(request):
            if isinstance(event, TextDelta):
                chunks.append(event.text)
            elif isinstance(event, CompletionCompleted):
                input_tokens = event.usage.input_tokens
                output_tokens = event.usage.output_tokens
                model_key = event.model_key
                provider_key = event.provider
        return EvaluationResponse(
            text="".join(chunks),
            latency_ms=(time.perf_counter() - started) * 1000,
            model_key=model_key,
            provider_key=provider_key,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    runner = EvaluationRunner(
        evaluators=(
            KeywordPresenceEvaluator(),
            ForbiddenPatternEvaluator(),
            ResponseLengthEvaluator(min_chars=20),
        )
    )
    return await runner.run(tuple(cases or default_cases()), responder=responder)


def main() -> None:
    report = asyncio.run(run_mock_benchmark())
    sys.stdout.write(report.to_json())
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
