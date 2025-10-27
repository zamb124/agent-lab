"""
Инструменты для интеграций с внешними сервисами.

Категория: Integrations
Включает интеграции с AmoCRM, FASHN, Telegram, NanoBanana и другими сервисами.
"""

from .amocrm_tools import AMOCRM_TOOLS
from .fashn_tools import FASHN_TOOLS
from .nano_banana_tools import NANO_BANANA_TOOLS
from .telegram_channel_tools import publish_to_telegram_channel

__all__ = [
    "AMOCRM_TOOLS",
    "FASHN_TOOLS",
    "NANO_BANANA_TOOLS",
    "publish_to_telegram_channel",
]

