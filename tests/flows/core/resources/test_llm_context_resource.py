from __future__ import annotations

from apps.flows.src.models.resource import (
    ResourceDefinition,
    ResourceType,
    parse_typed_resource_config,
)
from core.llm_context import LLMContextPatch
from core.rag import RagResourceBindParams


def test_llm_context_resource_config_is_strictly_typed() -> None:
    typed = parse_typed_resource_config(
        ResourceType.LLM_CONTEXT,
        {"profile": "agent", "retrieval": {"top_k": 12}},
    )

    assert isinstance(typed, LLMContextPatch)
    assert typed.profile == "agent"
    assert typed.retrieval is not None
    assert typed.retrieval.top_k == 12


def test_resource_definition_returns_llm_context_patch() -> None:
    definition = ResourceDefinition(
        resource_id="ctx_agent",
        type=ResourceType.LLM_CONTEXT,
        name="Agent context",
        config={"budget": "large", "memory": "session"},
    )

    typed = definition.get_typed_config()

    assert isinstance(typed, LLMContextPatch)
    assert typed.budget == "large"
    assert typed.memory == "session"


def test_rag_resource_config_is_strictly_typed() -> None:
    typed = parse_typed_resource_config(
        ResourceType.RAG,
        {
            "namespace": "company-kb",
            "default_top_k": 12,
            "filters": {"collection_id": "support"},
            "search_options": {"rerank": True},
        },
    )

    assert isinstance(typed, RagResourceBindParams)
    assert typed.namespace == "company-kb"
    assert typed.filters == {"collection_id": "support"}
    assert typed.search_options == {"rerank": True}
