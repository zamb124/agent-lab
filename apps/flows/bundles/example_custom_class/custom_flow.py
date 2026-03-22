"""
Пример кастомного класса react-ноды (flow).

Демонстрирует свой класс ноды с логикой до и после ReAct через super().ainvoke().
"""

from datetime import datetime
from typing import Any, Dict, Optional

from apps.flows.src.runtime.nodes import LlmNode
from core.logging import get_logger

logger = get_logger(__name__)


class CustomFlowWithLogging(LlmNode):
    """
    Нода с расширенным логированием.

    Добавляет:
    - Логирование времени начала/окончания
    - Подсчет итераций
    - Сохранение метаданных в state
    """

    name = "custom_flow_with_logging"
    description = "Нода с расширенным логированием и метриками"

    async def ainvoke(
        self, input_data: Dict[str, Any], state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Выполняет ноду с логированием до и после."""
        if state is None:
            state = {"messages": [], "interrupts": []}

        start_time = datetime.now()
        logger.info(f"[{self.node_id}] Начало выполнения: {start_time.isoformat()}")

        if "__custom_metadata__" not in state:
            state["__custom_metadata__"] = {}

        state["__custom_metadata__"]["start_time"] = start_time.isoformat()
        state["__custom_metadata__"]["llm_node_class"] = self.__class__.__name__

        state = await super().ainvoke(input_data, state)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(f"[{self.node_id}] Завершение: {end_time.isoformat()}, длительность: {duration:.2f}s")

        state["__custom_metadata__"]["end_time"] = end_time.isoformat()
        state["__custom_metadata__"]["duration_seconds"] = duration

        return state


class CustomFlowWithPreprocessing(LlmNode):
    """
    Нода с предобработкой входных данных.

    Добавляет:
    - Нормализация текста
    - Контекст времени суток
    """

    name = "custom_flow_with_preprocessing"
    description = "Нода с предобработкой входных данных"

    async def ainvoke(
        self, input_data: Dict[str, Any], state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Выполняет ноду с предобработкой."""
        if state is None:
            state = {"messages": [], "interrupts": []}

        original_content = input_data.get("content", "")
        processed_content = self._preprocess(original_content)

        logger.info(f"[{self.node_id}] Предобработка: '{original_content[:50]}' -> '{processed_content[:50]}'")

        input_data["content"] = processed_content
        state["__original_content__"] = original_content

        return await super().ainvoke(input_data, state)

    def _preprocess(self, content: str) -> str:
        """Нормализация текста и контекст времени."""
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
