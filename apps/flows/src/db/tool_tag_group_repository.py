"""Репозиторий платформенных описаний tag-групп tools."""

from __future__ import annotations

from typing import ClassVar, override

from apps.flows.src.models.tool_tag_group import ToolTagGroup
from core.db import BaseRepository, Storage


class ToolTagGroupRepository(BaseRepository[ToolTagGroup]):
    """CRUD platform-wide tool tag group descriptions (is_global)."""

    is_global: ClassVar[bool] = True
    owner_service: ClassVar[str] = "flows"

    def __init__(self, storage: Storage) -> None:
        super().__init__(storage, ToolTagGroup)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"tool_tag_group:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "tool_tag_group:"

    @override
    def _get_table_name(self) -> str:
        return "tool_tag_groups"

    @override
    def _extract_entity_id(self, entity: ToolTagGroup) -> str:
        return entity.tag
