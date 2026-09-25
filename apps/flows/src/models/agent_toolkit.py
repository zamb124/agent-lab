"""Группа инструментов HumanitecAgent (Platform MCP extension)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Literal, Self, override

import yaml
from oxyde import Field as DbField
from pydantic import ConfigDict, Field, model_validator

from apps.flows.src.models.bundle_registry import AgentToolkitRegistryEntry, FlowBundleRegistry
from core.context.context import require_active_company
from core.logging import get_logger
from core.models.base import StrictBaseModel
from core.models.platform_model import CompanyScopedModel
from core.types import require_json_object

logger = get_logger(__name__)


class AgentToolkit(CompanyScopedModel):
    """Группа flows/tools. Таблица ``agent_toolkits`` в базе flows."""

    __database_alias__: ClassVar[str | None] = "flows"
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    class Meta:
        is_table: bool = True
        table_name: str = "agent_toolkits"
        unique_together: list[tuple[str, str]] = [("company_id", "toolkit_id")]

    toolkit_id: str = DbField(min_length=1, db_index=True, description="Стабильный id группы (slug)")
    name: str = DbField(min_length=1, description="Отображаемое имя в агенте")
    description: str = DbField(min_length=1, description="Описание для UI агента")
    company_id: str = DbField(default="", db_index=True)
    agent_toolkit_id: str = DbField(default="", db_pk=True)
    default_enabled: bool = DbField(
        default=False,
        description="Включать расширение по умолчанию при первом появлении на устройстве",
    )
    position: int = DbField(default=0, description="Порядок в списке расширений")
    flow_ids: list[str] = DbField(default_factory=list, description="flow_id, входящие в группу")
    tool_ids: list[str] = DbField(
        default_factory=list,
        description="tool_id (builtin и custom), входящие в группу",
    )
    source: str = DbField(
        default="platform",
        min_length=1,
        description="platform — из registry bootstrap; custom — создана компанией",
    )

    @classmethod
    def row_id(cls, toolkit_id: str) -> str:
        company_id = require_active_company().company_id
        if toolkit_id == "" or company_id == "":
            raise ValueError("toolkit_id is required")
        if ":" in toolkit_id or ":" in company_id:
            raise ValueError("toolkit_id and company_id must not contain ':'")
        return f"{company_id}:{toolkit_id}"

    @model_validator(mode="after")
    def bind_company(self) -> Self:
        company_id = require_active_company().company_id
        if company_id == "":
            raise ValueError("company_id is required")
        if self.company_id == "":
            self.company_id = company_id
        elif self.company_id != company_id:
            raise ValueError("company_id does not match the active company")
        expected = type(self).row_id(self.toolkit_id)
        if self.agent_toolkit_id == "":
            self.agent_toolkit_id = expected
        elif self.agent_toolkit_id != expected:
            raise ValueError("agent_toolkit_id does not match company_id and toolkit_id")
        return self

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        expected = type(self).row_id(self.toolkit_id)
        if self.company_id == "" or self.agent_toolkit_id != expected:
            raise ValueError("agent_toolkit_id does not match the active company")

    @classmethod
    async def list_agent_toolkits(cls) -> list[Self]:
        rows = await cls.objects.limit(1000).offset(0).all()
        rows.sort(key=lambda row: (row.position, row.toolkit_id))
        return rows

    @classmethod
    async def by_toolkit_id(cls, toolkit_id: str) -> Self | None:
        agent_toolkit_id = cls.row_id(toolkit_id)
        if agent_toolkit_id == "":
            raise ValueError("AgentToolkit agent_toolkit_id is required")
        return await cls.objects.filter(agent_toolkit_id=agent_toolkit_id).get_or_none()

    @classmethod
    async def delete_by_toolkit_id(cls, toolkit_id: str) -> bool:
        agent_toolkit_id = cls.row_id(toolkit_id)
        if agent_toolkit_id == "":
            raise ValueError("AgentToolkit agent_toolkit_id is required")
        deleted = await cls.objects.filter(agent_toolkit_id=agent_toolkit_id).delete()
        return deleted > 0

    @classmethod
    async def toolkit_ids_by_flow_ids(
        cls,
        flow_ids: Sequence[str],
    ) -> dict[str, list[str]]:
        wanted = set(flow_ids)
        by_flow: dict[str, list[str]] = {flow_id: [] for flow_id in flow_ids}
        if not wanted:
            return by_flow
        for toolkit in await cls.list_agent_toolkits():
            for flow_id in toolkit.flow_ids:
                if flow_id in wanted:
                    by_flow[flow_id].append(toolkit.toolkit_id)
        return by_flow

    @classmethod
    async def get_toolkit_ids_for_flow(cls, flow_id: str) -> list[str]:
        by_flow = await cls.toolkit_ids_by_flow_ids([flow_id])
        return by_flow[flow_id]

    @classmethod
    async def get_toolkit_ids_for_tool(cls, tool_id: str) -> list[str]:
        toolkit_ids: list[str] = []
        for toolkit in await cls.list_agent_toolkits():
            if tool_id in toolkit.tool_ids:
                toolkit_ids.append(toolkit.toolkit_id)
        return toolkit_ids

    @classmethod
    async def set_flow_toolkit_membership(
        cls,
        *,
        flow_id: str,
        toolkit_ids: list[str],
    ) -> None:
        desired = set(toolkit_ids)
        for toolkit in await cls.list_agent_toolkits():
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
            _ = await cls.set(updated)

    @classmethod
    async def set_tool_toolkit_membership(
        cls,
        *,
        tool_id: str,
        toolkit_ids: list[str],
    ) -> None:
        desired = set(toolkit_ids)
        for toolkit in await cls.list_agent_toolkits():
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
            _ = await cls.set(updated)

    @classmethod
    def _registry_entry_to_toolkit(cls, entry: AgentToolkitRegistryEntry) -> Self:
        return cls(
            toolkit_id=entry.id,
            name=entry.name,
            description=entry.description,
            default_enabled=entry.default_enabled,
            position=entry.position,
            flow_ids=list(entry.flow_ids),
            tool_ids=list(entry.tool_ids),
            source="platform",
        )

    @classmethod
    def _merge_registry_toolkit(
        cls,
        existing: Self | None,
        registry_toolkit: Self,
    ) -> Self:
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

    @classmethod
    async def bootstrap_agent_toolkits_from_registry(
        cls,
        registry_path: Path,
        *,
        filter_public: bool,
        only_missing: bool = False,
    ) -> int:
        if not registry_path.exists():
            logger.warning("flows.agent_toolkits", registry_path=registry_path)
            return 0
        with open(registry_path, encoding="utf-8") as registry_file:
            registry_raw = require_json_object(yaml.safe_load(registry_file) or {}, "registry.yaml")
        bundle_registry = FlowBundleRegistry.model_validate(registry_raw)
        loaded_count = 0
        for entry in bundle_registry.agent_toolkits:
            if filter_public and not entry.public:
                continue
            registry_toolkit = cls._registry_entry_to_toolkit(entry)
            existing = await cls.by_toolkit_id(registry_toolkit.toolkit_id)
            if only_missing and existing is not None:
                continue
            merged = (
                registry_toolkit
                if only_missing
                else cls._merge_registry_toolkit(existing, registry_toolkit)
            )
            _ = await cls.set(merged)
            loaded_count += 1
        logger.info(
            "flows.agent_toolkits",
            loaded=loaded_count,
            filter_public=filter_public,
            only_missing=only_missing,
        )
        return loaded_count

    @classmethod
    async def ensure_agent_toolkits_bootstrapped(
        cls,
        *,
        company_id: str,
        registry_path: Path | None = None,
    ) -> bool:
        """Гарантирует platform toolkits из registry; не затирает уже существующие записи."""
        resolved_registry_path = (
            registry_path if registry_path is not None else get_agent_toolkits_registry_path()
        )
        inserted = await cls.bootstrap_agent_toolkits_from_registry(
            resolved_registry_path,
            filter_public=(company_id != "system"),
            only_missing=True,
        )
        return inserted > 0


def get_agent_toolkits_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "registry.yaml"


class AgentToolkitIdPayload(StrictBaseModel):
    toolkit_id: str = Field(min_length=1)


class AgentToolkitCreateRequest(StrictBaseModel):
    toolkit_id: str
    name: str
    description: str
    default_enabled: bool = False
    position: int = 100
    flow_ids: list[str] = []
    tool_ids: list[str] = []


class AgentToolkitUpdateRequest(StrictBaseModel):
    name: str
    description: str
    default_enabled: bool
    position: int
    flow_ids: list[str]
    tool_ids: list[str]


class AgentToolkitUpdatePayload(AgentToolkitUpdateRequest):
    toolkit_id: str = Field(min_length=1)


class AgentToolkitDeletedResponse(StrictBaseModel):
    status: Literal["deleted"]
    toolkit_id: str


class AgentToolkitCatalogListPayload(StrictBaseModel):
    """Каталог для LinnexAgent: MCP URL строятся под публичный origin фронта вызывающего."""

    frontend_base_url: str = Field(min_length=1)
    desktop_only: bool = False


class AgentToolkitCatalogItem(StrictBaseModel):
    toolkit_id: str
    name: str
    description: str
    default_enabled: bool
    position: int
    mcp_url: str
