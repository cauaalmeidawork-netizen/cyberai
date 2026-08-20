"""Prometheus adapter for the metrics abstraction."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from cyberai.observability.metrics import (
    CounterMetric,
    GaugeMetric,
    HistogramMetric,
    MetricLabels,
    validate_labels,
)

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class _PrometheusCounter:
    def __init__(self, counter: Counter, labels: MetricLabels) -> None:
        self._counter = counter
        self._labels = labels

    def add(self, amount: float = 1.0) -> None:
        self._counter.labels(**self._labels).inc(amount)


class _PrometheusHistogram:
    def __init__(self, histogram: Histogram, labels: MetricLabels) -> None:
        self._histogram = histogram
        self._labels = labels

    def record(self, value: float) -> None:
        self._histogram.labels(**self._labels).observe(value)


class _PrometheusGauge:
    def __init__(self, gauge: Gauge, labels: MetricLabels) -> None:
        self._gauge = gauge
        self._labels = labels

    def set(self, value: float) -> None:
        self._gauge.labels(**self._labels).set(value)


class PrometheusMetricsRecorder:
    """Prometheus-backed metrics recorder with per-process registry."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry()
        self._counters: dict[tuple[str, tuple[str, ...]], Counter] = {}
        self._histograms: dict[tuple[str, tuple[str, ...]], Histogram] = {}
        self._gauges: dict[tuple[str, tuple[str, ...]], Gauge] = {}

    def counter(self, name: str, labels: MetricLabels | None = None) -> CounterMetric:
        safe_labels = validate_labels(labels)
        label_names = tuple(sorted(safe_labels))
        key = (name, label_names)
        metric = self._counters.get(key)
        if metric is None:
            metric = Counter(name, f"{name} counter", label_names, registry=self.registry)
            self._counters[key] = metric
        return _PrometheusCounter(metric, safe_labels)

    def histogram(self, name: str, labels: MetricLabels | None = None) -> HistogramMetric:
        safe_labels = validate_labels(labels)
        label_names = tuple(sorted(safe_labels))
        key = (name, label_names)
        metric = self._histograms.get(key)
        if metric is None:
            metric = Histogram(name, f"{name} histogram", label_names, registry=self.registry)
            self._histograms[key] = metric
        return _PrometheusHistogram(metric, safe_labels)

    def gauge(self, name: str, labels: MetricLabels | None = None) -> GaugeMetric:
        safe_labels = validate_labels(labels)
        label_names = tuple(sorted(safe_labels))
        key = (name, label_names)
        metric = self._gauges.get(key)
        if metric is None:
            metric = Gauge(name, f"{name} gauge", label_names, registry=self.registry)
            self._gauges[key] = metric
        return _PrometheusGauge(metric, safe_labels)

    def render(self) -> bytes:
        return generate_latest(self.registry)
