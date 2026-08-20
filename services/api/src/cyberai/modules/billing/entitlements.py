"""Plan entitlement checks."""

from __future__ import annotations

from cyberai.modules.billing.plans import StaticPlanCatalog
from cyberai.modules.billing.types import EntitlementDecision, Subscription


class EntitlementService:
    def __init__(self, plan_catalog: StaticPlanCatalog) -> None:
        self._plan_catalog = plan_catalog

    def can_use_model(self, subscription: Subscription, model_key: str) -> EntitlementDecision:
        plan = self._plan_catalog.get(subscription.plan_key)
        allowed_models = plan.limits.allowed_models
        if allowed_models is None or model_key in allowed_models:
            return EntitlementDecision(allowed=True)
        return EntitlementDecision(
            allowed=False,
            reason="model_not_allowed",
            resource="model",
        )

    def can_use_rag(self, subscription: Subscription) -> EntitlementDecision:
        plan = self._plan_catalog.get(subscription.plan_key)
        if plan.limits.rag_allowed:
            return EntitlementDecision(allowed=True)
        return EntitlementDecision(False, reason="rag_not_allowed", resource="rag")

    def can_ingest_document(
        self, subscription: Subscription, current_documents: int
    ) -> EntitlementDecision:
        plan = self._plan_catalog.get(subscription.plan_key)
        if current_documents < plan.limits.document_limit:
            return EntitlementDecision(allowed=True)
        return EntitlementDecision(
            allowed=False,
            reason="document_limit_exceeded",
            resource="documents",
        )

    def can_make_request(self, subscription: Subscription) -> EntitlementDecision:
        self._plan_catalog.get(subscription.plan_key)
        return EntitlementDecision(allowed=True)
