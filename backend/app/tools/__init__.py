"""
Инструменты для агентов.
"""

from .calc_tools import CALC_TOOLS
from .fashn_tools import FASHN_TOOLS
from .file_tools import FILE_TOOLS
from .standard import STANDARD_TOOLS
from .weather_tools import WEATHER_TOOLS
from .voice_tools import VOICE_TOOLS

# Все доступные инструменты
ALL_TOOLS = (
    CALC_TOOLS +
    FASHN_TOOLS +
    FILE_TOOLS +
    STANDARD_TOOLS +
    WEATHER_TOOLS +
    VOICE_TOOLS
)

__all__ = [
    "CALC_TOOLS",
    "FASHN_TOOLS", 
    "FILE_TOOLS",
    "STANDARD_TOOLS",
    "WEATHER_TOOLS",
    "VOICE_TOOLS",
    "ALL_TOOLS",
]
