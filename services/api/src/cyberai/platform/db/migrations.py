"""Database migration readiness helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class SchemaRevisionStatus:
    healthy: bool
    detail: str


def schema_revision_health(
    *, applied_revision: str | None, expected_head: str | None
) -> SchemaRevisionStatus:
    if not applied_revision or not expected_head:
        return SchemaRevisionStatus(healthy=False, detail="schema_unknown")
    if applied_revision != expected_head:
        return SchemaRevisionStatus(healthy=False, detail="schema_mismatch")
    return SchemaRevisionStatus(healthy=True, detail="schema_current")


def expected_schema_head(project_root: Path | None = None) -> str | None:
    root = project_root or Path(__file__).resolve().parents[4]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


async def applied_schema_revision(session: AsyncSession) -> str | None:
    result = await session.execute(text("SELECT version_num FROM alembic_version"))
    value = result.scalar_one_or_none()
    return str(value) if value else None
