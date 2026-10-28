"""
Публичный каталог демо-агентов для лендинга (компания system, embed с landing_visible).
"""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from apps.flows.src.models import FlowConfig
from apps.frontend.api.public_session_security import (
    enforce_public_session_issue_rate_limit,
    new_embed_session_id,
)
from apps.frontend.di import Di
from apps.frontend.services.landing_demo_seed import (
    ensure_system_landing_demo_embeds,
    public_landing_demo_card_url,
)
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.identity.landing_public_demo import LANDING_PUBLIC_EMBED_SESSION_ISSUER
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.logging import get_logger
from core.models.embed_models import EmbedConfig, EmbedStatus
from core.models.identity_models import SYSTEM_COMPANY_ID
from core.utils.tokens import get_token_service
from core.websocket import WsCommandError

logger = get_logger(__name__)

router = APIRouter(prefix="/api/public/landing-agents", tags=["public_landing"])


class PublicLandingAgentCard(BaseModel):
    embed_id: str
    name: str
    flow_id: str
    branch_id: str
    assistant_title: str | None
    greeting_message: str | None
    landing_card_image_url: str
    theme: str
    primary_color: str
    interface_locale: str
    placeholder: str
    branding: bool
    landing_sort_order: int
    voice_enabled: bool
    voice_default_on: bool


class PublicLandingAgentsResponse(BaseModel):
    items: list[PublicLandingAgentCard]


class PublicLandingSessionRequest(BaseModel):
    embed_id: str = Field(min_length=1)
    expires_in_seconds: int = Field(default=300, ge=60, le=900)


class PublicLandingSessionResponse(BaseModel):
    token: str
    token_type: str
    expires_at: datetime
    flow_id: str
    branch_id: str


