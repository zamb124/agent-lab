"""
API для управления конфигурациями встраиваемых виджетов.
"""

import logging
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.pagination import OffsetPage
from core.models.embed_models import EmbedConfig, EmbedStatus, EmbedMapping
from core.utils.tokens import get_token_service
from apps.frontend.dependencies import ContainerDep
from apps.flows.src.models import FlowType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/embed/configs", tags=["embed_configs"])


class CreateEmbedConfigRequest(BaseModel):
    """Запрос на создание конфигурации виджета"""
    name: str = Field(description="Название виджета")
    flow_id: str = Field(description="ID агента")
    skill_id: str = Field(default="default", description="Skill flow (LOCAL); для EXTERNAL не используется")
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
    placeholder: str = Field(default="Введите сообщение...", description="Placeholder")
    branding: bool = Field(default=True, description="Показывать брендинг")


class UpdateEmbedConfigRequest(BaseModel):
    """Запрос на обновление конфигурации виджета"""
    name: Optional[str] = None
    flow_id: Optional[str] = None
    skill_id: Optional[str] = None
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


class EmbedConfigResponse(BaseModel):
    """Ответ с конфигурацией виджета"""
    embed_id: str
    name: str
    flow_id: str
    skill_id: str
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


class EmbedSessionTokenRequest(BaseModel):
    origin: Optional[str] = Field(default=None, description="Origin внешнего сайта")
    expires_in_seconds: int = Field(default=300, ge=60, le=900, description="TTL токена в секундах")


class EmbedSessionTokenResponse(BaseModel):
    token: str
    token_type: str
    expires_at: datetime
    flow_id: str
    skill_id: str


