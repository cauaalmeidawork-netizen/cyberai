"""Small metrics abstraction used by application boundaries.

The interface deliberately models only counters, histograms and gauges so the
domain does not depend on Prometheus APIs or registry details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MetricLabels = dict[str, str]

_FORBIDDEN_LABELS = frozenset(
    {
        "request_id",
        "trace_id",
        "user_id",
        "org_id",
        "organization_id",
        "conversation_id",
        "project_id",
        "document_id",
        "chunk_id",
        "prompt",
        "content",
        "authorization",
    }
)


def validate_labels(labels: MetricLabels | None) -> MetricLabels:
    safe_labels = dict(labels or {})
    forbidden = sorted(set(safe_labels) & _FORBIDDEN_LABELS)
    if forbidden:
        joined = ", ".join(forbidden)
        raise ValueError(
            f"Metrics label set contains high-cardinality or sensitive labels: {joined}"
        )
    return safe_labels


class CounterMetric(Protocol):
    def add(self, amount: float = 1.0) -> None:
        """Increment the counter by amount."""


class HistogramMetric(Protocol):
    def record(self, value: float) -> None:
        """Record a histogram observation."""


class GaugeMetric(Protocol):
    def set(self, value: float) -> None:
        """Set the gauge value."""


class MetricsRecorder(Protocol):
    def counter(self, name: str, labels: MetricLabels | None = None) -> CounterMetric:
        """Return a counter handle."""

    def histogram(self, name: str, labels: MetricLabels | None = None) -> HistogramMetric:
        """Return a histogram handle."""

    def gauge(self, name: str, labels: MetricLabels | None = None) -> GaugeMetric:
        """Return a gauge handle."""


@dataclass(frozen=True, slots=True)
class MetricSample:
    kind: str
    name: str
    labels: MetricLabels
    value: float


class _NoopMetric:
    def add(self, amount: float = 1.0) -> None:
        return None

    def record(self, value: float) -> None:
        return None

    def set(self, value: float) -> None:
        return None


class NoopMetricsRecorder:
    def counter(self, name: str, labels: MetricLabels | None = None) -> CounterMetric:
        validate_labels(labels)
        return _NoopMetric()

    def histogram(self, name: str, labels: MetricLabels | None = None) -> HistogramMetric:
        validate_labels(labels)
        return _NoopMetric()

    def gauge(self, name: str, labels: MetricLabels | None = None) -> GaugeMetric:
        validate_labels(labels)
        return _NoopMetric()


class _InMemoryMetric:
    def __init__(
        self,
        recorder: InMemoryMetricsRecorder,
        *,
        kind: str,
        name: str,
        labels: MetricLabels,
    ) -> None:
        self._recorder = recorder
        self._kind = kind
        self._name = name
        self._labels = labels

    def add(self, amount: float = 1.0) -> None:
        self._recorder.samples.append(
            MetricSample(self._kind, self._name, self._labels, float(amount))
        )

    def record(self, value: float) -> None:
        self._recorder.samples.append(
            MetricSample(self._kind, self._name, self._labels, float(value))
        )

    def set(self, value: float) -> None:
        self._recorder.samples.append(
            MetricSample(self._kind, self._name, self._labels, float(value))
        )


class InMemoryMetricsRecorder:
    """Recorder used by tests to inspect emitted samples without Prometheus."""

    def __init__(self) -> None:
        self.samples: list[MetricSample] = []

    def counter(self, name: str, labels: MetricLabels | None = None) -> CounterMetric:
        return _InMemoryMetric(self, kind="counter", name=name, labels=validate_labels(labels))

    def histogram(self, name: str, labels: MetricLabels | None = None) -> HistogramMetric:
        return _InMemoryMetric(self, kind="histogram", name=name, labels=validate_labels(labels))

    def gauge(self, name: str, labels: MetricLabels | None = None) -> GaugeMetric:
        return _InMemoryMetric(self, kind="gauge", name=name, labels=validate_labels(labels))
