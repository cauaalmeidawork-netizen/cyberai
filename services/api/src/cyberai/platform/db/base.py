"""Declarative base and metadata conventions.

Explicit constraint naming is set up before the first table exists: Alembic
cannot autogenerate a reliable downgrade for unnamed constraints, and renaming
them later means rewriting migrations.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Base class for every ORM model.

    Tenant-scoped tables (from M1 on) must declare a non-null ``org_id`` column
    and enable Row Level Security in their migration.
    """

    metadata = metadata
