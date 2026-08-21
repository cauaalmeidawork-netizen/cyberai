"""Application state and services definition.

Separated from container.py to avoid transitive imports of concrete providers into the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cyberai.core.config import Settings
from cyberai.modules.billing import LimitEnforcer, StaticPlanCatalog
from cyberai.modules.billing.providers import BillingProvider
from cyberai.modules.billing.repository import BillingRepository
from cyberai.modules.inference import InferenceGateway, ProviderRegistry
from cyberai.modules.modelgw import ModelCatalog, ModelGateway, ModelRouter
from cyberai.modules.orchestrator.service import OrchestratorService
from cyberai.modules.policy import AbuseTracker, PolicyEngine
from cyberai.modules.policy.audit import SecurityAuditRecorder
from cyberai.observability.metrics import MetricsRecorder
from cyberai.platform.cache import RedisCache
from cyberai.platform.db import Database


@dataclass(frozen=True, slots=True)
class Services:
    """Every long-lived dependency of the process."""

    started_at: datetime
    settings: Settings
    database: Database
    cache: RedisCache
    providers: ProviderRegistry
    inference_gateway: InferenceGateway
    catalog: ModelCatalog
    router: ModelRouter
    plan_catalog: StaticPlanCatalog
    billing_repository: BillingRepository
    billing_provider: BillingProvider | None
    limit_enforcer: LimitEnforcer
    policy_engine: PolicyEngine
    abuse_tracker: AbuseTracker
    security_audit_recorder: SecurityAuditRecorder
    model_gateway: ModelGateway
    orchestrator: OrchestratorService
    metrics: MetricsRecorder
