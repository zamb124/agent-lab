"""
Пример кастомного класса агента.

Демонстрирует как создать свой класс агента с дополнительной логикой
до и после выполнения основного ReAct цикла через super().ainvoke().
"""

from datetime import datetime
from typing import Any, Dict, Optional

from apps.agents.src.agent.nodes import ReactNode
from core.logging import get_logger

logger = get_logger(__name__)


class CustomAgentWithLogging(ReactNode):
    """
    Кастомный агент с расширенным логированием.
    
    Добавляет:
    - Логирование времени начала/окончания
    - Подсчет итераций
    - Сохранение метаданных в state
    """

    name = "custom_agent_with_logging"
    description = "Агент с расширенным логированием и метриками"

    async def ainvoke(
        self, input_data: Dict[str, Any], state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Выполняет агента с логированием до и после."""
        if state is None:
            state = {"messages": [], "interrupts": []}

        start_time = datetime.now()
        logger.info(f"[{self.node_id}] Начало выполнения: {start_time.isoformat()}")

        # Сохраняем метаданные в state
        if "__custom_metadata__" not in state:
            state["__custom_metadata__"] = {}
        
        state["__custom_metadata__"]["start_time"] = start_time.isoformat()
        state["__custom_metadata__"]["react_node_class"] = self.__class__.__name__

        # Вызываем базовую логику через super()
        state = await super().ainvoke(input_data, state)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(f"[{self.node_id}] Завершение: {end_time.isoformat()}, длительность: {duration:.2f}s")

        # Сохраняем результаты в state
        state["__custom_metadata__"]["end_time"] = end_time.isoformat()
        state["__custom_metadata__"]["duration_seconds"] = duration

        return state


class CustomAgentWithPreprocessing(ReactNode):
    """
    Кастомный агент с предобработкой входных данных.
    
    Добавляет:
    - Нормализация текста
    - Добавление контекста времени
    """

    name = "custom_agent_with_preprocessing"
    description = "Агент с предобработкой входных данных"

    async def ainvoke(
        self, input_data: Dict[str, Any], state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Выполняет агента с предобработкой."""
        if state is None:
            state = {"messages": [], "interrupts": []}

        # Предобработка: нормализация и добавление контекста
        original_content = input_data.get("content", "")
        processed_content = self._preprocess(original_content)
        
        logger.info(f"[{self.node_id}] Предобработка: '{original_content[:50]}' -> '{processed_content[:50]}'")

        input_data["content"] = processed_content
        state["__original_content__"] = original_content

        # Вызываем базовую логику через super()
        return await super().ainvoke(input_data, state)

    def _preprocess(self, content: str) -> str:
        """Предобработка текста."""
        content = " ".join(content.split())
        current_hour = datetime.now().hour
        if 6 <= current_hour < 12:
            time_context = "Сейчас утро."
        elif 12 <= current_hour < 18:
            time_context = "Сейчас день."
        elif 18 <= current_hour < 22:
            time_context = "Сейчас вечер."
        else:
            time_context = "Сейчас ночь."
        
        return f"{time_context} {content}"

