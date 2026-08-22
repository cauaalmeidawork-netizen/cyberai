"""Generic web-search adapters (Brave, Tavily).

These adapters require API keys and are therefore optional. They share a small
SSRF-guarded HTTP helper so no adapter can accidentally fetch a private address.
"""

from __future__ import annotations

from typing import Any

import httpx

from cyberai.core.config import ResearchSettings
from cyberai.core.logging import get_logger
from cyberai.modules.research.providers.base import SearchProvider
from cyberai.modules.research.ssrf import SSRFGuard
from cyberai.modules.research.types import Source, SourceType

logger = get_logger(__name__)

_USER_AGENT = "NomercyAI/1.0 (+research; retrieval-only)"


async def safe_get_json(
    url: str,
    *,
    request_timeout: float,
    guard: SSRFGuard,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """SSRF-guarded GET returning parsed JSON, or None on any failure."""
    if not guard.validate(url):
        logger.warning("research.ssrf_blocked", url=url)
        return None
    try:
        async with httpx.AsyncClient(timeout=request_timeout, follow_redirects=False) as client:
            response = await client.get(
                url,
                params=params,
                headers={"User-Agent": _USER_AGENT, **(headers or {})},
            )
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.warning("research.fetch_failed", url=url, error=type(exc).__name__)
        return None


class BraveSearchProvider(SearchProvider):
    """Brave Search API adapter."""

    name = "brave"

    def __init__(self, api_key: str, timeout: float, guard: SSRFGuard) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._guard = guard

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str) -> list[Source]:
        data = await safe_get_json(
            "https://api.search.brave.com/res/v1/web/search",
            request_timeout=self._timeout,
            guard=self._guard,
            params={"q": query, "count": "10"},
            headers={"X-Subscription-Token": self._api_key},
        )
        if not data:
            return []
        return [
            Source(
                url=result.get("url", ""),
                title=result.get("title", ""),
                domain=_domain(result.get("url", "")),
                source_type=SourceType.WEB,
                snippet=result.get("description", ""),
                published_at=result.get("page_age") or None,
                provider=self.name,
            )
            for result in data.get("web", {}).get("results", [])
            if result.get("url")
        ]


class TavilySearchProvider(SearchProvider):
    """Tavily Search API adapter."""

    name = "tavily"

    def __init__(self, api_key: str, timeout: float, guard: SSRFGuard) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._guard = guard

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str) -> list[Source]:
        data = await safe_get_json(
            "https://api.tavily.com/search",
            request_timeout=self._timeout,
            guard=self._guard,
            params={"api_key": self._api_key, "query": query, "max_results": "10"},
        )
        if not data:
            return []
        return [
            Source(
                url=result.get("url", ""),
                title=result.get("title", ""),
                domain=_domain(result.get("url", "")),
                source_type=SourceType.WEB,
                snippet=result.get("content", ""),
                published_at=result.get("published_date") or None,
                provider=self.name,
            )
            for result in data.get("results", [])
            if result.get("url")
        ]


def _domain(url: str) -> str:
    from cyberai.modules.research.sources import domain_of

    return domain_of(url)


def build_web_providers(settings: ResearchSettings, guard: SSRFGuard) -> list[SearchProvider]:
    """Build every *configured* web-search provider."""
    providers: list[SearchProvider] = []
    if settings.brave_api_key is not None:
        providers.append(
            BraveSearchProvider(
                settings.brave_api_key.get_secret_value(),
                settings.request_timeout_seconds,
                guard,
            )
        )
    if settings.tavily_api_key is not None:
        providers.append(
            TavilySearchProvider(
                settings.tavily_api_key.get_secret_value(),
                settings.request_timeout_seconds,
                guard,
            )
        )
    return providers
