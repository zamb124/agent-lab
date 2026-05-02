"""
Узкие точки входа к сервисам платформы для inline-кода и платформенных тулов.

Контейнер целиком в namespace не передаётся: только явно перечисленные сервисы.
Каждая функция возвращает минимально необходимый объект, не контейнер.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.flows.src.clients.mcp_client import MCPClient
    from apps.flows.src.eval.lara_facade import LaraFacade
    from apps.flows.src.models.mcp import MCPCallResult
    from apps.flows.src.services.operator_handoff_service import OperatorHandoffService
    from apps.flows.src.services.schedule_service import ScheduleService
    from core.integrations.oauth_service import OAuthService
    from core.state import ExecutionState


def get_operator_handoff_service() -> "OperatorHandoffService":
    from apps.flows.src.container import get_container

    return get_container().operator_handoff_service


def get_schedule_service() -> "ScheduleService":
    from apps.flows.src.container import get_container

    return get_container().schedule_service


def get_oauth_service() -> "OAuthService":
    from apps.flows.src.container import get_container

    return get_container().oauth_service


def get_lara_facade() -> "LaraFacade":
    from apps.flows.src.container import get_container

    return get_container().lara_facade


def get_code_runner(language: str = "python", resources: dict | None = None) -> Any:
    """PythonCodeRunner (или runner для `language`) без доступа к `FlowContainer` из namespace."""
    from apps.flows.src.container import get_container

    return get_container().get_code_runner(language=language, resources=resources)


async def get_mcp_client(
    server_id: str,
    *,
    state: "ExecutionState | None" = None,
    timeout: float = 60.0,
) -> "MCPClient":
    """Вернуть MCP-клиент по `server_id` для inline-кода (без доступа к контейнеру)."""
    from apps.flows.src.clients.mcp_client import get_mcp_client as build_mcp_client
    from apps.flows.src.container import get_container

    if not isinstance(server_id, str) or server_id.strip() == "":
        raise ValueError("server_id обязателен")
    config = await get_container().mcp_server_repository.get(server_id.strip())
    if config is None:
        raise ValueError(f"MCP server not found: {server_id}")
    variables: dict[str, Any] = {}
    if state is not None:
        variables = dict(getattr(state, "variables", {}) or {})
    return await build_mcp_client(
        config=config,
        variables=variables,
        timeout=timeout,
    )


async def call_mcp_tool(
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    state: "ExecutionState | None" = None,
    timeout: float = 60.0,
) -> "MCPCallResult":
    """Вызвать MCP tool из inline-кода и вернуть `MCPCallResult`."""
    if not isinstance(tool_name, str) or tool_name.strip() == "":
        raise ValueError("tool_name обязателен")
    client = await get_mcp_client(server_id, state=state, timeout=timeout)
    return await client.call_tool(tool_name.strip(), arguments or {})


async def get_file_bytes(file_id: str) -> bytes:
    """Скачивает содержимое файла по ID из хранилища платформы (FileRepository + S3)."""
    from apps.flows.src.container import get_container
    from core.files import S3ClientFactory

    container = get_container()
    record = await container.file_repository.get(file_id)
    if record is None:
        raise ValueError(f"Файл {file_id} не найден в хранилище")
    s3 = S3ClientFactory.create_client_for_bucket(record.s3_bucket)
    return await s3.download_bytes(record.s3_key)


async def get_google_oauth_token(state: "ExecutionState", service: str) -> str:
    """
    Per-user OAuth для Google API.

    Ищет сохранённый токен в БД. Если нет — бросает FlowInterrupt с ссылкой
    на авторизацию Google. Flow ставится на паузу и автоматически
    продолжается после OAuth callback.

    Args:
        state: ExecutionState текущего flow
        service: идентификатор сервиса (docs, calendar, drive, ...)

    Returns:
        access_token (строка)
    """
    from apps.flows.src.runtime.exceptions import FlowInterrupt
    from core.context import get_context
    from core.integrations.models import IntegrationProvider
    from core.logging import get_logger
    from core.state.interrupt import OAuthInterrupt
    from core.tracing.context import get_current_trace_context

    logger = get_logger(__name__)

    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]

    ctx = get_context()
    if ctx is None or ctx.active_company is None or ctx.user is None:
        raise ValueError("Контекст с активной компанией обязателен для Google OAuth")

    oauth = get_oauth_service()
    credential = await oauth.get_valid_token(
        company_id=ctx.active_company.company_id,
        user_id=ctx.user.user_id,
        provider=IntegrationProvider.GOOGLE,
        service=service,
    )
    if credential:
        logger.debug("Google OAuth: credential found, user=%s, service=%s", ctx.user.user_id, service)
        return credential.access_token

    flow_context: dict[str, Any] = {
        "flow_id": state.session_flow_id,
        "session_id": state.session_id,
        "task_id": state.task_id,
        "context_id": state.context_id,
        "branch_id": state.branch_id,
        "channel": "a2a",
        "user_id": ctx.user.user_id,
        "context_data": ctx.model_dump(mode="json"),
    }
    saved_trace_context = get_current_trace_context()
    if saved_trace_context is not None:
        flow_context["trace_context"] = saved_trace_context

    auth_url = await oauth.build_auth_url(
        provider=IntegrationProvider.GOOGLE,
        service=service,
        scopes=scopes,
        user_id=ctx.user.user_id,
        company_id=ctx.active_company.company_id,
        flow_context=flow_context,
    )
    logger.info("Google OAuth: no credential, raising OAuthInterrupt for user=%s, service=%s", ctx.user.user_id, service)
    raise FlowInterrupt(
        body=OAuthInterrupt(
            question="Для работы с Google необходима авторизация",
            auth_url=auth_url,
            provider="google",
            service=service,
        ),
    )
