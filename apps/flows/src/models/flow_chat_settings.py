"""
Re-export канона политики поведения чата из core.

Канон живёт в `core.models.flow_chat_settings` (используется и EmbedConfig
в core, и flows). Здесь только совместимый импорт-путь для flows-кода.
"""

from core.models.flow_chat_settings import (
    ChatErrorsDisplay,
    ChatToolCallsDisplay,
    EmbedChatPolicyOverride,
    FlowChatSettings,
    compact_embed_chat_policy_override,
    resolve_effective_flow_chat,
)

__all__ = [
    "ChatErrorsDisplay",
    "ChatToolCallsDisplay",
    "EmbedChatPolicyOverride",
    "FlowChatSettings",
    "compact_embed_chat_policy_override",
    "resolve_effective_flow_chat",
]
