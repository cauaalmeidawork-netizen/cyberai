"""Model Gateway - *which* model and provider should serve a request.

It owns the model catalog, the routing policy and the fallback chain, and it
emits the usage record that the cost ledger is built on. It reaches inference
only through the Inference Gateway, and it never imports a provider.
"""

from cyberai.modules.modelgw.catalog import ModelCatalog, default_catalog
from cyberai.modules.modelgw.errors import ModelNotFoundError, NoModelAvailableError
from cyberai.modules.modelgw.gateway import ModelGateway
from cyberai.modules.modelgw.routing import ModelRouter
from cyberai.modules.modelgw.types import (
    CompletionCompleted,
    CompletionRequest,
    CompletionStarted,
    GatewayEvent,
    ModelRoute,
    ModelSpec,
    RequestPrincipal,
    TaskType,
)
from cyberai.modules.modelgw.usage import (
    LoggingUsageSink,
    NullUsageSink,
    UsageRecord,
    UsageSink,
    UsageStatus,
    estimate_cost_usd,
)

__all__ = [
    "CompletionCompleted",
    "CompletionRequest",
    "CompletionStarted",
    "GatewayEvent",
    "LoggingUsageSink",
    "ModelCatalog",
    "ModelGateway",
    "ModelNotFoundError",
    "ModelRoute",
    "ModelRouter",
    "ModelSpec",
    "NoModelAvailableError",
    "NullUsageSink",
    "RequestPrincipal",
    "TaskType",
    "UsageRecord",
    "UsageSink",
    "UsageStatus",
    "default_catalog",
    "estimate_cost_usd",
]
