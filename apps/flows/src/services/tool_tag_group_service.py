"""Сбор tag→tools и LLM-описания групп для tool picker."""

from __future__ import annotations

import hashlib
import importlib
from collections import defaultdict
from datetime import datetime, timezone

from apps.flows.src.db.flow_repository import FlowRepository
from apps.flows.src.db.tool_tag_group_repository import ToolTagGroupRepository
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.models.tool_tag_group import (
    ToolTagGroup,
    ToolTagGroupDescribeResult,
    ToolTagGroupTickStats,
)
from apps.flows.src.tools.base import BaseTool
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS
from core.ai.providers import AICapability
from core.ai.resolver import resolve_ai_model
from core.ai.runtime import create_llm_client_from_ai_model
from core.logging import get_logger
from core.types import JsonObject, JsonValue

logger = get_logger(__name__)

_DESCRIPTION_MAX_LEN = 120
_USAGE_SAMPLES_PER_TAG = 8
_FLOW_SCAN_LIMIT = 200


class ToolTagGroupService:
    """Platform catalog описаний tag-групп + idle LLM refresh."""

    _repository: ToolTagGroupRepository
    _flow_repository: FlowRepository

    def __init__(
        self,
        *,
        repository: ToolTagGroupRepository,
        flow_repository: FlowRepository,
    ) -> None:
        self._repository = repository
        self._flow_repository = flow_repository

    async def list_groups(self, *, limit: int = 500, offset: int = 0) -> list[ToolTagGroup]:
        groups = await self._repository.list(limit=limit, offset=offset)
        return sorted(groups, key=lambda item: item.tag)

    async def describe_all_platform_tags(self) -> ToolTagGroupTickStats:
        tools_by_tag = self._collect_builtin_tools_by_tag()
        usage_by_tag = await self._sample_flow_usage_by_tag(tools_by_tag)
        updated = 0
        skipped = 0
        for tag in sorted(tools_by_tag.keys()):
            tools = tools_by_tag[tag]
            content_hash = self._content_hash(tools)
            existing = await self._repository.get(tag)
            if existing is not None and existing.content_hash == content_hash:
                skipped += 1
                continue
            described = await self._describe_tag_with_llm(
                tag=tag,
                tools=tools,
                usage_flow_ids=usage_by_tag.get(tag, []),
            )
            record = ToolTagGroup(
                tag=tag,
                description_ru=described.description_ru[:_DESCRIPTION_MAX_LEN],
                description_en=described.description_en[:_DESCRIPTION_MAX_LEN],
                content_hash=content_hash,
                updated_at=datetime.now(timezone.utc),
            )
            _ = await self._repository.set(record)
            updated += 1
            logger.info(
                "tool_tag_group.described",
                tag=tag,
                tools_count=len(tools),
            )
        return ToolTagGroupTickStats(
            tags_total=len(tools_by_tag),
            tags_updated=updated,
            tags_skipped=skipped,
        )

    def _collect_builtin_tools_by_tag(self) -> dict[str, list[tuple[str, str]]]:
        by_tag: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for module_name, attr_name in BUILTIN_TOOL_SPECS:
            module = importlib.import_module(module_name)
            raw_tool = module.__dict__.get(attr_name)
            if not isinstance(raw_tool, BaseTool):
                raise TypeError(
                    f"builtin tool {module_name}.{attr_name} must be BaseTool, got {type(raw_tool)!r}"
                )
            tool_id = raw_tool.name
            if tool_id.strip() == "":
                raise ValueError(f"builtin tool {module_name}.{attr_name} has empty name")
            description = raw_tool.description
            for tag in raw_tool.get_tags():
                if tag.strip() == "":
                    raise ValueError(f"tool {tool_id} has empty tag")
                by_tag[tag].append((tool_id, description))
        return {tag: sorted(items, key=lambda pair: pair[0]) for tag, items in by_tag.items()}

    async def _sample_flow_usage_by_tag(
        self,
        tools_by_tag: dict[str, list[tuple[str, str]]],
    ) -> dict[str, list[str]]:
        if len(tools_by_tag) == 0:
            return {}
        flows = await self._flow_repository.list(limit=_FLOW_SCAN_LIMIT, offset=0)
        tool_to_tags: dict[str, set[str]] = defaultdict(set)
        for tag, tool_pairs in tools_by_tag.items():
            for tool_id, _ in tool_pairs:
                tool_to_tags[tool_id].add(tag)

        usage: dict[str, list[str]] = {tag: [] for tag in tools_by_tag}
        for flow in flows:
            used_tool_ids = self._tool_ids_from_flow(flow)
            if len(used_tool_ids) == 0:
                continue
            for tool_id in used_tool_ids:
                for tag in tool_to_tags.get(tool_id, set()):
                    bucket = usage[tag]
                    if flow.flow_id in bucket:
                        continue
                    if len(bucket) >= _USAGE_SAMPLES_PER_TAG:
                        continue
                    bucket.append(flow.flow_id)
        return usage

    def _tool_ids_from_flow(self, flow: FlowConfig) -> set[str]:
        found: set[str] = set()
        nodes = flow.nodes
        if nodes is None:
            return found
        for node in nodes.values():
            node_obj: JsonObject = node
            raw_tools: JsonValue | None = node_obj.get("tools")
            if not isinstance(raw_tools, list):
                continue
            for tool_ref in raw_tools:
                if isinstance(tool_ref, str) and tool_ref.strip() != "":
                    found.add(tool_ref)
                    continue
                if not isinstance(tool_ref, dict):
                    continue
                tool_id = tool_ref.get("tool_id")
                if isinstance(tool_id, str) and tool_id.strip() != "":
                    found.add(tool_id)
        return found

    def _content_hash(self, tools: list[tuple[str, str]]) -> str:
        digest = hashlib.sha256()
        for tool_id, description in tools:
            digest.update(tool_id.encode("utf-8"))
            digest.update(b"\0")
            digest.update(description.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    async def _describe_tag_with_llm(
        self,
        *,
        tag: str,
        tools: list[tuple[str, str]],
        usage_flow_ids: list[str],
    ) -> ToolTagGroupDescribeResult:
        resolved = resolve_ai_model(
            AICapability.LLM_CHAT,
            include_platform_default=True,
        )
        if resolved is None:
            raise ValueError(
                "tool_tag_groups_describe: platform default for capability=llm_chat not configured"
            )
        llm = create_llm_client_from_ai_model(resolved)
        tools_block = "\n".join(
            f"- {tool_id}: {description}" if description else f"- {tool_id}"
            for tool_id, description in tools
        )
        usage_block = ", ".join(usage_flow_ids) if usage_flow_ids else "(none)"
        prompt = (
            f"Tag group slug: {tag}\n"
            f"Tools in this group:\n{tools_block}\n"
            f"Example flow_ids that use tools from this group: {usage_block}\n\n"
            "Write one very short phrase describing what this tool group is for. "
            "No marketing. No lists. Max 120 characters each language. "
            "Return description_ru and description_en."
        )
        result = await llm.chat(prompt, response_model=ToolTagGroupDescribeResult)
        if result.description_ru.strip() == "" or result.description_en.strip() == "":
            raise ValueError(f"empty LLM description for tag {tag!r}")
        return result