def _normalize_interface_locale(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in {"auto", "ru", "en"}:
        raise HTTPException(status_code=400, detail="interface_locale должен быть auto, ru или en")
    return normalized


def _resolve_embed_allowed_origins(agent, request_data: CreateEmbedConfigRequest) -> list[str]:
    """Возвращает allowlist origins для embed-конфига."""
    if request_data.allowed_origins:
        return request_data.allowed_origins

    flow_variable = agent.variables.get("embed_allowed_origins")
    if flow_variable is None:
        return []

    variable_value = flow_variable.value if hasattr(flow_variable, "value") else flow_variable
    if not isinstance(variable_value, list):
        raise HTTPException(
            status_code=400,
            detail="Flow variable embed_allowed_origins должна быть list[str]",
        )

    resolved: list[str] = []
    for origin in variable_value:
        if not isinstance(origin, str):
            raise HTTPException(
                status_code=400,
                detail="Flow variable embed_allowed_origins должна содержать только строки",
            )
        normalized_origin = origin.strip()
        if not normalized_origin:
            raise HTTPException(
                status_code=400,
                detail="Flow variable embed_allowed_origins не должна содержать пустые строки",
            )
        resolved.append(normalized_origin)
    return resolved


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
    
    logger.info(f"🔍 DEBUG create_embed_config: user={user.user_id}, active_company_id={user.active_company_id}")
    
    if not company_id:
        raise HTTPException(status_code=400, detail="Необходимо выбрать компанию")
    
    from apps.flows.src.container import get_container as get_flows_container

    flows_container = get_flows_container()
    agent = await flows_container.flow_repository.get(request_data.flow_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Агент {request_data.flow_id} не найден")

    skill_id = request_data.skill_id
    if agent.type == FlowType.EXTERNAL:
        skill_id = "default"
    else:
        skills = agent.skills or {}
        if skills:
            if skill_id not in skills:
                raise HTTPException(
                    status_code=400,
                    detail=f"Skill '{skill_id}' не найден у flow {request_data.flow_id}",
                )
        else:
            skill_id = "default"
    
    # Генерируем уникальный embed_id
    embed_id = f"embed_{uuid.uuid4().hex[:16]}"
    
    interface_locale = _normalize_interface_locale(request_data.interface_locale)

    allowed_origins = _resolve_embed_allowed_origins(agent, request_data)

    # Создаем конфигурацию
    config = EmbedConfig(
        embed_id=embed_id,
        name=request_data.name,
        flow_id=request_data.flow_id,
        skill_id=skill_id,
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
        created_by=user.user_id,
    )
    
    embed_config_repo = container.embed_config_repository
    await embed_config_repo.set(config)
    
    # Создаем глобальный маппинг
    mapping = EmbedMapping(embed_id=embed_id, company_id=company_id)
    embed_mapping_repo = container.embed_mapping_repository
    await embed_mapping_repo.set(mapping)
    
    logger.info(f"Создана конфигурация виджета {embed_id} для компании {company_id}")
    
    return EmbedConfigResponse(
        embed_id=config.embed_id,
        name=config.name,
        flow_id=config.flow_id,
        skill_id=config.skill_id,
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
        usage_count=config.usage_count,
        last_used_at=config.last_used_at,
        created_at=config.created_at,
        created_by=config.created_by,
        updated_at=config.updated_at,
    )


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

    items = [
        EmbedConfigResponse(
            embed_id=c.embed_id,
            name=c.name,
            flow_id=c.flow_id,
            skill_id=c.skill_id,
            allowed_origins=c.allowed_origins,
            status=c.status,
            theme=c.theme,
            position=c.position,
            show_launcher=c.show_launcher,
            show_reasoning=c.show_reasoning,
            show_tool_calls=c.show_tool_calls,
            primary_color=c.primary_color,
            greeting_message=c.greeting_message,
            assistant_title=c.assistant_title,
            interface_locale=c.interface_locale,
            placeholder=c.placeholder,
            branding=c.branding,
            usage_count=c.usage_count,
            last_used_at=c.last_used_at,
            created_at=c.created_at,
            created_by=c.created_by,
            updated_at=c.updated_at,
        )
        for c in configs
    ]
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
    
    return EmbedConfigResponse(
        embed_id=config.embed_id,
        name=config.name,
        flow_id=config.flow_id,
        skill_id=config.skill_id,
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
        usage_count=config.usage_count,
        last_used_at=config.last_used_at,
        created_at=config.created_at,
        created_by=config.created_by,
        updated_at=config.updated_at,
    )


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
    if "interface_locale" in update_data and update_data["interface_locale"] is not None:
        update_data["interface_locale"] = _normalize_interface_locale(update_data["interface_locale"])
    
    for field, value in update_data.items():
        if hasattr(config, field):
            setattr(config, field, value)
    
    config.updated_at = datetime.now(timezone.utc)
    await embed_config_repo.set(config)
    
    logger.info(f"Обновлена конфигурация виджета {embed_id}")
    
    return EmbedConfigResponse(
        embed_id=config.embed_id,
        name=config.name,
        flow_id=config.flow_id,
        skill_id=config.skill_id,
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
        usage_count=config.usage_count,
        last_used_at=config.last_used_at,
        created_at=config.created_at,
        created_by=config.created_by,
        updated_at=config.updated_at,
    )


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
    
    # Определяем base URL
    from core.config import get_settings
    settings = get_settings()
    
    # Канонический Web Component путь
    if settings.server.env == "production":
        script_url = "https://cdn.humanitec.ru/lib/embed-chat/platform-lara-assistant.js"
        base_url = "https://api.humanitec.ru"
    else:
        host = request.headers.get("host", "localhost:8000")
        protocol = "https" if settings.server.env == "production" else "http"
        script_url = f"{protocol}://{host}/static/core/lib/embed-chat/platform-lara-assistant.js"
        base_url = f"{protocol}://{host}"

    token_endpoint = f"{base_url}/frontend/api/embed/configs/{embed_id}/session-token"
    assistant_title = config.assistant_title or config.name
    theme_js = json.dumps(config.theme, ensure_ascii=False)
    show_launcher_js = json.dumps(config.show_launcher, ensure_ascii=False)
    flow_id_js = json.dumps(config.flow_id, ensure_ascii=False)
    skill_id_js = json.dumps(config.skill_id, ensure_ascii=False)
    assistant_title_js = json.dumps(assistant_title, ensure_ascii=False)
    locale_js = json.dumps(config.interface_locale, ensure_ascii=False)
    flows_base_url_js = json.dumps(f"{base_url}/flows", ensure_ascii=False)
    token_endpoint_js = json.dumps(token_endpoint, ensure_ascii=False)

    html_code = f'''<!-- Humanitec Platform Embed Chat -->
<script type="module" src="{script_url}"></script>
<script>
  async function getEmbedToken() {{
    // Рекомендуемый путь: ваш backend получает short-lived token server-to-server
    const response = await fetch({token_endpoint_js}, {{
      method: 'POST',
      credentials: 'include',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ origin: window.location.origin, expires_in_seconds: 300 }})
    }});
    if (!response.ok) throw new Error('Cannot get embed session token');
    const data = await response.json();
    return {{ Authorization: `Bearer ${{data.token}}` }};
  }}

  const assistant = document.createElement('platform-lara-assistant');
  assistant.setAttribute('flow-id', {flow_id_js});
  assistant.setAttribute('skill-id', {skill_id_js});
  assistant.setAttribute('assistant-title', {assistant_title_js});
  assistant.setAttribute('theme', {theme_js});
  assistant.setAttribute('event-namespace', 'assistant');
  assistant.setAttribute('toggle-event-name', 'humanitec-embed-chat-toggle');
  assistant.setAttribute('use-credentials', 'false');
  assistant.setAttribute('locale', {locale_js});
  assistant.showLauncher = {show_launcher_js};
  assistant.flowsBaseUrl = {flows_base_url_js};
  assistant.getAuthToken = getEmbedToken;
  document.body.appendChild(assistant);
</script>'''
    
    return EmbedCodeResponse(
        html_code=html_code,
        script_url=script_url,
        embed_id=embed_id,
        token_endpoint=token_endpoint,
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
            "embed_skill_id": config.skill_id,
            "allowed_origin": origin,
            "issued_by": "frontend.embed_configs",
        },
    )

    return EmbedSessionTokenResponse(
        token=token,
        token_type="Bearer",
        expires_at=expires_at,
        flow_id=config.flow_id,
        skill_id=config.skill_id,
    )

