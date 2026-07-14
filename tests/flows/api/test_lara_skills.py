"""Lara unified Agent Skills: attach roots, zero standing domain tools, cross-domain load."""

from __future__ import annotations

import pytest

from apps.flows.src.runtime.agent_skill_runtime import (
    AgentSkillRuntimeHost,
    agent_skill_runtime_host_scope,
)
from apps.flows.src.services.platform_assistant_skills import (
    LARA_PLATFORM_SKILL_ROOTS,
    seed_platform_assistant_skills,
)
from apps.flows.tools.agent_skill_tools import load_agent_skill
from core.types import JsonObject, require_json_array, require_json_object
from tests.flows.agent_skills_harness import (
    assert_lara_attach,
    company_scope,
    ensure_lara_flow,
    make_skill_state,
    node_tool_ids,
)


def _load_payload(raw: object) -> JsonObject:
    return require_json_object(raw, "load_agent_skill.result")


def _tools_unlocked(payload: JsonObject) -> list[str]:
    return [str(item) for item in require_json_array(payload["tools_unlocked"], "tools_unlocked")]


@pytest.mark.asyncio
async def test_lara_flow_attaches_full_skill_roots(container, unique_id: str) -> None:
    _ = unique_id
    flow = await ensure_lara_flow(container)
    assert_lara_attach(flow)
    assert "reflection_node_helper" in (flow.branches or {})


@pytest.mark.asyncio
async def test_lara_effective_branch_keeps_full_roots_and_ask_user_only(
    container,
    unique_id: str,
) -> None:
    _ = unique_id
    flow = await ensure_lara_flow(container)
    factory = container.flow_factory
    for branch_id in ("crm", "flows", "code_helper", "docs", "llm_node_helper"):
        effective = factory.apply_branch(flow, branch_id)
        main = effective["nodes"]["main"]
        main_obj = require_json_object(main, f"effective.{branch_id}.main")
        skills = require_json_array(main_obj.get("agent_skills", []), "agent_skills")
        assert [str(item) for item in skills] == list(LARA_PLATFORM_SKILL_ROOTS)
        assert node_tool_ids(main_obj) == ["ask_user"]


@pytest.mark.asyncio
async def test_lara_cross_domain_skill_loads_from_any_root(
    container,
    unique_id: str,
) -> None:
    """Flows entry can load networkle; CRM entry path can load flows-editor via chain."""
    company_id = f"company_{unique_id}"
    async with company_scope(company_id, unique_id):
        await seed_platform_assistant_skills(
            container.agent_skill_service,
            container.files_service,
            company_id,
        )
        host = AgentSkillRuntimeHost(
            attached_ids=frozenset(LARA_PLATFORM_SKILL_ROOTS),
            index_entries=tuple(
                await container.agent_skill_service.resolve_index(
                    list(LARA_PLATFORM_SKILL_ROOTS)
                )
            ),
        )
        state = make_skill_state(flow_id="lara", unique_id=unique_id)

        with agent_skill_runtime_host_scope(host):
            net = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "networkle"}, state)
            )
            assert net["depth"] == 0
            entities = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "crm-entities"}, state)
            )
            assert entities["depth"] == 1
            entity_tools = _tools_unlocked(entities)
            assert "crm_search_entities" in entity_tools
            assert "crm_create_entity" in entity_tools

            flows_root = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "flows-platform"}, state)
            )
            assert flows_root["depth"] == 0
            editor = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "flows-editor"}, state)
            )
            assert editor["depth"] == 1
            editor_tools = _tools_unlocked(editor)
            assert "flows_patch_node" in editor_tools
            assert "flows_read_context" in editor_tools

            docs = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "docs-knowledge"}, state)
            )
            assert docs["depth"] == 0
            assert "docs_prepare_context" in _tools_unlocked(docs)

            workspace = _load_payload(
                await load_agent_skill.run(
                    {"agent_skill_id": "platform-workspace"},
                    state,
                )
            )
            assert workspace["depth"] == 0
            work = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "work-tracking"}, state)
            )
            assert work["depth"] == 1
            assert "work_item_create" in _tools_unlocked(work)
