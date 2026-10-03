"""Public first-party session issuance for EmbedConfig.presentation=page."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from apps.frontend.api.public_session_security import (
    enforce_public_session_issue_rate_limit,
    new_embed_session_id,
)
from apps.frontend.di import Di
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.logging import get_logger
from core.models.embed_models import EmbedConfig, EmbedStatus
from core.models.identity_models import Company
from core.utils.tokens import get_token_service
from core.websocket import WsCommandError

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
        raise WsCommandError("ws_invalid_payload", "origin must be an absolute http(s) URL", error_code="ws_invalid_payload")
    return f"{parsed.scheme}://{parsed.netloc}"


@router.post("/session", response_model=EmbedPageSessionResponse)
async def issue_embed_page_session(
    body: EmbedPageSessionRequest,
    request: Request,
    di: Di,
) -> EmbedPageSessionResponse:
    embed_id = body.embed_id.strip()
    origin = _normalize_origin(body.origin)
    if not origin:
        raise WsCommandError("ws_invalid_payload", "origin is required", error_code="ws_invalid_payload")

    config = await EmbedConfig.get(embed_id)
    if config is None:
        raise WsCommandError("not_found", "Widget not found", error_code="not_found")

    company = await Company.get(config.company_id)
    if company is None:
        raise WsCommandError("not_found", "Widget not found", error_code="not_found")

    if config.preview_share_link:
        raise WsCommandError("not_found", "Configuration not found", error_code="not_found")
    if config.status != EmbedStatus.ACTIVE:
        raise WsCommandError("forbidden", "Widget is disabled", error_code="forbidden")

    if config.presentation != "page":
        raise WsCommandError(
            "forbidden",
            "Fullscreen page is available only when presentation=page",
            error_code="forbidden",
        )

    page_origin = f"{request.url.scheme}://{request.url.netloc}"
    if origin != page_origin:
        raise WsCommandError(
            "forbidden",
            "origin must match the first-party host of the page",
            error_code="forbidden",
        )

    await enforce_public_session_issue_rate_limit(
        redis_client=di.redis_client,
        request=request,
        scope="public_embed_page",
    )

    guest_id = f"embed_page_guest_{uuid.uuid4().hex}"
    embed_session_id = new_embed_session_id()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_seconds)
    _ = await ensure_persisted_runtime_user(
        di.authz_service,
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
