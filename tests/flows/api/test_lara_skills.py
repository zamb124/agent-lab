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


def _assert_tools_include(payload: JsonObject, expected_tool_ids: set[str]) -> None:
    assert expected_tool_ids <= set(_tools_unlocked(payload))


@pytest.mark.asyncio
async def test_lara_flow_attaches_full_skill_roots(container, unique_id: str) -> None:
    _ = unique_id
    flow = await ensure_lara_flow(container)
    assert_lara_attach(flow)
    assert "reflection_node_helper" in (flow.branches or {})
    main = flow.nodes["main"] if flow.nodes is not None else None
    main_obj = require_json_object(main, "lara.main")
    skills = require_json_array(main_obj.get("agent_skills", []), "lara.main.agent_skills")
    assert [str(item) for item in skills] == list(LARA_PLATFORM_SKILL_ROOTS)


@pytest.mark.asyncio
async def test_lara_every_effective_branch_keeps_full_roots_and_ask_user_only(
    container,
    unique_id: str,
) -> None:
    _ = unique_id
    flow = await ensure_lara_flow(container)
    branches = flow.branches
    assert branches is not None
    assert {
        "console",
        "crm",
        "flows",
        "sync",
        "rag",
        "documents",
        "worktracker",
        "litserve",
        "docs",
        "node_helper",
    } <= set(branches)
    docs_branch = branches["docs"]
    assert docs_branch.entry == "docs_lookup"
    assert docs_branch.edges is not None
    assert any(edge.from_node == "docs_lookup" and edge.to_node == "main" for edge in docs_branch.edges)
    factory = container.flow_factory
    for branch_id in sorted(branches):
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
            _assert_tools_include(
                entities,
                {
                    "crm_search_entities",
                    "crm_create_entity",
                    "crm_get_entity",
                    "crm_create_relationship",
                    "crm_list_entity_types",
                    "crm_daily_summary",
                },
            )

            flows_root = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "flows-platform"}, state)
            )
            assert flows_root["depth"] == 0
            editor = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "flows-editor"}, state)
            )
            assert editor["depth"] == 1
            _assert_tools_include(
                editor,
                {"flows_patch_node", "flows_patch_flow", "flows_read_context", "push_embed_blocks"},
            )

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
            assert set(workspace["depends_on"]) == {
                "document-workspace",
                "diagrams-viz",
                "web-research",
                "work-tracking",
            }
            work = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "work-tracking"}, state)
            )
            assert work["depth"] == 1
            _assert_tools_include(
                work,
                {
                    "work_item_create",
                    "work_item_list",
                    "work_item_complete",
                    "schedule_cron_task",
                    "schedule_interval_task",
                    "schedule_one_time_task",
                    "list_scheduled_tasks",
                    "cancel_scheduled_task",
                },
            )

            sync = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "sync-platform"}, state)
            )
            assert sync["depth"] == 0
            assert _tools_unlocked(sync) == [
                "sync_list_messages",
                "sync_send_message",
            ]

            rag = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "rag-platform"}, state)
            )
            assert rag["depth"] == 0
            knowledge = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "knowledge-rag"}, state)
            )
            assert knowledge["depth"] == 1
            assert "rag_search" in _tools_unlocked(knowledge)

            documents = _load_payload(
                await load_agent_skill.run(
                    {"agent_skill_id": "documents-platform"},
                    state,
                )
            )
            assert documents["depth"] == 0
            assert set(documents["depends_on"]) == {"document-workspace", "diagrams-viz"}
            document_workspace = _load_payload(
                await load_agent_skill.run(
                    {"agent_skill_id": "document-workspace"},
                    state,
                )
            )
            _assert_tools_include(
                document_workspace,
                {
                    "read_file",
                    "create_file",
                    "documents_open_file",
                    "documents_replace_text",
                    "documents_append_text",
                    "documents_update_cells",
                },
            )
            diagrams = _load_payload(
                await load_agent_skill.run({"agent_skill_id": "diagrams-viz"}, state)
            )
            _assert_tools_include(diagrams, {"create_viz", "update_viz", "export_viz", "viz_open_file"})

            worktracker = _load_payload(
                await load_agent_skill.run(
                    {"agent_skill_id": "worktracker-platform"},
                    state,
                )
            )
            assert worktracker["depth"] == 0
            assert worktracker["depends_on"] == ["work-tracking"]

            console = _load_payload(
                await load_agent_skill.run(
                    {"agent_skill_id": "console-platform"},
                    state,
                )
            )
            assert console["depth"] == 0
            assert _tools_unlocked(console) == []

            litserve = _load_payload(
                await load_agent_skill.run(
                    {"agent_skill_id": "litserve-platform"},
                    state,
                )
            )
            assert litserve["depth"] == 0
            assert _tools_unlocked(litserve) == []
