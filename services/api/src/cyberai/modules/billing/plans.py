"""Plan catalog for M6 billing foundation."""

from __future__ import annotations

from cyberai.modules.billing.types import Plan, PlanLimits


class StaticPlanCatalog:
    """Small static catalog; future admin-managed plans can satisfy this API."""

    def __init__(self, plans: tuple[Plan, ...] | None = None) -> None:
        entries = plans or _DEFAULT_PLANS
        self._plans = {plan.key: plan for plan in entries}

    def get(self, key: str) -> Plan:
        try:
            return self._plans[key]
        except KeyError as exc:
            raise ValueError(f"Unknown plan '{key}'.") from exc

    def list_plans(self) -> tuple[Plan, ...]:
        return tuple(self._plans.values())


_DEFAULT_PLANS: tuple[Plan, ...] = (
    Plan(
        key="free",
        display_name="Free",
        limits=PlanLimits(
            monthly_requests=100,
            monthly_input_tokens=100_000,
            monthly_output_tokens=50_000,
            monthly_total_tokens=150_000,
            allowed_models=frozenset(
                {"mock-analyst-1", "mock-analyst-mini", "openai-compatible-chat"}
            ),
            rag_allowed=False,
            document_limit=5,
            rate_limit_requests=30,
            rate_limit_window_seconds=60,
        ),
    ),
    Plan(
        key="pro",
        display_name="Pro",
        limits=PlanLimits(
            monthly_requests=2_000,
            monthly_input_tokens=2_000_000,
            monthly_output_tokens=1_000_000,
            monthly_total_tokens=3_000_000,
            allowed_models=frozenset(
                {"mock-analyst-1", "mock-analyst-mini", "openai-compatible-chat"}
            ),
            rag_allowed=True,
            document_limit=100,
            rate_limit_requests=120,
            rate_limit_window_seconds=60,
        ),
    ),
    Plan(
        key="business",
        display_name="Business",
        limits=PlanLimits(
            monthly_requests=20_000,
            monthly_input_tokens=20_000_000,
            monthly_output_tokens=10_000_000,
            monthly_total_tokens=30_000_000,
            allowed_models=frozenset(
                {"mock-analyst-1", "mock-analyst-mini", "openai-compatible-chat"}
            ),
            rag_allowed=True,
            document_limit=1_000,
            rate_limit_requests=600,
            rate_limit_window_seconds=60,
        ),
    ),
    Plan(
        key="enterprise",
        display_name="Enterprise",
        limits=PlanLimits(
            monthly_requests=1_000_000,
            monthly_input_tokens=1_000_000_000,
            monthly_output_tokens=500_000_000,
            monthly_total_tokens=1_500_000_000,
            allowed_models=None,
            rag_allowed=True,
            document_limit=100_000,
            rate_limit_requests=5_000,
            rate_limit_window_seconds=60,
        ),
    ),
)
