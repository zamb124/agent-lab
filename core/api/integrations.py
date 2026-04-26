"""
Generic OAuth callback и CRUD credentials для всех интеграций (Google, Yandex, ...).

Endpoints (в приложении под префиксом /{server.name}, напр. flows: /flows/api/v1/...):
  GET  .../api/v1/integrations/oauth/callback — OAuth redirect после авторизации
  GET  .../api/v1/integrations/credentials     — список подключённых интеграций пользователя
  DELETE .../api/v1/integrations/credentials/{provider}/{service} — отключить интеграцию
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from starlette.responses import HTMLResponse, RedirectResponse

from core.config import get_settings
from core.context import get_context
from core.integrations.models import CredentialInfo, IntegrationProvider
from core.logging import get_logger
from core.pagination import ListResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

# Реестр callback для resume flow после OAuth.
# Регистрируется из apps/ при старте сервиса (apps/flows/main.py).
_flow_resume_handler: Optional[Callable[..., Coroutine]] = None


def set_flow_resume_handler(handler: Callable[..., Coroutine]) -> None:
    """Регистрирует обработчик resume flow (вызывается из apps при старте)."""
    global _flow_resume_handler
    _flow_resume_handler = handler


@router.get("/credentials", response_model=ListResponse[CredentialInfo])
async def list_credentials(request: Request) -> ListResponse[CredentialInfo]:
    """Список подключённых интеграций текущего пользователя (без токенов)."""
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")

    repository = request.app.state.container.integration_credential_repository
    credentials = await repository.list_by_user(
        company_id=ctx.active_company.company_id,
        user_id=ctx.user.user_id,
    )
    return ListResponse[CredentialInfo](items=[
        CredentialInfo(
            provider=c.provider,
            service=c.service,
            created_at=c.created_at,
        )
        for c in credentials
    ])


@router.delete("/credentials/{provider}/{service}")
async def delete_credential(
    request: Request,
    provider: str,
    service: str,
) -> dict[str, bool]:
    """Отключить интеграцию (удалить credential пользователя)."""
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        provider_enum = IntegrationProvider(provider)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown provider: {provider}")

    repository = request.app.state.container.integration_credential_repository
    deleted = await repository.delete_by_user_provider_service(
        company_id=ctx.active_company.company_id,
        user_id=ctx.user.user_id,
        provider=provider_enum,
        service=service,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"deleted": True}


@router.get("/oauth/callback", response_model=None)
async def oauth_callback(
    request: Request,
    state: Optional[str] = Query(default=None),
    code: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    referer: Optional[str] = Query(default=None),
) -> HTMLResponse | RedirectResponse:
    """
    Универсальный OAuth callback.

    Google (и другие провайдеры) редиректят сюда после авторизации пользователя.
    State декодируется из Storage, code обменивается на токены через OAuthService.
    Если flow_context присутствует — запускает resume flow через TaskIQ.
    """
    if error:
        logger.error("Integration OAuth error: %s", error)
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing required parameters: code and state")

    oauth_service = request.app.state.container.oauth_service
    try:
        credential, return_path, flow_context, post_auth_redirect_origin = await oauth_service.complete_oauth(
            state_token=state,
            code=code,
            referer=referer,
        )
    except ValueError as exc:
        logger.warning("OAuth complete_oauth ValueError: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        logger.error("OAuth provider token exchange error: status=%d", exc.response.status_code)
        raise HTTPException(status_code=502, detail="OAuth provider error")

    if flow_context is not None:
        await _resume_flow(flow_context, credential.provider, credential.service)
        return HTMLResponse(
            content=_success_page(credential.provider, credential.service),
            status_code=200,
        )

    settings = get_settings()
    public_base = settings.server.platform_public_base_url
    if public_base and public_base.strip() and isinstance(return_path, str) and return_path.startswith(
        "/"
    ):
        origin = post_auth_redirect_origin if post_auth_redirect_origin else public_base.rstrip("/")
        target = f"{origin}{return_path}"
        return RedirectResponse(url=target, status_code=302)

    return HTMLResponse(
        content=_success_page(credential.provider, credential.service),
        status_code=200,
    )


async def _resume_flow(
    flow_context: dict[str, Any],
    provider: str,
    service: str,
) -> None:
    """Продолжает flow после OAuth. Использует зарегистрированный handler из apps/."""
    if _flow_resume_handler is None:
        logger.warning("OAuth flow_context получен, но flow_resume_handler не зарегистрирован")
        return

    flow_id = flow_context.get("flow_id")
    session_id = flow_context.get("session_id")
    context_data = flow_context.get("context_data")

    if not flow_id or not session_id or not context_data:
        logger.warning(
            "OAuth flow_context incomplete, skip resume: flow_id=%s session_id=%s",
            flow_id, session_id,
        )
        return

    task_id = flow_context.get("task_id", "")
    context_id = flow_context.get("context_id", session_id)
    skill_id = flow_context.get("skill_id", "default")
    channel = flow_context.get("channel", "a2a")
    user_id = flow_context.get("user_id", "")
    trace_context = flow_context.get("trace_context")

    await _flow_resume_handler(
        flow_id=flow_id,
        session_id=session_id,
        user_id=user_id,
        content=f"oauth_completed:{provider}:{service}",
        skill_id=skill_id,
        channel=channel,
        task_id=task_id,
        context_id=context_id,
        metadata={},
        is_resume=True,
        files=[],
        context_data=context_data,
        trace_context=trace_context,
    )
    logger.info(
        "OAuth auto-resume kicked: flow_id=%s session_id=%s provider=%s service=%s",
        flow_id, session_id, provider, service,
    )


def _success_page(provider: str, service: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Authorization Complete</title></head>
<body style="font-family:sans-serif;text-align:center;padding:60px">
<h2>Authorization successful</h2>
<p>{provider} / {service} connected. You can close this tab and return to the chat.</p>
</body>
</html>"""
