"""
API для управления конфигурациями встраиваемых виджетов.
"""

from core.logging import get_logger
import html
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.pagination import OffsetPage
from core.models.embed_models import (
    DEFAULT_EMBED_INPUT_PLACEHOLDER,
    EmbedConfig,
    EmbedMapping,
    EmbedStatus,
)
from core.utils.tokens import get_token_service
from apps.frontend.dependencies import ContainerDep
from core.clients.service_client import ServiceClientError
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID

logger = get_logger(__name__)
router = APIRouter(prefix="/api/embed/configs", tags=["embed_configs"])

_EMBED_CODE_SESSION_TOKEN_TTL_SECONDS = 300


def _build_embed_integration_snippets(
    *,
    token_endpoint: str,
    embed_id: str,
    allowed_origins: list[str],
    expires_in_seconds: int,
) -> tuple[str, str]:
    ttl = expires_in_seconds
    token_ep_js = json.dumps(token_endpoint, ensure_ascii=False)
    embed_id_js = json.dumps(embed_id, ensure_ascii=False)
    origins_js = json.dumps(allowed_origins, ensure_ascii=False)

    backend_proxy_code = (
        "// Server-to-server: API-ключ платформы hum_... "
        "(scopes agents:read и/или agents:write, см. выдачу ключей) -> embed-session JWT.\n"
        f"// expires_in_seconds допустимо 60..900; в примере: {ttl}.\n"
        "// Поле origin в теле POST — строка сайта посетителя "
        "(как у window.location.origin на странице клиента).\n"
        "// Если список allowed_origins виджета не пустой, это значение должно быть в списке.\n"
        f"// allowed_origins виджета: {origins_js}\n"
        "// Задайте browserOrigin, например из входящего HTTP-запроса к вашему POST /api/chat-token:\n"
        "// const browserOrigin = req.headers.origin; // примерный Express\n"
        f"const response = await fetch({token_ep_js}, {{\n"
        "  method: 'POST',\n"
        "  headers: {\n"
        "    'Content-Type': 'application/json',\n"
        "    'Authorization': 'Bearer hum_<ISSUER_TOKEN>',\n"
        "  },\n"
        "  body: JSON.stringify({\n"
        "    origin: browserOrigin,\n"
        f"    expires_in_seconds: {ttl},\n"
        "  }),\n"
        "});\n"
        "if (!response.ok) throw new Error('Humanitec session-token request failed');\n"
        "const data = await response.json();\n"
        "// data.token — Bearer для виджета; data.expires_at — при необходимости клиенту.\n"
    )

    browser_to_host_backend_code = (
        "// Браузер вызывает только ваш backend, не платформу напрямую.\n"
        "async function getChatToken() {\n"
        "  const r = await fetch('/api/chat-token', {\n"
        "    method: 'POST',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify({\n"
        f"      embed_id: {embed_id_js},\n"
        "      origin: window.location.origin,\n"
        f"      expires_in_seconds: {ttl},\n"
        "    }),\n"
        "  });\n"
        "  if (!r.ok) throw new Error('Cannot get chat token');\n"
        "  return await r.json();\n"
        "}\n"
    )

    return backend_proxy_code, browser_to_host_backend_code


def _validate_landing_catalog_fields(
    *,
    landing_visible: bool,
    landing_card_image_url: Optional[str],
    company_id: str,
) -> None:
    if not landing_visible:
        return
    if company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(
            status_code=400,
            detail="Показ в каталоге лендинга доступен только для компании system",
        )
    url = (landing_card_image_url or "").strip()
    if not url:
        raise HTTPException(
            status_code=400,
            detail="Для показа на лендинге укажите landing_card_image_url",
        )


def _validate_guest_max_user_messages(value: Optional[int]) -> None:
    if value is None:
        return
    if value < 1 or value > 500:
        raise HTTPException(
            status_code=400,
            detail="guest_max_user_messages должен быть от 1 до 500 или не задан",
        )


def _validate_voice_flags(*, voice_enabled: bool, voice_default_on: bool) -> None:
    if voice_default_on and not voice_enabled:
        raise HTTPException(
            status_code=400,
            detail="voice_default_on можно включить только вместе с voice_enabled",
        )


