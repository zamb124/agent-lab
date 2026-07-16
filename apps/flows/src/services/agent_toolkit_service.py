"""Сервис групп инструментов HumanitecAgent."""

from __future__ import annotations

from pathlib import Path

import yaml

from apps.flows.src.db.agent_toolkit_repository import AgentToolkitRepository
from apps.flows.src.models.agent_toolkit import AgentToolkit
from apps.flows.src.models.bundle_registry import AgentToolkitRegistryEntry, FlowBundleRegistry
from core.logging import get_logger
from core.types import require_json_object

logger = get_logger(__name__)

PLATFORM_TOOLKIT_SOURCE = "platform"
CUSTOM_TOOLKIT_SOURCE = "custom"


def get_agent_toolkits_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "registry.yaml"


async def list_agent_toolkits(repository: AgentToolkitRepository) -> list[AgentToolkit]:
    rows = await repository.list(limit=1000)
    rows.sort(key=lambda row: (row.position, row.toolkit_id))
    return rows


async def get_agent_toolkit(
    repository: AgentToolkitRepository,
    toolkit_id: str,
) -> AgentToolkit | None:
    return await repository.get(toolkit_id)


async def save_agent_toolkit(
    repository: AgentToolkitRepository,
    toolkit: AgentToolkit,
) -> AgentToolkit:
    _ = await repository.set(toolkit)
    return toolkit


async def delete_agent_toolkit(
    repository: AgentToolkitRepository,
    toolkit_id: str,
) -> None:
    _ = await repository.delete(toolkit_id)


async def get_toolkit_ids_for_flow(
    repository: AgentToolkitRepository,
    flow_id: str,
) -> list[str]:
    toolkit_ids: list[str] = []
    for toolkit in await list_agent_toolkits(repository):
        if flow_id in toolkit.flow_ids:
            toolkit_ids.append(toolkit.toolkit_id)
    return toolkit_ids


async def get_toolkit_ids_for_tool(
    repository: AgentToolkitRepository,
    tool_id: str,
) -> list[str]:
    toolkit_ids: list[str] = []
    for toolkit in await list_agent_toolkits(repository):
        if tool_id in toolkit.tool_ids:
            toolkit_ids.append(toolkit.toolkit_id)
    return toolkit_ids


async def set_flow_toolkit_membership(
    repository: AgentToolkitRepository,
    *,
    flow_id: str,
    toolkit_ids: list[str],
) -> None:
    desired = set(toolkit_ids)
    for toolkit in await list_agent_toolkits(repository):
        has_flow = flow_id in toolkit.flow_ids
        should_have = toolkit.toolkit_id in desired
        if has_flow == should_have:
            continue
        updated_flow_ids = list(toolkit.flow_ids)
        if should_have and flow_id not in updated_flow_ids:
            updated_flow_ids.append(flow_id)
        if not should_have and flow_id in updated_flow_ids:
            updated_flow_ids = [item for item in updated_flow_ids if item != flow_id]
        updated = toolkit.model_copy(update={"flow_ids": updated_flow_ids})
        _ = await repository.set(updated)


async def set_tool_toolkit_membership(
    repository: AgentToolkitRepository,
    *,
    tool_id: str,
    toolkit_ids: list[str],
) -> None:
    desired = set(toolkit_ids)
    for toolkit in await list_agent_toolkits(repository):
        has_tool = tool_id in toolkit.tool_ids
        should_have = toolkit.toolkit_id in desired
        if has_tool == should_have:
            continue
        updated_tool_ids = list(toolkit.tool_ids)
        if should_have and tool_id not in updated_tool_ids:
            updated_tool_ids.append(tool_id)
        if not should_have and tool_id in updated_tool_ids:
            updated_tool_ids = [item for item in updated_tool_ids if item != tool_id]
        updated = toolkit.model_copy(update={"tool_ids": updated_tool_ids})
        _ = await repository.set(updated)


