"""
HTTP клиенты с автоматической настройкой прокси.

ВАЖНО: 
- Для OAuth провайдеров (Google, Yandex, GitHub) ВСЕГДА использовать use_proxy_from_config=False
- Для внутренних API можно использовать use_proxy_from_config=True
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
        timeout: Таймаут запросов (по умолчанию 30.0)
        proxy: Явно указанный прокси URL
        use_proxy_from_config: Использовать прокси из конфигурации (по умолчанию False)
        **kwargs: Дополнительные параметры для httpx.AsyncClient
        
    Returns:
        Настроенный httpx.AsyncClient
        
    Examples:
        >>> async with get_httpx_client(timeout=30.0, use_proxy_from_config=False) as client:
        ...     response = await client.get("https://api.example.com")
    """
    proxy_url = proxy
    
    if proxy_url is None and use_proxy_from_config:
        from core.config import get_settings
        settings = get_settings()
        proxy_url = settings.proxy.get_proxy_url("https")
        
        if proxy_url:
            logger.debug(f"Используем прокси из конфигурации: {proxy_url}")
    elif proxy_url is None and not use_proxy_from_config:
        proxy_url = None
    
    client_kwargs = {
        "timeout": timeout or 30.0,
        **kwargs
    }
    
    if not use_proxy_from_config and proxy is None:
        client_kwargs["trust_env"] = False
        client_kwargs["proxy"] = None
    else:
        client_kwargs["proxy"] = proxy_url
    
    return httpx.AsyncClient(**client_kwargs)


def get_proxy_url() -> Optional[str]:
    """
    Получает URL прокси из конфигурации.
    
    Returns:
        URL прокси или None если прокси отключен
    """
    from core.config import get_settings
    settings = get_settings()
    return settings.proxy.get_proxy_url("https")

