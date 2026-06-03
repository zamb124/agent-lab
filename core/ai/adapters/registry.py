from __future__ import annotations

from collections.abc import Iterable

from core.ai.adapters.base import AIProviderAdapter


class AIProviderAdapterRegistry:
    def __init__(self, adapters: Iterable[AIProviderAdapter]) -> None:
        self._adapters: dict[str, AIProviderAdapter] = {
            adapter.provider: adapter for adapter in adapters
        }

    def get(self, provider: str) -> AIProviderAdapter:
        return self._adapters[provider]

    def has(self, provider: str) -> bool:
        return provider in self._adapters

    def all(self) -> tuple[AIProviderAdapter, ...]:
        return tuple(self._adapters.values())

    def enabled_adapters(self, providers: Iterable[str] | None = None) -> tuple[AIProviderAdapter, ...]:
        if providers is None:
            return self.all()
        return tuple(self._adapters[provider] for provider in providers if provider in self._adapters)
