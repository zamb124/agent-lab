"""Публичный session endpoint для Linnex Search."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, ClassVar
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from apps.frontend.api.public_session_security import (
    PUBLIC_SEARCH_RESEARCH_QUOTA_COST,
    enforce_public_search_run_quota,
    enforce_public_session_issue_rate_limit,
    new_embed_session_id,
)
from apps.frontend.di import Di
from apps.frontend.services.public_search_bootstrap import (
    PUBLIC_SEARCH_SPEC_BY_MODE,
    ensure_public_search_embed_configs,
)
from core.clients.service_client import ServiceClient
from core.context import get_context
from core.http import get_httpx_client
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.logging import get_logger
from core.models.embed_models import EmbedConfig, EmbedStatus
from core.models.identity_models import SYSTEM_COMPANY_ID, User
from core.search import PUBLIC_SEARCH_FLOW_ID, PUBLIC_SEARCH_SESSION_ISSUER, PublicSearchMode
from core.search.models import MetaSearchResponse, MetaSearchSerpMoreRequest, SerpClickEvent
from core.types import JsonObject
from core.utils.tokens import TokenType, get_token_service
from core.websocket import WsCommandError, raise_not_found, raise_upstream

logger = get_logger(__name__)

router = APIRouter(prefix="/api/public/search", tags=["public_search"])


class PublicSearchSessionRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: PublicSearchMode = "quick"
    origin: str = Field(default="", description="window.location.origin")
    expires_in_seconds: int = Field(default=300, ge=60, le=900)
    consume_search_quota: bool = Field(
        default=True,
        description="True только для полноценного поискового запуска; serp/more и source AI не тратят квоту",
    )


class PublicSearchSessionResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    token: str
    token_type: str
    expires_at: datetime
    embed_id: str
    flow_id: str
    branch_id: str


class PublicSearchSerpMoreRequestBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    serp_cache_key: str = Field(..., min_length=1, max_length=64)
    offset: int = Field(..., ge=0)
    limit: int = Field(default=10, ge=1, le=25)


_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)


def _normalize_origin(raw: str) -> str:
    value = raw.strip()
    if value == "":
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


def _referer_path_allowed(referer: str) -> bool:
    if referer.strip() == "":
        return False
    path = urlparse(referer.strip()).path
    if path in {"", "/", "/frontend"}:
        return True
    return path.startswith("/search") or path.startswith("/frontend/search")


def _platform_authenticated_user() -> User | None:
    ctx = get_context()
    if ctx is None:
        return None
    user = ctx.user
    if user.user_id.startswith("search_guest_"):
        return None
    if user.attributes.get("kind") == "embed_session_guest":
        return None
    auth_token = ctx.auth_token
    if auth_token is None or auth_token.strip() == "":
        return None
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        return None
    if token_data.token_type != TokenType.SESSION:
        return None
    return user


async def _resolve_platform_authenticated_user(
    request: Request,
) -> User | None:
    platform_user = _platform_authenticated_user()
    if platform_user is not None:
        return platform_user

    auth_token_raw = request.cookies.get("auth_token")
    if auth_token_raw is None or auth_token_raw.strip() == "":
        return None

    token_data = get_token_service().validate_token(auth_token_raw)
    if token_data is None:
        return None
    if token_data.token_type != TokenType.SESSION:
        return None
    if token_data.user_id.startswith("search_guest_"):
        return None

    user = await User.get(token_data.user_id)
    if user is None:
        return None
    if user.attributes.get("kind") == "embed_session_guest":
        return None
    return user


def _platform_user_roles(user: User) -> list[str]:
    system_roles = user.companies.get(SYSTEM_COMPANY_ID)
    if system_roles is not None and len(system_roles) > 0:
        return list(system_roles)
    active_company_id = user.active_company_id.strip()
    if active_company_id == "":
        raise WsCommandError("forbidden", "User active company is not set", error_code="forbidden")
    active_roles = user.companies.get(active_company_id)
    if active_roles is None or len(active_roles) == 0:
        raise WsCommandError("forbidden", "User roles not found", error_code="forbidden")
    return list(active_roles)


@router.post("/session", response_model=PublicSearchSessionResponse)
async def issue_public_search_session(
    body: PublicSearchSessionRequest,
    request: Request,
    di: Di,
) -> PublicSearchSessionResponse:
    if body.mode not in PUBLIC_SEARCH_SPEC_BY_MODE:
        raise WsCommandError("ws_invalid_payload", "Unsupported search mode", error_code="ws_invalid_payload")

    configs = await ensure_public_search_embed_configs()
    config = configs[body.mode]

    referer = request.headers.get("referer", "")
    if not _referer_path_allowed(referer):
        raise WsCommandError("forbidden", "Search is available only from the public search page", error_code="forbidden")

    origin = _normalize_origin(body.origin)
    referer_origin = _origin_from_referer(referer)
    if origin == "" and referer_origin != "":
        origin = referer_origin
    if origin != "" and referer_origin != "" and origin != referer_origin:
        raise WsCommandError("forbidden", "origin does not match the search page", error_code="forbidden")
    if origin == "":
        raise WsCommandError("forbidden", "origin is required for a public search session", error_code="forbidden")

    platform_user = await _resolve_platform_authenticated_user(request)
    if platform_user is None and body.consume_search_quota:
        quota_cost = (
            PUBLIC_SEARCH_RESEARCH_QUOTA_COST if body.mode == "research" else 1
        )
        await enforce_public_search_run_quota(
            redis_client=di.redis_client,
            request=request,
            cost=quota_cost,
        )

    persisted_config = await EmbedConfig.get(config.embed_id)
    if persisted_config is None or persisted_config.company_id != SYSTEM_COMPANY_ID:
        raise WsCommandError("not_found", "Widget not found", error_code="not_found")
    if persisted_config.status != EmbedStatus.ACTIVE:
        raise WsCommandError("forbidden", "Widget is disabled", error_code="forbidden")
    if persisted_config.flow_id != PUBLIC_SEARCH_FLOW_ID:
        raise WsCommandError("internal", "Search configuration is corrupt", error_code="internal")
    if persisted_config.branch_id != config.branch_id:
        raise WsCommandError("internal", "Search branch configuration is corrupt", error_code="internal")

    embed_session_id = new_embed_session_id()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_seconds)
    runtime_attributes: JsonObject
    if platform_user is not None:
        session_user_id = platform_user.user_id
        session_user_name = platform_user.name
        session_roles = _platform_user_roles(platform_user)
        runtime_attributes = {
            "issued_by": PUBLIC_SEARCH_SESSION_ISSUER,
            "token_expires_at": expires_at.isoformat(),
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
        }
    else:
        session_user_id = f"search_guest_{uuid.uuid4().hex}"
        session_user_name = "Search Guest"
        session_roles = ["guest"]
        runtime_attributes = {
            "kind": "embed_session_guest",
            "embed_id": persisted_config.embed_id,
            "embed_flow_id": persisted_config.flow_id,
            "embed_branch_id": persisted_config.branch_id,
            "issued_by": PUBLIC_SEARCH_SESSION_ISSUER,
            "token_expires_at": expires_at.isoformat(),
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
        }

    _ = await ensure_persisted_runtime_user(
        di.authz_service,
        user_id=session_user_id,
        company_id=SYSTEM_COMPANY_ID,
        name=session_user_name,
        roles=session_roles,
        attributes=runtime_attributes,
    )
    token = get_token_service().create_embed_session_token(
        user_id=session_user_id,
        company_id=SYSTEM_COMPANY_ID,
        roles=session_roles,
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


def _validate_public_search_guest() -> None:
    if _platform_authenticated_user() is not None:
        return
    ctx = get_context()
    if ctx is None:
        raise WsCommandError("unauthorized", "Public search session is required", error_code="unauthorized")
    issued_by = ctx.user.attributes.get("issued_by")
    if issued_by != PUBLIC_SEARCH_SESSION_ISSUER:
        auth_token = ctx.auth_token
        if auth_token is None or auth_token.strip() == "":
            raise WsCommandError("forbidden", "Invalid session type for SERP", error_code="forbidden")
        token_data = get_token_service().validate_token(auth_token)
        if token_data is None:
            raise WsCommandError("unauthorized", "Public search session is required", error_code="unauthorized")
        token_issued_by = token_data.metadata.get("issued_by")
        if token_issued_by != PUBLIC_SEARCH_SESSION_ISSUER:
            raise WsCommandError("forbidden", "Invalid session type for SERP", error_code="forbidden")


@router.post("/serp/more", response_model=MetaSearchResponse)
async def public_search_serp_more(
    body: PublicSearchSerpMoreRequestBody,
    di: Di,
) -> MetaSearchResponse:
    _ = di
    _validate_public_search_guest()
    search_body = MetaSearchSerpMoreRequest(
        serp_cache_key=body.serp_cache_key,
        offset=body.offset,
        limit=body.limit,
    )
    client = ServiceClient()
    try:
        payload = await client.post(
            "search",
            "/search/api/v1/search/serp/more",
            json=search_body.model_dump(mode="json"),
        )
    except Exception as exc:
        message = str(exc)
        if "404" in message or "serp cache expired" in message.lower():
            raise_not_found(exc)
        raise_upstream(exc)
    return MetaSearchResponse.model_validate(payload)


@router.post("/serp/click", status_code=204)
async def public_search_serp_click(
    body: SerpClickEvent,
    di: Di,
) -> None:
    _ = di
    _validate_public_search_guest()
    client = ServiceClient()
    try:
        _ = await client.post(
            "search",
            "/search/api/v1/search/serp/click",
            json=body.model_dump(mode="json"),
        )
    except Exception as exc:
        raise_upstream(exc)


@router.get("/favicon")
async def public_search_favicon(
    request: Request,
    domain: Annotated[str, Query(min_length=1, max_length=255)],
    di: Di,
) -> Response:
    host = domain.strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if not _DOMAIN_RE.match(host):
        raise WsCommandError("ws_invalid_payload", "invalid domain", error_code="ws_invalid_payload")
    await enforce_public_session_issue_rate_limit(
        redis_client=di.redis_client,
        request=request,
        scope="public_search_favicon",
    )
    favicon_url = f"https://{host}/favicon.ico"
    async with get_httpx_client(timeout=5.0, follow_redirects=True) as http_client:
        response = await http_client.get(favicon_url)
        if response.status_code >= 400:
            raise WsCommandError("not_found", "favicon not found", error_code="not_found")
        content_type = "image/x-icon"
        for header_name, header_value in response.headers.multi_items():
            if header_name.lower() == "content-type" and header_value.strip():
                content_type = header_value.strip()
                break
        if not content_type.startswith("image/"):
            raise WsCommandError("not_found", "favicon is not an image", error_code="not_found")
        return Response(
            content=response.content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
