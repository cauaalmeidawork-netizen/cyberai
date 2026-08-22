"""Short-lived cache for research results."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from redis.asyncio import Redis

from cyberai.modules.research.types import Source, SourceType

_CACHE_PREFIX = "nomercy:research"


class ResearchCache:
    """Caches provider search results for a configurable TTL.

    Never used as a substitute for freshness: keys include the query and
    provider, and the TTL is kept short. A cache hit is a convenience, not a
    promise that a result is still current.
    """

    def __init__(self, client: Redis | None, ttl_seconds: int) -> None:
        self._client = client
        self._ttl = ttl_seconds

    @property
    def enabled(self) -> bool:
        return self._client is not None and self._ttl > 0

    def _key(self, provider: str, query: str) -> str:
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        return f"{_CACHE_PREFIX}:{provider}:{digest}"

    async def get(self, provider: str, query: str) -> list[Source] | None:
        if not self.enabled:
            return None
        try:
            raw = await self._client.get(self._key(provider, query))  # type: ignore[union-attr]
        except Exception:
            return None
        if raw is None:
            return None
        try:
            return [_source_from_dict(item) for item in json.loads(raw)]
        except (TypeError, ValueError):
            return None

    async def set(self, provider: str, query: str, sources: list[Source]) -> None:
        if not self.enabled:
            return
        payload = json.dumps([_source_to_dict(source) for source in sources])
        try:
            await self._client.setex(self._key(provider, query), self._ttl, payload)  # type: ignore[union-attr]
        except Exception:
            return


def _source_to_dict(source: Source) -> dict[str, Any]:
    return {
        "url": source.url,
        "title": source.title,
        "domain": source.domain,
        "source_type": source.source_type.value,
        "snippet": source.snippet,
        "published_at": source.published_at,
        "provider": source.provider,
        "authority_score": source.authority_score,
        "relevance_score": source.relevance_score,
    }


def _source_from_dict(data: dict[str, Any]) -> Source:
    return Source(
        url=data.get("url", ""),
        title=data.get("title", ""),
        domain=data.get("domain", ""),
        source_type=SourceType(data.get("source_type", "web")),
        snippet=data.get("snippet", ""),
        published_at=data.get("published_at"),
        provider=data.get("provider", "web"),
        authority_score=float(data.get("authority_score", 0.0)),
        relevance_score=float(data.get("relevance_score", 0.0)),
    )
