"""
Multi-auth для OpenAI-compatible LLM proxy:

1. device JWT (LinnexAgent) — validate + set_context из company_id/user_id токена;
2. execution token (guest code_agent) — 2-part HMAC, ``user_id`` обязателен;
3. OnlyOffice editor JWT — ``platformAi`` claims + set_context.

Route ``/flows/api/v1/agent/llm/*`` — anonymous (middleware не ставит company из JWT).
Поэтому Context с active_company обязан выставляться здесь. Без фолбека на system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from apps.flows.src.agent.device_auth import require_active_device_bearer
from apps.flows.src.dependencies import ContainerDep
from core.capabilities import verify_execution_token
from core.clients.onlyoffice import OnlyOfficeJwtError, verify_onlyoffice_jwt_hs256
from core.context import get_context, set_context
from core.logging import bind_test_scope, get_logger
from core.models.context_models import Context
from core.models.identity_models import UserStatus
from core.office.jwt_secret import resolve_onlyoffice_jwt_secret
from core.office.platform_ai_claims import (
    OfficePlatformAiClaims,
    extract_office_platform_ai_claims,
)
from core.types import JsonObject
from core.utils.tokens import TokenData, TokenService
from core.websocket import WsCommandError

logger = get_logger(__name__)

LlmProxyAuthKind = Literal["device", "office_editor", "execution"]


@dataclass(frozen=True)
class LlmProxyAuthResult:
    kind: LlmProxyAuthKind
    office_ai: OfficePlatformAiClaims | None = None


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        raise WsCommandError(
            "unauthorized",
            "Authorization Bearer is required",
            error_code="authorization_bearer_required",
        )
    if not authorization.lower().startswith("bearer "):
        raise WsCommandError(
            "unauthorized",
            "Authorization Bearer is required",
            error_code="authorization_bearer_required",
        )
    token = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
    if not token:
        raise WsCommandError(
            "unauthorized",
            "Authorization Bearer is required",
            error_code="authorization_bearer_required",
        )
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
        raise WsCommandError(
            "unauthorized",
            "company_id is required in token",
            error_code="token_company_id_required",
        )
    user = await container.user_repository.get(user_id)
    if user is None:
        raise WsCommandError(
            "unauthorized",
            "user from token not found",
            error_code="token_user_not_found",
        )
    if user.status != UserStatus.ACTIVE:
        raise WsCommandError(
            "forbidden",
            "user is inactive",
            error_code="user_inactive",
        )
    company = await container.company_repository.get(company_id)
    if company is None:
        raise WsCommandError(
            "unauthorized",
            "company from token not found",
            error_code="token_company_not_found",
        )
    if company_id not in user.companies:
        raise WsCommandError(
            "forbidden",
            "user is not a member of token company",
            error_code="token_company_membership",
        )

    _ = set_context(
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
        raise WsCommandError(
            "unauthorized",
            "device JWT has no company_id",
            error_code="device_jwt_company_id_missing",
        )
    device_id = token_data.metadata.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise WsCommandError(
            "unauthorized",
            "device_id is missing from token",
            error_code="device_id_missing",
        )
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
    Device JWT, execution token (guest code_agent) или OnlyOffice editor JWT с ``platformAi``.

    Device: revoke-check + set_context(company из device JWT).
    Execution: 2-part HMAC token; ``user_id`` обязателен.
    Office: verify HS256 office secret → set_context из claims.
    """
    token = _extract_bearer_token(request)
    token_parts = token.split(".")
    if len(token_parts) == 2:
        try:
            claims = verify_execution_token(token)
        except ValueError as exc:
            raise WsCommandError(
                "unauthorized",
                "execution token is invalid",
                error_code="execution_token_invalid",
            ) from exc
        if claims.user_id is None or not claims.user_id.strip():
            raise WsCommandError(
                "unauthorized",
                "execution token user_id is required",
                error_code="execution_token_user_id_required",
            )
        execution_namespace = claims.namespace
        if execution_namespace is None:
            execution_namespace = "default"
        await _set_context_for_company_user(
            container,
            user_id=claims.user_id.strip(),
            company_id=claims.company_id,
            request=request,
            channel="guest_llm",
            metadata={"token_purpose": "execution"},
            active_namespace=execution_namespace,
        )
        execution_context = get_context()
        if execution_context is None or execution_context.active_company is None:
            raise RuntimeError("context with active_company is required after execution token")
        if claims.test_scope is not None:
            bind_test_scope(claims.test_scope)
        return LlmProxyAuthResult(kind="execution")

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
                raise RuntimeError("context with active_company is required after device auth")
            return LlmProxyAuthResult(kind="device")

    try:
        office_secret = resolve_onlyoffice_jwt_secret()
    except ValueError as exc:
        logger.warning("agent.llm_proxy.office_jwt_secret_missing", error=str(exc))
        raise WsCommandError(
            "unavailable",
            "OnlyOffice JWT secret is unavailable",
            error_code="office_jwt_secret_unavailable",
        ) from exc

    try:
        payload = verify_onlyoffice_jwt_hs256(token, office_secret)
        claims = extract_office_platform_ai_claims(payload)
    except (OnlyOfficeJwtError, ValueError) as exc:
        raise WsCommandError(
            "unauthorized",
            "LLM proxy token is invalid (device JWT or OnlyOffice editor JWT required)",
            error_code="llm_proxy_token_invalid",
        ) from exc

    await _set_context_from_office_ai_claims(container, claims=claims, request=request)
    office_context = get_context()
    if office_context is None or office_context.active_company is None:
        raise RuntimeError("context with active_company is required after OnlyOffice auth")
    return LlmProxyAuthResult(kind="office_editor", office_ai=claims)


__all__ = [
    "LlmProxyAuthKind",
    "LlmProxyAuthResult",
    "require_llm_proxy_auth",
]
