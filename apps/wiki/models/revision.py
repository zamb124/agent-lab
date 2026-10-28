"""Таблица wiki."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.wiki.content.prosemirror import ProseMirrorNode
from core.models.platform_model import PlatformModel


class WikiRevision(PlatformModel):
    """Снимок страницы. Таблица ``wiki_revisions``."""

    __database_alias__: ClassVar[str | None] = "wiki"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "wiki_revisions"
        indexes: list[Index] = [
            Index(["company_id", "namespace", "wiki_page_id", "created_at"]),
        ]

    wiki_revision_id: str = DbField(db_pk=True, max_length=64)
    wiki_page_id: str = DbField(max_length=64)
    company_id: str = DbField(max_length=100)
    namespace: str = DbField(max_length=100)
    content: ProseMirrorNode = DbField(db_type="JSONB")
    author_user_id: str = DbField(max_length=100)
    created_at: datetime = DbField()
    title: str = DbField(default="", db_type="TEXT")
    text_markdown: str = DbField(default="", db_type="TEXT")

    @classmethod
    async def create(cls, revision: Self) -> Self:
        return await cls.objects.create(instance=revision)

    @classmethod
    async def list_recent_for_page(
        cls,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
        *,
        limit: int,
    ) -> list[Self]:
        return await (
            cls.objects.filter(
                company_id=company_id,
                namespace=namespace,
                wiki_page_id=wiki_page_id,
            )
            .order_by("-created_at")
            .limit(limit)
            .all()
        )

    @classmethod
    async def in_namespace(
        cls,
        company_id: str,
        namespace: str,
        wiki_revision_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_revision_id=wiki_revision_id,
        ).get_or_none()
