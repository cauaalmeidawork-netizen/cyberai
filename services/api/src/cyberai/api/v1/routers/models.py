"""The model catalog, as seen by a client.

Read-only, and deliberately narrower than ``ModelSpec``: pricing and provider
routing are internal business data. A client needs to know what it can ask for,
not what it costs us to serve.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cyberai.api.deps import ModelCatalogDep

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


@router.get("/models", response_model=ModelListResponse, summary="List available models")
async def list_models(catalog: ModelCatalogDep) -> ModelListResponse:
    return ModelListResponse(
        data=[
            ModelInfo(
                key=model.key,
                display_name=model.display_name,
                description=model.description,
                context_window=model.context_window,
                max_output_tokens=model.max_output_tokens,
                tasks=sorted(task.value for task in model.tasks),
            )
            for model in catalog.list_all()
        ]
    )
