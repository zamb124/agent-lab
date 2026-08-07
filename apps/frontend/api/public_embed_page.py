"""Public first-party session issuance for EmbedConfig.presentation=page."""

from __future__ import annotations

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
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.logging import get_logger
from core.models.embed_models import EmbedStatus, resolve_embed_presentation
from core.utils.tokens import get_token_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/public/embed-page", tags=["public_embed_page"])

EMBED_PAGE_PUBLIC_SESSION_ISSUER = "frontend.embed_page_public"
_DEFAULT_TTL_SECONDS = 300


class EmbedPageSessionRequest(BaseModel):
    embed_id: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    expires_in_seconds: int = Field(default=_DEFAULT_TTL_SECONDS, ge=60, le=900)


class EmbedPageSessionResponse(BaseModel):
    token: str
    token_type: str
    expires_at: datetime
    flow_id: str
    branch_id: str
    flows_base_url: str
    theme: str
    interface_locale: str


def _normalize_origin(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="origin must be an absolute http(s) URL")
    return f"{parsed.scheme}://{parsed.netloc}"


@router.post("/session", response_model=EmbedPageSessionResponse)
async def issue_embed_page_session(
    body: EmbedPageSessionRequest,
    request: Request,
    container: ContainerDep,
) -> EmbedPageSessionResponse:
    embed_id = body.embed_id.strip()
    origin = _normalize_origin(body.origin)
    if not origin:
        raise HTTPException(status_code=400, detail="origin обязателен")

    mapping = await container.embed_mapping_repository.get(embed_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="Виджет не найден")

    company = await container.company_repository.get(mapping.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Виджет не найден")

    company_identifier = (company.subdomain or "").strip() or company.company_id
    config = await container.embed_config_repository.get_for_company_identifier(
        company_identifier,
        embed_id,
    )
    if config is None:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    if config.preview_share_link:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    if config.status != EmbedStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Виджет отключён")

    presentation = resolve_embed_presentation(
        presentation=config.presentation,
        position=config.position,
    )
    if presentation != "page":
        raise HTTPException(
            status_code=403,
            detail="Полноэкранная страница доступна только при presentation=page",
        )

    page_origin = f"{request.url.scheme}://{request.url.netloc}"
    if origin != page_origin:
        raise HTTPException(
            status_code=403,
            detail="origin должен совпадать с first-party host страницы",
        )

    await enforce_public_session_issue_rate_limit(
        redis_client=container.redis_client,
        request=request,
        scope="public_embed_page",
    )

    guest_id = f"embed_page_guest_{uuid.uuid4().hex}"
    embed_session_id = new_embed_session_id()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_seconds)
    _ = await ensure_persisted_runtime_user(
        container,
        user_id=guest_id,
        company_id=company.company_id,
        name="Embed Page Guest",
        roles=["guest"],
        attributes={
            "kind": "embed_session_guest",
            "embed_id": embed_id,
            "embed_flow_id": config.flow_id,
            "embed_branch_id": config.branch_id,
            "issued_by": EMBED_PAGE_PUBLIC_SESSION_ISSUER,
            "token_expires_at": expires_at.isoformat(),
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
        },
    )
    token = get_token_service().create_embed_session_token(
        user_id=guest_id,
        company_id=company.company_id,
        roles=["guest"],
        expires_in=body.expires_in_seconds,
        metadata={
            "embed_id": embed_id,
            "embed_flow_id": config.flow_id,
            "embed_branch_id": config.branch_id,
            "allowed_origin": origin,
            "issued_by": EMBED_PAGE_PUBLIC_SESSION_ISSUER,
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
        },
    )
    flows_base_url = f"{page_origin}/flows"
    logger.info(
        "public_embed_page_session_issued",
        embed_id=embed_id,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
        company_id=company.company_id,
    )
    return EmbedPageSessionResponse(
        token=token,
        token_type="Bearer",
        expires_at=expires_at,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
        flows_base_url=flows_base_url,
        theme=config.theme,
        interface_locale=config.interface_locale,
    )
