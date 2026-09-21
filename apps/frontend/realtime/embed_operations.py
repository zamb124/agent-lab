"""Команды embed-виджетов компании: CRUD конфигураций и код для встраивания.

`issue_embed_session_token` — HTTP-протокол для backend клиента по API-ключу
(`apps/frontend/api/embed_configs.py`), не команда.
"""

from __future__ import annotations

import html
import json
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from apps.flows.src.models.flow_config import FlowType
from apps.frontend.container import FrontendContainer
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.config import get_settings
from core.errors.boundary import PlatformNotFoundError
from core.flow_ui.document import FlowUIConversationSettings, FlowUIPageId
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.embed_models import (
    DEFAULT_EMBED_INPUT_PLACEHOLDER,
    EmbedConfig,
    EmbedMapping,
    EmbedPosition,
    EmbedPresentation,
    EmbedStatus,
)
from core.models.identity_models import SYSTEM_COMPANY_ID, User
from core.pagination import OffsetPage
from core.platform_brand.resolver import resolve_embed_origins
from core.request_scope import CompanyScope, require_company_viewer
from core.websocket import raise_forbidden, raise_invalid

logger = get_logger(__name__)

EMBED_CODE_SESSION_TOKEN_TTL_SECONDS = 300


async def _require_edit_embed_flow(container: FrontendContainer, flow_id: str) -> CompanyScope:
    scope = await require_company_viewer(container.authz_service)
    try:
        await container.authz_service.require_can_edit(
            AuthzObject.flow(flow_id, company_id=scope.company_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


async def _require_visible_config(container: FrontendContainer, embed_id: str) -> EmbedConfig:
    config = await container.embed_config_repository.get(embed_id)
    if not config or config.preview_share_link:
        raise PlatformNotFoundError("Configuration not found", error_code='not_found')
    return config


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
        "// Задайте browserOrigin, например из входящего HTTP-запроса к вашему POST /api/flow-ui-token:\n"
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
        "if (!response.ok) throw new Error('Platform session-token request failed');\n"
        "const data = await response.json();\n"
        "// data.token — Bearer для виджета; data.expires_at — при необходимости клиенту.\n"
    )

    browser_to_host_backend_code = (
        "// Браузер вызывает только ваш backend, не платформу напрямую.\n"
        "async function getFlowUIToken() {\n"
        "  const r = await fetch('/api/flow-ui-token', {\n"
        "    method: 'POST',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify({\n"
        f"      embed_id: {embed_id_js},\n"
        "      origin: window.location.origin,\n"
        f"      expires_in_seconds: {ttl},\n"
        "    }),\n"
        "  });\n"
        "  if (!r.ok) throw new Error('Cannot get Flow UI token');\n"
        "  return await r.json();\n"
        "}\n"
    )

    return backend_proxy_code, browser_to_host_backend_code


def _validate_landing_catalog_fields(
    *,
    landing_visible: bool,
    landing_card_image_url: str | None,
    company_id: str,
) -> None:
    if not landing_visible:
        return
    if company_id != SYSTEM_COMPANY_ID:
        raise_invalid(ValueError("landing catalog is available only for the system company"))
    url = (landing_card_image_url or "").strip()
    if not url:
        raise_invalid(ValueError("landing_card_image_url is required when landing_visible is true"))


def _validate_guest_max_user_messages(value: int | None) -> None:
    if value is None:
        return
    if value < 1 or value > 500:
        raise_invalid(ValueError("guest_max_user_messages must be between 1 and 500 or omitted"))


def _validate_voice_flags(*, voice_enabled: bool, voice_default_on: bool) -> None:
    if voice_default_on and not voice_enabled:
        raise_invalid(ValueError("voice_default_on requires voice_enabled"))


class CreateEmbedConfigRequest(BaseModel):
    """Запрос на создание конфигурации виджета"""
    name: str = Field(description="Название виджета")
    flow_id: str = Field(description="ID агента")
    branch_id: str = Field(default="default", description="Skill flow (LOCAL); для EXTERNAL не используется")
    allowed_origins: list[str] = Field(default_factory=list, description="Разрешенные домены")
    presentation: EmbedPresentation = Field(
        default="drawer",
        description="drawer — FAB + панель; page — полноэкранный Flow UI",
    )
    theme: str = Field(default="dark", description="Тема оформления")
    position: EmbedPosition = Field(default="bottom-right", description="Угол launcher-кнопки (drawer)")
    show_launcher: bool = Field(default=True, description="Показывать встроенную кнопку запуска")
    primary_color: str = Field(default="#6366f1", description="Основной цвет")
    assistant_title: str | None = Field(default=None, description="Имя ассистента в шапке")
    interface_locale: str = Field(default="auto", description="Язык интерфейса embed-чата (auto, ru, en)")
    placeholder: str = Field(
        default=DEFAULT_EMBED_INPUT_PLACEHOLDER,
        description="Текст placeholder в поле ввода виджета",
    )
    branding: bool = Field(default=True, description="Показывать брендинг")
    landing_visible: bool = Field(default=False, description="Показ в публичном каталоге лендинга (только company system)")
    landing_card_image_url: str | None = Field(default=None, description="Картинка карточки на лендинге")
    landing_sort_order: int = Field(default=0, description="Порядок в каталоге (меньше — выше)")
    guest_max_user_messages: int | None = Field(
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
    session_share_enabled: bool = Field(
        default=False,
        description="Разрешить Share текущей сессии из embed-чата",
    )
    conversation: FlowUIConversationSettings | None = Field(
        default=None,
        description="Настройки блока conversation для этой embed-поверхности; null — как у flow",
    )
    start_page_id: FlowUIPageId | None = Field(
        default=None,
        description="Стартовая страница интерфейса для embed; null — как у flow",
    )

class UpdateEmbedConfigRequest(BaseModel):
    """Запрос на обновление конфигурации виджета"""
    name: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None
    allowed_origins: list[str] | None = None
    status: EmbedStatus | None = None
    presentation: EmbedPresentation | None = None
    theme: str | None = None
    position: EmbedPosition | None = None
    show_launcher: bool | None = None
    primary_color: str | None = None
    assistant_title: str | None = None
    interface_locale: str | None = None
    placeholder: str | None = None
    branding: bool | None = None
    landing_visible: bool | None = None
    landing_card_image_url: str | None = None
    landing_sort_order: int | None = None
    guest_max_user_messages: int | None = None
    voice_enabled: bool | None = None
    voice_default_on: bool | None = None
    session_share_enabled: bool | None = None
    conversation: FlowUIConversationSettings | None = None
    start_page_id: FlowUIPageId | None = None

class EmbedCodeResponse(BaseModel):
    """Код для встраивания виджета"""

    html_code: str
    script_url: str
    embed_id: str
    presentation: EmbedPresentation
    page_url: str
    token_endpoint: str
    backend_proxy_code: str
    browser_to_host_backend_code: str
    allowed_origins: list[str]



class EmbedIdPayload(StrictBaseModel):
    embed_id: str = Field(min_length=1)


class EmbedConfigsListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class EmbedCodePayload(EmbedIdPayload):
    public_origin: str = Field(min_length=1, description="scheme://host браузера — база URL скрипта и token endpoint")


class EmbedConfigUpdatePayload(UpdateEmbedConfigRequest):
    embed_id: str = Field(min_length=1)


class EmbedConfigDeleted(StrictBaseModel):
    success: bool = True
    message: str = "Конфигурация успешно удалена"


def _normalize_interface_locale(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in {"auto", "ru", "en"}:
        raise_invalid(ValueError("interface_locale must be auto, ru or en"))
    return normalized



async def op_embed_configs_create(
    request_data: CreateEmbedConfigRequest, *, user: User, container: FrontendContainer
) -> EmbedConfig:
    """Создаёт EmbedConfig компании и глобальный маппинг embed_id -> company_id."""
    flow = await container.flows_flow_repository.get(request_data.flow_id)
    if flow is None:
        raise PlatformNotFoundError(
            (
                f"Agent {request_data.flow_id} not found in flows for the current company "
                "(check flow_id in the flows editor and company match)."
            ),
            error_code="not_found",
        )
    scope = await _require_edit_embed_flow(container, request_data.flow_id)
    company_id = scope.company_id

    branch_id = request_data.branch_id
    if flow.type == FlowType.EXTERNAL:
        branch_id = "default"
    else:
        if flow.branches:
            if branch_id not in flow.branches:
                raise_invalid(ValueError(f"branch {branch_id!r} not found on flow {request_data.flow_id}"))
        else:
            branch_id = "default"

    # Генерируем уникальный embed_id
    embed_id = f"embed_{uuid.uuid4().hex[:16]}"

    interface_locale = _normalize_interface_locale(request_data.interface_locale)

    allowed_origins: list[str] = []
    for origin in request_data.allowed_origins:
        normalized = origin.strip()
        if not normalized:
            raise_invalid(ValueError("allowed_origins must not contain empty strings"))
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

    config = EmbedConfig(
        embed_id=embed_id,
        name=request_data.name,
        flow_id=request_data.flow_id,
        branch_id=branch_id,
        allowed_origins=allowed_origins,
        status=EmbedStatus.ACTIVE,
        presentation=request_data.presentation,
        theme=request_data.theme,
        position=request_data.position,
        show_launcher=request_data.show_launcher,
        primary_color=request_data.primary_color,
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
        session_share_enabled=request_data.session_share_enabled,
        conversation=request_data.conversation,
        start_page_id=request_data.start_page_id,
        preview_share_link=False,
        created_by=user.user_id,
    )

    _ = await container.embed_config_repository.set(config)
    _ = await container.embed_mapping_repository.set(EmbedMapping(embed_id=embed_id, company_id=company_id))
    logger.info("embed_configs.created", embed_id=embed_id, company_id=company_id)
    return config


async def op_embed_configs_update(
    request_data: EmbedConfigUpdatePayload, *, user: User, container: FrontendContainer
) -> EmbedConfig:
    _ = user
    config = await _require_visible_config(container, request_data.embed_id)
    scope = await _require_edit_embed_flow(container, config.flow_id)
    company_id = scope.company_id

    fields = request_data.model_fields_set - {"embed_id"}
    if "name" in fields:
        if request_data.name is None:
            raise_invalid(ValueError("name cannot be null"))
        config.name = request_data.name
    if "flow_id" in fields:
        if request_data.flow_id is None:
            raise_invalid(ValueError("flow_id cannot be null"))
        try:
            await container.authz_service.require_can_edit(
                AuthzObject.flow(request_data.flow_id, company_id=company_id), user_id=scope.user_id
            )
        except AuthzDenied as exc:
            raise_forbidden(exc)
        config.flow_id = request_data.flow_id
    if "branch_id" in fields:
        if request_data.branch_id is None:
            raise_invalid(ValueError("branch_id cannot be null"))
        config.branch_id = request_data.branch_id
    if "allowed_origins" in fields:
        if request_data.allowed_origins is None:
            raise_invalid(ValueError("allowed_origins cannot be null"))
        config.allowed_origins = request_data.allowed_origins
    if "status" in fields:
        if request_data.status is None:
            raise_invalid(ValueError("status cannot be null"))
        config.status = request_data.status
    if "theme" in fields:
        if request_data.theme is None:
            raise_invalid(ValueError("theme cannot be null"))
        config.theme = request_data.theme
    if "presentation" in fields:
        if request_data.presentation is None:
            raise_invalid(ValueError("presentation cannot be null"))
        config.presentation = request_data.presentation
    if "position" in fields:
        if request_data.position is None:
            raise_invalid(ValueError("position cannot be null"))
        config.position = request_data.position
    if "show_launcher" in fields:
        if request_data.show_launcher is None:
            raise_invalid(ValueError("show_launcher cannot be null"))
        config.show_launcher = request_data.show_launcher
    if "primary_color" in fields:
        if request_data.primary_color is None:
            raise_invalid(ValueError("primary_color cannot be null"))
        config.primary_color = request_data.primary_color
    if "assistant_title" in fields:
        config.assistant_title = request_data.assistant_title
    if "interface_locale" in fields:
        if request_data.interface_locale is None:
            raise_invalid(ValueError("interface_locale cannot be null"))
        config.interface_locale = _normalize_interface_locale(request_data.interface_locale)
    if "placeholder" in fields:
        if request_data.placeholder is None:
            raise_invalid(ValueError("placeholder cannot be null"))
        config.placeholder = request_data.placeholder
    if "branding" in fields:
        if request_data.branding is None:
            raise_invalid(ValueError("branding cannot be null"))
        config.branding = request_data.branding
    if "landing_visible" in fields:
        if request_data.landing_visible is None:
            raise_invalid(ValueError("landing_visible cannot be null"))
        config.landing_visible = request_data.landing_visible
    if "landing_card_image_url" in fields:
        card_url = request_data.landing_card_image_url
        config.landing_card_image_url = (
            card_url.strip() if card_url is not None and card_url.strip() else None
        )
    if "landing_sort_order" in fields:
        if request_data.landing_sort_order is None:
            raise_invalid(ValueError("landing_sort_order cannot be null"))
        config.landing_sort_order = request_data.landing_sort_order
    if "guest_max_user_messages" in fields:
        _validate_guest_max_user_messages(request_data.guest_max_user_messages)
        config.guest_max_user_messages = request_data.guest_max_user_messages
    if "voice_enabled" in fields:
        if request_data.voice_enabled is None:
            raise_invalid(ValueError("voice_enabled cannot be null"))
        config.voice_enabled = request_data.voice_enabled
    if "voice_default_on" in fields:
        if request_data.voice_default_on is None:
            raise_invalid(ValueError("voice_default_on cannot be null"))
        config.voice_default_on = request_data.voice_default_on
    if "session_share_enabled" in fields:
        if request_data.session_share_enabled is None:
            raise_invalid(ValueError("session_share_enabled cannot be null"))
        config.session_share_enabled = request_data.session_share_enabled
    if "conversation" in fields:
        config.conversation = request_data.conversation
    if "start_page_id" in fields:
        config.start_page_id = request_data.start_page_id

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
    _ = await container.embed_config_repository.set(config)
    logger.info("embed_configs.updated", embed_id=request_data.embed_id)
    return config


async def op_embed_configs_list(
    payload: EmbedConfigsListPayload, *, user: User, container: FrontendContainer
) -> OffsetPage[EmbedConfig]:
    """Конфигурации активной компании без preview-share ссылок."""
    _ = user
    _ = await require_company_viewer(container.authz_service)
    configs = await container.embed_config_repository.list(limit=payload.limit, offset=payload.offset)
    items = [config for config in configs if not config.preview_share_link]
    return OffsetPage[EmbedConfig](items=items, total=len(items), limit=payload.limit, offset=payload.offset)


async def op_embed_configs_item(
    payload: EmbedIdPayload, *, user: User, container: FrontendContainer
) -> EmbedConfig:
    _ = user
    _ = await require_company_viewer(container.authz_service)
    return await _require_visible_config(container, payload.embed_id)


async def op_embed_configs_remove(
    payload: EmbedIdPayload, *, user: User, container: FrontendContainer
) -> EmbedConfigDeleted:
    """Удаляет конфигурацию компании и глобальный маппинг embed_id -> company_id."""
    _ = user
    config = await _require_visible_config(container, payload.embed_id)
    _ = await _require_edit_embed_flow(container, config.flow_id)
    _ = await container.embed_config_repository.delete(payload.embed_id)
    _ = await container.embed_mapping_repository.delete_by_embed_id(payload.embed_id)
    logger.info("embed_configs.removed", embed_id=payload.embed_id)
    return EmbedConfigDeleted()


async def op_embed_configs_code(
    payload: EmbedCodePayload, *, user: User, container: FrontendContainer
) -> EmbedCodeResponse:
    """Готовый `<script>` для сайта клиента и примеры выдачи embed-session токена."""
    _ = user
    scope = await require_company_viewer(container.authz_service)
    config = await _require_visible_config(container, payload.embed_id)
    settings = get_settings()
    origin = payload.public_origin.strip().rstrip("/")
    scheme, _separator, host_value = origin.partition("://")
    if scheme not in ("http", "https") or not host_value:
        raise_invalid(ValueError(f"public_origin must be http(s)://host, got {payload.public_origin!r}"))
    if settings.server.env == "production":
        script_url, base_url = resolve_embed_origins(host_value)
    else:
        script_url = f"{origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js"
        base_url = origin
    token_endpoint = f"{base_url}/frontend/api/embed/configs/{payload.embed_id}/session-token"
    ttl = EMBED_CODE_SESSION_TOKEN_TTL_SECONDS
    allowed_origins = list(config.allowed_origins)
    backend_proxy_code, browser_to_host_backend_code = _build_embed_integration_snippets(
        token_endpoint=token_endpoint,
        embed_id=config.embed_id,
        allowed_origins=allowed_origins,
        expires_in_seconds=ttl,
    )
    open_tag_parts = [
        f'src="{html.escape(script_url, quote=True)}"',
        f'data-embed-id="{html.escape(config.embed_id, quote=True)}"',
        f'data-presentation="{config.presentation}"',
        f'data-position="{config.position}"',
        f'data-theme="{html.escape(config.theme, quote=True)}"',
        f'data-locale="{html.escape(config.interface_locale, quote=True)}"',
        ('data-show-launcher="true"' if config.show_launcher else 'data-show-launcher="false"'),
        f'data-flows-base-url="{html.escape(f"{base_url}/flows", quote=True)}"',
        f'data-platform-ui-origin="{html.escape(base_url, quote=True)}"',
        'data-token-url="/api/flow-ui-token"',
        f'data-token-expires-seconds="{ttl}"',
        'data-use-credentials="false"',
        'data-toggle-event-name="linnex-flow-ui-toggle"',
        f'data-voice-base-url="{html.escape(f"{base_url}/voice", quote=True)}"',
        f'data-company-id="{html.escape(scope.company_id, quote=True)}"',
    ]
    attrs_block = "\n  ".join(open_tag_parts)
    return EmbedCodeResponse(
        html_code=f"<script type=\"module\"\n  {attrs_block}\n></script>",
        script_url=script_url,
        embed_id=payload.embed_id,
        presentation=config.presentation,
        page_url=f"{base_url}/flow-embed-page?embed={config.embed_id}",
        token_endpoint=token_endpoint,
        backend_proxy_code=backend_proxy_code,
        browser_to_host_backend_code=browser_to_host_backend_code,
        allowed_origins=allowed_origins,
    )
