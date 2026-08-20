"""Composition root.

The only place that knows which concrete adapters exist. Everything else
depends on interfaces, which is what makes the model runtime, the cache and the
database replaceable without touching business code.
"""

from __future__ import annotations

from cyberai.core.config import Settings
from cyberai.core.logging import get_logger
from cyberai.modules.inference import InferenceGateway, ProviderRegistry
from cyberai.modules.inference.providers import MockModelProvider, OpenAICompatibleModelProvider
from cyberai.modules.modelgw import (
    LoggingUsageSink,
    ModelGateway,
    ModelRouter,
    default_catalog,
)
from cyberai.modules.orchestrator.service import OrchestratorService
from cyberai.observability import PrometheusMetricsRecorder
from cyberai.platform.cache import RedisCache
from cyberai.platform.db import Database
from cyberai.state import Services as Services

logger = get_logger(__name__)


def build_services(settings: Settings) -> Services:
    """Wire the object graph.

    The mock provider is always registered. Real providers are enabled only by
    explicit configuration so development and CI remain deterministic.
    """
    database = Database(settings.database)
    cache = RedisCache(settings.redis)
    metrics = PrometheusMetricsRecorder()

    providers = ProviderRegistry([MockModelProvider(settings.mock)])
    if settings.openai_compatible.enabled:
        providers.register(OpenAICompatibleModelProvider(settings.openai_compatible))
    inference_gateway = InferenceGateway(providers, settings.inference, metrics=metrics)

    catalog = default_catalog(openai_compatible=settings.openai_compatible)
    router = ModelRouter(catalog, settings.models)
    model_gateway = ModelGateway(router, inference_gateway, LoggingUsageSink(), metrics=metrics)
    orchestrator = OrchestratorService(model_gateway, metrics=metrics)

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
        metrics=metrics,
    )


async def shutdown_services(services: Services) -> None:
    """Release every resource, reporting failures instead of masking them."""
    await services.cache.close()
    await services.database.dispose()
