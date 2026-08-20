"""Tests for Row Level Security tenant binding."""

from __future__ import annotations

from uuid import uuid4

import pytest

from cyberai.core.config import DatabaseSettings
from cyberai.platform.db import Database, TenantContext
from cyberai.platform.db.engine import Database as DatabaseEngine
from cyberai.platform.db.tenant import apply_tenant_context, current_tenant

pytestmark = pytest.mark.integration


async def _skip_if_no_postgres() -> bool:
    settings = DatabaseSettings()
    db = DatabaseEngine(settings)
    ok = await db.check_health()
    await db.dispose()
    return ok




@pytest.mark.asyncio
async def test_tenant_context_applied_within_transaction(db: Database) -> None:
    if not await _skip_if_no_postgres():
        pytest.skip("PostgreSQL is not reachable")

    tenant_id = uuid4()
    async with db.session(tenant=TenantContext(org_id=tenant_id)) as session:
        bound = await current_tenant(session)
        assert bound == tenant_id


@pytest.mark.asyncio
async def test_tenant_context_requires_transaction(db: Database) -> None:
    if not await _skip_if_no_postgres():
        pytest.skip("PostgreSQL is not reachable")

    database = DatabaseEngine(DatabaseSettings())
    session = database.session_factory()
    with pytest.raises(RuntimeError, match="requires an open transaction"):
        await apply_tenant_context(session, TenantContext(org_id=uuid4()))
    await session.close()
    await database.dispose()


@pytest.mark.asyncio
async def test_no_tenant_is_no_isolation(db: Database) -> None:
    if not await _skip_if_no_postgres():
        pytest.skip("PostgreSQL is not reachable")

    async with db.session() as session:
        bound = await current_tenant(session)
        assert bound is None


@pytest.mark.asyncio
async def test_tenant_parse_validates_uuid() -> None:
    from cyberai.core.errors import ForbiddenError

    with pytest.raises(ForbiddenError):
        TenantContext.parse("not-a-uuid")
