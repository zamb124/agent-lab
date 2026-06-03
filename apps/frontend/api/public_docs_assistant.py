"""Публичный session-эндпоинт для embed documentation assistant."""

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
from core.docs.assistant import (
    DOCS_ASSISTANT_BRANCH_ID,
    DOCS_ASSISTANT_EMBED_ID,
    DOCS_ASSISTANT_FLOW_ID,
    DOCS_ASSISTANT_SESSION_ISSUER,
)
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID, SYSTEM_COMPANY_SUBDOMAIN
from core.logging import get_logger
from core.models.embed_models import EmbedStatus
from core.utils.tokens import get_token_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/public/docs-assistant", tags=["public_docs_assistant"])


class PublicDocsAssistantSessionRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    embed_id: str = Field(default=DOCS_ASSISTANT_EMBED_ID, min_length=1)
    origin: str = Field(default="", description="window.location.origin")
    expires_in_seconds: int = Field(default=300, ge=60, le=900)


class PublicDocsAssistantSessionResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

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


def _referer_path_allowed(referer: str) -> bool:
    if not referer.strip():
        return False
    path = urlparse(referer.strip()).path or ""
    return path.startswith("/documentation") or path.startswith("/frontend/documentation")


@router.post("/session", response_model=PublicDocsAssistantSessionResponse)
async def issue_public_docs_assistant_session(
    body: PublicDocsAssistantSessionRequest,
    request: Request,
    container: ContainerDep,
) -> PublicDocsAssistantSessionResponse:
    embed_id = body.embed_id.strip()
    if embed_id != DOCS_ASSISTANT_EMBED_ID:
        raise HTTPException(status_code=404, detail="Виджет не найден")

    referer = request.headers.get("referer", "")
    if not _referer_path_allowed(referer):
        raise HTTPException(status_code=403, detail="Виджет доступен только из документации")

    origin = _normalize_origin(body.origin or request.headers.get("origin", ""))
    referer_origin = _origin_from_referer(referer)
    if not origin and referer_origin:
        origin = referer_origin
    if origin and referer_origin and origin != referer_origin:
        raise HTTPException(status_code=403, detail="origin не совпадает с документацией")
    if not origin:
        raise HTTPException(status_code=403, detail="origin обязателен для публичной сессии документации")

    await enforce_public_session_issue_rate_limit(
        redis_client=container.redis_client,
        request=request,
        scope="public_docs_assistant",
    )

    mapping = await container.embed_mapping_repository.get(embed_id)
    if mapping is None or mapping.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=404, detail="Виджет не найден")

    config = await container.embed_config_repository.get_for_company_identifier(
        SYSTEM_COMPANY_SUBDOMAIN,
        embed_id,
    )
    if config is None:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    if config.status != EmbedStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Виджет отключён")
    if config.flow_id != DOCS_ASSISTANT_FLOW_ID or config.branch_id != DOCS_ASSISTANT_BRANCH_ID:
        raise HTTPException(status_code=500, detail="Конфигурация виджета повреждена")

    guest_id = f"docs_guest_{uuid.uuid4().hex}"
    embed_session_id = new_embed_session_id()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_seconds)
    _ = await ensure_persisted_runtime_user(
        container,
        user_id=guest_id,
        company_id=SYSTEM_COMPANY_ID,
        name="Documentation Guest",
        roles=["guest"],
        attributes={
            "kind": "embed_session_guest",
            "embed_id": embed_id,
            "embed_flow_id": config.flow_id,
            "embed_branch_id": config.branch_id,
            "issued_by": DOCS_ASSISTANT_SESSION_ISSUER,
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
            "issued_by": DOCS_ASSISTANT_SESSION_ISSUER,
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
        },
    )
    logger.info(
        "public_docs_assistant_session_issued",
        embed_id=embed_id,
        origin=origin,
    )
    return PublicDocsAssistantSessionResponse(
        token=token,
        token_type="Bearer",
        expires_at=expires_at,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
    )
