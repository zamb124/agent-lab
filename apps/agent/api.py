"""
API для HumanitecAgent: скачивание, auth, device registration, pairing.
"""

from typing import Annotated
from urllib.parse import quote as url_quote

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from apps.agent.config import get_agent_settings
from apps.agent.desktop.build_contract import VALID_PLATFORMS
from apps.agent.local_releases import (
    resolve_local_release_artifact_path,
    use_local_release_artifact,
)
from apps.agent.models import (
    AgentDiscoverResponse,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DeviceRegisterWithAuthRequest,
)
from apps.agent.service import (
    fetch_agent_discover,
    fetch_latest_release_asset_url,
    register_device,
    register_device_with_auth,
)
from apps.frontend.dependencies import ContainerDep
from core.app_state import get_request_token_data
from core.context import require_context
from core.logging import get_logger
from core.utils.tokens import TokenService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])

DEVICE_TOKEN_EXPIRES = 30 * 86400


@router.get("/download/{platform}", tags=["agent", "public"])
async def download_agent(platform: str) -> RedirectResponse:
    if platform not in VALID_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемая платформа: {platform!r}. Допустимые: {sorted(VALID_PLATFORMS)}",
        )
    settings = get_agent_settings()
    logger.info(
        "agent.download.requested",
        platform=platform,
        github_owner=settings.releases.github_owner,
        github_repo=settings.releases.github_repo,
    )
    try:
        url = await fetch_latest_release_asset_url(platform)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "agent.download.failed",
            platform=platform,
            github_owner=settings.releases.github_owner,
            github_repo=settings.releases.github_repo,
            status_code=exc.response.status_code,
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"GitHub release недоступен для {settings.releases.github_owner}/"
                f"{settings.releases.github_repo}: HTTP {exc.response.status_code}"
            ),
        ) from exc
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(
            "agent.download.local_failed",
            platform=platform,
            detail=str(exc),
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(url=url)


@router.get("/releases/artifact/{platform}", tags=["agent", "public"])
async def serve_local_release_artifact(platform: str) -> FileResponse:
    if platform not in VALID_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемая платформа: {platform!r}. Допустимые: {sorted(VALID_PLATFORMS)}",
        )
    if not use_local_release_artifact():
        raise HTTPException(status_code=404, detail="Local release artifacts disabled")
    artifact_path = resolve_local_release_artifact_path(platform)
    return FileResponse(
        path=str(artifact_path),
        filename=artifact_path.name,
        media_type="application/octet-stream",
    )


@router.get("/discover", response_model=AgentDiscoverResponse, tags=["agent", "public"])
async def agent_discover(
    container: ContainerDep,
    origin: Annotated[str | None, Query(description="Opt-in override публичного origin (lvh.me dev)")] = None,
) -> AgentDiscoverResponse:
    return await fetch_agent_discover(container, origin_override=origin)


