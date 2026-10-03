"""Чтение ``office.jwt_secret`` для верификации OnlyOffice editor JWT вне apps/office."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.config.loader import load_merged_config
from core.types import require_json_object


class _OfficeJwtBlock(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    jwt_secret: str = ""


class _OnlyOfficeJwtEnv(BaseSettings):
    """ENV ``OFFICE__JWT_SECRET``. JSON services.office сюда не входит."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="ignore",
    )

    office: _OfficeJwtBlock = Field(default_factory=_OfficeJwtBlock)


def resolve_onlyoffice_jwt_secret() -> str:
    """
    Секрет DS / editor JWT.

    ``OFFICE__JWT_SECRET`` имеет приоритет: ``load_merged_config`` вырезает
    ключи, перекрытые окружением, поэтому сырой JSON после merge не содержит
    ``jwt_secret``, когда переменная задана.
    """
    from_env = _OnlyOfficeJwtEnv().office.jwt_secret.strip()
    if from_env != "":
        return from_env

    merged = load_merged_config(service_name="office", silent=True)
    office_section = merged.get("office")
    if not isinstance(office_section, dict):
        raise ValueError("office config section is required for OnlyOffice JWT secret")
    office_object = require_json_object(office_section, "office")
    secret_raw = office_object.get("jwt_secret")
    if not isinstance(secret_raw, str) or not secret_raw.strip():
        raise ValueError("office.jwt_secret is required and must be non-empty")
    return secret_raw.strip()


__all__ = ["resolve_onlyoffice_jwt_secret"]
