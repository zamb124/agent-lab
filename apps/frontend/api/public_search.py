"""Публичный session endpoint для Humanitec Search."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import ClassVar
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.frontend.api.public_session_security import (
    enforce_public_session_issue_rate_limit,
    new_embed_session_id,
)
from apps.frontend.dependencies import ContainerDep
from apps.frontend.services.public_search_bootstrap import (
    PUBLIC_SEARCH_SPEC_BY_MODE,
    ensure_public_search_embed_configs,
)
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID, SYSTEM_COMPANY_SUBDOMAIN
from core.logging import get_logger
from core.models.embed_models import EmbedStatus
from core.search import PUBLIC_SEARCH_FLOW_ID, PUBLIC_SEARCH_SESSION_ISSUER, PublicSearchMode
from core.utils.tokens import get_token_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/public/search", tags=["public_search"])


class PublicSearchSessionRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: PublicSearchMode = "quick"
    origin: str = Field(default="", description="window.location.origin")
    expires_in_seconds: int = Field(default=300, ge=60, le=900)


class PublicSearchSessionResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    token: str
    token_type: str
    expires_at: datetime
    embed_id: str
    flow_id: str
    branch_id: str


def _normalize_origin(raw: str) -> str:
    value = raw.strip()
    if value == "":
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


def _referer_path_allowed(referer: str) -> bool:
    if referer.strip() == "":
        return False
    path = urlparse(referer.strip()).path
    if path in {"", "/", "/frontend"}:
        return True
    return path.startswith("/search") or path.startswith("/frontend/search")


@router.post("/session", response_model=PublicSearchSessionResponse)
async def issue_public_search_session(
    body: PublicSearchSessionRequest,
    request: Request,
    container: ContainerDep,
) -> PublicSearchSessionResponse:
    if body.mode not in PUBLIC_SEARCH_SPEC_BY_MODE:
        raise HTTPException(status_code=400, detail="Неподдерживаемый режим поиска")

    configs = await ensure_public_search_embed_configs(container)
    config = configs[body.mode]

    referer = request.headers.get("referer", "")
    if not _referer_path_allowed(referer):
        raise HTTPException(status_code=403, detail="Поиск доступен только с публичной страницы поиска")

    origin = _normalize_origin(body.origin)
    referer_origin = _origin_from_referer(referer)
    if origin == "" and referer_origin != "":
        origin = referer_origin
    if origin != "" and referer_origin != "" and origin != referer_origin:
        raise HTTPException(status_code=403, detail="origin не совпадает со страницей поиска")
    if origin == "":
        raise HTTPException(status_code=403, detail="origin обязателен для публичной сессии поиска")

    await enforce_public_session_issue_rate_limit(
        redis_client=container.redis_client,
        request=request,
        scope="public_search",
    )

    mapping = await container.embed_mapping_repository.get(config.embed_id)
    if mapping is None or mapping.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=404, detail="Виджет не найден")

    persisted_config = await container.embed_config_repository.get_for_company_identifier(
        SYSTEM_COMPANY_SUBDOMAIN,
        config.embed_id,
    )
    if persisted_config is None:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    if persisted_config.status != EmbedStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Виджет отключён")
    if persisted_config.flow_id != PUBLIC_SEARCH_FLOW_ID:
        raise HTTPException(status_code=500, detail="Конфигурация поиска повреждена")
    if persisted_config.branch_id != config.branch_id:
        raise HTTPException(status_code=500, detail="Конфигурация ветки поиска повреждена")

    guest_id = f"search_guest_{uuid.uuid4().hex}"
    embed_session_id = new_embed_session_id()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_seconds)
    _ = await ensure_persisted_runtime_user(
        container,
        user_id=guest_id,
        company_id=SYSTEM_COMPANY_ID,
        name="Search Guest",
        roles=["guest"],
        attributes={
            "kind": "embed_session_guest",
            "embed_id": persisted_config.embed_id,
            "embed_flow_id": persisted_config.flow_id,
            "embed_branch_id": persisted_config.branch_id,
            "issued_by": PUBLIC_SEARCH_SESSION_ISSUER,
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
            "embed_id": persisted_config.embed_id,
            "embed_flow_id": persisted_config.flow_id,
            "embed_branch_id": persisted_config.branch_id,
            "allowed_origin": origin,
            "issued_by": PUBLIC_SEARCH_SESSION_ISSUER,
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
        },
    )
    logger.info(
        "public_search_session_issued",
        embed_id=persisted_config.embed_id,
        flow_id=persisted_config.flow_id,
        branch_id=persisted_config.branch_id,
        origin=origin,
    )
    return PublicSearchSessionResponse(
        token=token,
        token_type="Bearer",
        expires_at=expires_at,
        embed_id=persisted_config.embed_id,
        flow_id=persisted_config.flow_id,
        branch_id=persisted_config.branch_id,
    )