def _render_login_page(
    redirect_uri: str = "humanitec://auth/callback",
    already_logged_in: bool = False,
    user_email: str | None = None,
    session_token: str | None = None,
) -> HTMLResponse:
    title = "HumanitecAgent — Вход"
    redirect_escaped = url_quote(redirect_uri, safe="")

    if already_logged_in:
        if not session_token:
            raise HTTPException(status_code=500, detail="session token is required for agent login redirect")
        redirect_escaped_token = url_quote(session_token, safe="")
        body = f"""
        <div class="card">
            <div class="logo">H</div>
            <h1>Добро пожаловать</h1>
            <p>Вы вошли как <strong>{user_email or 'пользователь'}</strong></p>
            <p>Регистрируем HumanitecAgent на платформе...</p>
            <div class="spinner"></div>
            <p class="hint">Если приложение не открылось автоматически, нажмите кнопку ниже.</p>
            <button id="open-agent" class="btn btn-primary">Открыть HumanitecAgent</button>
        </div>
        <script>
            window.location.href = '{redirect_uri}?token=' + encodeURIComponent('{redirect_escaped_token}');
            document.getElementById('open-agent').addEventListener('click', function() {{
                window.location.href = '{redirect_uri}?token=' + encodeURIComponent('{redirect_escaped_token}');
            }});
        </script>
        """
    else:
        body = f"""
        <div class="card">
            <div class="logo">H</div>
            <h1>Вход в HumanitecAgent</h1>
            <p>Войдите в аккаунт Humanitec для подключения агента</p>
            <a href="/login?redirect={redirect_escaped}" class="btn btn-primary">Войти через Humanitec</a>
            <p class="hint">Нет аккаунта? <a href="/register?redirect={redirect_escaped}">Создать</a></p>
        </div>
        """

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #0D0D0D; color: #FFFFFF; display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
        .card {{ background: #1A1A1A; border: 1px solid #2A2A2A; border-radius: 16px; padding: 48px; max-width: 420px; width: 100%; text-align: center; }}
        .logo {{ width: 64px; height: 64px; background: #0066FF; border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: 700; margin: 0 auto 24px; }}
        h1 {{ font-size: 24px; font-weight: 600; margin-bottom: 12px; }}
        p {{ font-size: 14px; color: #999999; margin-bottom: 24px; line-height: 1.5; }}
        .btn {{ display: inline-block; padding: 12px 32px; border-radius: 8px; font-size: 15px; font-weight: 500; text-decoration: none; cursor: pointer; border: none; }}
        .btn-primary {{ background: #0066FF; color: #FFFFFF; }}
        .btn-primary:hover {{ background: #0052CC; }}
        .hint {{ font-size: 13px; color: #666666; margin-top: 20px; }}
        .hint a {{ color: #0066FF; text-decoration: none; }}
        .spinner {{ width: 32px; height: 32px; border: 3px solid #2A2A2A; border-top-color: #0066FF; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 24px auto; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
{body}
</body>
</html>""")


@router.get("/login", response_class=HTMLResponse)
async def agent_login_page(
    request: Request,
    container: ContainerDep,
    redirect: Annotated[str, Query()] = "humanitec://auth/callback",
) -> HTMLResponse:
    _ = container
    token_data = get_request_token_data(request)
    if token_data is not None:
        token_service = TokenService()
        session_token = token_service.create_token(
            user_id=token_data.user_id,
            company_id=token_data.company_id,
            roles=token_data.roles,
            session_id=token_data.session_id,
            email=token_data.email,
        )
        return _render_login_page(
            redirect_uri=redirect,
            already_logged_in=True,
            user_email=token_data.email,
            session_token=session_token,
        )

    return _render_login_page(redirect_uri=redirect, already_logged_in=False)


@router.post("/auth/device-token")
async def issue_device_token(
    container: ContainerDep,
) -> dict[str, str]:
    _ = container
    context = require_context()
    user = context.user
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    token_service = TokenService()
    token = token_service.create_token(
        user_id=user.user_id,
        company_id=company.company_id,
        roles=company.members.get(user.user_id, []),
        expires_in=DEVICE_TOKEN_EXPIRES,
        metadata={"token_purpose": "device", "device_id": "pending"},
    )
    logger.info("agent.device_token_issued", user_id=user.user_id, company_id=company.company_id)
    return {"token": token}


@router.post("/register-with-auth", response_model=DeviceRegisterResponse, tags=["agent", "public"])
async def register_agent_device_with_auth(
    body: DeviceRegisterWithAuthRequest,
    container: ContainerDep,
    origin: Annotated[str | None, Query(description="Opt-in override публичного origin (lvh.me dev)")] = None,
) -> DeviceRegisterResponse:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return await register_device_with_auth(
        container,
        body,
        user_id=context.user.user_id,
        company_id=company.company_id,
        origin_override=origin,
    )


@router.post("/register", response_model=DeviceRegisterResponse, tags=["agent", "public"])
async def register_agent_device(
    body: DeviceRegisterRequest,
    request: Request,
    container: ContainerDep,
    origin: Annotated[str | None, Query(description="Opt-in override публичного origin (lvh.me dev)")] = None,
) -> DeviceRegisterResponse:
    client_host = request.client.host if request.client is not None else "unknown"
    client_key = f"{client_host}:{body.device_id}"
    return await register_device(
        container,
        body,
        client_key=client_key,
        origin_override=origin,
    )
