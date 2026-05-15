"""
Пример кастомного класса react-ноды (flow).

Демонстрирует свой класс ноды с логикой до и после ReAct через super().ainvoke().
"""

from datetime import datetime
from typing import Any, Dict

from apps.flows.src.runtime.nodes import LlmNode
from core.logging import get_logger
from core.state import ExecutionState

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

    async def _run_impl(
        self, state: ExecutionState, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Выполняет ноду с логированием до и после."""
        start_time = datetime.now()
        logger.info(f"[{self.node_id}] Начало выполнения: {start_time.isoformat()}")

        metadata_raw = state.variables.get("__custom_metadata__")
        metadata: Dict[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}
        state.variables["__custom_metadata__"] = metadata

        metadata["start_time"] = start_time.isoformat()
        metadata["llm_node_class"] = self.__class__.__name__

        result = await super()._run_impl(state, inputs)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(f"[{self.node_id}] Завершение: {end_time.isoformat()}, длительность: {duration:.2f}s")

        metadata["end_time"] = end_time.isoformat()
        metadata["duration_seconds"] = duration

        return result if isinstance(result, dict) else {"result": result}


class CustomFlowWithPreprocessing(LlmNode):
    """
    Нода с предобработкой входных данных.

    Добавляет:
    - Нормализация текста
    - Контекст времени суток
    """

    name = "custom_flow_with_preprocessing"
    description = "Нода с предобработкой входных данных"

    async def _run_impl(
        self, state: ExecutionState, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Выполняет ноду с предобработкой."""
        original_content = str(inputs.get("content", ""))
        processed_content = self._preprocess(original_content)

        logger.info(f"[{self.node_id}] Предобработка: '{original_content[:50]}' -> '{processed_content[:50]}'")

        inputs["content"] = processed_content
        state.variables["__original_content__"] = original_content

        result = await super()._run_impl(state, inputs)
        return result if isinstance(result, dict) else {"result": result}

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