def _normalize_origin(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WsCommandError("ws_invalid_payload", "origin must be an HTTP(S) origin", error_code="ws_invalid_payload")
    return f"{parsed.scheme}://{parsed.netloc}"


def _origin_from_referer(referer: str) -> str:
    parsed = urlparse(referer.strip())
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


async def _landing_flow_config(
    company_id: str,
    flow_id: str,
) -> FlowConfig | None:
    return await FlowConfig.current_for_company(company_id, flow_id)


def _effective_landing_card_image_url(
    embed: EmbedConfig,
    flow_cfg: FlowConfig | None,
) -> str:
    demo_url = public_landing_demo_card_url(embed.embed_id)
    if demo_url is not None:
        return demo_url
    direct = (embed.landing_card_image_url or "").strip()
    if direct:
        return direct
    if flow_cfg is None:
        return ""
    return (flow_cfg.store_card_image_url or "").strip()


async def _collect_landing_cards(
    configs: list[EmbedConfig],
) -> list[PublicLandingAgentCard]:
    cards: list[PublicLandingAgentCard] = []
    for c in configs:
        if c.status != EmbedStatus.ACTIVE or not c.landing_visible:
            continue
        flow_cfg = await _landing_flow_config(c.company_id, c.flow_id)
        img = _effective_landing_card_image_url(c, flow_cfg)
        if not img:
            continue
        greeting_message: str | None = None
        if flow_cfg is not None:
            document = flow_cfg.interface_for_branch(c.branch_id).with_embed_overrides(
                conversation=c.conversation,
                start_page_id=c.start_page_id,
            )
            greeting = document.conversation_settings().greeting
            greeting_message = greeting if greeting != "" else None
        cards.append(
            PublicLandingAgentCard(
                embed_id=c.embed_id,
                name=c.name,
                flow_id=c.flow_id,
                branch_id=c.branch_id,
                assistant_title=c.assistant_title,
                greeting_message=greeting_message,
                landing_card_image_url=img,
                theme=c.theme,
                primary_color=c.primary_color,
                interface_locale=c.interface_locale,
                placeholder=c.placeholder,
                branding=c.branding,
                landing_sort_order=c.landing_sort_order,
                voice_enabled=c.voice_enabled,
                voice_default_on=c.voice_default_on,
            )
        )
    cards.sort(key=lambda x: (x.landing_sort_order, x.name))
    return cards


@router.get("", response_model=PublicLandingAgentsResponse)
async def list_public_landing_agents() -> PublicLandingAgentsResponse:
    await ensure_system_landing_demo_embeds()
    configs = await EmbedConfig.list_unordered_window_for_company(
        SYSTEM_COMPANY_ID,
        limit=2000,
        offset=0,
    )
    cards = await _collect_landing_cards(configs)
    if not cards:
        await ensure_system_landing_demo_embeds()
        configs = await EmbedConfig.list_unordered_window_for_company(
            SYSTEM_COMPANY_ID,
            limit=2000,
            offset=0,
        )
        cards = await _collect_landing_cards(configs)
    return PublicLandingAgentsResponse(items=cards)


@router.post("/session", response_model=PublicLandingSessionResponse)
async def issue_public_landing_session(
    body: PublicLandingSessionRequest,
    request: Request,
    di: Di,
) -> PublicLandingSessionResponse:
    embed_id = body.embed_id.strip()
    config = await EmbedConfig.get(embed_id)
    if config is None or config.company_id != SYSTEM_COMPANY_ID:
        raise WsCommandError("not_found", "Configuration not found", error_code="not_found")
    if config.status != EmbedStatus.ACTIVE:
        raise WsCommandError("forbidden", "Widget is disabled", error_code="forbidden")
    if not config.landing_visible:
        raise WsCommandError("forbidden", "Widget is not available for public chat", error_code="forbidden")
    session_flow_cfg = await _landing_flow_config(config.company_id, config.flow_id)
    img = _effective_landing_card_image_url(config, session_flow_cfg)
    if not img:
        raise WsCommandError("forbidden", "Widget is not published in the catalog", error_code="forbidden")

    origin = _normalize_origin(request.headers.get("origin", ""))
    referer_origin = _origin_from_referer(request.headers.get("referer", ""))
    if not origin and referer_origin:
        origin = referer_origin
    if origin and referer_origin and origin != referer_origin:
        raise WsCommandError("forbidden", "origin does not match the catalog page", error_code="forbidden")
    if not origin:
        raise WsCommandError("forbidden", "origin is required for a public session", error_code="forbidden")

    await enforce_public_session_issue_rate_limit(
        redis_client=di.redis_client,
        request=request,
        scope="public_landing_agents",
    )

    guest_id = f"landing_guest_{uuid.uuid4().hex}"
    embed_session_id = new_embed_session_id()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_seconds)
    _ = await ensure_persisted_runtime_user(
        di.authz_service,
        user_id=guest_id,
        company_id=SYSTEM_COMPANY_ID,
        name="Landing Guest",
        roles=["guest"],
        attributes={
            "kind": "embed_session_guest",
            "embed_id": embed_id,
            "embed_flow_id": config.flow_id,
            "embed_branch_id": config.branch_id,
            "issued_by": LANDING_PUBLIC_EMBED_SESSION_ISSUER,
            "token_expires_at": expires_at.isoformat(),
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
        },
    )
    token = get_token_service().create_embed_session_token(
        user_id=guest_id,
        company_id=SYSTEM_COMPANY_ID,
        roles=["guest"],
        expires_in=body.expires_in_seconds,
        metadata={
            "embed_id": embed_id,
            "embed_flow_id": config.flow_id,
            "embed_branch_id": config.branch_id,
            "allowed_origin": origin,
            "issued_by": LANDING_PUBLIC_EMBED_SESSION_ISSUER,
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
        },
    )
    logger.info(
        "public_landing_session_issued",
        embed_id=embed_id,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
    )
    return PublicLandingSessionResponse(
        token=token,
        token_type="Bearer",
        expires_at=expires_at,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
    )
