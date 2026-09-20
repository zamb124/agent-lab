"""Контракты каталога LLM-провайдеров и моделей редактора flows."""

from __future__ import annotations

from typing import Literal

from core.models.base import StrictBaseModel


class RegistryProviderOption(StrictBaseModel):
    value: str
    label: str
    kind: Literal["custom", "virtual"]
    custom_id: str | None = None


class RegistryCatalogPayload(StrictBaseModel):
    capability: str | None = None
    provider: str | None = None
