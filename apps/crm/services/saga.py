"""
Saga Pattern для каскадных операций через ChromaDB и PostgreSQL.

Обеспечивает транзакционность при работе с двумя хранилищами.
"""

from typing import List, Callable, Any, Optional, Awaitable
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
    execute_fn: Optional[Callable[[], Awaitable[Any]]]
    compensate_fn: Optional[Callable[[], Awaitable[Any]]]
    data: Any = None
    executed: bool = False


class EntityDeletionSaga:
    """
    Saga для каскадного удаления entity.
    
    Шаги:
    1. Удалить relationships (PostgreSQL)
    2. Удалить attachments (RAG + ChromaDB)
    3. Удалить entity (ChromaDB)
    
    При ошибке - откат в обратном порядке.
    """
    
    def __init__(self):
        self._steps: List[SagaStep] = []
    
    def add_step(self, step: SagaStep):
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
    
    async def _compensate(self):
        """Откатывает выполненные шаги в обратном порядке"""
        for step in reversed(self._steps):
            if step.executed and step.compensate_fn:
                try:
                    logger.info(f"Compensating step: {step.name}")
                    await step.compensate_fn()
                except Exception as comp_error:
                    logger.error(
                        f"Compensation failed for {step.name}: {comp_error}. "
                        f"Manual intervention may be required!"
                    )


class EntityDeletionError(Exception):
    """Ошибка каскадного удаления entity"""
    pass

