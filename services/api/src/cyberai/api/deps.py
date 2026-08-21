"""FastAPI dependencies.

Dependencies read from ``app.state``, which the lifespan populates from the
composition root. Nothing here constructs a dependency, so a test can swap the
whole object graph by building a different ``Services``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from cyberai.core.config import Settings
from cyberai.modules.billing import StaticPlanCatalog
from cyberai.modules.billing.providers import BillingProvider
from cyberai.modules.billing.repository import BillingRepository
from cyberai.modules.inference import InferenceGateway
from cyberai.modules.modelgw import ModelCatalog, ModelGateway
from cyberai.modules.orchestrator.service import OrchestratorService
from cyberai.observability.metrics import MetricsRecorder
from cyberai.platform.cache import RedisCache
from cyberai.platform.db import Database
from cyberai.state import Services


def get_services(request: Request) -> Services:
    services: Services | None = getattr(request.app.state, "services", None)
    if services is None:  # pragma: no cover - only reachable if lifespan did not run
        raise RuntimeError("application services are not initialised")
    return services


def get_settings_dep(services: Annotated[Services, Depends(get_services)]) -> Settings:
    return services.settings


def get_database(services: Annotated[Services, Depends(get_services)]) -> Database:
    return services.database


def get_cache(services: Annotated[Services, Depends(get_services)]) -> RedisCache:
    return services.cache


def get_model_catalog(services: Annotated[Services, Depends(get_services)]) -> ModelCatalog:
    return services.catalog


def get_model_gateway(services: Annotated[Services, Depends(get_services)]) -> ModelGateway:
    return services.model_gateway


def get_inference_gateway(
    services: Annotated[Services, Depends(get_services)],
) -> InferenceGateway:
    return services.inference_gateway


def get_orchestrator(
    services: Annotated[Services, Depends(get_services)],
) -> OrchestratorService:
    return services.orchestrator


def get_metrics(services: Annotated[Services, Depends(get_services)]) -> MetricsRecorder:
    return services.metrics


def get_billing_repository(
    services: Annotated[Services, Depends(get_services)],
) -> BillingRepository:
    return services.billing_repository


def get_billing_provider(
    services: Annotated[Services, Depends(get_services)],
) -> BillingProvider | None:
    return services.billing_provider


def get_plan_catalog(services: Annotated[Services, Depends(get_services)]) -> StaticPlanCatalog:
    return services.plan_catalog


ServicesDep = Annotated[Services, Depends(get_services)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DatabaseDep = Annotated[Database, Depends(get_database)]
CacheDep = Annotated[RedisCache, Depends(get_cache)]
ModelCatalogDep = Annotated[ModelCatalog, Depends(get_model_catalog)]
ModelGatewayDep = Annotated[ModelGateway, Depends(get_model_gateway)]
InferenceGatewayDep = Annotated[InferenceGateway, Depends(get_inference_gateway)]
OrchestratorServiceDep = Annotated[OrchestratorService, Depends(get_orchestrator)]
MetricsDep = Annotated[MetricsRecorder, Depends(get_metrics)]
BillingRepositoryDep = Annotated[BillingRepository, Depends(get_billing_repository)]
BillingProviderDep = Annotated[BillingProvider | None, Depends(get_billing_provider)]
PlanCatalogDep = Annotated[StaticPlanCatalog, Depends(get_plan_catalog)]
