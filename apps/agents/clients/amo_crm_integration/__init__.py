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


def get_amocrm_chat_client(subdomain: str):
    """
    Заглушка для Chat API клиента.
    TODO: Реализовать полноценный Chat API клиент.
    """
    raise NotImplementedError("AmoCRM Chat API client не реализован")


__all__ = [
    # Основной клиент API v4
    "AmoCRMClient",
    "AmoCRMLead",
    "AmoCRMContact",
    "get_amocrm_client",
    "register_subdomain",
    # Chat API (заглушка)
    "get_amocrm_chat_client",
]