def _embed_config_to_response(config: EmbedConfig) -> "EmbedConfigResponse":
    return EmbedConfigResponse(
        embed_id=config.embed_id,
        name=config.name,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
        allowed_origins=config.allowed_origins,
        status=config.status,
        theme=config.theme,
        position=config.position,
        show_launcher=config.show_launcher,
        show_reasoning=config.show_reasoning,
        show_tool_calls=config.show_tool_calls,
        primary_color=config.primary_color,
        greeting_message=config.greeting_message,
        assistant_title=config.assistant_title,
        interface_locale=config.interface_locale,
        placeholder=config.placeholder,
        branding=config.branding,
        landing_visible=config.landing_visible,
        landing_card_image_url=config.landing_card_image_url,
        landing_sort_order=config.landing_sort_order,
        guest_max_user_messages=config.guest_max_user_messages,
        voice_enabled=config.voice_enabled,
        voice_default_on=config.voice_default_on,
        usage_count=config.usage_count,
        last_used_at=config.last_used_at,
        created_at=config.created_at,
        created_by=config.created_by,
        updated_at=config.updated_at,
    )

class CreateEmbedConfigRequest(BaseModel):
    """Запрос на создание конфигурации виджета"""
    name: str = Field(description="Название виджета")
    flow_id: str = Field(description="ID агента")
    branch_id: str = Field(default="default", description="Skill flow (LOCAL); для EXTERNAL не используется")
    allowed_origins: List[str] = Field(default_factory=list, description="Разрешенные домены")
    theme: str = Field(default="dark", description="Тема оформления")
    position: str = Field(default="bottom-right", description="Позиция на странице")
    show_launcher: bool = Field(default=True, description="Показывать встроенную кнопку запуска")
    show_reasoning: bool = Field(default=False, description="Показывать reasoning")
    show_tool_calls: bool = Field(default=False, description="Показывать tool calls")
    primary_color: str = Field(default="#6366f1", description="Основной цвет")
    greeting_message: Optional[str] = Field(default=None, description="Приветственное сообщение")
    assistant_title: Optional[str] = Field(default=None, description="Имя ассистента в шапке")
    interface_locale: str = Field(default="auto", description="Язык интерфейса embed-чата (auto, ru, en)")
    placeholder: str = Field(
        default=DEFAULT_EMBED_INPUT_PLACEHOLDER,
        description="Текст placeholder в поле ввода виджета",
    )
    branding: bool = Field(default=True, description="Показывать брендинг")
    landing_visible: bool = Field(default=False, description="Показ в публичном каталоге лендинга (только company system)")
    landing_card_image_url: Optional[str] = Field(default=None, description="Картинка карточки на лендинге")
    landing_sort_order: int = Field(default=0, description="Порядок в каталоге (меньше — выше)")
    guest_max_user_messages: Optional[int] = Field(
        default=None,
        description="Лимит пользовательских сообщений на диалог (embed-session); не задан — без лимита",
    )
    voice_enabled: bool = Field(
        default=False,
        description="Дуплекс голоса (WebSocket эфир); при false — только браузерная диктовка при поддержке",
    )
    voice_default_on: bool = Field(
        default=False,
        description="Автоматически включать голосовой режим при открытии виджета",
    )

class UpdateEmbedConfigRequest(BaseModel):
    """Запрос на обновление конфигурации виджета"""
    name: Optional[str] = None
    flow_id: Optional[str] = None
    branch_id: Optional[str] = None
    allowed_origins: Optional[List[str]] = None
    status: Optional[EmbedStatus] = None
    theme: Optional[str] = None
    position: Optional[str] = None
    show_launcher: Optional[bool] = None
    show_reasoning: Optional[bool] = None
    show_tool_calls: Optional[bool] = None
    primary_color: Optional[str] = None
    greeting_message: Optional[str] = None
    assistant_title: Optional[str] = None
    interface_locale: Optional[str] = None
    placeholder: Optional[str] = None
    branding: Optional[bool] = None
    landing_visible: Optional[bool] = None
    landing_card_image_url: Optional[str] = None
    landing_sort_order: Optional[int] = None
    guest_max_user_messages: Optional[int] = None
    voice_enabled: Optional[bool] = None
    voice_default_on: Optional[bool] = None

class EmbedConfigResponse(BaseModel):
    """Ответ с конфигурацией виджета"""
    embed_id: str
    name: str
    flow_id: str
    branch_id: str
    allowed_origins: List[str]
    status: EmbedStatus
    theme: str
    position: str
    show_launcher: bool
    show_reasoning: bool
    show_tool_calls: bool
    primary_color: str
    greeting_message: Optional[str]
    assistant_title: Optional[str]
    interface_locale: str
    placeholder: str
    branding: bool
    landing_visible: bool
    landing_card_image_url: Optional[str]
    landing_sort_order: int
    guest_max_user_messages: Optional[int]
    voice_enabled: bool
    voice_default_on: bool
    usage_count: int
    last_used_at: Optional[datetime]
    created_at: datetime
    created_by: str
    updated_at: datetime

