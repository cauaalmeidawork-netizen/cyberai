"""Policy engine types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class PolicyDecisionType(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"
    SANITIZE = "sanitize"


class PolicyStage(StrEnum):
    INPUT = "input"
    RAG = "rag"
    OUTPUT = "output"


class PolicyProfile(StrEnum):
    DEFAULT = "default"
    STRICT = "strict"
    ENTERPRISE = "enterprise"


class PolicyAction(StrEnum):
    CHAT = "chat"
    RAG_INGEST = "rag_ingest"
    RAG_RETRIEVE = "rag_retrieve"


@dataclass(frozen=True, slots=True)
class PolicyContext:
    org_id: str | None
    user_id: str | None
    request_id: str | None
    model_key: str | None
    provider_key: str | None
    rag_enabled: bool
    source_type: str | None
    action_type: PolicyAction
    policy_profile: PolicyProfile
    stage: PolicyStage


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    rule_id: str
    severity: str
    category: str
    safe_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: PolicyDecisionType
    violations: tuple[PolicyViolation, ...] = ()
    sanitized_content: str | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is PolicyDecisionType.ALLOW


class PolicyRule(Protocol):
    rule_id: str

    def evaluate(self, context: PolicyContext, content: str) -> PolicyDecision | None: ...
