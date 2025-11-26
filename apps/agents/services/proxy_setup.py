"""
Модуль для настройки глобального прокси.
Импортируется первым для установки переменных окружения.
"""

import os
import logging
from core.config import get_settings
settings = get_settings()
logger = logging.getLogger(__name__)

_proxy_configured = False


def configure_proxy_from_settings():
    """
    Настраивает прокси из конфигурации.
    Вызывается один раз при первом импорте.
    """
    global _proxy_configured
    
    if _proxy_configured:
        return
    
    try:
        if settings.proxy.enabled:
            http_proxy = settings.proxy.get_proxy_url("http")
            https_proxy = settings.proxy.get_proxy_url("https")
            
            if http_proxy:
                os.environ["HTTP_PROXY"] = http_proxy
                os.environ["http_proxy"] = http_proxy
                logger.info(f"🌐 HTTP прокси: {http_proxy.split('@')[1] if '@' in http_proxy else http_proxy}")
            
            if https_proxy:
                os.environ["HTTPS_PROXY"] = https_proxy
                os.environ["https_proxy"] = https_proxy
                logger.info(f"🌐 HTTPS прокси: {https_proxy.split('@')[1] if '@' in https_proxy else https_proxy}")
            
            # Исключаем localhost и внутренние сервисы из прокси
            no_proxy = "localhost,127.0.0.1,sgr,postgres,app,worker"
            os.environ["NO_PROXY"] = no_proxy
            os.environ["no_proxy"] = no_proxy
            logger.info(f"🌐 NO_PROXY: {no_proxy}")
            
            _proxy_configured = True
            logger.info("✅ Глобальный прокси настроен")
        else:
            logger.debug("Прокси отключен в конфигурации")
    except Exception as e:
        logger.warning(f"Не удалось настроить прокси: {e}")


configure_proxy_from_settings()

