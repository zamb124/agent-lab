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

        Raises:
            EntityDeletionError: исходный шаг упал, компенсация прошла успешно.
            SagaCompensationError: компенсация тоже сломалась — БД в неконсистентном
                состоянии, требуется ручное вмешательство (caller обязан записать
                инцидент в workflow_events / alerting).
        """
        try:
            for step in self._steps:
                if step.execute_fn:
                    logger.info(f"Executing saga step: {step.name}")
                    await step.execute_fn()

                step.executed = True

            logger.info(f"Saga completed successfully ({len(self._steps)} steps)")
            return True

        except Exception as execute_error:
            logger.error(f"Saga failed at step, compensating: {execute_error}")
            try:
                await self._compensate()
            except SagaCompensationError as compensation_error:
                compensation_error.__cause__ = execute_error
                raise
            raise EntityDeletionError(f"Cascade delete failed: {execute_error}") from execute_error

    async def _compensate(self) -> None:
        """
        Откатывает выполненные шаги в обратном порядке.

        Контракт Zero-Guess: если хотя бы одна компенсация упала — БД осталась
        в inconsistent-состоянии (удалили relationships, но не смогли вернуть
        attachments, и наоборот). Раньше ошибка глушилась в `logger.error`,
        caller получал только исходный `EntityDeletionError` и не знал, что
        откат тоже сломался; запись о повреждении не оставалась нигде, кроме
        текстового лога.

        Теперь каждая упавшая компенсация:
        - агрегируется (продолжаем откатывать остальные шаги, чтобы откатить
          максимум возможного);
        - после прохода всех шагов поднимается `SagaCompensationError` с
          перечнем шагов, требующих ручного вмешательства.

        Caller обязан поймать `SagaCompensationError` и записать инцидент в
        `workflow_events` / алертинг — это уровень saga-owner, а не самой saga.
        """
        compensation_failures: list[tuple[str, BaseException]] = []
        for step in reversed(self._steps):
            if step.executed and step.compensate_fn:
                try:
                    logger.info(f"Compensating step: {step.name}")
                    await step.compensate_fn()
                except Exception as comp_error:
                    logger.error(
                        f"Compensation failed for {step.name}: {comp_error}. Manual intervention required!"
                    )
                    compensation_failures.append((step.name, comp_error))
        if compensation_failures:
            failed_names = ", ".join(name for name, _ in compensation_failures)
            raise SagaCompensationError(
                f"Saga compensation failed for steps: {failed_names}",
                failures=compensation_failures,
            )


class EntityDeletionError(Exception):
    """Ошибка каскадного удаления entity."""


class SagaCompensationError(Exception):
    """
    Откат saga завершился с ошибками.

    Атрибут `failures` — список `(step_name, original_exception)` для
    диагностики и записи в `workflow_events`.
    """

    def __init__(self, message: str, *, failures: list[tuple[str, BaseException]]) -> None:
        super().__init__(message)
        self.failures: list[tuple[str, BaseException]] = failures
