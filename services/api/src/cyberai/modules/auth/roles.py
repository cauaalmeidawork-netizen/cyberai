"""RBAC roles and permissions."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(StrEnum):
    PROJECT_READ = "project.read"
    PROJECT_WRITE = "project.write"
    CONVERSATION_READ = "conversation.read"
    CONVERSATION_WRITE = "conversation.write"
    DOCUMENT_READ = "document.read"
    DOCUMENT_WRITE = "document.write"
    BILLING_READ = "billing.read"
    ORGANIZATION_MANAGE = "organization.manage"
    MEMBER_MANAGE = "member.manage"


_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_WRITE,
            Permission.CONVERSATION_READ,
            Permission.CONVERSATION_WRITE,
            Permission.DOCUMENT_READ,
            Permission.DOCUMENT_WRITE,
            Permission.BILLING_READ,
            Permission.ORGANIZATION_MANAGE,
            Permission.MEMBER_MANAGE,
        }
    ),
    Role.MEMBER: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_WRITE,
            Permission.CONVERSATION_READ,
            Permission.CONVERSATION_WRITE,
            Permission.DOCUMENT_READ,
            Permission.DOCUMENT_WRITE,
            Permission.BILLING_READ,
        }
    ),
    Role.VIEWER: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.CONVERSATION_READ,
            Permission.DOCUMENT_READ,
            Permission.BILLING_READ,
        }
    ),
}


def parse_role(raw: str) -> Role:
    try:
        return Role(raw)
    except ValueError:
        return Role.MEMBER


def permissions_for_role(role: Role) -> frozenset[Permission]:
    return _ROLE_PERMISSIONS[role]
