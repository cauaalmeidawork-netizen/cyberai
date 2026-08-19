"""Structured logging.

Logs are events, not sentences: one JSON object per event, always carrying the
correlation fields of the current request. Two safeguards are built in rather
than left to reviewer discipline:

* a redaction processor masks any field whose name looks like a credential;
* connection URLs are masked so passwords never reach the log stream.

Prompt and model output are deliberately *not* logged anywhere in this module.
From M2 on they are customer data, and a log leak must not become a data leak.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any, Final

import structlog

from cyberai.core.config import LoggingSettings, mask_credentials
from cyberai.core.context import current_context

REDACTED: Final = "***redacted***"

_SENSITIVE_KEY_PARTS: Final = (
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "id_token",
    "password",
    "passwd",
    "secret",
    "private_key",
    "cookie",
    "session_token",
    "credential",
)

_URL_KEY_PARTS: Final = ("url", "dsn", "uri")

_MAX_REDACTION_DEPTH: Final = 6


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _looks_like_url(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _URL_KEY_PARTS)


def _redact_value(key: str, value: Any, depth: int) -> Any:
    if _is_sensitive(key):
        return REDACTED
    if depth >= _MAX_REDACTION_DEPTH:
        return value
    if isinstance(value, Mapping):
        return {k: _redact_value(str(k), v, depth + 1) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_redact_value(key, item, depth + 1) for item in value)
    if isinstance(value, str) and _looks_like_url(key):
        return mask_credentials(value)
    return value


def redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Mask credential-looking fields before they are rendered."""
    for key in list(event_dict.keys()):
        event_dict[key] = _redact_value(key, event_dict[key], 0)
    return event_dict


def request_context_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Attach request_id / trace_id / org_id / user_id to every event."""
    for key, value in current_context().as_log_fields().items():
        event_dict.setdefault(key, value)
    return event_dict


def logger_name_processor(
    logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Add the logger name, tolerating both stdlib loggers and structlog writers."""
    if "logger" not in event_dict:
        event_dict["logger"] = getattr(logger, "name", "cyberai")
    return event_dict


def configure_logging(settings: LoggingSettings, *, service: str, environment: str) -> None:
    """Configure structlog and route the stdlib logging module through it."""
    level = getattr(logging, settings.level)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        logger_name_processor,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        request_context_processor,
        redact_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: structlog.typing.Processor
    if settings.format == "json":
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.WriteLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Bring uvicorn / sqlalchemy / alembic output into the same stream and format.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).handlers = []
        logging.getLogger(noisy).propagate = True

    structlog.contextvars.bind_contextvars(service=service, environment=environment)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for the given module."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
