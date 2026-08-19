"""Model Gateway failures."""

from __future__ import annotations

from cyberai.core.errors import AppError


class ModelNotFoundError(AppError):
    code = "model_not_found"
    status_code = 404
    title = "Model Not Found"
    default_detail = "The requested model does not exist or is not available to you."


class NoModelAvailableError(AppError):
    """Routing produced no candidate, or every candidate failed."""

    code = "no_model_available"
    status_code = 503
    title = "No Model Available"
    default_detail = "No model is currently able to serve this request."
