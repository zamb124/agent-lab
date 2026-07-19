"""
Claims ``platformAi`` внутри OnlyOffice editor JWT.

Document Server отдаёт весь editor JWT в ``Asc.plugin.info.jwt``;
AI plugin шлёт его как ``Authorization: Bearer`` на ``aiSettings.proxy``.
"""

from __future__ import annotations

from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.types import JsonObject, require_json_object

OFFICE_AI_JWT_CLAIM_KEY: Final[str] = "platformAi"
OFFICE_AI_TOKEN_TYP: Final[str] = "office_ai"


class OfficePlatformAiClaims(BaseModel):
    """Контекст компании/документа для LLM proxy из editor JWT."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    typ: Literal["office_ai"] = OFFICE_AI_TOKEN_TYP
    company_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    file_id: str = Field(min_length=1)
    viewer_scope: Literal["catalog", "file"] = "catalog"


def extract_office_platform_ai_claims(editor_jwt_payload: JsonObject) -> OfficePlatformAiClaims:
    raw = editor_jwt_payload.get(OFFICE_AI_JWT_CLAIM_KEY)
    if raw is None:
        raise ValueError(f"{OFFICE_AI_JWT_CLAIM_KEY} claim is required in OnlyOffice editor JWT")
    return OfficePlatformAiClaims.model_validate(
        require_json_object(raw, OFFICE_AI_JWT_CLAIM_KEY),
    )


__all__ = [
    "OFFICE_AI_JWT_CLAIM_KEY",
    "OFFICE_AI_TOKEN_TYP",
    "OfficePlatformAiClaims",
    "extract_office_platform_ai_claims",
]
