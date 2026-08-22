"""Research decision: does a query need live research, and how much?"""

from __future__ import annotations

import re

from cyberai.modules.research.types import ResearchDecision, ResearchPlan

_CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)

_EXPLICIT_RESEARCH = (
    "pesquise",
    "pesquisa",
    "search the web",
    "search for",
    "look up",
    "lookup",
    "google it",
    "find current",
    "find the latest",
)

_RECENCY = (
    "atual",
    "current",
    "latest",
    "recent",
    "news",
    "today",
    "this week",
    "this month",
    "right now",
    "em 2026",
    "agora",
    "última versão",
    "latest version",
    "recentemente",
)

_DEEP_SIGNALS = (
    "compare",
    "comparar",
    "differences between",
    "versus",
    "trade-offs",
    "pros and cons",
    "em profundidade",
    "deep",
    "multiplas fontes",
    "summarize the research",
)

#: Stable-knowledge questions that must not pay search latency.
_STABLE_MARKERS = ("how does", "what is", "explain", "como funciona", "o que é")


class ResearchDecider:
    """Heuristically classifies a query into a research budget."""

    def decide(self, query: str) -> ResearchPlan:
        normalized = _normalize(query)
        if not normalized:
            return ResearchPlan(ResearchDecision.NONE)

        has_cve = bool(_CVE_PATTERN.search(query))
        explicit = any(signal in normalized for signal in _EXPLICIT_RESEARCH)
        recency = any(signal in normalized for signal in _RECENCY)
        deep = any(signal in normalized for signal in _DEEP_SIGNALS)

        if deep:
            return ResearchPlan(ResearchDecision.DEEP, self._queries(query))
        if explicit or has_cve or recency:
            return ResearchPlan(ResearchDecision.QUICK, self._queries(query))
        return ResearchPlan(ResearchDecision.NONE)

    def _queries(self, query: str) -> tuple[str, ...]:
        cve_match = _CVE_PATTERN.search(query)
        if cve_match:
            return (cve_match.group(0).upper(),)
        return (_normalize_query(query),)


def _normalize(query: str) -> str:
    return re.sub(r"\s+", " ", query.lower()).strip()


def _normalize_query(query: str) -> str:
    return " ".join(query.split()).strip()
