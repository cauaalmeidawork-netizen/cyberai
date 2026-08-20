"""Tests for M4 observability metrics, tracing and instrumentation."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from cyberai.core.config import InferenceSettings, MockProviderSettings, ModelSettings
from cyberai.core.context import bind_context
from cyberai.modules.inference import InferenceGateway, Message, ProviderRegistry, Role
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
from cyberai.modules.orchestrator.service import OrchestratorService
from cyberai.modules.rag.abstractions import RetrievedChunk, Retriever, VectorStore
from cyberai.modules.rag.providers import MockEmbeddingProvider, StandardRetriever
from cyberai.observability.metrics import InMemoryMetricsRecorder, MetricSample
from cyberai.observability.prometheus import PrometheusMetricsRecorder
from cyberai.platform.db.models import Chunk


async def _drain(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


def test_in_memory_metrics_records_low_cardinality_samples() -> None:
    metrics = InMemoryMetricsRecorder()

    metrics.counter("inference_requests_total", labels={"provider": "mock"}).add()
    metrics.histogram("inference_duration_seconds", labels={"provider": "mock"}).record(0.25)
    metrics.gauge("rag_chunks_returned", labels={"status": "success"}).set(3)

    assert MetricSample("counter", "inference_requests_total", {"provider": "mock"}, 1.0) in (
        metrics.samples
    )
    assert MetricSample("histogram", "inference_duration_seconds", {"provider": "mock"}, 0.25) in (
        metrics.samples
    )
    assert MetricSample("gauge", "rag_chunks_returned", {"status": "success"}, 3.0) in (
        metrics.samples
    )


def test_metrics_reject_high_cardinality_labels() -> None:
    metrics = InMemoryMetricsRecorder()

    with pytest.raises(ValueError, match="high-cardinality"):
        metrics.counter("http_requests_total", labels={"request_id": "req-1"}).add()


def test_prometheus_adapter_exports_expected_metric_names() -> None:
    metrics = PrometheusMetricsRecorder()

    metrics.counter("http_requests_total", labels={"method": "GET", "route": "/healthz"}).add()
    metrics.histogram("http_request_duration_seconds", labels={"method": "GET"}).record(0.01)

    rendered = metrics.render().decode("utf-8")

    assert "http_requests_total" in rendered
    assert "http_request_duration_seconds" in rendered
    assert 'method="GET"' in rendered


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus(app_client: AsyncClient) -> None:
    await app_client.get("/api/v1/meta")

    response = await app_client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_requests_total" in response.text


@pytest.mark.asyncio
async def test_http_metrics_do_not_use_request_id_label(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/v1/meta", headers={"x-request-id": "req-low-card"})

    assert response.status_code == 200
    metrics_response = await app_client.get("/metrics")
    assert "req-low-card" not in metrics_response.text
    assert "http_requests_total" in metrics_response.text


def test_trace_context_adds_request_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    from cyberai.observability import tracing

    captured: dict[str, object] = {}

    class FakeSpan:
        def record_exception(self, exception: BaseException, attributes: dict[str, object]) -> None:
            captured["exception"] = type(exception).__name__
            captured["exception_attributes"] = attributes

    class FakeSpanContext:
        def __enter__(self) -> FakeSpan:
            return FakeSpan()

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

    class FakeTracer:
        def start_as_current_span(
            self,
            name: str,
            attributes: dict[str, object],
        ) -> FakeSpanContext:
            captured["name"] = name
            captured["attributes"] = attributes
            return FakeSpanContext()

    monkeypatch.setattr(tracing, "get_tracer", lambda name: FakeTracer())

    with (
        bind_context(request_id="req-trace", trace_id="trace-context"),
        tracing.start_span("ai.orchestrator"),
    ):
        pass

    attributes = captured["attributes"]
    assert isinstance(attributes, dict)
    assert captured["name"] == "ai.orchestrator"
    assert attributes["cyberai.request_id"] == "req-trace"
    assert attributes["cyberai.trace_id"] == "trace-context"


@pytest.mark.asyncio
async def test_model_gateway_and_inference_record_metrics() -> None:
    metrics = InMemoryMetricsRecorder()
    providers = ProviderRegistry([MockModelProvider(MockProviderSettings())])
    inference = InferenceGateway(
        providers,
        InferenceSettings(request_timeout_seconds=5.0, first_token_timeout_seconds=1.0),
        metrics=metrics,
    )
    router = ModelRouter(default_catalog(), ModelSettings())
    gateway = ModelGateway(router, inference, CollectingUsageSink(), metrics=metrics)
    request = CompletionRequest(
        messages=(Message(role=Role.USER, content="hello"),),
        principal=RequestPrincipal(request_id="req-test"),
    )

    events = await _drain(gateway.stream(request))

    assert isinstance(events[-1], CompletionCompleted)
    metric_names = {sample.name for sample in metrics.samples}
    assert "model_gateway_requests_total" in metric_names
    assert "model_gateway_duration_seconds" in metric_names
    assert "inference_requests_total" in metric_names
    assert "inference_duration_seconds" in metric_names
    assert "inference_input_tokens_total" in metric_names
    assert "inference_output_tokens_total" in metric_names


@pytest.mark.asyncio
async def test_orchestrator_records_rag_metrics() -> None:
    class StaticRetriever(Retriever):
        async def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
            return [RetrievedChunk(content="least privilege context", metadata=None, score=1.0)]

    metrics = InMemoryMetricsRecorder()
    gateway, _sink = _build_gateway_with_metrics(metrics)
    orchestrator = OrchestratorService(gateway, metrics=metrics)
    request_principal = RequestPrincipal(request_id="req-orch")

    events = await _drain(
        orchestrator.stream_chat(
            messages=(Message(role=Role.USER, content="What is least privilege?"),),
            model=None,
            max_tokens=128,
            temperature=0.2,
            principal=request_principal,
            retriever=StaticRetriever(),
        )
    )

    assert isinstance(events[-1], CompletionCompleted)
    metric_names = {sample.name for sample in metrics.samples}
    assert "ai_orchestrator_requests_total" in metric_names
    assert "ai_orchestrator_duration_seconds" in metric_names
    assert "rag_retrieval_duration_seconds" in metric_names
    assert "rag_chunks_returned" in metric_names


def test_log_processor_attaches_request_and_trace_ids() -> None:
    from cyberai.core.logging import request_context_processor

    with bind_context(request_id="req-log", trace_id="trace-log"):
        event = request_context_processor(None, "info", {})

    assert event["request_id"] == "req-log"
    assert event["trace_id"] == "trace-log"


@pytest.mark.asyncio
async def test_rag_embedding_and_retrieval_record_metrics() -> None:
    class StaticVectorStore(VectorStore):
        async def add_chunks(self, chunks: list[Chunk]) -> None:
            return None

        async def search(self, query_vector: list[float], top_k: int = 3) -> list[RetrievedChunk]:
            return [RetrievedChunk(content="retrieved", metadata=None, score=1.0)]

    metrics = InMemoryMetricsRecorder()
    embeddings = MockEmbeddingProvider(dim=4, metrics=metrics)
    retriever = StandardRetriever(embeddings, StaticVectorStore(), metrics=metrics)

    chunks = await retriever.retrieve("least privilege", top_k=3)

    assert len(chunks) == 1
    metric_names = {sample.name for sample in metrics.samples}
    assert "rag_embedding_duration_seconds" in metric_names
    assert "rag_retrieval_requests_total" in metric_names
    assert "rag_retrieval_duration_seconds" in metric_names


def _build_gateway_with_metrics(
    metrics: InMemoryMetricsRecorder,
) -> tuple[ModelGateway, CollectingUsageSink]:
    providers = ProviderRegistry([MockModelProvider(MockProviderSettings())])
    inference = InferenceGateway(
        providers,
        InferenceSettings(request_timeout_seconds=5.0, first_token_timeout_seconds=1.0),
        metrics=metrics,
    )
    router = ModelRouter(default_catalog(), ModelSettings())
    sink = CollectingUsageSink()
    return ModelGateway(router, inference, sink, metrics=metrics), sink
