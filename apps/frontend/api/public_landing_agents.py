"""
Публичный каталог демо-агентов для лендинга (компания system, embed с landing_visible).
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.frontend.dependencies import ContainerDep
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID, SYSTEM_COMPANY_SUBDOMAIN
from core.logging import get_logger
from core.models.embed_models import EmbedStatus
from core.utils.tokens import get_token_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/public/landing-agents", tags=["public_landing"])


class PublicLandingAgentCard(BaseModel):
    embed_id: str
    name: str
    flow_id: str
    branch_id: str
    assistant_title: Optional[str]
    greeting_message: Optional[str]
    landing_card_image_url: str
    theme: str
    primary_color: str
    interface_locale: str
    placeholder: str
    show_reasoning: bool
    show_tool_calls: bool
    branding: bool
    landing_sort_order: int


class PublicLandingAgentsResponse(BaseModel):
    items: List[PublicLandingAgentCard]


class PublicLandingSessionRequest(BaseModel):
    embed_id: str = Field(min_length=1)
    expires_in_seconds: int = Field(default=300, ge=60, le=900)


class PublicLandingSessionResponse(BaseModel):
    token: str
    token_type: str
    expires_at: datetime
    flow_id: str
    branch_id: str


@router.get("", response_model=PublicLandingAgentsResponse)
async def list_public_landing_agents(container: ContainerDep) -> PublicLandingAgentsResponse:
    repo = container.embed_config_repository
    configs = await repo.list_for_company_identifier(
        SYSTEM_COMPANY_SUBDOMAIN,
        limit=2000,
        offset=0,
    )
    cards: List[PublicLandingAgentCard] = []
    for c in configs:
        if c.status != EmbedStatus.ACTIVE or not c.landing_visible:
            continue
        img = (c.landing_card_image_url or "").strip()
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
            )
        )
    cards.sort(key=lambda x: (x.landing_sort_order, x.name))
    return PublicLandingAgentsResponse(items=cards)


@router.post("/session", response_model=PublicLandingSessionResponse)
async def issue_public_landing_session(
    body: PublicLandingSessionRequest,
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
    img = (config.landing_card_image_url or "").strip()
    if not img:
        raise HTTPException(status_code=403, detail="Виджет не опубликован в каталоге")

    guest_id = f"landing_guest_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_seconds)
    token = get_token_service().create_embed_session_token(
        user_id=guest_id,
        company_id=SYSTEM_COMPANY_ID,
        roles=["guest"],
        expires_in=body.expires_in_seconds,
        metadata={
            "embed_id": embed_id,
            "embed_flow_id": config.flow_id,
            "embed_branch_id": config.branch_id,
            "allowed_origin": "",
            "issued_by": "frontend.public_landing_agents",
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
