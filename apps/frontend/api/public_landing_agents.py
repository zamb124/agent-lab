"""
Публичный каталог демо-агентов для лендинга (компания system, embed с landing_visible).
"""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.frontend.api.public_session_security import (
    enforce_public_session_issue_rate_limit,
    new_embed_session_id,
)
from apps.frontend.dependencies import ContainerDep
from apps.frontend.services.landing_demo_seed import (
    ensure_system_landing_demo_embeds,
    public_landing_demo_card_url,
)
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.identity.landing_public_demo import LANDING_PUBLIC_EMBED_SESSION_ISSUER
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID, SYSTEM_COMPANY_SUBDOMAIN
from core.logging import get_logger
from core.models.embed_models import EmbedConfig, EmbedStatus
from core.utils.tokens import get_token_service

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
    show_reasoning: bool
    show_tool_calls: bool
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
        raise HTTPException(status_code=400, detail="origin должен быть HTTP(S) origin")
    return f"{parsed.scheme}://{parsed.netloc}"


def _origin_from_referer(referer: str) -> str:
    parsed = urlparse(referer.strip())
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


async def _effective_landing_card_image_url(
    container: ContainerDep,
    embed: EmbedConfig,
) -> str:
    demo_url = public_landing_demo_card_url(embed.embed_id)
    if demo_url is not None:
        return demo_url
    direct = (embed.landing_card_image_url or "").strip()
    if direct:
        return direct
    flow_repo = container.flows_flow_repository
    pair = await flow_repo.get_latest_by_flow_id_unscoped(embed.flow_id)
    if pair is None:
        return ""
    cfg, _company_identifier = pair
    return (cfg.store_card_image_url or "").strip()


async def _collect_landing_cards(
    container: ContainerDep,
    configs: list[EmbedConfig],
) -> list[PublicLandingAgentCard]:
    cards: list[PublicLandingAgentCard] = []
    for c in configs:
        if c.status != EmbedStatus.ACTIVE or not c.landing_visible:
            continue
        img = await _effective_landing_card_image_url(container, c)
        if not img:
            continue
        cards.append(
            PublicLandingAgentCard(
                embed_id=c.embed_id,
                name=c.name,
                flow_id=c.flow_id,
                branch_id=c.branch_id,
                assistant_title=c.assistant_title,
                greeting_message=c.greeting_message,
                landing_card_image_url=img,
                theme=c.theme,
                primary_color=c.primary_color,
                interface_locale=c.interface_locale,
                placeholder=c.placeholder,
                show_reasoning=c.show_reasoning,
                show_tool_calls=c.show_tool_calls,
                branding=c.branding,
                landing_sort_order=c.landing_sort_order,
                voice_enabled=c.voice_enabled,
                voice_default_on=c.voice_default_on,
            )
        )
    cards.sort(key=lambda x: (x.landing_sort_order, x.name))
    return cards


@router.get("", response_model=PublicLandingAgentsResponse)
async def list_public_landing_agents(container: ContainerDep) -> PublicLandingAgentsResponse:
    await ensure_system_landing_demo_embeds(container)
    repo = container.embed_config_repository
    configs = await repo.list_for_company_identifier(
        SYSTEM_COMPANY_SUBDOMAIN,
        limit=2000,
        offset=0,
    )
    cards = await _collect_landing_cards(container, configs)
    if not cards:
        await ensure_system_landing_demo_embeds(container)
        configs = await repo.list_for_company_identifier(
            SYSTEM_COMPANY_SUBDOMAIN,
            limit=2000,
            offset=0,
        )
        cards = await _collect_landing_cards(container, configs)
    return PublicLandingAgentsResponse(items=cards)


@router.post("/session", response_model=PublicLandingSessionResponse)
async def issue_public_landing_session(
    body: PublicLandingSessionRequest,
    request: Request,
    container: ContainerDep,
) -> PublicLandingSessionResponse:
    embed_id = body.embed_id.strip()
    mapping_repo = container.embed_mapping_repository
    mapping = await mapping_repo.get(embed_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="Виджет не найден")
    if mapping.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=404, detail="Виджет не найден")

    embed_repo = container.embed_config_repository
    config = await embed_repo.get_for_company_identifier(SYSTEM_COMPANY_SUBDOMAIN, embed_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    if config.status != EmbedStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Виджет отключён")
    if not config.landing_visible:
        raise HTTPException(status_code=403, detail="Виджет недоступен для публичного чата")
    img = await _effective_landing_card_image_url(container, config)
    if not img:
        raise HTTPException(status_code=403, detail="Виджет не опубликован в каталоге")

    origin = _normalize_origin(request.headers.get("origin", ""))
    referer_origin = _origin_from_referer(request.headers.get("referer", ""))
    if not origin and referer_origin:
        origin = referer_origin
    if origin and referer_origin and origin != referer_origin:
        raise HTTPException(status_code=403, detail="origin не совпадает со страницей каталога")
    if not origin:
        raise HTTPException(status_code=403, detail="origin обязателен для публичной сессии")

    await enforce_public_session_issue_rate_limit(
        redis_client=container.redis_client,
        request=request,
        scope="public_landing_agents",
    )

    guest_id = f"landing_guest_{uuid.uuid4().hex}"
    embed_session_id = new_embed_session_id()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_seconds)
    _ = await ensure_persisted_runtime_user(
        container,
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
