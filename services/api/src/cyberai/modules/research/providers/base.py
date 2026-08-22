"""Search provider abstraction.

Every adapter implements :class:`SearchProvider`. Adapters are *optional*: the
application builds only the adapters that are configured, so a development
environment without any paid API key still boots and answers (research is simply
skipped or limited to the keyless authoritative security sources).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from cyberai.modules.research.types import Source


class SearchProvider(ABC):
    """A single search/retrieval capability."""

    name: str = "search"

    @property
    def is_configured(self) -> bool:
        return False

    @abstractmethod
    async def search(self, query: str) -> list[Source]:
        """Return ranked sources for ``query``. Never raises; returns [] on failure."""
