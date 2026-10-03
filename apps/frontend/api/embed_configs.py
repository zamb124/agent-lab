"""REST-зеркало команд `frontend/embed_configs/*` и протокольная выдача embed-session токена.

`POST /{embed_id}/session-token` зовёт backend клиента по API-ключу платформы (Bearer `hum_…`)
из своего сервера — это выдача токена внешней интеграции, не команда пользователя.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from apps.frontend.di import Di
from apps.frontend.realtime.embed_operations import (
    CreateEmbedConfigRequest,
    EmbedCodePayload,
    EmbedCodeResponse,
    EmbedConfigDeleted,
    EmbedConfigsListPayload,
    EmbedConfigUpdatePayload,
    EmbedIdPayload,
    UpdateEmbedConfigRequest,
    op_embed_configs_code,
    op_embed_configs_create,
    op_embed_configs_item,
    op_embed_configs_list,
    op_embed_configs_remove,
    op_embed_configs_update,
)
from core.authz.models import AuthzObject
from core.context import require_active_company, require_context
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.middleware.auth.company_resolver import build_service_base_url
from core.models.embed_models import EmbedConfig, EmbedStatus
from core.pagination import OffsetPage
from core.utils.tokens import get_token_service
from core.websocket import WsCommandError

router = APIRouter(prefix="/api/embed/configs", tags=["embed_configs"])


class EmbedSessionTokenRequest(BaseModel):
    origin: str | None = Field(default=None, description="Origin внешнего сайта")
    expires_in_seconds: int = Field(default=300, ge=60, le=900, description="TTL токена в секундах")


class EmbedSessionTokenResponse(BaseModel):
    token: str
    token_type: str
    expires_at: datetime
    flow_id: str
    branch_id: str


@router.post("", response_model=EmbedConfig)
async def create_embed_config(request_data: CreateEmbedConfigRequest, di: Di) -> EmbedConfig:
    return await op_embed_configs_create(request_data, user=require_context().user, di=di)


@router.get("", response_model=OffsetPage[EmbedConfig])
async def list_embed_configs(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[EmbedConfig]:
    return await op_embed_configs_list(
        EmbedConfigsListPayload(limit=limit, offset=offset), user=require_context().user, di=di
    )


@router.get("/{embed_id}", response_model=EmbedConfig)
async def get_embed_config(embed_id: str, di: Di) -> EmbedConfig:
    return await op_embed_configs_item(
        EmbedIdPayload(embed_id=embed_id), user=require_context().user, di=di
    )


@router.patch("/{embed_id}", response_model=EmbedConfig)
async def update_embed_config(
    embed_id: str, request_data: UpdateEmbedConfigRequest, di: Di
) -> EmbedConfig:
    return await op_embed_configs_update(
        EmbedConfigUpdatePayload.model_validate(
            {"embed_id": embed_id, **request_data.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{embed_id}", response_model=EmbedConfigDeleted)
async def delete_embed_config(embed_id: str, di: Di) -> EmbedConfigDeleted:
    return await op_embed_configs_remove(
        EmbedIdPayload(embed_id=embed_id), user=require_context().user, di=di
    )


@router.get("/{embed_id}/code", response_model=EmbedCodeResponse)
async def get_embed_code(embed_id: str, request: Request, di: Di) -> EmbedCodeResponse:
    return await op_embed_configs_code(
        EmbedCodePayload(embed_id=embed_id, public_origin=build_service_base_url(request)),
        user=require_context().user,
        di=di,
    )


@router.post("/{embed_id}/session-token", response_model=EmbedSessionTokenResponse)
async def issue_embed_session_token(
    embed_id: str,
    request_data: EmbedSessionTokenRequest,
    di: Di,
) -> EmbedSessionTokenResponse:
    """Short-lived embed-session токен для канонического A2A embed-пути (протокол интеграции)."""
    user = require_context().user
    company = require_active_company()
    await di.authz_service.require_can_view(AuthzObject.company(company.company_id), user_id=user.user_id)
    config = await EmbedConfig.embed_for_company(embed_id, company.company_id)
    if not config or config.preview_share_link:
        raise WsCommandError("not_found", "Configuration not found", error_code="not_found")
    if config.status != EmbedStatus.ACTIVE:
        raise WsCommandError("forbidden", "Widget configuration is disabled", error_code="forbidden")
    origin = (request_data.origin or "").strip()
    if config.allowed_origins:
        if not origin:
            raise WsCommandError("ws_invalid_payload", "origin is required for a restricted embed", error_code="ws_invalid_payload")
        if origin not in config.allowed_origins:
            raise WsCommandError("forbidden", "origin is not allowed for this configuration", error_code="forbidden")
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=request_data.expires_in_seconds)
    token = get_token_service().create_embed_session_token(
        user_id=user.user_id,
        company_id=company.company_id,
        roles=user.companies.get(company.company_id, []),
        expires_in=request_data.expires_in_seconds,
        metadata={
            "embed_id": embed_id,
            "embed_flow_id": config.flow_id,
            "embed_branch_id": config.branch_id,
            "allowed_origin": origin,
            "issued_by": "frontend.embed_configs",
            EMBED_SESSION_ID_METADATA_KEY: f"embsess_{uuid.uuid4().hex}",
        },
    )
    return EmbedSessionTokenResponse(
        token=token,
        token_type="Bearer",
        expires_at=expires_at,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
    )
