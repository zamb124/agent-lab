"""Таблица wiki."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class WikiComment(PlatformModel):
    """Комментарий к странице. Таблица ``wiki_comments``."""

    __database_alias__: ClassVar[str | None] = "wiki"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "wiki_comments"
        indexes: list[Index] = [
            Index(["company_id", "namespace", "wiki_page_id", "created_at"]),
        ]

    wiki_comment_id: str = DbField(db_pk=True, max_length=64)
    wiki_page_id: str = DbField(max_length=64)
    company_id: str = DbField(max_length=100)
    namespace: str = DbField(max_length=100)
    author_user_id: str = DbField(max_length=100)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    parent_comment_id: str | None = DbField(default=None, max_length=64)
    body_markdown: str = DbField(default="", db_type="TEXT")
    anchor_text: str = DbField(default="", db_type="TEXT")
    resolved_at: datetime | None = DbField(default=None)
    resolved_by_user_id: str | None = DbField(default=None, max_length=100)

    @classmethod
    async def list_comments(
        cls,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
    ) -> list[Self]:
        return await (
            cls.objects.filter(
                company_id=company_id,
                namespace=namespace,
                wiki_page_id=wiki_page_id,
            )
            .order_by("created_at")
            .all()
        )

    @classmethod
    async def create_comment(cls, comment: Self) -> Self:
        return await cls.objects.create(instance=comment)

    @classmethod
    async def get_comment(
        cls,
        company_id: str,
        namespace: str,
        wiki_comment_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_comment_id=wiki_comment_id,
        ).get_or_none()

    @classmethod
    async def delete_comment(
        cls,
        company_id: str,
        namespace: str,
        wiki_comment_id: str,
    ) -> int:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_comment_id=wiki_comment_id,
        ).delete()
