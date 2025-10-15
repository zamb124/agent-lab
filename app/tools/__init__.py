"""
Инструменты для агентов.

Категоризированы по типам:
- search/ - поиск информации (Tavily, Serper, web extract)
- analysis/ - анализ текста и данных
- session/ - работа с сессионным хранилищем
- calc/ - математические операции
- voice/ - распознавание и синтез речи
- files/ - работа с файлами
- integrations/ - интеграции (AmoCRM, FASHN, Telegram, NanoBanana)
- misc/ - разное (weather, rag, standard)
"""

from .integrations.amocrm_tools import AMOCRM_TOOLS
from .calc.calc_tools import CALC_TOOLS
from .integrations.fashn_tools import FASHN_TOOLS
from .files.file_tools import FILE_TOOLS
from .integrations.nano_banana_tools import NANO_BANANA_TOOLS
from .misc.standard import STANDARD_TOOLS
from .misc.weather_tools import WEATHER_TOOLS
from .voice.voice_tools import VOICE_TOOLS
from ..clients.amo_crm_integration import register_subdomain

# Все доступные инструменты
ALL_TOOLS = (
    AMOCRM_TOOLS +
    CALC_TOOLS +
    FASHN_TOOLS +
    FILE_TOOLS +
    NANO_BANANA_TOOLS +
    STANDARD_TOOLS +
    WEATHER_TOOLS +
    VOICE_TOOLS
)

__all__ = [
    "AMOCRM_TOOLS",
    "CALC_TOOLS",
    "FASHN_TOOLS",
    "FILE_TOOLS",
    "NANO_BANANA_TOOLS",
    "STANDARD_TOOLS",
    "WEATHER_TOOLS",
    "VOICE_TOOLS",
    "ALL_TOOLS",
    "register_subdomain",
]
