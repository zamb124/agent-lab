"""Тесты Agent Skills: model, service, API, runtime host."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from apps.flows.src.models.agent_skill import AgentSkill
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.runtime.agent_skill_runtime import (
    AgentSkillRuntimeHost,
    agent_skill_runtime_host_scope,
)
from apps.flows.src.services.agent_skill_service import (
    AgentSkillCreateInput,
    parse_skill_md,
)
from apps.flows.tools.agent_skill_tools import load_agent_skill, read_agent_skill_reference
from core.context import Context, clear_context, get_context, set_context
from core.files.create_spec import FileCreateSpec
from core.files.file_ref import FileRef
from core.models.identity_models import Company, User
from core.state import ExecutionState
from tests.flows.agent_skills_harness import company_scope


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
async def _company_scope(unique_id: str) -> AsyncIterator[None]:
    previous = get_context()
    set_context(_company_context(f"company_{unique_id}", unique_id))
    try:
        yield
    finally:
        clear_context()
        if previous is not None:
            set_context(previous)


def test_parse_skill_md_frontmatter_and_body() -> None:
    markdown = """---
name: review-pr
description: Review pull requests with a checklist
allowed-tools: calculator finish
activation: explicit
---

# Review PR

1. Read the diff
2. Leave comments
"""
    skill = parse_skill_md(markdown)
    assert skill.agent_skill_id == "review-pr"
    assert skill.name == "review-pr"
    assert "checklist" in skill.description
    assert "Read the diff" in skill.body_markdown
    assert [ref.tool_id for ref in skill.tool_refs] == ["calculator", "finish"]
    assert skill.activation == "explicit"


def test_parse_skill_md_rejects_missing_frontmatter() -> None:
    with pytest.raises(ValueError, match="frontmatter"):
        parse_skill_md("# Just a body\n")


@pytest.mark.asyncio
async def test_agent_skill_service_crud(container, unique_id: str) -> None:
    skill_id = f"skill-crud-{unique_id}"
    async with _company_scope(unique_id):
        created = await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=skill_id,
                name=skill_id,
                description="CRUD skill for tests",
                body_markdown="## Body\n\nDo the thing.",
                tool_refs=[
                    ToolReference(
                        tool_id="calculator",
                        description="calc",
                        parameters_schema={
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    )
                ],
            )
        )
        assert created.agent_skill_id == skill_id
        loaded = await container.agent_skill_service.get(skill_id)
        assert loaded.body_markdown.startswith("## Body")
        index = await container.agent_skill_service.resolve_index([skill_id])
        assert len(index) == 1
        assert index[0].agent_skill_id == skill_id
        await container.agent_skill_service.delete(skill_id)
        with pytest.raises(LookupError):
            await container.agent_skill_service.get(skill_id)


@pytest.mark.asyncio
async def test_agent_skill_import_md_persists(container, unique_id: str) -> None:
    skill_id = f"skill-import-{unique_id}"
    markdown = f"""---
name: {skill_id}
description: Imported skill for {unique_id}
allowed-tools: calculator
---

Imported body for {unique_id}
"""
    async with _company_scope(unique_id):
        imported = await container.agent_skill_service.import_skill_md(markdown)
        assert imported.agent_skill_id == skill_id
        assert imported.tool_refs[0].tool_id == "calculator"
        await container.agent_skill_service.delete(skill_id)


@pytest.mark.asyncio
async def test_agent_skills_api_crud(client, unique_id: str) -> None:
    skill_id = f"skill-api-{unique_id}"
    create_resp = await client.post(
        "/flows/api/v1/agent-skills",
        json={
            "agent_skill_id": skill_id,
            "name": skill_id,
            "description": "API skill",
            "body_markdown": "API body",
            "tool_refs": [],
            "depends_on": [],
            "references": [],
            "assets": [],
            "activation": "explicit",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["agent_skill_id"] == skill_id

    get_resp = await client.get(f"/flows/api/v1/agent-skills/{skill_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["body_markdown"] == "API body"

    list_resp = await client.get("/flows/api/v1/agent-skills", params={"limit": 50})
    assert list_resp.status_code == 200
    ids = {item["agent_skill_id"] for item in list_resp.json()["items"]}
    assert skill_id in ids

    delete_resp = await client.delete(f"/flows/api/v1/agent-skills/{skill_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_agent_skills_api_import(client, unique_id: str) -> None:
    skill_id = f"skill-api-import-{unique_id}"
    markdown = f"""---
name: {skill_id}
description: Import via API
---

