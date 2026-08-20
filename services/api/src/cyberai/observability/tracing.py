"""OpenTelemetry helpers that add CyberAI correlation attributes."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry.trace import Span, get_tracer

from cyberai.core.context import current_context


@contextmanager
def start_span(
    name: str, attributes: Mapping[str, str | int | float | bool] | None = None
) -> Iterator[Span]:
    tracer = get_tracer("cyberai")
    ctx = current_context()
    span_attributes: dict[str, str | int | float | bool] = dict(attributes or {})
    if ctx.request_id is not None:
        span_attributes["cyberai.request_id"] = ctx.request_id
    if ctx.trace_id is not None:
        span_attributes["cyberai.trace_id"] = ctx.trace_id

    with tracer.start_as_current_span(name, attributes=span_attributes) as span:
        yield span


def record_exception(
    span: Span, exc: BaseException, *, attributes: Mapping[str, Any] | None = None
) -> None:
    span.record_exception(exc, attributes=dict(attributes or {}))
