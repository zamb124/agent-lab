"""
Политика поведения чата flow: что видит пользователь чата (не редактор).

Единственный канон конфигурации chat-поверхности платформы: SPA-чат, editor test,
embed на внешних сайтах и публичный лендинг получают эту политику через
chat-profile endpoint и применяют её при рендере на клиенте. В режиме
editor_test клиент игнорирует политику и показывает всё.

Базовая политика живёт в `FlowConfig.chat`; embed-виджет может частично
переопределить её через `EmbedConfig.chat_override` (`EmbedChatPolicyOverride`).
Effective policy для embed вычисляется на backend в chat-profile через
`resolve_effective_flow_chat`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from core.models.base import StrictBaseModel

ChatToolCallsDisplay = Literal["hidden", "compact", "detailed"]
ChatErrorsDisplay = Literal["generic", "detailed"]


class FlowChatSettings(StrictBaseModel):
    """Per-flow настройки видимости и поведения единого чат-компонента."""

    show_reasoning: bool = Field(
        default=False,
        description="Показывать блоки reasoning ассистента",
    )
    tool_calls_display: ChatToolCallsDisplay = Field(
        default="compact",
        description="Отображение вызовов инструментов: hidden, compact или detailed",
    )
    show_activity: bool = Field(
        default=True,
        description="Показывать строку активности агента (текущая нода/инструмент)",
    )
    errors_display: ChatErrorsDisplay = Field(
        default="generic",
        description="Ошибки выполнения: generic (обезличенный текст) или detailed (текст ошибки)",
    )
    show_run_trace: bool = Field(
        default=False,
        description="Показывать таймлайн выполнения (run trace) под ответом",
    )
    show_trace_actions: bool = Field(
        default=False,
        description="Показывать действия перехода к трейсам/логам",
    )
    show_browser_previews: bool = Field(
        default=True,
        description="Показывать live-превью browser-сессий агента",
    )
    show_files_panel: bool = Field(
        default=True,
        description="Показывать панель файлов диалога",
    )
    allow_cancel: bool = Field(
        default=True,
        description="Разрешить пользователю отменять выполнение (tasks/cancel)",
    )
    greeting_message: str | None = Field(
        default=None,
        description="Приветственное сообщение при открытии чата",
    )
    suggested_prompts: list[str] = Field(
        default_factory=list,
        description="Подсказки-примеры первых сообщений",
    )


class EmbedChatPolicyOverride(StrictBaseModel):
    """
    Частичное переопределение FlowChatSettings для одного embed-виджета.

    Все поля опциональны: None = поле наследуется из FlowConfig.chat.
    Explicit false — валидное переопределение (например скрыть tool calls
    только на внешнем сайте). Merge — `resolve_effective_flow_chat`.
    """

    show_reasoning: bool | None = Field(
        default=None,
        description="Переопределить показ reasoning; None — наследовать из flow",
    )
    tool_calls_display: ChatToolCallsDisplay | None = Field(
        default=None,
        description="Переопределить отображение вызовов инструментов; None — наследовать",
    )
    show_activity: bool | None = Field(
        default=None,
        description="Переопределить строку активности; None — наследовать",
    )
    errors_display: ChatErrorsDisplay | None = Field(
        default=None,
        description="Переопределить режим ошибок; None — наследовать",
    )
    show_run_trace: bool | None = Field(
        default=None,
        description="Переопределить показ run trace; None — наследовать",
    )
    show_trace_actions: bool | None = Field(
        default=None,
        description="Переопределить действия трейсов/логов; None — наследовать",
    )
    show_browser_previews: bool | None = Field(
        default=None,
        description="Переопределить live-превью браузера; None — наследовать",
    )
    show_files_panel: bool | None = Field(
        default=None,
        description="Переопределить панель файлов; None — наследовать",
    )
    allow_cancel: bool | None = Field(
        default=None,
        description="Переопределить возможность отмены; None — наследовать",
    )
    greeting_message: str | None = Field(
        default=None,
        description="Переопределить приветствие; None — наследовать из flow",
    )
    suggested_prompts: list[str] | None = Field(
        default=None,
        description="Переопределить подсказки первых сообщений; None — наследовать",
    )


def resolve_effective_flow_chat(
    flow_chat: FlowChatSettings,
    embed_override: EmbedChatPolicyOverride | None,
) -> FlowChatSettings:
    """
    Effective policy embed-виджета: FlowConfig.chat + non-None поля override.

    None в override означает «поле не задано в patch» (наследование).
    Explicit None / false / пустой список переопределяют flow, если поле
    присутствует в model_fields_set (PATCH/create с явным ключом).
    """
    if embed_override is None:
        return flow_chat
    compact_override = compact_embed_chat_policy_override(embed_override)
    if compact_override is None:
        return flow_chat
    override_patch = compact_override.model_dump(exclude_unset=True)
    if not override_patch:
        return flow_chat
    return flow_chat.model_copy(update=override_patch)


def compact_embed_chat_policy_override(
    override: EmbedChatPolicyOverride | None,
) -> EmbedChatPolicyOverride | None:
    """
    Храним и мержим только явно заданные поля override (exclude_unset).

    Без компактизации round-trip через JSON/storage раздувает patch до полного
    объекта с null и ломает наследование из FlowConfig.chat.
    """
    if override is None:
        return None
    compact_payload = override.model_dump(exclude_unset=True)
    if not compact_payload:
        return None
    return EmbedChatPolicyOverride.model_validate(compact_payload)


__all__ = [
    "ChatErrorsDisplay",
    "ChatToolCallsDisplay",
    "EmbedChatPolicyOverride",
    "FlowChatSettings",
    "compact_embed_chat_policy_override",
    "resolve_effective_flow_chat",
]
