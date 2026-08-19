"""Provider registry.

Maps a provider name to the adapter instance wired in the composition root.
Keeping the lookup here means no other layer needs to know which providers
exist in a given deployment.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping

from cyberai.modules.inference.errors import ProviderNotRegisteredError
from cyberai.modules.inference.ports import ModelProvider


class ProviderRegistry:
    """An immutable-by-convention lookup of the providers available at runtime."""

    def __init__(self, providers: Iterable[ModelProvider] = ()) -> None:
        self._providers: dict[str, ModelProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ModelProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"provider '{provider.name}' is already registered")
        self._providers[provider.name] = provider

    def get(self, name: str) -> ModelProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderNotRegisteredError(
                f"Inference provider '{name}' is not configured.", provider=name
            ) from exc

    def has(self, name: str) -> bool:
        return name in self._providers

    def all(self) -> Mapping[str, ModelProvider]:
        return dict(self._providers)

    def __iter__(self) -> Iterator[ModelProvider]:
        return iter(self._providers.values())

    def __len__(self) -> int:
        return len(self._providers)
