"""
Конфигурация для работы с Figma.
"""

import logging
from typing import Optional
from app.core.container import get_container
from app.core.context import get_context

logger = logging.getLogger(__name__)


class FigmaConfig:
    """Конфигурация Figma для текущего проекта"""

    def __init__(self):
        self._file_key: Optional[str] = None
        self._library_file_key: Optional[str] = None
        self._page_id: Optional[str] = None

    async def get_file_key(self) -> str:
        """File key текущего проекта Figma"""
        if not self._file_key:
            # Получаем из переменных компании
            context = get_context()
            if context and context.active_company:
                variables_service = get_container().variables_service
                file_key = await variables_service.get_var("figma_file_key")
                if file_key:
                    self._file_key = file_key
                else:
                    raise ValueError(
                        "figma_file_key не установлен. "
                        "Установите переменную figma_file_key для компании."
                    )
            else:
                raise ValueError("Нет активной компании в контексте")

        return self._file_key

    @property
    def library_file_key(self) -> str:
        """File key библиотеки Туту.ру"""
        # Константа для библиотеки Туту.ру
        return "XYL0E4cBCEfGJEWk7FIrwD"

    async def get_page_id(self) -> str:
        """ID страницы в файле"""
        if not self._page_id:
            # Можно получить из переменных или использовать дефолтную
            context = get_context()
            if context and context.active_company:
                variables_service = get_container().variables_service
                page_id = await variables_service.get_var("figma_page_id")
                if page_id:
                    self._page_id = page_id
                else:
                    # Дефолтная страница
                    self._page_id = "1:16"
            else:
                self._page_id = "1:16"

        return self._page_id


_figma_config: Optional[FigmaConfig] = None


async def get_figma_config() -> FigmaConfig:
    """Получить конфигурацию Figma"""
    global _figma_config
    if _figma_config is None:
        _figma_config = FigmaConfig()
    return _figma_config

