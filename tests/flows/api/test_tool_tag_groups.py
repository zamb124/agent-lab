"""Тесты API и сервиса platform tool tag groups."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.flows.src.models.tool_tag_group import ToolTagGroup, ToolTagGroupDescribeResult
from apps.flows.src.services.tool_tag_group_service import ToolTagGroupService
from tests.fixtures.billing import make_test_billing_service


@pytest.mark.asyncio
async def test_list_tool_tag_groups_empty(client, di, unique_id):
    tag = f"empty_{unique_id}"
    response = await client.get("/flows/api/v1/tools/tag-groups?limit=200&offset=0")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    assert all(item["tag"] != tag for item in body["items"])


@pytest.mark.asyncio
async def test_list_tool_tag_groups_returns_stored(client, di, unique_id):
    tag = f"math_{unique_id}"
    record = ToolTagGroup(
        tag=tag,
        description_ru="Математика",
        description_en="Math",
        content_hash="abc",
        updated_at=datetime.now(timezone.utc),
    )
    await ToolTagGroup.set(record)
    response = await client.get("/flows/api/v1/tools/tag-groups?limit=200&offset=0")
    assert response.status_code == 200
    body = response.json()
    match = next((item for item in body["items"] if item["tag"] == tag), None)
    assert match is not None
    assert match["description_ru"] == "Математика"
    assert match["description_en"] == "Math"


@pytest.mark.asyncio
async def test_describe_skips_unchanged_hash(di, monkeypatch):
    service = di.tool_tag_group_service
    tools_by_tag = service._collect_builtin_tools_by_tag()
    assert "misc" in tools_by_tag
    misc_tools = tools_by_tag["misc"]
    content_hash = service._content_hash(misc_tools)
    await ToolTagGroup.set(
        ToolTagGroup(
            tag="misc",
            description_ru="старое",
            description_en="old",
            content_hash=content_hash,
            updated_at=datetime.now(timezone.utc),
        )
    )

    async def _fail_llm(*_args, **_kwargs):
        raise AssertionError("LLM must not be called when content_hash matches")

    monkeypatch.setattr(service, "_describe_tag_with_llm", _fail_llm)

    monkeypatch.setattr(
        service,
        "_collect_builtin_tools_by_tag",
        lambda: {"misc": misc_tools},
    )

    async def _empty_usage(_tools_by_tag):
        return {"misc": []}

    monkeypatch.setattr(service, "_sample_flow_usage_by_tag", _empty_usage)

    stats = await service.describe_all_platform_tags()
    assert stats.tags_total == 1
    assert stats.tags_skipped == 1
    assert stats.tags_updated == 0


@pytest.mark.asyncio
async def test_describe_writes_llm_result(di, monkeypatch):
    service = di.tool_tag_group_service
    tools = [("calculator", "Math expressions")]
    content_hash = service._content_hash(tools)

    monkeypatch.setattr(
        service,
        "_collect_builtin_tools_by_tag",
        lambda: {"misc": tools},
    )

    async def _empty_usage(_tools_by_tag):
        return {"misc": ["demo_flow"]}

    monkeypatch.setattr(service, "_sample_flow_usage_by_tag", _empty_usage)

    async def _fake_llm(*, tag, tools, usage_flow_ids):
        assert tag == "misc"
        assert tools == [("calculator", "Math expressions")]
        assert usage_flow_ids == ["demo_flow"]
        return ToolTagGroupDescribeResult(
            description_ru="Счёт и формулы",
            description_en="Calc and formulas",
        )

    monkeypatch.setattr(service, "_describe_tag_with_llm", _fake_llm)

    stats = await service.describe_all_platform_tags()
    assert stats.tags_updated == 1
    stored = await ToolTagGroup.get("misc")
    assert stored is not None
    assert stored.description_ru == "Счёт и формулы"
    assert stored.description_en == "Calc and formulas"
    assert stored.content_hash == content_hash


@pytest.mark.asyncio
async def test_content_hash_stable_order():
    service = ToolTagGroupService(make_test_billing_service())
    a = service._content_hash([("a", "1"), ("b", "2")])
    b = service._content_hash([("a", "1"), ("b", "2")])
    c = service._content_hash([("b", "2"), ("a", "1")])
    assert a == b
    assert a != c
