"""Публичный session endpoint для Humanitec Search."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, ClassVar
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from apps.frontend.api.public_session_security import (
    enforce_public_search_run_quota,
    enforce_public_session_issue_rate_limit,
    new_embed_session_id,
)
from apps.frontend.dependencies import ContainerDep
from apps.frontend.services.public_search_bootstrap import (
    PUBLIC_SEARCH_SPEC_BY_MODE,
    ensure_public_search_embed_configs,
)
from core.clients.service_client import ServiceClient
from core.context import get_context
from core.http import get_httpx_client
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID, SYSTEM_COMPANY_SUBDOMAIN
from core.logging import get_logger
from core.models.embed_models import EmbedStatus
from core.models.identity_models import User
from core.search import PUBLIC_SEARCH_FLOW_ID, PUBLIC_SEARCH_SESSION_ISSUER, PublicSearchMode
from core.search.models import MetaSearchResponse, MetaSearchSerpMoreRequest
from core.types import JsonObject
from core.utils.tokens import TokenType, get_token_service

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


def _platform_user_roles(user: User) -> list[str]:
    system_roles = user.companies.get(SYSTEM_COMPANY_ID)
    if system_roles is not None and len(system_roles) > 0:
        return list(system_roles)
    active_company_id = user.active_company_id.strip()
    if active_company_id == "":
        raise HTTPException(status_code=403, detail="Активная компания пользователя не задана")
    active_roles = user.companies.get(active_company_id)
    if active_roles is None or len(active_roles) == 0:
        raise HTTPException(status_code=403, detail="Роли пользователя не найдены")
    return list(active_roles)


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

    platform_user = _platform_authenticated_user()
    if platform_user is None and body.consume_search_quota:
        await enforce_public_search_run_quota(
            redis_client=container.redis_client,
            request=request,
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
        container,
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
        raise HTTPException(status_code=401, detail="Требуется публичная search-сессия")
    issued_by = ctx.user.attributes.get("issued_by")
    if issued_by != PUBLIC_SEARCH_SESSION_ISSUER:
        auth_token = ctx.auth_token
        if auth_token is None or auth_token.strip() == "":
            raise HTTPException(status_code=403, detail="Недопустимый тип сессии для SERP")
        token_data = get_token_service().validate_token(auth_token)
        if token_data is None:
            raise HTTPException(status_code=401, detail="Требуется публичная search-сессия")
        token_issued_by = token_data.metadata.get("issued_by")
        if token_issued_by != PUBLIC_SEARCH_SESSION_ISSUER:
            raise HTTPException(status_code=403, detail="Недопустимый тип сессии для SERP")


@router.post("/serp/more", response_model=MetaSearchResponse)
async def public_search_serp_more(
    body: PublicSearchSerpMoreRequestBody,
    container: ContainerDep,
) -> MetaSearchResponse:
    _ = container
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
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=502, detail=message) from exc
    return MetaSearchResponse.model_validate(payload)


@router.get("/favicon")
async def public_search_favicon(
    request: Request,
    domain: Annotated[str, Query(min_length=1, max_length=255)],
    container: ContainerDep,
) -> Response:
    host = domain.strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if not _DOMAIN_RE.match(host):
        raise HTTPException(status_code=400, detail="invalid domain")
    await enforce_public_session_issue_rate_limit(
        redis_client=container.redis_client,
        request=request,
        scope="public_search_favicon",
    )
    favicon_url = f"https://{host}/favicon.ico"
    async with get_httpx_client(timeout=5.0, follow_redirects=True) as http_client:
        response = await http_client.get(favicon_url)
        if response.status_code >= 400:
            raise HTTPException(status_code=404, detail="favicon not found")
        content_type = "image/x-icon"
        for header_name, header_value in response.headers.multi_items():
            if header_name.lower() == "content-type" and header_value.strip():
                content_type = header_value.strip()
                break
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=404, detail="favicon is not an image")
        return Response(
            content=response.content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
