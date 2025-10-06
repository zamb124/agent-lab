"""
AmoCRM Integration Package

Полнофункциональная интеграция с AmoCRM API v4 и Chat API.

Основные компоненты:
- AmoCRMClient: клиент для работы с основным API v4 (сделки, контакты, задачи)
- AmoCRMChatClient: клиент для работы с Chat API (amojo.amocrm.ru)
- register_subdomain: регистрация маппинга subdomain -> access_token
- get_amocrm_client: фабрика для создания singleton клиента основного API
- get_amocrm_chat_client: фабрика для создания singleton клиента Chat API
"""

from .client import (
    AmoCRMClient,
    AmoCRMLead,
    AmoCRMContact,
    get_amocrm_client,
    register_subdomain,
)

from .chat_client import (
    AmoCRMChatClient,
    ChatMessage,
    get_amocrm_chat_client,
)

__all__ = [
    # Основной клиент API v4
    "AmoCRMClient",
    "AmoCRMLead",
    "AmoCRMContact",
    "get_amocrm_client",
    "register_subdomain",
    # Chat API клиент
    "AmoCRMChatClient",
    "ChatMessage",
    "get_amocrm_chat_client",
]

