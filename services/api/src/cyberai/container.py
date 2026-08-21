"""Composition root.

The only place that knows which concrete adapters exist. Everything else
depends on interfaces, which is what makes the model runtime, the cache and the
database replaceable without touching business code.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cyberai.core.config import Settings
from cyberai.core.logging import get_logger
from cyberai.modules.billing import (
    EntitlementService,
    LimitEnforcer,
    ProviderTokenEstimator,
    StaticPlanCatalog,
)
from cyberai.modules.billing.redis_rate_limit import RedisRateLimiter
from cyberai.modules.billing.repository import BillingRepository, PersistentUsageSink
from cyberai.modules.inference import InferenceGateway, ProviderRegistry
from cyberai.modules.inference.providers import MockModelProvider, OpenAICompatibleModelProvider
from cyberai.modules.modelgw import (
    ModelGateway,
    ModelRouter,
    default_catalog,
)
from cyberai.modules.orchestrator.service import OrchestratorService
from cyberai.modules.policy import AbuseTracker, NoopPolicyEngine, PolicyEngine, PolicyProfile
from cyberai.modules.policy.audit import SecurityAuditRecorder
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
    metrics.gauge(
        "cyberai_build_info",
        labels={
            "version": settings.version,
            "environment": settings.environment.value,
            "commit": settings.build.commit[:12],
        },
    ).set(1)
    plan_catalog = StaticPlanCatalog()
    billing_repository = BillingRepository(database, plan_catalog, metrics=metrics)
    policy_engine = PolicyEngine()
    abuse_tracker = AbuseTracker(
        threshold=settings.policy.abuse_threshold,
        window_seconds=settings.policy.abuse_window_seconds,
    )
    security_audit_recorder = SecurityAuditRecorder(database, metrics=metrics)

    providers = ProviderRegistry()
    if not settings.environment.is_deployed:
        providers.register(MockModelProvider(settings.mock))
    if settings.openai_compatible.enabled:
        providers.register(OpenAICompatibleModelProvider(settings.openai_compatible))
    inference_gateway = InferenceGateway(providers, settings.inference, metrics=metrics)

    catalog = default_catalog(
        openai_compatible=settings.openai_compatible,
        include_mock=not settings.environment.is_deployed,
    )
    router = ModelRouter(catalog, settings.models)
    token_estimator = ProviderTokenEstimator(catalog, inference_gateway)
    rate_limiter = RedisRateLimiter(
        cache.client,
        fail_open=settings.billing.rate_limit_fail_open,
    )
    limit_enforcer = LimitEnforcer(
        plan_catalog=plan_catalog,
        entitlement_service=EntitlementService(plan_catalog),
        quota_store=billing_repository,
        rate_limiter=rate_limiter,
        token_estimator=token_estimator,
        subscription_provider=billing_repository,
        default_model_key=settings.models.default_model,
        metrics=metrics,
    )
    model_gateway = ModelGateway(
        router,
        inference_gateway,
        PersistentUsageSink(billing_repository),
        metrics=metrics,
    )
    orchestrator = OrchestratorService(
        model_gateway,
        limit_enforcer=limit_enforcer if settings.billing.enabled else None,
        policy_engine=policy_engine if settings.policy.enabled else NoopPolicyEngine(),
        abuse_tracker=abuse_tracker if settings.policy.enabled else None,
        security_audit_sink=security_audit_recorder if settings.policy.enabled else None,
        policy_profile=PolicyProfile(settings.policy.profile),
        metrics=metrics,
    )

    logger.info(
        "services.wired",
        providers=sorted(providers.all()),
        models=[model.key for model in catalog],
        default_model=settings.models.default_model,
        fallback_models=settings.models.fallback_models,
    )
    return Services(
        started_at=datetime.now(UTC),
        settings=settings,
        database=database,
        cache=cache,
        providers=providers,
        inference_gateway=inference_gateway,
        catalog=catalog,
        router=router,
        plan_catalog=plan_catalog,
        billing_repository=billing_repository,
        limit_enforcer=limit_enforcer,
        policy_engine=policy_engine,
        abuse_tracker=abuse_tracker,
        security_audit_recorder=security_audit_recorder,
        model_gateway=model_gateway,
        orchestrator=orchestrator,
        metrics=metrics,
    )


async def shutdown_services(services: Services) -> None:
    """Release every resource, reporting failures instead of masking them."""
    await services.cache.close()
    await services.database.dispose()
