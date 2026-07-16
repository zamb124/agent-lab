"""Тесты platform_assistant Agent Skills seed и attach."""

from __future__ import annotations

import pytest

from apps.flows.src.runtime.agent_skill_runtime import (
    AgentSkillRuntimeHost,
    agent_skill_runtime_host_scope,
)
from apps.flows.src.services.platform_assistant_skills import (
    LARA_PLATFORM_SKILL_ROOTS,
    PLATFORM_ASSISTANT_SEED_SKILL_IDS,
    seed_platform_assistant_skills,
)
from apps.flows.tools.agent_skill_tools import load_agent_skill, read_agent_skill_reference
from apps.flows.tools.builtin_specs import builtin_tool_ids
from tests.flows.agent_skills_harness import (
    company_scope,
    make_skill_state,
)


@pytest.mark.asyncio
async def test_seed_platform_assistant_skills_idempotent(container, unique_id: str) -> None:
    assert PLATFORM_ASSISTANT_SEED_SKILL_IDS == (
        "docx-templates",
        "document-workspace",
        "documents-catalog",
        "diagrams-viz",
        "knowledge-rag",
        "web-research",
        "crm-notes",
        "crm-entities",
        "work-tracking",
        "flows-editor",
        "flows-node-edit",
        "code-node",
        "llm-node-config",
        "flows-code",
        "flows-platform",
        "docs-knowledge",
        "networkle",
        "platform-workspace",
        "console-platform",
        "sync-platform",
        "documents-platform",
        "worktracker-platform",
        "litserve-platform",
    )
    company_id = f"company_{unique_id}"
    async with company_scope(company_id, unique_id):
        first = await seed_platform_assistant_skills(
            container.agent_skill_service,
            container.files_service,
            company_id,
        )
        second = await seed_platform_assistant_skills(
            container.agent_skill_service,
            container.files_service,
            company_id,
        )
        assert first == 23
        assert second == 23
        for skill_id in LARA_PLATFORM_SKILL_ROOTS:
            skill = await container.agent_skill_service.get(skill_id)
            assert skill.agent_skill_id == skill_id
        documents_platform = await container.agent_skill_service.get("documents-platform")
        assert "knowledge-rag" in documents_platform.depends_on
        assert "document-workspace" in documents_platform.depends_on
        assert "documents-catalog" in documents_platform.depends_on
        assert "diagrams-viz" in documents_platform.depends_on
        documents_catalog = await container.agent_skill_service.get("documents-catalog")
        catalog_tool_ids = {ref.tool_id for ref in documents_catalog.tool_refs}
        assert catalog_tool_ids == {
            "documents_list_catalog",
            "documents_find",
            "documents_read",
            "documents_get_link",
        }
        networkle = await container.agent_skill_service.get("networkle")
        assert "crm-entities" in networkle.depends_on
        assert "crm-notes" in networkle.depends_on
        addon = await container.agent_skill_service.get("docx-templates")
        assert addon.depends_on == []
        assert "fill_docx_template" in [ref.tool_id for ref in addon.tool_refs]
        docs = await container.agent_skill_service.get("document-workspace")
        assert docs.depends_on == ["docx-templates"]
        assert "create_file" in [ref.tool_id for ref in docs.tool_refs]
        assert docs.references
        sync = await container.agent_skill_service.get("sync-platform")
        assert [ref.tool_id for ref in sync.tool_refs] == [
            "sync_list_messages",
            "sync_send_message",
        ]
        work = await container.agent_skill_service.get("work-tracking")
        work_tool_ids = [ref.tool_id for ref in work.tool_refs]
        assert "schedule_cron_task" in work_tool_ids
        assert "schedule_interval_task" in work_tool_ids
        web = await container.agent_skill_service.get("web-research")
        web_tool_ids = [ref.tool_id for ref in web.tool_refs]
        assert "browser_duckduckgo_links_batch" in web_tool_ids
        assert "browser_page_snapshot" in web_tool_ids

        seeded_skills = await container.agent_skill_service.list_skills(
            limit=100,
            offset=0,
        )
        registered_tool_ids = builtin_tool_ids()
        for seeded_skill in seeded_skills:
            assert {
                tool_ref.tool_id for tool_ref in seeded_skill.tool_refs
            } <= registered_tool_ids

@pytest.mark.asyncio
async def test_platform_assistant_skill_load_docs_viz_and_depends_on(
    container,
    unique_id: str,
) -> None:
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
        host.ensure_index_block()
        assert any(b.stable_key == "agent_skills.index" for b in host.context_blocks)
        assert not any(
            b.stable_key == "agent_skills.body.document-workspace" for b in host.context_blocks
        )

        state = make_skill_state(flow_id="platform_assistant", unique_id=unique_id)
        with agent_skill_runtime_host_scope(host):
            workspace_result = await load_agent_skill.run(
                {"agent_skill_id": "platform-workspace"},
                state,
            )
            assert workspace_result["success"] is True
            assert workspace_result["depth"] == 0

            docs_result = await load_agent_skill.run(
                {"agent_skill_id": "document-workspace"},
                state,
            )
            assert docs_result["success"] is True
            assert docs_result["depth"] == 1
            assert "create_file" in docs_result["tools_unlocked"]
            assert any(
                b.stable_key == "agent_skills.body.document-workspace"
                for b in host.context_blocks
            )

            ref_result = await read_agent_skill_reference.run(
                {
                    "agent_skill_id": "document-workspace",
                    "original_name": "document-workspace-reference.md",
                },
                state,
            )
            assert ref_result["success"] is True
            assert "create_file" in ref_result["content"]

            addon_result = await load_agent_skill.run(
                {"agent_skill_id": "docx-templates"},
                state,
            )
            assert addon_result["depth"] == 2
            assert "fill_docx_template" in addon_result["tools_unlocked"]

            viz_result = await load_agent_skill.run(
                {"agent_skill_id": "diagrams-viz"},
                state,
            )
            assert viz_result["depth"] == 1
            assert "create_viz" in viz_result["tools_unlocked"]

            with pytest.raises(ValueError, match="not attached"):
                await load_agent_skill.run(
                    {"agent_skill_id": "foreign-skill"},
                    state,
                )
