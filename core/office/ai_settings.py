"""
Канон OnlyOffice AI plugin ``aiSettings`` (Document Server local.json).

CapabilitiesUI (sdkjs-plugins AI base.js):
  Chat=0x01, Image=0x02, Vision=0x80
Actions (AI.ActionType / docs): Chat, Summarization, Translation, TextAnalyze,
ImageGeneration, OCR, Vision.
"""

from __future__ import annotations

from typing import Final

from core.types import JsonObject

ONLYOFFICE_AI_PLUGIN_GUID: Final[str] = "asc.{9DC93CDB-B576-4F0C-B55E-FCC9C48DD007}"

# Browser Origin плагина AI (CDN + DS host). flows CORS обязан их принимать —
# иначе fetch на /agent/llm/** блокируется до proxy и UI показывает «Ошибка: [provider]».
ONLYOFFICE_AI_BROWSER_CORS_ORIGINS: Final[tuple[str, ...]] = (
    "https://onlyoffice.github.io",
    "https://onlyoffice-plugins.github.io",
    "https://onlyoffice.linnex.io",
    "https://onlyoffice.humanitec.ru",
)

ONLYOFFICE_AI_CAPABILITY_CHAT: Final[int] = 0x01
ONLYOFFICE_AI_CAPABILITY_IMAGE: Final[int] = 0x02
ONLYOFFICE_AI_CAPABILITY_VISION: Final[int] = 0x80
ONLYOFFICE_AI_CAPABILITY_CHAT_VISION: Final[int] = (
    ONLYOFFICE_AI_CAPABILITY_CHAT | ONLYOFFICE_AI_CAPABILITY_VISION
)

# OpenAI Endpoints.Types.v1 из AI plugin (Chat_Completions=0x01, Images_Generations=0x11)
_OO_ENDPOINT_CHAT_COMPLETIONS: Final[int] = 0x01
_OO_ENDPOINT_IMAGES_GENERATIONS: Final[int] = 0x11

LARA_MODEL_PREFIX: Final[str] = "lara:"
IMAGE_AUTO_MODEL_ID: Final[str] = "image-auto"
PLATFORM_AUTO_MODEL_ID: Final[str] = "auto"
LARA_DOCUMENTS_MODEL_ID: Final[str] = "lara:documents"

ONLYOFFICE_AI_ACTION_KEYS: Final[tuple[str, ...]] = (
    "Chat",
    "Summarization",
    "Translation",
    "TextAnalyze",
    "OCR",
    "Vision",
    "ImageGeneration",
)


def parse_lara_branch_model_id(model_id: str) -> str | None:
    """``lara:<branch_id>`` → branch_id; иначе None."""
    normalized = model_id.strip()
    if not normalized.startswith(LARA_MODEL_PREFIX):
        return None
    branch_id = normalized[len(LARA_MODEL_PREFIX) :].strip()
    if not branch_id:
        return None
    return branch_id


def build_onlyoffice_ai_settings(
    *,
    llm_api_base_url: str,
    proxy_url: str,
    provider_display_name: str,
    allowed_cors_origins: list[str],
) -> JsonObject:
    """
    Полный ``aiSettings`` для Document Server.

    ``llm_api_base_url`` — origin+path без ``/v1`` (плагин добавит addon ``v1``),
    например ``https://host/flows/api/v1/agent/llm``.
    """
    base = llm_api_base_url.rstrip("/")
    if base.endswith("/v1"):
        raise ValueError("llm_api_base_url must not include trailing /v1 (addon=v1)")
    proxy = proxy_url.strip()
    if not proxy:
        raise ValueError("proxy_url is required")
    name = provider_display_name.strip()
    if not name:
        raise ValueError("provider_display_name is required")

    cors = [origin.strip() for origin in allowed_cors_origins if origin.strip()]
    if not cors:
        raise ValueError("allowed_cors_origins must be non-empty")

    return {
        "version": 4,
        "actionsOverride": True,
        "timeout": "5m",
        "proxy": proxy,
        "allowedCorsOrigins": cors,
        "providers": {
            "platform": {
                "name": name,
                "url": base,
                "key": "",
                "addon": "v1",
                "models": [
                    {
                        "id": LARA_DOCUMENTS_MODEL_ID,
                        "name": LARA_DOCUMENTS_MODEL_ID,
                        "endpoints": [_OO_ENDPOINT_CHAT_COMPLETIONS],
                        "options": {},
                    },
                    {
                        "id": PLATFORM_AUTO_MODEL_ID,
                        "name": PLATFORM_AUTO_MODEL_ID,
                        "endpoints": [_OO_ENDPOINT_CHAT_COMPLETIONS],
                        "options": {},
                    },
                    {
                        "id": IMAGE_AUTO_MODEL_ID,
                        "name": IMAGE_AUTO_MODEL_ID,
                        "endpoints": [_OO_ENDPOINT_IMAGES_GENERATIONS],
                        "options": {},
                    },
                ],
            }
        },
        "models": [
            {
                "id": LARA_DOCUMENTS_MODEL_ID,
                "name": "Lara Documents",
                "provider": "platform",
                "capabilities": ONLYOFFICE_AI_CAPABILITY_CHAT,
            },
            {
                "id": PLATFORM_AUTO_MODEL_ID,
                "name": f"{name} Auto",
                "provider": "platform",
                "capabilities": ONLYOFFICE_AI_CAPABILITY_CHAT_VISION,
            },
            {
                "id": IMAGE_AUTO_MODEL_ID,
                "name": f"{name} Image",
                "provider": "platform",
                "capabilities": ONLYOFFICE_AI_CAPABILITY_IMAGE,
            },
        ],
        "actions": {
            "Chat": {"model": LARA_DOCUMENTS_MODEL_ID},
            "Summarization": {"model": PLATFORM_AUTO_MODEL_ID},
            "Translation": {"model": PLATFORM_AUTO_MODEL_ID},
            "TextAnalyze": {"model": PLATFORM_AUTO_MODEL_ID},
            "OCR": {"model": PLATFORM_AUTO_MODEL_ID},
            "Vision": {"model": PLATFORM_AUTO_MODEL_ID},
            "ImageGeneration": {"model": IMAGE_AUTO_MODEL_ID},
        },
    }


__all__ = [
    "IMAGE_AUTO_MODEL_ID",
    "LARA_DOCUMENTS_MODEL_ID",
    "LARA_MODEL_PREFIX",
    "ONLYOFFICE_AI_ACTION_KEYS",
    "ONLYOFFICE_AI_BROWSER_CORS_ORIGINS",
    "ONLYOFFICE_AI_CAPABILITY_CHAT",
    "ONLYOFFICE_AI_CAPABILITY_CHAT_VISION",
    "ONLYOFFICE_AI_CAPABILITY_IMAGE",
    "ONLYOFFICE_AI_CAPABILITY_VISION",
    "ONLYOFFICE_AI_PLUGIN_GUID",
    "PLATFORM_AUTO_MODEL_ID",
    "build_onlyoffice_ai_settings",
    "parse_lara_branch_model_id",
]