async def resolve_allowed_flow_ids(
    repository: AgentToolkitRepository,
    *,
    toolkit_id: str | None,
) -> set[str]:
    allowed: set[str] = set()
    for toolkit in await list_agent_toolkits(repository):
        if toolkit_id is not None and toolkit.toolkit_id != toolkit_id:
            continue
        allowed.update(toolkit.flow_ids)
    return allowed


async def resolve_allowed_tool_ids(
    repository: AgentToolkitRepository,
    *,
    toolkit_id: str | None,
) -> set[str]:
    allowed: set[str] = set()
    for toolkit in await list_agent_toolkits(repository):
        if toolkit_id is not None and toolkit.toolkit_id != toolkit_id:
            continue
        allowed.update(toolkit.tool_ids)
    return allowed


async def is_flow_in_agent_toolkits(
    repository: AgentToolkitRepository,
    flow_id: str,
) -> bool:
    for toolkit in await list_agent_toolkits(repository):
        if flow_id in toolkit.flow_ids:
            return True
    return False


async def is_tool_in_agent_toolkits(
    repository: AgentToolkitRepository,
    tool_id: str,
) -> bool:
    for toolkit in await list_agent_toolkits(repository):
        if tool_id in toolkit.tool_ids:
            return True
    return False


def _registry_entry_to_toolkit(entry: AgentToolkitRegistryEntry) -> AgentToolkit:
    return AgentToolkit(
        toolkit_id=entry.id,
        name=entry.name,
        description=entry.description,
        default_enabled=entry.default_enabled,
        position=entry.position,
        flow_ids=list(entry.flow_ids),
        tool_ids=list(entry.tool_ids),
        source=PLATFORM_TOOLKIT_SOURCE,
    )


def _merge_registry_toolkit(
    existing: AgentToolkit | None,
    registry_toolkit: AgentToolkit,
) -> AgentToolkit:
    if existing is None:
        return registry_toolkit
    merged_flow_ids = list(
        dict.fromkeys([*registry_toolkit.flow_ids, *existing.flow_ids])
    )
    merged_tool_ids = list(
        dict.fromkeys([*registry_toolkit.tool_ids, *existing.tool_ids])
    )
    return registry_toolkit.model_copy(
        update={
            "flow_ids": merged_flow_ids,
            "tool_ids": merged_tool_ids,
            "source": existing.source,
        }
    )


async def bootstrap_agent_toolkits_from_registry(
    repository: AgentToolkitRepository,
    registry_path: Path,
    *,
    filter_public: bool,
    only_missing: bool = False,
) -> int:
    if not registry_path.exists():
        logger.warning("agent_toolkits registry not found: %s", registry_path)
        return 0
    with open(registry_path, encoding="utf-8") as registry_file:
        registry_raw = require_json_object(yaml.safe_load(registry_file) or {}, "registry.yaml")
    bundle_registry = FlowBundleRegistry.model_validate(registry_raw)
    loaded_count = 0
    for entry in bundle_registry.agent_toolkits:
        if filter_public and not entry.public:
            continue
        registry_toolkit = _registry_entry_to_toolkit(entry)
        existing = await repository.get(registry_toolkit.toolkit_id)
        if only_missing and existing is not None:
            continue
        merged = (
            registry_toolkit
            if only_missing
            else _merge_registry_toolkit(existing, registry_toolkit)
        )
        _ = await repository.set(merged)
        loaded_count += 1
    logger.info(
        "agent_toolkits bootstrap loaded=%s filter_public=%s only_missing=%s",
        loaded_count,
        filter_public,
        only_missing,
    )
    return loaded_count


async def ensure_agent_toolkits_bootstrapped(
    repository: AgentToolkitRepository,
    *,
    company_id: str,
    registry_path: Path | None = None,
) -> bool:
    """Гарантирует platform toolkits из registry; не затирает уже существующие записи."""
    resolved_registry_path = (
        registry_path if registry_path is not None else get_agent_toolkits_registry_path()
    )
    inserted = await bootstrap_agent_toolkits_from_registry(
        repository,
        resolved_registry_path,
        filter_public=(company_id != "system"),
        only_missing=True,
    )
    return inserted > 0
