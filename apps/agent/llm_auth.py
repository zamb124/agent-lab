"""
Multi-auth для OpenAI-compatible LLM proxy:

1. device JWT (LinnexAgent) — validate + set_context из company_id/user_id токена;
2. OnlyOffice editor JWT — ``platformAi`` claims + set_context.

Route ``/flows/api/v1/agent/llm/*`` — anonymous (middleware не ставит company из JWT).
Поэтому Context с active_company обязан выставляться здесь. Без фолбека на system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request

from apps.agent.device_auth import require_active_device_bearer
from apps.flows.src.dependencies import ContainerDep
from core.clients.onlyoffice import OnlyOfficeJwtError, verify_onlyoffice_jwt_hs256
from core.context import get_context, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import UserStatus
from core.office.jwt_secret import resolve_onlyoffice_jwt_secret
from core.office.platform_ai_claims import (
    OfficePlatformAiClaims,
    extract_office_platform_ai_claims,
)
from core.types import JsonObject
from core.utils.tokens import TokenData, TokenService

logger = get_logger(__name__)

LlmProxyAuthKind = Literal["device", "office_editor"]


@dataclass(frozen=True)
class LlmProxyAuthResult:
    kind: LlmProxyAuthKind
    office_ai: OfficePlatformAiClaims | None = None


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        raise HTTPException(status_code=401, detail="Authorization Bearer обязателен")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization Bearer обязателен")
    token = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization Bearer обязателен")
    return token


def _request_host(request: Request) -> str:
    host_header = request.headers.get("host")
    return host_header if host_header is not None else ""


async def _set_context_for_company_user(
    container: ContainerDep,
    *,
    user_id: str,
    company_id: str,
    request: Request,
    channel: str,
    metadata: JsonObject,
    active_namespace: str = "default",
) -> None:
    if not company_id.strip():
        raise HTTPException(status_code=401, detail="company_id обязателен в токене")
    user = await container.user_repository.get(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user из токена не найден")
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="user неактивен")
    company = await container.company_repository.get(company_id)
    if company is None:
        raise HTTPException(status_code=401, detail="company из токена не найдена")
    if company_id not in user.companies:
        raise HTTPException(status_code=403, detail="user не состоит в company из токена")

    set_context(
        Context(
            user=user,
            host=_request_host(request),
            channel=channel,
            active_company=company,
            user_companies=[company],
            active_namespace=active_namespace,
            metadata=metadata,
        )
    )


async def _set_context_from_device_token(
    container: ContainerDep,
    *,
    token_data: TokenData,
    request: Request,
) -> None:
    if not token_data.company_id.strip():
        raise HTTPException(status_code=401, detail="device JWT без company_id")
    device_id = token_data.metadata.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise HTTPException(status_code=401, detail="device_id отсутствует в токене")
    metadata: JsonObject = {
        "token_purpose": "device",
        "device_id": device_id.strip(),
    }
    await _set_context_for_company_user(
        container,
        user_id=token_data.user_id,
        company_id=token_data.company_id.strip(),
        request=request,
        channel="agent_llm_device",
        metadata=metadata,
    )


async def _set_context_from_office_ai_claims(
    container: ContainerDep,
    *,
    claims: OfficePlatformAiClaims,
    request: Request,
) -> None:
    metadata: JsonObject = {
        "office_ai": True,
        "file_id": claims.file_id,
        "viewer_scope": claims.viewer_scope,
    }
    await _set_context_for_company_user(
        container,
        user_id=claims.user_id,
        company_id=claims.company_id,
        request=request,
        channel="onlyoffice_ai",
        metadata=metadata,
        active_namespace=claims.namespace,
    )


async def require_llm_proxy_auth(
    request: Request,
    container: ContainerDep,
) -> LlmProxyAuthResult:
    """
    Device JWT или OnlyOffice editor JWT с ``platformAi``.

    Device: revoke-check + set_context(company из device JWT).
    Office: verify HS256 office secret → set_context из claims.
    """
    token = _extract_bearer_token(request)

    platform_token = TokenService().validate_token(token)
    if platform_token is not None:
        purpose = platform_token.metadata.get("token_purpose")
        if purpose == "device":
            await require_active_device_bearer(request, container)
            await _set_context_from_device_token(
                container,
                token_data=platform_token,
                request=request,
            )
            device_context = get_context()
            if device_context is None or device_context.active_company is None:
                raise HTTPException(
                    status_code=500,
                    detail="Context с active_company обязателен после device auth",
                )
            return LlmProxyAuthResult(kind="device")

    try:
        office_secret = resolve_onlyoffice_jwt_secret()
    except ValueError as exc:
        logger.warning("agent.llm_proxy.office_jwt_secret_missing", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="OnlyOffice JWT secret недоступен",
        ) from exc

    try:
        payload = verify_onlyoffice_jwt_hs256(token, office_secret)
        claims = extract_office_platform_ai_claims(payload)
    except (OnlyOfficeJwtError, ValueError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Недействительный LLM proxy token (нужен device JWT или OnlyOffice editor JWT)",
        ) from exc

    await _set_context_from_office_ai_claims(container, claims=claims, request=request)
    office_context = get_context()
    if office_context is None or office_context.active_company is None:
        raise HTTPException(
            status_code=500,
            detail="Context с active_company обязателен после OnlyOffice auth",
        )
    return LlmProxyAuthResult(kind="office_editor", office_ai=claims)


__all__ = [
    "LlmProxyAuthKind",
    "LlmProxyAuthResult",
    "require_llm_proxy_auth",
]
