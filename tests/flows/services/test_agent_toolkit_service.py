"""Unit-тесты agent_toolkit_service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from apps.flows.src.models.agent_toolkit import AgentToolkit
from apps.flows.src.services.agent_toolkit_service import (
    bootstrap_agent_toolkits_from_registry,
    ensure_agent_toolkits_bootstrapped,
    get_toolkit_ids_for_flow,
    is_flow_in_agent_toolkits,
    is_tool_in_agent_toolkits,
    list_agent_toolkits,
    resolve_allowed_flow_ids,
    resolve_allowed_tool_ids,
    set_flow_toolkit_membership,
    set_tool_toolkit_membership,
)
from core.context import Context, clear_context, get_context, set_context
from core.models.identity_models import Company, User


@pytest.fixture
def registry_path() -> Path:
    return Path(__file__).resolve().parents[3] / "apps" / "flows" / "registry.yaml"


def _company_context(company_id: str, unique_id: str) -> Context:
    return Context(
        user=User(user_id=f"user_{unique_id}", name="Test User"),
        active_company=Company(
            company_id=company_id,
            name=f"Company {company_id}",
            subdomain=f"sub-{unique_id}",
        ),
        session_id="test_session",
        channel="test",
        metadata={},
    )


@asynccontextmanager
async def _repository_context(container, unique_id: str) -> AsyncIterator[None]:
    previous = get_context()
    set_context(_company_context(f"company_{unique_id}", unique_id))
    try:
        yield
    finally:
        clear_context()
        if previous is not None:
            set_context(previous)


@asynccontextmanager
async def _repository_context_for_company(
    container,
    company_id: str,
    unique_id: str,
) -> AsyncIterator[None]:
    previous = get_context()
    set_context(_company_context(company_id, unique_id))
    try:
        yield
    finally:
        clear_context()
        if previous is not None:
            set_context(previous)


@pytest.mark.asyncio
async def test_list_agent_toolkits_sorted_by_position(container, unique_id: str) -> None:
    async with _repository_context(container, unique_id):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=f"tk_b_{unique_id}",
                name="B",
                description="B",
                position=20,
                source="custom",
            )
        )
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=f"tk_a_{unique_id}",
                name="A",
                description="A",
                position=10,
                source="custom",
            )
        )
        try:
            toolkits = await list_agent_toolkits(container.agent_toolkit_repository)
            ids = [toolkit.toolkit_id for toolkit in toolkits if unique_id in toolkit.toolkit_id]
            assert ids == [f"tk_a_{unique_id}", f"tk_b_{unique_id}"]
        finally:
            await container.agent_toolkit_repository.delete(f"tk_a_{unique_id}")
            await container.agent_toolkit_repository.delete(f"tk_b_{unique_id}")


@pytest.mark.asyncio
async def test_set_flow_toolkit_membership_add_remove(container, unique_id: str) -> None:
    flow_id = f"flow_mem_{unique_id}"
    toolkit_a = f"tk_a_{unique_id}"
    toolkit_b = f"tk_b_{unique_id}"
    async with _repository_context(container, unique_id):
        for toolkit_id in (toolkit_a, toolkit_b):
            await container.agent_toolkit_repository.set(
                AgentToolkit(
                    toolkit_id=toolkit_id,
                    name=toolkit_id,
                    description=toolkit_id,
                    source="custom",
                )
            )
        try:
            await set_flow_toolkit_membership(
                container.agent_toolkit_repository,
                flow_id=flow_id,
                toolkit_ids=[toolkit_a],
            )
            assert await get_toolkit_ids_for_flow(container.agent_toolkit_repository, flow_id) == [
                toolkit_a
            ]
            await set_flow_toolkit_membership(
                container.agent_toolkit_repository,
                flow_id=flow_id,
                toolkit_ids=[toolkit_a, toolkit_b],
            )
            assert set(
                await get_toolkit_ids_for_flow(container.agent_toolkit_repository, flow_id)
            ) == {toolkit_a, toolkit_b}
            await set_flow_toolkit_membership(
                container.agent_toolkit_repository,
                flow_id=flow_id,
                toolkit_ids=[],
            )
            assert await get_toolkit_ids_for_flow(container.agent_toolkit_repository, flow_id) == []
        finally:
            await container.agent_toolkit_repository.delete(toolkit_a)
            await container.agent_toolkit_repository.delete(toolkit_b)


@pytest.mark.asyncio
async def test_set_tool_toolkit_membership(container, unique_id: str) -> None:
    tool_id = f"tool_mem_{unique_id}"
    toolkit_id = f"tk_tool_{unique_id}"
    async with _repository_context(container, unique_id):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name=toolkit_id,
                description=toolkit_id,
                source="custom",
            )
        )
        try:
            await set_tool_toolkit_membership(
                container.agent_toolkit_repository,
                tool_id=tool_id,
                toolkit_ids=[toolkit_id],
            )
            toolkit = await container.agent_toolkit_repository.get(toolkit_id)
            assert toolkit is not None
            assert tool_id in toolkit.tool_ids
            assert await is_tool_in_agent_toolkits(container.agent_toolkit_repository, tool_id)
        finally:
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_resolve_allowed_ids_scoped_and_union(container, unique_id: str) -> None:
    toolkit_a = f"tk_scope_a_{unique_id}"
    toolkit_b = f"tk_scope_b_{unique_id}"
    async with _repository_context(container, unique_id):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_a,
                name="A",
                description="A",
                flow_ids=[f"flow_a_{unique_id}"],
                tool_ids=["calculator"],
                source="custom",
            )
        )
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_b,
                name="B",
                description="B",
                flow_ids=[f"flow_b_{unique_id}"],
                tool_ids=["rag_search"],
                source="custom",
            )
        )
        try:
            scoped_flows = await resolve_allowed_flow_ids(
                container.agent_toolkit_repository,
                toolkit_id=toolkit_a,
            )
            assert scoped_flows == {f"flow_a_{unique_id}"}
            union_flows = await resolve_allowed_flow_ids(
                container.agent_toolkit_repository,
                toolkit_id=None,
            )
            assert union_flows == {f"flow_a_{unique_id}", f"flow_b_{unique_id}"}
            missing = await resolve_allowed_flow_ids(
                container.agent_toolkit_repository,
                toolkit_id=f"missing_{unique_id}",
            )
            assert missing == set()
            scoped_tools = await resolve_allowed_tool_ids(
                container.agent_toolkit_repository,
                toolkit_id=toolkit_b,
            )
            assert scoped_tools == {"rag_search"}
        finally:
            await container.agent_toolkit_repository.delete(toolkit_a)
            await container.agent_toolkit_repository.delete(toolkit_b)


@pytest.mark.asyncio
async def test_bootstrap_merge_preserves_custom_membership(
    container,
    registry_path: Path,
    unique_id: str,
) -> None:
    extra_flow = f"extra_flow_{unique_id}"
    async with _repository_context(container, unique_id):
        await bootstrap_agent_toolkits_from_registry(
            container.agent_toolkit_repository,
            registry_path,
            filter_public=False,
        )
        toolkit = await container.agent_toolkit_repository.get("humanitec_core")
        assert toolkit is not None
        updated = toolkit.model_copy(update={"flow_ids": [*toolkit.flow_ids, extra_flow]})
        _ = await container.agent_toolkit_repository.set(updated)
        await bootstrap_agent_toolkits_from_registry(
            container.agent_toolkit_repository,
            registry_path,
            filter_public=False,
        )
        merged = await container.agent_toolkit_repository.get("humanitec_core")
        assert merged is not None
        assert extra_flow in merged.flow_ids
        assert "humanitec_agent" in merged.flow_ids


@pytest.mark.asyncio
async def test_ensure_agent_toolkits_bootstrapped_lazy_backfill(
    container,
    registry_path: Path,
    unique_id: str,
) -> None:
    company_id = f"company_backfill_{unique_id}"
    async with _repository_context_for_company(container, company_id, unique_id):
        bootstrapped = await ensure_agent_toolkits_bootstrapped(
            container.agent_toolkit_repository,
            company_id=company_id,
            registry_path=registry_path,
        )
        assert bootstrapped is True
        toolkits = await list_agent_toolkits(container.agent_toolkit_repository)
        assert len(toolkits) >= 6
        again = await ensure_agent_toolkits_bootstrapped(
            container.agent_toolkit_repository,
            company_id=company_id,
            registry_path=registry_path,
        )
        assert again is False


@pytest.mark.asyncio
async def test_is_flow_in_agent_toolkits(container, unique_id: str) -> None:
    flow_id = f"flow_check_{unique_id}"
    toolkit_id = f"tk_check_{unique_id}"
    async with _repository_context(container, unique_id):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name=toolkit_id,
                description=toolkit_id,
                flow_ids=[flow_id],
                source="custom",
            )
        )
        try:
            assert await is_flow_in_agent_toolkits(container.agent_toolkit_repository, flow_id)
            assert not await is_flow_in_agent_toolkits(
                container.agent_toolkit_repository,
                f"missing_{unique_id}",
            )
        finally:
            await container.agent_toolkit_repository.delete(toolkit_id)
