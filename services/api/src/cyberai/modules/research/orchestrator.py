"""Research orchestrator: plan, search, rank, cite.

This is the only place that coordinates retrieval. It composes:

- :class:`ResearchDecider` — chooses the research budget (none/quick/deep);
- providers — keyless authoritative sources plus configured web search;
- :class:`ResearchCache` — short-TTL caching;
- :func:`rank_sources` — scoring, dedupe and canonicalization.

It never executes anything: retrieval is the only external capability.
"""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis

from cyberai.core.config import ResearchSettings
from cyberai.core.logging import get_logger
from cyberai.modules.research.cache import ResearchCache
from cyberai.modules.research.decision import ResearchDecider
from cyberai.modules.research.providers import (
    SearchProvider,
    build_cyber_providers,
    build_web_providers,
)
from cyberai.modules.research.sources import rank_sources
from cyberai.modules.research.ssrf import SSRFGuard
from cyberai.modules.research.types import (
    Citation,
    ResearchDecision,
    ResearchPlan,
    ResearchResult,
    Source,
)

logger = get_logger(__name__)

_PROVIDER_LABELS = {
    "nvd": "NVD",
    "cisa-kev": "CISA KEV",
    "osv": "OSV",
    "ghsa": "GitHub Advisory",
    "brave": "Brave",
    "tavily": "Tavily",
    "exa": "Exa",
    "firecrawl": "Firecrawl",
}


class ResearchOrchestrator:
    """Coordinates grounded retrieval and produces citable evidence."""

    def __init__(
        self,
        settings: ResearchSettings,
        *,
        cache_client: Redis | None = None,
        providers: list[SearchProvider] | None = None,
        cyber_providers: list[SearchProvider] | None = None,
        guard: SSRFGuard | None = None,
    ) -> None:
        self._settings = settings
        self._guard = guard or SSRFGuard()
        self._cache = ResearchCache(cache_client, settings.cache_ttl_seconds)
        self._decider = ResearchDecider()
        self._cyber = (
            cyber_providers
            if cyber_providers is not None
            else build_cyber_providers(settings.request_timeout_seconds, self._guard)
        )
        self._web = (
            providers if providers is not None else build_web_providers(settings, self._guard)
        )

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @property
    def web_configured(self) -> bool:
        return any(provider.is_configured for provider in self._web)

    def decide(self, query: str) -> ResearchPlan:
        if not self.enabled:
            return ResearchPlan(ResearchDecision.NONE)
        return self._decider.decide(query)

    def provider_labels(self, plan: ResearchPlan) -> tuple[str, ...]:
        """Human-readable names of the providers a plan will consult."""
        queries = plan.queries or ()
        has_cve = any(q.upper().startswith("CVE-") for q in queries)
        labels: list[str] = []
        if has_cve:
            labels.extend(_PROVIDER_LABELS.get(p.name, p.name) for p in self._cyber)
        labels.extend(_PROVIDER_LABELS.get(p.name, p.name) for p in self._web)
        return tuple(labels)

    async def run(self, plan: ResearchPlan) -> ResearchResult:
        if plan.is_empty:
            return ResearchResult()

        queries = plan.queries or ("",)
        tasks: list[tuple[str, SearchProvider]] = []

        has_cve = any(q.upper().startswith("CVE-") for q in queries)
        if has_cve:
            tasks.extend((q, provider) for q in queries for provider in self._cyber)
        tasks.extend((q, provider) for q in queries for provider in self._web)

        if not tasks:
            return ResearchResult()

        results = await asyncio.gather(
            *(self._search_cached(provider, query) for query, provider in tasks)
        )

        flattened = [source for batch in results for source in batch]
        ranked = rank_sources(
            flattened,
            query=" ".join(queries),
            limit=self._settings.max_sources,
        )
        citations = tuple(
            Citation(index=i, source=source) for i, source in enumerate(ranked, start=1)
        )
        return ResearchResult(sources=tuple(ranked), citations=citations)

    async def _search_cached(self, provider: SearchProvider, query: str) -> list[Source]:
        cached = await self._cache.get(provider.name, query)
        if cached is not None:
            return cached
        try:
            sources = await provider.search(query)
        except Exception as exc:
            logger.warning(
                "research.provider_failed",
                provider=provider.name,
                error=type(exc).__name__,
            )
            sources = []
        await self._cache.set(provider.name, query, sources)
        return sources
