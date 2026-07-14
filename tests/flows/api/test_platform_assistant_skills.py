"""Тесты platform_assistant Agent Skills seed и attach."""

from __future__ import annotations

import pytest

from apps.flows.src.runtime.agent_skill_runtime import (
    AgentSkillRuntimeHost,
    agent_skill_runtime_host_scope,
)
from apps.flows.src.services.platform_assistant_skills import (
    PLATFORM_ASSISTANT_ATTACHED_SKILL_IDS,
    seed_platform_assistant_skills,
)
from apps.flows.tools.agent_skill_tools import load_agent_skill, read_agent_skill_reference
from tests.flows.agent_skills_harness import (
    assert_platform_assistant_attach,
    company_scope,
    ensure_platform_assistant_flow,
    make_skill_state,
)


@pytest.mark.asyncio
async def test_seed_platform_assistant_skills_idempotent(container, unique_id: str) -> None:
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
        assert first == 7
        assert second == 7
        for skill_id in PLATFORM_ASSISTANT_ATTACHED_SKILL_IDS:
            skill = await container.agent_skill_service.get(skill_id)
            assert skill.agent_skill_id == skill_id
        addon = await container.agent_skill_service.get("docx-templates")
        assert addon.depends_on == []
        assert "fill_docx_template" in [ref.tool_id for ref in addon.tool_refs]
        docs = await container.agent_skill_service.get("document-workspace")
        assert docs.depends_on == ["docx-templates"]
        assert "create_file" in [ref.tool_id for ref in docs.tool_refs]
        assert docs.references


@pytest.mark.asyncio
async def test_platform_assistant_flow_attaches_skills(container, unique_id: str) -> None:
    _ = unique_id
    flow = await ensure_platform_assistant_flow(container)
    assert_platform_assistant_attach(flow)


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
            attached_ids=frozenset(PLATFORM_ASSISTANT_ATTACHED_SKILL_IDS),
            index_entries=tuple(
                await container.agent_skill_service.resolve_index(
                    list(PLATFORM_ASSISTANT_ATTACHED_SKILL_IDS)
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
            docs_result = await load_agent_skill.run(
                {"agent_skill_id": "document-workspace"},
                state,
            )
            assert docs_result["success"] is True
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
            assert addon_result["depth"] == 1
            assert "fill_docx_template" in addon_result["tools_unlocked"]

            viz_result = await load_agent_skill.run(
                {"agent_skill_id": "diagrams-viz"},
                state,
            )
            assert "create_viz" in viz_result["tools_unlocked"]

            with pytest.raises(ValueError, match="not attached"):
                await load_agent_skill.run(
                    {"agent_skill_id": "foreign-skill"},
                    state,
                )
