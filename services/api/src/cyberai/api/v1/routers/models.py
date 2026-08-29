"""The model catalog, as seen by a client.

Read-only, and deliberately narrower than ``ModelSpec``: pricing and provider
routing are internal business data. A client needs to know what it can ask for,
not what it costs us to serve.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cyberai.api.deps import ModelCatalogDep, SettingsDep

router = APIRouter(tags=["models"])


class ModelInfo(BaseModel):
    key: str
    display_name: str
    description: str
    context_window: int
    max_output_tokens: int
    tasks: list[str]


class ModelListResponse(BaseModel):
    data: list[ModelInfo]
    default_model: str


@router.get("/models", response_model=ModelListResponse, summary="List available models")
async def list_models(catalog: ModelCatalogDep, settings: SettingsDep) -> ModelListResponse:
    # Public catalog: internal/test providers (mock) are never exposed to clients.
    models = list(catalog.list_all(include_internal=False))
    models.sort(key=lambda model: model.key != settings.models.default_model)
    if any(model.key == settings.models.default_model for model in models):
        public_default = settings.models.default_model
    elif models:
        public_default = models[0].key
    else:
        public_default = ""
    return ModelListResponse(
        default_model=public_default,
        data=[
            ModelInfo(
                key=model.key,
                display_name=model.display_name,
                description=model.description,
                context_window=model.context_window,
                max_output_tokens=model.max_output_tokens,
                tasks=sorted(task.value for task in model.tasks),
            )
            for model in models
        ],
    )
