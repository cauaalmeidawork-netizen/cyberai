"""Persistent billing repository and usage recorder."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cyberai.modules.billing.plans import StaticPlanCatalog
from cyberai.modules.billing.quotas import monthly_period
from cyberai.modules.billing.types import (
    BillingPeriod,
    BillingReservation,
    Plan,
    QuotaResource,
    QuotaSnapshot,
    Subscription,
    TokenEstimate,
    WebhookProcessingDecision,
)
from cyberai.modules.modelgw.usage import UsageRecord
from cyberai.observability.metrics import MetricsRecorder, NoopMetricsRecorder
from cyberai.platform.db import Database, TenantContext
from cyberai.platform.db.models import (
    BillingCustomerModel,
    BillingWebhookEventModel,
    SubscriptionModel,
    UsageAggregateModel,
    UsageRecordModel,
    UsageReservationModel,
)


class BillingRepository:
    """SQL-backed billing state with tenant-scoped access."""

    def __init__(
        self,
        db: Database,
        plan_catalog: StaticPlanCatalog | None = None,
        *,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._db = db
        self._plan_catalog = plan_catalog or StaticPlanCatalog()
        self._metrics = metrics or NoopMetricsRecorder()

    @property
    def database(self) -> Database:
        return self._db

    async def get_subscription(self, org_id: UUID) -> Subscription:
        async with self._db.session(TenantContext(org_id=org_id)) as session:
            result = await session.execute(
                select(SubscriptionModel)
                .where(
                    SubscriptionModel.org_id == org_id,
                    SubscriptionModel.status.in_(("active", "trialing")),
                )
                .order_by(SubscriptionModel.created_at.desc())
            )
            subscription = result.scalar_one_or_none()
        if subscription is None:
            return Subscription(org_id=org_id, plan_key="free")
        return Subscription(
            org_id=org_id,
            plan_key=subscription.plan_key,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
        )

    async def upsert_billing_customer(
        self,
        *,
        org_id: UUID,
        provider: str,
        provider_customer_id: str,
    ) -> BillingCustomerModel:
        async with self._db.session(TenantContext(org_id=org_id)) as session:
            customer = await session.scalar(
                select(BillingCustomerModel).where(
                    BillingCustomerModel.org_id == org_id,
                    BillingCustomerModel.provider == provider,
                )
            )
            if customer is None:
                customer = BillingCustomerModel(
                    org_id=org_id,
                    provider=provider,
                    provider_customer_id=provider_customer_id,
                )
            else:
                customer.provider_customer_id = provider_customer_id
            session.add(customer)
            await session.flush()
            await session.refresh(customer)
            return customer

    async def get_billing_customer(
        self, *, org_id: UUID, provider: str
    ) -> BillingCustomerModel | None:
        async with self._db.session(TenantContext(org_id=org_id)) as session:
            customer = await session.scalar(
                select(BillingCustomerModel)
                .where(
                    BillingCustomerModel.org_id == org_id,
                    BillingCustomerModel.provider == provider,
                )
                .limit(1)
            )
        return customer

    async def begin_webhook_event(
        self,
        *,
        provider: str,
        event_id: str,
        event_type: str | None = None,
    ) -> WebhookProcessingDecision:
        async with self._db.session() as session:
            existing = await session.scalar(
                select(BillingWebhookEventModel).where(
                    BillingWebhookEventModel.provider == provider,
                    BillingWebhookEventModel.event_id == event_id,
                )
            )
            if existing is not None:
                previous_status = existing.status
                if previous_status == "failed":
                    existing.status = "processing"
                    existing.error_code = None
                    session.add(existing)
                return WebhookProcessingDecision(
                    should_process=previous_status == "failed",
                    status=previous_status,
                )
            session.add(
                BillingWebhookEventModel(
                    provider=provider,
                    event_id=event_id,
                    event_type=event_type,
                    status="processing",
                )
            )
            return WebhookProcessingDecision(should_process=True, status="processing")

    async def mark_webhook_event_processed(self, *, provider: str, event_id: str) -> None:
        async with self._db.session() as session:
            event = await session.scalar(
                select(BillingWebhookEventModel).where(
                    BillingWebhookEventModel.provider == provider,
                    BillingWebhookEventModel.event_id == event_id,
                )
            )
            if event is not None:
                event.status = "processed"
                event.error_code = None
                event.processed_at = datetime.now(UTC)
                session.add(event)

    async def mark_webhook_event_failed(
        self,
        *,
        provider: str,
        event_id: str,
        error_code: str,
    ) -> None:
        async with self._db.session() as session:
            event = await session.scalar(
                select(BillingWebhookEventModel).where(
                    BillingWebhookEventModel.provider == provider,
                    BillingWebhookEventModel.event_id == event_id,
                )
            )
            if event is not None:
                event.status = "failed"
                event.error_code = error_code
                session.add(event)

    async def sync_provider_subscription(
        self,
        *,
        provider: str,
        provider_customer_id: str,
        provider_subscription_id: str,
        provider_status: str,
        plan_key: str,
        current_period_start: datetime | None,
        current_period_end: datetime | None,
    ) -> None:
        local_status = _local_subscription_status(provider_status)
        async with self._db.session() as session:
            customer = await session.scalar(
                select(BillingCustomerModel).where(
                    BillingCustomerModel.provider == provider,
                    BillingCustomerModel.provider_customer_id == provider_customer_id,
                )
            )
            if customer is None:
                raise ValueError("billing_customer_not_found")
            subscription = await session.scalar(
                select(SubscriptionModel).where(
                    SubscriptionModel.org_id == customer.org_id,
                    SubscriptionModel.provider == provider,
                    SubscriptionModel.provider_subscription_id == provider_subscription_id,
                )
            )
            if subscription is None:
                subscription = SubscriptionModel(
                    org_id=customer.org_id,
                    plan_key=plan_key,
                )
            subscription.plan_key = plan_key
            subscription.status = local_status
            subscription.provider = provider
            subscription.provider_customer_id = provider_customer_id
            subscription.provider_subscription_id = provider_subscription_id
            subscription.provider_status = provider_status
            subscription.current_period_start = current_period_start
            subscription.current_period_end = current_period_end
            session.add(subscription)

    async def reserve(
        self,
        *,
        org_id: UUID,
        request_id: str,
        plan: Plan,
        estimate: TokenEstimate,
        now: datetime | None = None,
    ) -> BillingReservation:
        period = monthly_period(now)
        async with self._db.session(TenantContext(org_id=org_id)) as session:
            existing = await self._locked_reservation(session, org_id, request_id)
            if existing is not None:
                return BillingReservation(
                    org_id=org_id,
                    request_id=request_id,
                    plan_key=existing.plan_key,
                    period_start=existing.period_start,
                    period_end=existing.period_end,
                    input_tokens=existing.reserved_input_tokens,
                    output_tokens=existing.reserved_output_tokens,
                    total_tokens=existing.reserved_total_tokens,
                )

            aggregate = await self._locked_aggregate(session, org_id, period)
            self._raise_if_exceeds_limits(aggregate, plan, estimate)
            aggregate.reserved_requests += 1
            aggregate.reserved_input_tokens += estimate.input_tokens
            aggregate.reserved_output_tokens += estimate.reserved_output_tokens
            aggregate.reserved_total_tokens += estimate.total_reserved_tokens
            session.add(
                UsageReservationModel(
                    org_id=org_id,
                    request_id=request_id,
                    plan_key=plan.key,
                    period_start=period.start,
                    period_end=period.end,
                    reserved_input_tokens=estimate.input_tokens,
                    reserved_output_tokens=estimate.reserved_output_tokens,
                    reserved_total_tokens=estimate.total_reserved_tokens,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing_after_race = await self._reservation(org_id, request_id)
                if existing_after_race is not None:
                    return existing_after_race
                raise
        return BillingReservation(
            org_id=org_id,
            request_id=request_id,
            plan_key=plan.key,
            period_start=period.start,
            period_end=period.end,
            input_tokens=estimate.input_tokens,
            output_tokens=estimate.reserved_output_tokens,
            total_tokens=estimate.total_reserved_tokens,
        )

    async def record_usage_once(self, record: UsageRecord) -> bool:
        if record.organization_id is None or record.request_id is None:
            return False
        org_id = UUID(record.organization_id)
        user_id = UUID(record.user_id) if record.user_id else None
        period = monthly_period(record.occurred_at)
        async with self._db.session(TenantContext(org_id=org_id)) as session:
            aggregate = await self._locked_aggregate(session, org_id, period)
            reservation = await self._locked_reservation(session, org_id, record.request_id)
            session.add(
                UsageRecordModel(
                    org_id=org_id,
                    user_id=user_id,
                    request_id=record.request_id,
                    provider=record.provider,
                    model_key=record.model_key,
                    provider_model=record.provider_model,
                    task=record.task,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    cached_input_tokens=record.cached_input_tokens,
                    latency_ms=record.latency_ms,
                    time_to_first_token_ms=record.time_to_first_token_ms,
                    attempts=record.attempts,
                    used_fallback=record.used_fallback,
                    status=record.status.value,
                    finish_reason=record.finish_reason,
                    error_code=record.error_code,
                    estimated_cost_usd=record.estimated_cost_usd,
                    actual_cost_usd=record.actual_cost_usd,
                    occurred_at=record.occurred_at,
                )
            )
            self._apply_actual_usage(aggregate, record, reservation)
            if reservation is not None:
                await session.delete(reservation)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                self._metrics.counter(
                    "billing_usage_records_total", labels={"status": "duplicate"}
                ).add()
                return False
        self._metrics.counter("billing_usage_records_total", labels={"status": "recorded"}).add()
        return True

    async def snapshots(
        self, *, org_id: UUID, plan: Plan, now: datetime | None = None
    ) -> tuple[QuotaSnapshot, ...]:
        period = monthly_period(now)
        async with self._db.session(TenantContext(org_id=org_id)) as session:
            aggregate = await self._get_aggregate(session, org_id, period)
        return (
            QuotaSnapshot(
                QuotaResource.REQUESTS,
                aggregate.used_requests if aggregate else 0,
                aggregate.reserved_requests if aggregate else 0,
                plan.limits.monthly_requests,
                period.start,
                period.end,
            ),
            QuotaSnapshot(
                QuotaResource.INPUT_TOKENS,
                aggregate.used_input_tokens if aggregate else 0,
                aggregate.reserved_input_tokens if aggregate else 0,
                plan.limits.monthly_input_tokens,
                period.start,
                period.end,
            ),
            QuotaSnapshot(
                QuotaResource.OUTPUT_TOKENS,
                aggregate.used_output_tokens if aggregate else 0,
                aggregate.reserved_output_tokens if aggregate else 0,
                plan.limits.monthly_output_tokens,
                period.start,
                period.end,
            ),
            QuotaSnapshot(
                QuotaResource.TOTAL_TOKENS,
                aggregate.used_total_tokens if aggregate else 0,
                aggregate.reserved_total_tokens if aggregate else 0,
                plan.limits.monthly_total_tokens,
                period.start,
                period.end,
            ),
        )

    async def _locked_aggregate(
        self,
        session: AsyncSession,
        org_id: UUID,
        period: BillingPeriod,
    ) -> UsageAggregateModel:
        result = await session.execute(
            select(UsageAggregateModel)
            .where(
                UsageAggregateModel.org_id == org_id,
                UsageAggregateModel.period_start == period.start,
            )
            .with_for_update()
        )
        aggregate = result.scalar_one_or_none()
        if aggregate is None:
            aggregate = UsageAggregateModel(
                org_id=org_id,
                period_start=period.start,
                period_end=period.end,
            )
            session.add(aggregate)
            await session.flush()
        return aggregate

    async def _get_aggregate(
        self,
        session: AsyncSession,
        org_id: UUID,
        period: BillingPeriod,
    ) -> UsageAggregateModel | None:
        result = await session.execute(
            select(UsageAggregateModel).where(
                UsageAggregateModel.org_id == org_id,
                UsageAggregateModel.period_start == period.start,
            )
        )
        return result.scalar_one_or_none()

    async def _locked_reservation(
        self,
        session: AsyncSession,
        org_id: UUID,
        request_id: str,
    ) -> UsageReservationModel | None:
        result = await session.execute(
            select(UsageReservationModel)
            .where(
                UsageReservationModel.org_id == org_id,
                UsageReservationModel.request_id == request_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _reservation(self, org_id: UUID, request_id: str) -> BillingReservation | None:
        async with self._db.session(TenantContext(org_id=org_id)) as session:
            result = await session.execute(
                select(UsageReservationModel).where(
                    UsageReservationModel.org_id == org_id,
                    UsageReservationModel.request_id == request_id,
                )
            )
            reservation = result.scalar_one_or_none()
        if reservation is None:
            return None
        return BillingReservation(
            org_id=org_id,
            request_id=request_id,
            plan_key=reservation.plan_key,
            period_start=reservation.period_start,
            period_end=reservation.period_end,
            input_tokens=reservation.reserved_input_tokens,
            output_tokens=reservation.reserved_output_tokens,
            total_tokens=reservation.reserved_total_tokens,
        )

    def _raise_if_exceeds_limits(
        self,
        aggregate: UsageAggregateModel,
        plan: Plan,
        estimate: TokenEstimate,
    ) -> None:
        proposed = {
            QuotaResource.REQUESTS: aggregate.used_requests + aggregate.reserved_requests + 1,
            QuotaResource.INPUT_TOKENS: (
                aggregate.used_input_tokens
                + aggregate.reserved_input_tokens
                + estimate.input_tokens
            ),
            QuotaResource.OUTPUT_TOKENS: (
                aggregate.used_output_tokens
                + aggregate.reserved_output_tokens
                + estimate.reserved_output_tokens
            ),
            QuotaResource.TOTAL_TOKENS: (
                aggregate.used_total_tokens
                + aggregate.reserved_total_tokens
                + estimate.total_reserved_tokens
            ),
        }
        from cyberai.modules.billing.errors import BillingQuotaExceededError

        for resource, value in proposed.items():
            if value > plan.limits.limit_for(resource):
                raise BillingQuotaExceededError(
                    f"Quota exceeded for {resource.value}.",
                    extra={"resource": resource.value},
                )

    def _apply_actual_usage(
        self,
        aggregate: UsageAggregateModel,
        record: UsageRecord,
        reservation: UsageReservationModel | None,
    ) -> None:
        reserved_input = (
            reservation.reserved_input_tokens if reservation is not None else record.input_tokens
        )
        reserved_output = (
            reservation.reserved_output_tokens if reservation is not None else record.output_tokens
        )
        reserved_total = (
            reservation.reserved_total_tokens if reservation is not None else record.total_tokens
        )
        aggregate.reserved_requests = max(
            aggregate.reserved_requests - (1 if reservation else 0), 0
        )
        aggregate.reserved_input_tokens = max(aggregate.reserved_input_tokens - reserved_input, 0)
        aggregate.reserved_output_tokens = max(
            aggregate.reserved_output_tokens - reserved_output, 0
        )
        aggregate.reserved_total_tokens = max(aggregate.reserved_total_tokens - reserved_total, 0)
        aggregate.used_requests += 1
        aggregate.used_input_tokens += record.input_tokens
        aggregate.used_output_tokens += record.output_tokens
        aggregate.used_total_tokens += record.total_tokens


class PersistentUsageSink:
    """UsageSink adapter that persists each request once."""

    def __init__(self, repository: BillingRepository) -> None:
        self._repository = repository

    async def record(self, record: UsageRecord) -> None:
        await self._repository.record_usage_once(record)


def _local_subscription_status(provider_status: str) -> str:
    if provider_status in {"active", "trialing"}:
        return provider_status
    if provider_status in {"past_due", "canceled", "unpaid", "incomplete", "incomplete_expired"}:
        return provider_status
    return "inactive"
