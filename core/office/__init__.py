"""Office-related platform contracts shared across services (OnlyOffice AI, …)."""

from core.office.ai_settings import (
    IMAGE_AUTO_MODEL_ID,
    LARA_DOCUMENTS_MODEL_ID,
    LARA_MODEL_PREFIX,
    ONLYOFFICE_AI_ACTION_KEYS,
    ONLYOFFICE_AI_PLUGIN_GUID,
    PLATFORM_AUTO_MODEL_ID,
    build_onlyoffice_ai_settings,
    parse_lara_branch_model_id,
)
from core.office.jwt_secret import resolve_onlyoffice_jwt_secret
from core.office.platform_ai_claims import (
    OFFICE_AI_JWT_CLAIM_KEY,
    OfficePlatformAiClaims,
    extract_office_platform_ai_claims,
)

__all__ = [
    "IMAGE_AUTO_MODEL_ID",
    "LARA_DOCUMENTS_MODEL_ID",
    "LARA_MODEL_PREFIX",
    "OFFICE_AI_JWT_CLAIM_KEY",
    "ONLYOFFICE_AI_ACTION_KEYS",
    "ONLYOFFICE_AI_PLUGIN_GUID",
    "OfficePlatformAiClaims",
    "PLATFORM_AUTO_MODEL_ID",
    "build_onlyoffice_ai_settings",
    "extract_office_platform_ai_claims",
    "parse_lara_branch_model_id",
    "resolve_onlyoffice_jwt_secret",
]
