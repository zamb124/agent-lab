"""Git-ресурс Sync: таблица и тела команд."""

from __future__ import annotations

from enum import Enum
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index
from pydantic import BaseModel, Field

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class GitResourceRef(PlatformModel):
    """Строка ``sync_git_resource_refs``, алиас ``sync``, ``__global_model__``.

    Ответ API — ``GitResourceRefRead``: там enum провайдера и вида, без ``company_id``.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_git_resource_refs"
        indexes: list[Index] = [
            Index(["company_id"]),
            Index(["provider", "kind"]),
        ]

    git_ref_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    provider: str = DbField(max_length=32)
    kind: str = DbField(max_length=32)
    project_key: str = DbField(max_length=255)
    external_id: str = DbField(max_length=255)
    url: str = DbField(db_type="TEXT")
    extra: JsonObject = DbField(default_factory=dict, db_type="JSONB")


class GitProvider(str, Enum):
    """Поддерживаемые Git-провайдеры."""

    GITLAB = "gitlab"
    GITHUB = "github"
    GITEA = "gitea"
    BITBUCKET = "bitbucket"


class GitResourceKind(str, Enum):
    """Тип Git-ресурса."""

    REPO = "repo"
    MERGE_REQUEST = "merge_request"
    PULL_REQUEST = "pull_request"
    COMMIT = "commit"
    FILE_DIFF = "file_diff"
    FILE = "file"


class GitResourceRefRead(BaseModel):
    """Нормализованный Git-ресурс, возвращаемый из API."""

    git_ref_id: str = Field(description="Внутренний идентификатор Git-ресурса.")
    provider: GitProvider = Field(description="Провайдер Git.")
    kind: GitResourceKind = Field(description="Тип Git-ресурса.")
    project_key: str = Field(description="Ключ/путь проекта в провайдере.")
    external_id: str = Field(description="Идентификатор ресурса у провайдера.")
    url: str = Field(description="Канонический URL ресурса.")
    extra: JsonObject = Field(
        default_factory=dict,
        description="Дополнительные метаданные ресурса.",
    )


class GitResourceRefCreate(BaseModel):
    """Данные для создания/обновления Git-ресурса."""

    provider: GitProvider = Field(description="Провайдер Git.")
    kind: GitResourceKind = Field(description="Тип Git-ресурса.")
    project_key: str = Field(description="Ключ/путь проекта в провайдере.")
    external_id: str = Field(description="Идентификатор ресурса у провайдера.")
    url: str = Field(description="Канонический URL ресурса.")
    extra: JsonObject | None = Field(
        default=None,
        description="Дополнительные метаданные ресурса.",
    )
