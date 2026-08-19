"""Exception handlers.

Every failure leaves the API as an RFC 9457 problem document carrying the
request id. Internal details - exception types, driver messages, stack traces -
are logged and never serialised, in any environment. A stack trace in a
response is reconnaissance handed to an attacker, and this product's users are
precisely the people who know what to do with it.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from cyberai.core.errors import PROBLEM_CONTENT_TYPE, AppError, InternalError
from cyberai.core.logging import get_logger

logger = get_logger(__name__)

_STATUS_TITLES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    422: "Validation Failed",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def _problem_response(request: Request, problem: dict[str, Any], status_code: int) -> JSONResponse:
    request_id = request.scope.get("request_id")
    if request_id:
        problem.setdefault("request_id", request_id)
    return JSONResponse(
        status_code=status_code,
        content=problem,
        media_type=PROBLEM_CONTENT_TYPE,
    )


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    if exc.status_code >= 500:
        logger.error("request.failed", error_code=exc.code, path=request.url.path)
    else:
        logger.info("request.rejected", error_code=exc.code, path=request.url.path)
    return _problem_response(request, exc.to_problem(instance=request.url.path), exc.status_code)


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {
            "location": list(error.get("loc", ())),
            "message": error.get("msg", "invalid value"),
            "type": error.get("type", "invalid"),
        }
        for error in exc.errors()
    ]
    problem = {
        "type": "https://errors.cyberai.dev/validation_failed",
        "title": "Validation Failed",
        "status": 422,
        "detail": "The request payload is invalid.",
        "code": "validation_failed",
        "instance": request.url.path,
        "errors": errors,
    }
    logger.info("request.invalid_payload", path=request.url.path, error_count=len(errors))
    return _problem_response(request, problem, 422)


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status_code = exc.status_code
    title = _STATUS_TITLES.get(status_code, "Error")
    problem = {
        "type": f"https://errors.cyberai.dev/http_{status_code}",
        "title": title,
        "status": status_code,
        "detail": exc.detail if isinstance(exc.detail, str) else title,
        "code": f"http_{status_code}",
        "instance": request.url.path,
    }
    return _problem_response(request, problem, status_code)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Last line of defence: log everything, disclose nothing."""
    logger.exception(
        "request.unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=type(exc).__name__,
    )
    fallback = InternalError()
    return _problem_response(
        request, fallback.to_problem(instance=request.url.path), fallback.status_code
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