Body via import API
"""
    resp = await client.post(
        "/flows/api/v1/agent-skills/import",
        json={"markdown": markdown, "persist": True},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["agent_skill_id"] == skill_id
    delete_resp = await client.delete(f"/flows/api/v1/agent-skills/{skill_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_agent_skills_api_ensure_seed_idempotent(client, unique_id: str) -> None:
    _ = unique_id
    first = await client.post("/flows/api/v1/agent-skills/ensure-seed", json={})
    assert first.status_code == 200, first.text
    assert first.json()["seeded"] == 7

    second = await client.post("/flows/api/v1/agent-skills/ensure-seed", json={})
    assert second.status_code == 200, second.text
    assert second.json()["seeded"] == 7

    list_resp = await client.get("/flows/api/v1/agent-skills", params={"limit": 200})
    assert list_resp.status_code == 200, list_resp.text
    ids = {item["agent_skill_id"] for item in list_resp.json()["items"]}
    assert "document-workspace" in ids
    assert "docx-templates" in ids
    assert "work-tracking" in ids


@pytest.mark.asyncio
async def test_load_agent_skill_tool_injects_body_and_tools(
    container,
    unique_id: str,
) -> None:
    root_id = f"skill-root-{unique_id}"
    dep_id = f"skill-dep-{unique_id}"
    async with _company_scope(unique_id):
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=dep_id,
                name=dep_id,
                description="Dependency skill",
                body_markdown="Dep body",
            )
        )
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=root_id,
                name=root_id,
                description="Root skill",
                body_markdown="Root body with procedure",
                tool_refs=[
                    ToolReference(
                        tool_id="calculator",
                        description="calc",
                        parameters_schema={
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    )
                ],
                depends_on=[dep_id],
            )
        )
        host = AgentSkillRuntimeHost(
            attached_ids=frozenset({root_id}),
            index_entries=tuple(
                await container.agent_skill_service.resolve_index([root_id])
            ),
        )
        host.ensure_index_block()
        assert any(b.stable_key == "agent_skills.index" for b in host.context_blocks)

        state = ExecutionState(
            task_id=f"task_{unique_id}",
            context_id=f"ctx_{unique_id}",
            user_id=f"user_{unique_id}",
            session_id=f"flow_{unique_id}:ctx_{unique_id}",
        )
        with agent_skill_runtime_host_scope(host):
            result = await load_agent_skill.run({"agent_skill_id": root_id}, state)

        assert result["success"] is True
        assert result["already_loaded"] is False
        assert result["tools_unlocked"] == ["calculator"]
        assert any(
            b.stable_key == f"agent_skills.body.{root_id}" for b in host.context_blocks
        )
        assert len(host.pending_tool_refs) == 1
        assert host.pending_tool_refs[0].tool_id == "calculator"

        with agent_skill_runtime_host_scope(host):
            dep_result = await load_agent_skill.run({"agent_skill_id": dep_id}, state)
        assert dep_result["depth"] == 1

        foreign_id = f"skill-foreign-{unique_id}"
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=foreign_id,
                name=foreign_id,
                description="Not attached",
                body_markdown="Foreign",
            )
        )
        with agent_skill_runtime_host_scope(host):
            with pytest.raises(ValueError, match="not attached"):
                await load_agent_skill.run({"agent_skill_id": foreign_id}, state)

        await container.agent_skill_service.delete(root_id)
        await container.agent_skill_service.delete(dep_id)
        await container.agent_skill_service.delete(foreign_id)


@pytest.mark.asyncio
async def test_depends_on_depth_two_rejected(container, unique_id: str) -> None:
    a_id = f"skill-a-{unique_id}"
    b_id = f"skill-b-{unique_id}"
    c_id = f"skill-c-{unique_id}"
    async with _company_scope(unique_id):
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=c_id,
                name=c_id,
                description="C",
                body_markdown="C body",
            )
        )
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=b_id,
                name=b_id,
                description="B",
                body_markdown="B body",
                depends_on=[c_id],
            )
        )
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=a_id,
                name=a_id,
                description="A",
                body_markdown="A body",
                depends_on=[b_id],
            )
        )
        host = AgentSkillRuntimeHost(
            attached_ids=frozenset({a_id}),
            index_entries=tuple(
                await container.agent_skill_service.resolve_index([a_id])
            ),
        )
        state = ExecutionState(
            task_id=f"task_{unique_id}",
            context_id=f"ctx_{unique_id}",
            user_id=f"user_{unique_id}",
            session_id=f"flow_{unique_id}:ctx_{unique_id}",
        )
        with agent_skill_runtime_host_scope(host):
            await load_agent_skill.run({"agent_skill_id": a_id}, state)
            await load_agent_skill.run({"agent_skill_id": b_id}, state)
            with pytest.raises(ValueError, match="not attached"):
                await load_agent_skill.run({"agent_skill_id": c_id}, state)

        await container.agent_skill_service.delete(a_id)
        await container.agent_skill_service.delete(b_id)
        await container.agent_skill_service.delete(c_id)


def test_agent_skill_model_rejects_self_dependency() -> None:
    with pytest.raises(ValueError, match="depend on itself"):
        AgentSkill(
            agent_skill_id="self-skill",
            name="self-skill",
            description="x",
            body_markdown="body",
            depends_on=["self-skill"],
        )


@pytest.mark.asyncio
async def test_read_agent_skill_reference_returns_utf8(
    container,
    unique_id: str,
) -> None:
    skill_id = f"skill-ref-{unique_id}"
    content = f"reference body {unique_id}"
    async with _company_scope(unique_id):
        record = await container.files_service.create(
            FileCreateSpec.model_validate(
                {
                    "source_kind": "platform_auxiliary",
                    "source_ref": {},
                    "retention": {"kind": "platform_default"},
                    "post_create": {"is_public": True},
                }
            ),
            content.encode("utf-8"),
            original_name=f"skill-ref-{unique_id}.md",
            content_type="text/markdown",
        )
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=skill_id,
                name=skill_id,
                description="Skill with reference file",
                body_markdown="Body",
                references=[
                    FileRef(
                        file_id=record.file_id,
                        original_name=record.original_name,
                        url=record.url,
                        content_type=record.content_type,
                        file_size=record.file_size,
                    )
                ],
            )
        )
        host = AgentSkillRuntimeHost(
            attached_ids=frozenset({skill_id}),
            index_entries=tuple(
                await container.agent_skill_service.resolve_index([skill_id])
            ),
        )
        state = ExecutionState(
            task_id=f"task_{unique_id}",
            context_id=f"ctx_{unique_id}",
            user_id=f"user_{unique_id}",
            session_id=f"flow_{unique_id}:ctx_{unique_id}",
        )
        with agent_skill_runtime_host_scope(host):
            await load_agent_skill.run({"agent_skill_id": skill_id}, state)
            result = await read_agent_skill_reference.run(
                {
                    "agent_skill_id": skill_id,
                    "file_id": record.file_id,
                },
                state,
            )
        assert result["success"] is True
        assert result["content"] == content
        assert result["original_name"] == record.original_name
        await container.agent_skill_service.delete(skill_id)


@pytest.mark.asyncio
async def test_agent_skills_company_isolation_http(
    client,
    unique_id: str,
    container,
) -> None:
    """Skill компании A не виден HTTP-клиенту компании system."""
    company_a = f"company_skill_iso_a_{unique_id}"
    skill_id = f"iso-http-{unique_id}"

    async with company_scope(company_a, unique_id):
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=skill_id,
                name=skill_id,
                description="iso a",
                body_markdown="# A",
            )
        )

    missing = await client.get(f"/flows/api/v1/agent-skills/{skill_id}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_agent_skills_live_catalog_update_http(client, unique_id: str) -> None:
    """PUT skill меняет body — GET отражает live catalog."""
    skill_id = f"live-http-{unique_id}"
    calc_ref = {
        "tool_id": "calculator",
        "description": "calc",
        "parameters_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    }
    create_file_ref = {
        "tool_id": "create_file",
        "description": "create file",
        "parameters_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    }

    created = await client.post(
        "/flows/api/v1/agent-skills",
        json={
            "agent_skill_id": skill_id,
            "name": skill_id,
            "description": "v1",
            "body_markdown": "# body-v1",
            "tool_refs": [calc_ref],
            "depends_on": [],
            "references": [],
            "assets": [],
            "activation": "explicit",
        },
    )
    assert created.status_code == 201, created.text

    updated = await client.put(
        f"/flows/api/v1/agent-skills/{skill_id}",
        json={
            "name": skill_id,
            "description": "v2",
            "body_markdown": "# body-v2",
            "tool_refs": [calc_ref, create_file_ref],
            "depends_on": [],
            "references": [],
            "assets": [],
            "activation": "explicit",
        },
    )
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["description"] == "v2"
    assert payload["body_markdown"] == "# body-v2"
    assert [ref["tool_id"] for ref in payload["tool_refs"]] == [
        "calculator",
        "create_file",
    ]

    fetched = await client.get(f"/flows/api/v1/agent-skills/{skill_id}")
    assert fetched.status_code == 200
    assert fetched.json()["body_markdown"] == "# body-v2"
    assert [ref["tool_id"] for ref in fetched.json()["tool_refs"]] == [
        "calculator",
        "create_file",
    ]

    await client.delete(f"/flows/api/v1/agent-skills/{skill_id}")


@pytest.mark.asyncio
async def test_agent_skills_unknown_tool_ref_rejected(client, unique_id: str) -> None:
    skill_id = f"bad-tool-{unique_id}"
    response = await client.post(
        "/flows/api/v1/agent-skills",
        json={
            "agent_skill_id": skill_id,
            "name": skill_id,
            "description": "bad",
            "body_markdown": "# x",
            "tool_refs": [
                {
                    "tool_id": "definitely_not_a_builtin_tool_xyz",
                    "description": "missing",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                }
            ],
            "depends_on": [],
            "references": [],
            "assets": [],
            "activation": "explicit",
        },
    )
    assert response.status_code == 400
    detail = response.text.lower()
    assert (
        "tool" in detail
        or "не найден" in detail
        or "not found" in detail
        or "unknown" in detail
    )