class EmbedCodeResponse(BaseModel):
    """Код для встраивания виджета"""

    html_code: str
    script_url: str
    embed_id: str
    token_endpoint: str
    backend_proxy_code: str
    browser_to_host_backend_code: str
    allowed_origins: List[str]

class EmbedSessionTokenRequest(BaseModel):
    origin: Optional[str] = Field(default=None, description="Origin внешнего сайта")
    expires_in_seconds: int = Field(default=300, ge=60, le=900, description="TTL токена в секундах")

class EmbedSessionTokenResponse(BaseModel):
    token: str
    token_type: str
    expires_at: datetime
    flow_id: str
    branch_id: str

def _normalize_interface_locale(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in {"auto", "ru", "en"}:
        raise HTTPException(status_code=400, detail="interface_locale должен быть auto, ru или en")
    return normalized

@router.post("", response_model=EmbedConfigResponse)
async def create_embed_config(
    request_data: CreateEmbedConfigRequest,
    request: Request,
    container: ContainerDep
):
    """
    Создание новой конфигурации виджета.
    
    Проверяет авторизацию, существование агента и создает:
    1. EmbedConfig в компании
    2. Глобальный маппинг embed_id -> company_id
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    user = request.state.user
    company_id = user.active_company_id
    
    if not company_id:
        raise HTTPException(status_code=400, detail="Необходимо выбрать компанию")
    
    try:
        agent = await container.service_client.get(
            "flows", f"/flows/api/v1/flows/{request_data.flow_id}"
        )
    except ServiceClientError as e:
        if "404" in str(e):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Агент {request_data.flow_id} не найден в flows для текущей компании "
                    "(проверьте flow_id в редакторе flows и совпадение компании)."
                ),
            )
        raise HTTPException(status_code=500, detail=f"Ошибка обращения к flows: {str(e)}")

    branch_id = request_data.branch_id
    if agent.get("type") == "external":
        branch_id = "default"
    else:
        branches = agent.get("branches", {})
        if branches:
            if branch_id not in branches:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ветка '{branch_id}' не найдена у flow {request_data.flow_id}",
                )
        else:
            branch_id = "default"
    
    # Генерируем уникальный embed_id
    embed_id = f"embed_{uuid.uuid4().hex[:16]}"
    
    interface_locale = _normalize_interface_locale(request_data.interface_locale)

    allowed_origins: list[str] = []
    for origin in request_data.allowed_origins:
        normalized = origin.strip()
        if not normalized:
            raise HTTPException(
                status_code=400,
                detail="allowed_origins не должна содержать пустые строки",
            )
        allowed_origins.append(normalized)

    card_url = (request_data.landing_card_image_url or "").strip() or None
    _validate_landing_catalog_fields(
        landing_visible=request_data.landing_visible,
        landing_card_image_url=card_url,
        company_id=company_id,
    )

    _validate_guest_max_user_messages(request_data.guest_max_user_messages)
    _validate_voice_flags(
        voice_enabled=request_data.voice_enabled,
        voice_default_on=request_data.voice_default_on,
    )

    # Создаем конфигурацию
    config = EmbedConfig(
        embed_id=embed_id,
        name=request_data.name,
        flow_id=request_data.flow_id,
        branch_id=branch_id,
        allowed_origins=allowed_origins,
        status=EmbedStatus.ACTIVE,
        theme=request_data.theme,
        position=request_data.position,
        show_launcher=request_data.show_launcher,
        show_reasoning=request_data.show_reasoning,
        show_tool_calls=request_data.show_tool_calls,
        primary_color=request_data.primary_color,
        greeting_message=request_data.greeting_message,
        assistant_title=request_data.assistant_title,
        interface_locale=interface_locale,
        placeholder=request_data.placeholder,
        branding=request_data.branding,
        landing_visible=request_data.landing_visible,
        landing_card_image_url=card_url,
        landing_sort_order=request_data.landing_sort_order,
        guest_max_user_messages=request_data.guest_max_user_messages,
        voice_enabled=request_data.voice_enabled,
        voice_default_on=request_data.voice_default_on,
        created_by=user.user_id,
    )
    
    embed_config_repo = container.embed_config_repository
    await embed_config_repo.set(config)
    
    # Создаем глобальный маппинг
    mapping = EmbedMapping(embed_id=embed_id, company_id=company_id)
    embed_mapping_repo = container.embed_mapping_repository
    await embed_mapping_repo.set(mapping)
    
    logger.info(f"Создана конфигурация виджета {embed_id} для компании {company_id}")
    
    return _embed_config_to_response(config)

@router.get("", response_model=OffsetPage[EmbedConfigResponse])
async def list_embed_configs(
    request: Request,
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    Получение списка всех конфигураций виджетов компании.
    
    Автоматически фильтруется по активной компании (is_global=False).
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    user = request.state.user
    company_id = user.active_company_id
    
    if not company_id:
        raise HTTPException(status_code=400, detail="Необходимо выбрать компанию")
    
    embed_config_repo = container.embed_config_repository
    configs = await embed_config_repo.list(limit=limit, offset=offset)
    
    logger.info(f"Получен список из {len(configs)} конфигураций для компании {company_id}")

    items = [_embed_config_to_response(c) for c in configs]
    return OffsetPage[EmbedConfigResponse](items=items, total=len(items), limit=limit, offset=offset)

@router.get("/{embed_id}", response_model=EmbedConfigResponse)
async def get_embed_config(
    embed_id: str,
    request: Request,
    container: ContainerDep
):
    """Получение конфигурации виджета по ID"""
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    embed_config_repo = container.embed_config_repository
    config = await embed_config_repo.get(embed_id)
    
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    
    return _embed_config_to_response(config)

@router.patch("/{embed_id}", response_model=EmbedConfigResponse)
async def update_embed_config(
    embed_id: str,
    request_data: UpdateEmbedConfigRequest,
    request: Request,
    container: ContainerDep
):
    """Обновление конфигурации виджета"""
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    embed_config_repo = container.embed_config_repository
    config = await embed_config_repo.get(embed_id)
    
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    
    # Обновляем только переданные поля
    update_data = request_data.model_dump(exclude_unset=True)
    if "guest_max_user_messages" in update_data:
        _validate_guest_max_user_messages(update_data.get("guest_max_user_messages"))
    if "interface_locale" in update_data and update_data["interface_locale"] is not None:
        update_data["interface_locale"] = _normalize_interface_locale(update_data["interface_locale"])
    if "landing_card_image_url" in update_data and update_data["landing_card_image_url"] is not None:
        s = str(update_data["landing_card_image_url"]).strip()
        update_data["landing_card_image_url"] = s if s else None

    for field, value in update_data.items():
        if hasattr(config, field):
            setattr(config, field, value)

    user = request.state.user
    company_id = user.active_company_id
    if not company_id:
        raise HTTPException(status_code=400, detail="Необходимо выбрать компанию")
    _validate_landing_catalog_fields(
        landing_visible=config.landing_visible,
        landing_card_image_url=config.landing_card_image_url,
        company_id=company_id,
    )
    _validate_voice_flags(
        voice_enabled=config.voice_enabled,
        voice_default_on=config.voice_default_on,
    )

    config.updated_at = datetime.now(timezone.utc)
    await embed_config_repo.set(config)
    
    logger.info(f"Обновлена конфигурация виджета {embed_id}")
    
    return _embed_config_to_response(config)

@router.delete("/{embed_id}")
async def delete_embed_config(
    embed_id: str,
    request: Request,
    container: ContainerDep
):
    """
    Удаление конфигурации виджета.
    
    Удаляет:
    1. EmbedConfig из компании
    2. Глобальный маппинг embed_id -> company_id
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    embed_config_repo = container.embed_config_repository
    config = await embed_config_repo.get(embed_id)
    
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    
    # Удаляем конфигурацию
    await embed_config_repo.delete(embed_id)
    
    # Удаляем глобальный маппинг
    embed_mapping_repo = container.embed_mapping_repository
    await embed_mapping_repo.delete_by_embed_id(embed_id)
    
    logger.info(f"Удалена конфигурация виджета {embed_id}")
    
    return {"success": True, "message": "Конфигурация успешно удалена"}

@router.get("/{embed_id}/code", response_model=EmbedCodeResponse)
async def get_embed_code(
    embed_id: str,
    request: Request,
    container: ContainerDep
):
    """
    Получение кода для встраивания виджета.
    
    Возвращает готовый HTML код со скриптом для вставки на сайт.
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    embed_config_repo = container.embed_config_repository
    config = await embed_config_repo.get(embed_id)
    
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")

    user = request.state.user
    company_id = getattr(user, "active_company_id", None) or ""
    if config.voice_enabled and not company_id:
        raise HTTPException(
            status_code=400,
            detail="Для кода виджета с голосом выберите активную компанию",
        )

    # Определяем base URL
    from core.config import get_settings
    settings = get_settings()
    
    # Канонический Web Component путь
    if settings.server.env == "production":
        script_url = "https://cdn.humanitec.ru/lib/embed-chat/humanitec-embed-autoload.js"
        base_url = "https://api.humanitec.ru"
    else:
        host = request.headers.get("host", "localhost:8000")
        protocol = request.url.scheme
        if protocol not in ("http", "https"):
            raise ValueError(
                f"get_embed_code: ожидалась схема http или https, получено {protocol!r}"
            )
        script_url = f"{protocol}://{host}/static/core/lib/embed-chat/humanitec-embed-autoload.js"
        base_url = f"{protocol}://{host}"

    token_endpoint = f"{base_url}/frontend/api/embed/configs/{embed_id}/session-token"
    ttl = _EMBED_CODE_SESSION_TOKEN_TTL_SECONDS
    allowed_origins = list(config.allowed_origins)
    backend_proxy_code, browser_to_host_backend_code = _build_embed_integration_snippets(
        token_endpoint=token_endpoint,
        embed_id=config.embed_id,
        allowed_origins=allowed_origins,
        expires_in_seconds=ttl,
    )
    assistant_title = config.assistant_title or config.name
    voice_default_active = config.voice_enabled and config.voice_default_on

    open_tag_parts = [
        f'src="{html.escape(script_url, quote=True)}"',
        f'data-embed-id="{html.escape(config.embed_id, quote=True)}"',
        f'data-assistant-title="{html.escape(assistant_title, quote=True)}"',
        f'data-theme="{html.escape(config.theme, quote=True)}"',
        f'data-locale="{html.escape(config.interface_locale, quote=True)}"',
        ('data-show-launcher="true"' if config.show_launcher else 'data-show-launcher="false"'),
        f'data-flows-base-url="{html.escape(f"{base_url}/flows", quote=True)}"',
        f'data-platform-ui-origin="{html.escape(base_url, quote=True)}"',
        'data-chat-token-url="/api/chat-token"',
        f'data-token-expires-seconds="{ttl}"',
        'data-use-credentials="false"',
        'data-event-namespace="assistant"',
        'data-toggle-event-name="humanitec-embed-chat-toggle"',
        ('data-voice-enabled="true"' if config.voice_enabled else 'data-voice-enabled="false"'),
        ('data-voice-default-on="true"' if voice_default_active else 'data-voice-default-on="false"'),
        f'data-voice-base-url="{html.escape(f"{base_url}/voice", quote=True)}"',
        f'data-company-id="{html.escape(company_id, quote=True)}"',
    ]
    attrs_block = "\n  ".join(open_tag_parts)
    html_code = f"<script type=\"module\"\n  {attrs_block}\n></script>"

    return EmbedCodeResponse(
        html_code=html_code,
        script_url=script_url,
        embed_id=embed_id,
        token_endpoint=token_endpoint,
        backend_proxy_code=backend_proxy_code,
        browser_to_host_backend_code=browser_to_host_backend_code,
        allowed_origins=allowed_origins,
    )

@router.post("/{embed_id}/session-token", response_model=EmbedSessionTokenResponse)
async def issue_embed_session_token(
    embed_id: str,
    request_data: EmbedSessionTokenRequest,
    request: Request,
    container: ContainerDep,
):
    """Выдает short-lived embed-session токен для канонического A2A embed-пути."""
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")

    user = request.state.user
    company_id = user.active_company_id
    if not company_id:
        raise HTTPException(status_code=400, detail="Необходимо выбрать компанию")

    embed_config_repo = container.embed_config_repository
    config = await embed_config_repo.get(embed_id)
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    if config.status != EmbedStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Конфигурация виджета отключена")

    origin = (request_data.origin or "").strip()
    if config.allowed_origins:
        if not origin:
            raise HTTPException(status_code=400, detail="origin обязателен для ограниченного embed")
        if origin not in config.allowed_origins:
            raise HTTPException(status_code=403, detail="origin не разрешен для этой конфигурации")

    user_roles = user.companies.get(company_id, [])
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=request_data.expires_in_seconds)
    token = get_token_service().create_embed_session_token(
        user_id=user.user_id,
        company_id=company_id,
        roles=user_roles,
        expires_in=request_data.expires_in_seconds,
        metadata={
            "embed_id": embed_id,
            "embed_flow_id": config.flow_id,
            "embed_branch_id": config.branch_id,
            "allowed_origin": origin,
            "issued_by": "frontend.embed_configs",
        },
    )

    return EmbedSessionTokenResponse(
        token=token,
        token_type="Bearer",
        expires_at=expires_at,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
    )

