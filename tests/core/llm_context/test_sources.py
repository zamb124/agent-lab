from __future__ import annotations

import pytest

from core.context import clear_context, set_context
from core.llm_context import (
    LLM_CONTEXT_PROFILE_METADATA_KEY,
    IdentityLLMContextProfileSource,
    LLMContextBlock,
    LLMContextSourceRegistry,
    LLMContextSourceRequest,
    StaticLLMContextSource,
)
from core.models.context_models import Context
from core.models.identity_models import Company, User


class MemoryContextSource:
    name: str = "memory"

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        return [
            LLMContextBlock(
                kind="memory",
                budget_scope="memory",
                content=request.query or "empty",
                stable_key="memory:query",
                provenance={"source": "custom"},
            )
        ]


def _request() -> LLMContextSourceRequest:
    return LLMContextSourceRequest(
        messages=[{"role": "user", "content": "hello"}],
        query="hello",
    )


@pytest.mark.asyncio
async def test_empty_source_registry_collects_no_blocks() -> None:
    registry = LLMContextSourceRegistry()

    assert registry.has_sources is False
    assert await registry.collect(_request()) == []


@pytest.mark.asyncio
async def test_source_registry_collects_blocks_in_source_order_and_adds_provenance() -> None:
    registry = LLMContextSourceRegistry(
        [
            StaticLLMContextSource(
                "static",
                [
                    {
                        "kind": "profile",
                        "budget_scope": "profile",
                        "content": "profile facts",
                        "stable_key": "profile:1",
                    }
                ],
            ),
            MemoryContextSource(),
        ]
    )

    blocks = await registry.collect(_request())

    assert registry.has_sources is True
    assert [block.stable_key for block in blocks] == ["profile:1", "memory:query"]
    assert [block.provenance["source"] for block in blocks] == ["static", "custom"]


def test_source_registry_rejects_duplicate_source_names() -> None:
    source = StaticLLMContextSource("same", [])

    with pytest.raises(ValueError, match="Duplicate"):
        _ = LLMContextSourceRegistry([source, source])


def test_static_source_rejects_invalid_source_name() -> None:
    with pytest.raises(ValueError, match="source name"):
        _ = StaticLLMContextSource("bad name", [])


@pytest.mark.asyncio
async def test_identity_profile_source_reads_explicit_context_profile_fields() -> None:
    source = IdentityLLMContextProfileSource()
    context = Context(
        user=User(
            user_id="u1",
            name="User",
            bio="Prefers concise technical answers.",
            attributes={LLM_CONTEXT_PROFILE_METADATA_KEY: "User works on billing flows."},
        ),
        active_company=Company(
            company_id="c1",
            name="Company",
            metadata={LLM_CONTEXT_PROFILE_METADATA_KEY: "Company sells SaaS."},
        ),
        metadata={LLM_CONTEXT_PROFILE_METADATA_KEY: "Runtime project is context layer."},
        channel="test",
    )

    clear_context()
    assert await source.collect(_request()) == []
    try:
        set_context(context)
        blocks = await source.collect(_request())
    finally:
        clear_context()

    assert len(blocks) == 1
    block = blocks[0]
    assert block.kind == "profile"
    assert block.budget_scope == "profile"
    assert block.stable_key.startswith("profile:identity:c1:u1:")
    assert "Prefers concise technical answers." in block.content
    assert "User works on billing flows." in block.content
    assert "Company sells SaaS." in block.content
    assert "Runtime project is context layer." in block.content
    assert block.provenance == {
        "source": "profile.identity",
        "user_id": "u1",
        "company_id": "c1",
    }
