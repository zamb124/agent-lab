"""Composable sources for platform LLM context blocks."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import Field

from core.llm_context.models import LLMContextBlock, LLMContextProfile
from core.models import StrictBaseModel
from core.types import JsonObject


class LLMContextSourceRequest(StrictBaseModel):
    """Input passed to each context source for one LLM call."""

    messages: list[JsonObject] = Field(default_factory=list)
    policy: LLMContextProfile = Field(default_factory=LLMContextProfile)
    query: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class LLMContextSource(Protocol):
    """Source contract for retrieving candidate context blocks."""

    @property
    def name(self) -> str:
        ...  # pragma: no cover

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        ...  # pragma: no cover


@dataclass(frozen=True)
class StaticLLMContextSource:
    """Concrete source for already materialized blocks."""

    name: str
    blocks: tuple[LLMContextBlock, ...]

    def __init__(
        self,
        name: str,
        blocks: Iterable[LLMContextBlock | JsonObject],
    ) -> None:
        object.__setattr__(self, "name", _validate_source_name(name))
        object.__setattr__(
            self,
            "blocks",
            tuple(_coerce_block(block) for block in blocks),
        )

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        _ = request
        return list(self.blocks)


@dataclass(frozen=True)
class LLMContextSourceRegistry:
    """Ordered registry that collects context blocks from independent sources in parallel."""

    sources: tuple[LLMContextSource, ...] = ()

    def __init__(self, sources: Sequence[LLMContextSource] | None = None) -> None:
        normalized = tuple(sources or ())
        _validate_unique_source_names(normalized)
        object.__setattr__(self, "sources", normalized)

    @property
    def has_sources(self) -> bool:
        return bool(self.sources)

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        if not self.sources:
            return []
        collected_groups = await asyncio.gather(
            *(source.collect(request) for source in self.sources)
        )
        blocks: list[LLMContextBlock] = []
        for source, group in zip(self.sources, collected_groups, strict=True):
            for raw_block in group:
                block = _coerce_block(raw_block)
                provenance = dict(block.provenance)
                _ = provenance.setdefault("source", source.name)
                blocks.append(block.model_copy(update={"provenance": provenance}))
        return blocks


def _coerce_block(block: LLMContextBlock | JsonObject) -> LLMContextBlock:
    if isinstance(block, LLMContextBlock):
        return block
    return LLMContextBlock.model_validate(block)


def _validate_source_name(name: str) -> str:
    if not name or not all(ch.isalnum() or ch in ("_", "-", ".") for ch in name):
        raise ValueError("LLM context source name must be a non-empty slug")
    return name


def _validate_unique_source_names(sources: tuple[LLMContextSource, ...]) -> None:
    seen: set[str] = set()
    for source in sources:
        name = _validate_source_name(source.name)
        if name in seen:
            raise ValueError(f"Duplicate LLM context source name: {name!r}")
        seen.add(name)


__all__ = [
    "LLMContextSource",
    "LLMContextSourceRegistry",
    "LLMContextSourceRequest",
    "StaticLLMContextSource",
]
