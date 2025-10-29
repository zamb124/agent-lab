"""
Вспомогательные утилиты для HTTP клиентов с поддержкой прокси.
"""

import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_httpx_client(
    timeout: Optional[float] = None,
    proxy: Optional[str] = None,
    use_proxy_from_config: bool = False,
    **kwargs
) -> httpx.AsyncClient:
    """
    Создает httpx.AsyncClient с автоматической настройкой прокси.
    
    Args:
        timeout: Таймаут запросов
        proxy: Явно указанный прокси URL. Если None и use_proxy_from_config=True - берется из конфигурации
        use_proxy_from_config: Использовать прокси из глобальной конфигурации (по умолчанию False)
        **kwargs: Дополнительные параметры для httpx.AsyncClient
        
    Returns:
        Настроенный httpx.AsyncClient
    """
    # Определяем прокси
    proxy_url = proxy
    
    if proxy_url is None and use_proxy_from_config:
        from app.core.config import get_settings
        settings = get_settings()
        proxy_url = settings.proxy.get_proxy_url("https")
        
        if proxy_url:
            logger.debug(f"🌐 Используем прокси из конфигурации: {proxy_url}")
    elif proxy_url is None and not use_proxy_from_config:
        # Явно отключаем прокси, чтобы переопределить переменные окружения
        proxy_url = None
    
    # Создаем клиент
    client_kwargs = {
        "timeout": timeout or 30.0,
        **kwargs
    }
    
    # Явно передаем proxy (даже если None), чтобы переопределить переменные окружения
    if proxy_url is not None:
        client_kwargs["proxy"] = proxy_url
    else:
        # Явно отключаем прокси, чтобы игнорировать HTTP_PROXY/HTTPS_PROXY из окружения
        client_kwargs["proxy"] = None
    
    return httpx.AsyncClient(**client_kwargs)


def get_proxy_url() -> Optional[str]:
    """
    Получает URL прокси из конфигурации.
    
    Returns:
        URL прокси или None если прокси отключен
    """
    from app.core.config import get_settings
    settings = get_settings()
    return settings.proxy.get_proxy_url("https")

