"""Application state and services definition.

Separated from container.py to avoid transitive imports of concrete providers into the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyberai.core.config import Settings
from cyberai.modules.inference import InferenceGateway, ProviderRegistry
from cyberai.modules.modelgw import ModelCatalog, ModelGateway, ModelRouter
from cyberai.modules.orchestrator.service import OrchestratorService
from cyberai.platform.cache import RedisCache
from cyberai.platform.db import Database


@dataclass(frozen=True, slots=True)
class Services:
    """Every long-lived dependency of the process."""

    settings: Settings
    database: Database
    cache: RedisCache
    providers: ProviderRegistry
    inference_gateway: InferenceGateway
    catalog: ModelCatalog
    router: ModelRouter
    model_gateway: ModelGateway
    orchestrator: OrchestratorService
