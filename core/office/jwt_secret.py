"""Чтение ``office.jwt_secret`` для верификации OnlyOffice editor JWT вне apps/office."""

from __future__ import annotations

import os

from core.config.loader import load_merged_config
from core.types import require_json_object


def resolve_onlyoffice_jwt_secret() -> str:
    """
    Секрет DS / editor JWT из ENV или конфига сервиса office.

    ENV ``OFFICE__JWT_SECRET`` имеет приоритет: ``load_merged_config`` вырезает
    ключи, перекрытые окружением (канон Pydantic Settings), поэтому сырой JSON
    после merge не содержит ``jwt_secret`` при заданном ENV.
    """
    env_secret = os.environ.get("OFFICE__JWT_SECRET")
    if env_secret is not None and env_secret.strip():
        return env_secret.strip()

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
