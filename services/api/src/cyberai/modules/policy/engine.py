"""Deterministic policy engine."""

from __future__ import annotations

import re

from cyberai.modules.policy.types import (
    PolicyContext,
    PolicyDecision,
    PolicyDecisionType,
    PolicyStage,
    PolicyViolation,
)

_SECRET_PATTERN = re.compile(r"\b(?:sk|pk|ghp|xoxb)-(?:live|test)?[A-Za-z0-9_-]{20,}\b")


class PolicyEngine:
    """Contextual deterministic rules for M7 security policy."""

    def evaluate(self, context: PolicyContext, content: str) -> PolicyDecision:
        if not content.strip():
            return PolicyDecision(PolicyDecisionType.ALLOW)
        normalized = _normalize(content)
        if context.stage is PolicyStage.OUTPUT:
            return self._evaluate_output(normalized, content)
        if context.stage is PolicyStage.RAG:
            return self._evaluate_rag(normalized, content)
        return self._evaluate_input(normalized, content)

    def _evaluate_input(self, normalized: str, content: str) -> PolicyDecision:
        injection = _prompt_injection_violation(normalized)
        if injection is not None:
            return PolicyDecision(PolicyDecisionType.DENY, (injection,))
        if len(content) > 64_000:
            return PolicyDecision(
                PolicyDecisionType.DENY,
                (
                    PolicyViolation(
                        "input_too_large",
                        severity="medium",
                        category="payload",
                        safe_metadata={"limit": "64000"},
                    ),
                ),
            )
        if _is_abusive_operational_request(normalized) and not _is_defensive_context(normalized):
            return PolicyDecision(
                PolicyDecisionType.DENY,
                (
                    PolicyViolation(
                        "abusive_operational_capability",
                        severity="high",
                        category="cyber_abuse",
                    ),
                ),
            )
        return PolicyDecision(PolicyDecisionType.ALLOW)

    def _evaluate_rag(self, normalized: str, content: str) -> PolicyDecision:
        injection = _prompt_injection_violation(normalized)
        if injection is None:
            return PolicyDecision(PolicyDecisionType.ALLOW)
        return PolicyDecision(
            PolicyDecisionType.SANITIZE,
            (
                PolicyViolation(
                    "retrieved_context_instruction_injection",
                    severity="high",
                    category="prompt_injection",
                ),
            ),
            sanitized_content="",
        )

    def _evaluate_output(self, normalized: str, content: str) -> PolicyDecision:
        if _is_abusive_operational_request(normalized) and not _is_defensive_context(normalized):
            return PolicyDecision(
                PolicyDecisionType.DENY,
                (
                    PolicyViolation(
                        "unsafe_operational_output",
                        severity="high",
                        category="cyber_abuse",
                    ),
                ),
            )
        redacted = _SECRET_PATTERN.sub("[REDACTED_SECRET]", content)
        if redacted != content:
            return PolicyDecision(
                PolicyDecisionType.SANITIZE,
                (
                    PolicyViolation(
                        "secret_like_output",
                        severity="high",
                        category="secret_exposure",
                    ),
                ),
                sanitized_content=redacted,
            )
        return PolicyDecision(PolicyDecisionType.ALLOW)


class NoopPolicyEngine(PolicyEngine):
    """Policy engine used only when policy is explicitly disabled by config."""

    def evaluate(self, context: PolicyContext, content: str) -> PolicyDecision:
        return PolicyDecision(PolicyDecisionType.ALLOW)


def _normalize(content: str) -> str:
    return re.sub(r"\s+", " ", content.lower()).strip()


def _prompt_injection_violation(normalized: str) -> PolicyViolation | None:
    override_signals = (
        "ignore previous instructions",
        "ignore all system instructions",
        "reveal hidden system",
        "developer override",
        "disable policy",
        "bypass safety",
    )
    control_targets = ("system", "developer", "policy", "safety", "instruction")
    if any(signal in normalized for signal in override_signals) and any(
        target in normalized for target in control_targets
    ):
        return PolicyViolation(
            "prompt_injection_override",
            severity="high",
            category="prompt_injection",
        )
    return None


def _is_defensive_context(normalized: str) -> bool:
    # Phrases that describe evasion are offensive even though they contain a
    # defensive-looking substring such as "detection".
    evasion = (
        "evade detection",
        "bypass detection",
        "evade edr",
        "bypass edr",
        "avoid detection",
        "hide from",
        "disable antivirus",
    )
    if any(phrase in normalized for phrase in evasion):
        return False
    defensive_markers = (
        "defensive",
        "detection",
        "hardening",
        "analyze",
        "analysis",
        "education",
        "triage",
        "indicator",
        "incident response",
        "explain",
    )
    return any(marker in normalized for marker in defensive_markers)


def _is_abusive_operational_request(normalized: str) -> bool:
    intent = (
        "steal credentials",
        "phishing kit",
        "bypass mfa",
        "exfiltrate",
        "deploy malware",
        "persistence",
        "evade detection",
        "ransomware",
    )
    capability = (
        "build",
        "automate",
        "create",
        "generate",
        "write",
        "deploy",
        "give me code",
    )
    return any(item in normalized for item in intent) and any(
        item in normalized for item in capability
    )
