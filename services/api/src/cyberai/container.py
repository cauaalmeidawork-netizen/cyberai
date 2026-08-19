"""Composition root.

The only place that knows which concrete adapters exist. Everything else
depends on interfaces, which is what makes the model runtime, the cache and the
database replaceable without touching business code.
"""

from __future__ import annotations

from cyberai.core.config import Settings
from cyberai.core.logging import get_logger
from cyberai.modules.inference import InferenceGateway, ProviderRegistry
from cyberai.modules.inference.providers import MockModelProvider
from cyberai.modules.modelgw import (
    LoggingUsageSink,
    ModelGateway,
    ModelRouter,
    default_catalog,
)
from cyberai.modules.orchestrator.service import OrchestratorService
from cyberai.platform.cache import RedisCache
from cyberai.platform.db import Database
from cyberai.state import Services as Services

logger = get_logger(__name__)





def build_services(settings: Settings) -> Services:
    """Wire the object graph.

    M0 registers only the mock provider. Adding the commercial provider (M4) or
    a self-hosted GPU runtime (M11) is one extra ``registry.register(...)`` call
    plus a catalog entry - no consumer changes.
    """
    database = Database(settings.database)
    cache = RedisCache(settings.redis)

    providers = ProviderRegistry([MockModelProvider(settings.mock)])
    inference_gateway = InferenceGateway(providers, settings.inference)

    catalog = default_catalog()
    router = ModelRouter(catalog, settings.models)
    model_gateway = ModelGateway(router, inference_gateway, LoggingUsageSink())
    orchestrator = OrchestratorService(model_gateway)

    logger.info(
        "services.wired",
        providers=sorted(providers.all()),
        models=[model.key for model in catalog],
        default_model=settings.models.default_model,
        fallback_models=settings.models.fallback_models,
    )
    return Services(
        settings=settings,
        database=database,
        cache=cache,
        providers=providers,
        inference_gateway=inference_gateway,
        catalog=catalog,
        router=router,
        model_gateway=model_gateway,
        orchestrator=orchestrator,
    )


async def shutdown_services(services: Services) -> None:
    """Release every resource, reporting failures instead of masking them."""
    await services.cache.close()
    await services.database.dispose()
