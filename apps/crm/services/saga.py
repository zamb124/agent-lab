"""
Saga Pattern для каскадных операций через PostgreSQL (crm_entities + vector_documents).

Обеспечивает транзакционность при работе с несколькими таблицами.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SagaStep:
    """
    Шаг Saga с компенсацией.

    Attributes:
        name: Название шага
        execute_fn: Функция выполнения (опционально, если уже выполнено)
        compensate_fn: Функция компенсации (откат)
        data: Данные для компенсации
        executed: Флаг выполнения
    """

    name: str
    execute_fn: Callable[[], Awaitable[None]] | None
    compensate_fn: Callable[[], Awaitable[None]] | None
    data: object | None = None
    executed: bool = False


class EntityDeletionSaga:
    """
    Saga для каскадного удаления entity.

    Шаги:
    1. Удалить relationships (PostgreSQL)
    2. Удалить attachments (S3 + vector_documents)
    3. Удалить entity (crm_entities + vector_documents)

    При ошибке - откат в обратном порядке.
    """

    def __init__(self) -> None:
        self._steps: list[SagaStep] = []

    def add_step(self, step: SagaStep) -> None:
        """Добавляет шаг в Saga"""
        self._steps.append(step)

    async def execute(self) -> bool:
        """
        Выполняет все шаги Saga.

        Returns:
            True если все успешно, Exception при ошибке
        """
        try:
            for step in self._steps:
                if step.execute_fn:
                    logger.info(f"Executing saga step: {step.name}")
                    await step.execute_fn()

                step.executed = True

            logger.info(f"Saga completed successfully ({len(self._steps)} steps)")
            return True

        except Exception as e:
            logger.error(f"Saga failed at step, compensating: {e}")
            await self._compensate()
            raise EntityDeletionError(f"Cascade delete failed: {e}") from e

    async def _compensate(self) -> None:
        """Откатывает выполненные шаги в обратном порядке"""
        for step in reversed(self._steps):
            if step.executed and step.compensate_fn:
                try:
                    logger.info(f"Compensating step: {step.name}")
                    await step.compensate_fn()
                except Exception as comp_error:
                    logger.error(
                        f"Compensation failed for {step.name}: {comp_error}. Manual intervention may be required!"
                    )


class EntityDeletionError(Exception):
    """Ошибка каскадного удаления entity"""

    pass
