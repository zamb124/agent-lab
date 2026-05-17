"""Модели Git-ресурсов для Sync API."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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

    id: str = Field(description="Внутренний идентификатор Git-ресурса.")
    provider: GitProvider = Field(description="Провайдер Git.")
    kind: GitResourceKind = Field(description="Тип Git-ресурса.")
    project_key: str = Field(description="Ключ/путь проекта в провайдере.")
    external_id: str = Field(description="Идентификатор ресурса у провайдера.")
    url: str = Field(description="Канонический URL ресурса.")
    extra: dict[str, Any] = Field(
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
    extra: dict[str, Any] | None = Field(
        default=None,
        description="Дополнительные метаданные ресурса.",
    )
