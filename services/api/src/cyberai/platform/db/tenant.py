"""Tenant binding for Row Level Security.

Multi-tenancy uses a shared schema with an ``org_id`` column on every
tenant-scoped table, protected by PostgreSQL Row Level Security. Application
level filtering is the first layer; RLS is the boundary that holds when the
application has a bug.

Two implementation details make this safe and are easy to get wrong:

1. The setting is bound with ``set_config(..., is_local => true)``, which is the
   parameterisable equivalent of ``SET LOCAL``. ``SET LOCAL`` cannot take bind
   parameters, and building the statement with string concatenation would be an
   SQL injection vector on the one value that guards tenant isolation.
2. Being transaction-scoped is what makes the pattern correct behind a
   transaction-pooling connection pooler such as PgBouncer: the setting cannot
   survive into another tenant's request on a recycled connection.

The tables and policies themselves land in M1; the mechanism and its tests live
here from M0 so no tenant-scoped code is ever written without it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cyberai.core.errors import ForbiddenError

TENANT_SETTING = "app.current_org_id"

_SET_TENANT = text(f"SELECT set_config('{TENANT_SETTING}', :org_id, true)")
_GET_TENANT = text(f"SELECT current_setting('{TENANT_SETTING}', true)")


@dataclass(frozen=True, slots=True)
class TenantContext:
    """The organization a unit of work is scoped to.

    Always constructed from a server-verified identity. A client-supplied
    organization id is a request *hint* that must be authorised first; it is
    never passed straight into this object.
    """

    org_id: uuid.UUID

    @classmethod
    def parse(cls, raw: str) -> TenantContext:
        try:
            return cls(org_id=uuid.UUID(str(raw)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ForbiddenError("Invalid tenant context.") from exc


async def apply_tenant_context(session: AsyncSession, tenant: TenantContext) -> None:
    """Bind the tenant to the current transaction.

    Raises:
        RuntimeError: if the session is not inside a transaction, in which case
            the setting would leak to whatever runs next on this connection.
    """
    if not session.in_transaction():
        raise RuntimeError(
            "apply_tenant_context requires an open transaction: a transaction-scoped "
            "setting outside a transaction would leak across requests."
        )
    await session.execute(_SET_TENANT, {"org_id": str(tenant.org_id)})


async def current_tenant(session: AsyncSession) -> uuid.UUID | None:
    """Read back the tenant bound to the current transaction (used by tests)."""
    result = await session.execute(_GET_TENANT)
    raw = result.scalar_one_or_none()
    if not raw:
        return None
    return uuid.UUID(raw)
