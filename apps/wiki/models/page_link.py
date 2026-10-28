"""Таблица wiki."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic

from apps.wiki.models.domain import (
    WikiLinkTargetKind,
)
from core.models.platform_model import PlatformModel


class WikiPageLink(PlatformModel):
    """Исходящая ссылка страницы. Таблица ``wiki_page_links``."""

    __database_alias__: ClassVar[str | None] = "wiki"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "wiki_page_links"
        unique_together: list[tuple[str, str, str]] = [
            ("source_page_id", "target_kind", "target_id"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "namespace", "source_page_id"]),
            Index(["company_id", "target_kind", "target_id"]),
        ]

    wiki_page_link_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    namespace: str = DbField(max_length=100)
    source_page_id: str = DbField(max_length=64)
    target_kind: WikiLinkTargetKind = DbField()
    target_id: str = DbField(max_length=255)
    created_at: datetime = DbField()
    target_label: str = DbField(default="", db_type="TEXT")

    @classmethod
    async def replace_outgoing(
        cls,
        *,
        company_id: str,
        namespace: str,
        source_page_id: str,
        links: list[Self],
    ) -> None:
        async with atomic(using="wiki"):
            _ = await cls.objects.filter(
                company_id=company_id,
                namespace=namespace,
                source_page_id=source_page_id,
            ).delete()
            for link in links:
                _ = await cls.objects.create(instance=link)

    @classmethod
    async def list_for_target(
        cls,
        company_id: str,
        target_kind: WikiLinkTargetKind,
        target_id: str,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            target_kind=target_kind,
            target_id=target_id,
        ).all()
