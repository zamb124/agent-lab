"""
Базовый класс для test runners.
"""

import time
import uuid
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, AsyncIterator, Dict, List, Optional

from apps.agents.src.models import TestCaseConfig
from core.context import Context
from core.logging import get_logger
from core.tracing import get_tracer

logger = get_logger(__name__)


class BaseTestRunner(ABC):
    """Базовый класс для запуска тест-кейсов."""

    def __init__(
        self,
        agent_id: str,
        skill_id: str,
        run_date: date,
        iteration: int,
    ):
        self.agent_id = agent_id
        self.skill_id = skill_id
        self.run_date = run_date
        self.iteration = iteration

    @abstractmethod
    def run(
        self, test_case: TestCaseConfig, test_case_id: str, task_id: Optional[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Запускает тест-кейс со стримингом событий.

        Args:
            test_case: Конфигурация тест-кейса
            test_case_id: ID тест-кейса
            task_id: ID задачи для трейсинга (если не указан, генерируется автоматически)

        Yields:
            События:
            - {"type": "user", "content": ...} - сообщение пользователя
            - {"type": "assistant", "content": ...} - ответ ассистента
            - {"type": "result", "status": ..., "duration_ms": ..., ...} - финальный результат
        """
        pass

    async def send_message(
        self,
        content: str,
        session_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        is_resume: bool = False,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Отправляет сообщение в агента и возвращает результат.

        Args:
            content: Текст сообщения
            session_id: ID сессии (если None - создаётся новая)
            files: Файлы для отправки
            is_resume: Продолжение после interrupt
            task_id: ID задачи для трейсинга (если None - создаётся новый)

        Returns:
            Результат выполнения задачи
        """
        if session_id is None:
            session_id = f"eval:{self.agent_id}:{uuid.uuid4()}"

        if task_id is None:
            task_id = str(uuid.uuid4())
        context_id = session_id

        from core.models.identity_models import User, Company
        
        context = Context(
            user=User(
                user_id="evaluation_runner",
                name="Evaluation Runner",
                groups=["admin"],
            ),
            channel="evaluation",
            active_company=Company(company_id="system", name="System"),
        )

        # Создаём trace_context для передачи в worker
        # Всегда создаём, worker сам решает сохранять ли spans
        tracer = get_tracer()
        trace_ctx = tracer.create_trace_context(
            user_id="evaluation_runner",
            user_name="Evaluation Runner",
            user_groups=["admin"],
            task_id=task_id,
            context_id=context_id,
            agent_id=self.agent_id,
            skill_id=self.skill_id,
            channel="a2a",
            is_resume=is_resume,
        )
        trace_context_dict = trace_ctx.model_dump(exclude_none=False)

        from apps.agents.src.tasks.agent_tasks import process_agent_task
        
        task = await process_agent_task.kiq(
            agent_id=self.agent_id,
            session_id=session_id,
            user_id="evaluation_runner",
            content=content,
            skill_id=self.skill_id,
            channel="a2a",
            task_id=task_id,
            context_id=context_id,
            metadata={"evaluation": True},
            is_resume=is_resume,
            files=files,
            context_data=context.model_dump(exclude_none=False),
            trace_context=trace_context_dict,
        )

        result = await task.wait_result()

        if result.is_err:
            raise RuntimeError(f"Task failed: {result.error}")

        return result.return_value

    @staticmethod
    def measure_time():
        """Возвращает функцию для измерения времени в мс."""
        start = time.perf_counter()

        def elapsed_ms() -> int:
            return int((time.perf_counter() - start) * 1000)

        return elapsed_ms
