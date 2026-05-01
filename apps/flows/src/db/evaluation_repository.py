"""
Репозиторий для результатов оценки.

Использует специфичную таблицу evaluation_results (не key-value).
"""

import json
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import text

from core.logging import get_logger
from apps.flows.src.models import EvaluationResult
from core.db import Storage

logger = get_logger(__name__)


class EvaluationRepository:
    """
    Репозиторий для работы с результатами оценки.

    Таблица evaluation_results имеет составной уникальный ключ:
    (flow_id, branch_id, run_date, iteration, test_case_id)
    """

    def __init__(self, storage: Storage):
        self._storage = storage

    async def save(self, result: EvaluationResult) -> int:
        """
        Сохраняет результат оценки.

        Args:
            result: Результат для сохранения

        Returns:
            ID записи
        """
        async with self._storage._get_session() as session:
            query = text("""
                INSERT INTO evaluation_results
                    (flow_id, branch_id, run_date, iteration, test_case_id, task_id,
                     status, duration_ms, turns_count, dialog, scores,
                     judge_feedback, error, created_at)
                VALUES (:p1, :p2, :p3, :p4, :p5, :p6, :p7, :p8, :p9, :p10, :p11, :p12, :p13, :p14)
                ON CONFLICT (flow_id, branch_id, run_date, iteration, test_case_id)
                DO UPDATE SET
                    task_id = EXCLUDED.task_id,
                    status = EXCLUDED.status,
                    duration_ms = EXCLUDED.duration_ms,
                    turns_count = EXCLUDED.turns_count,
                    dialog = EXCLUDED.dialog,
                    scores = EXCLUDED.scores,
                    judge_feedback = EXCLUDED.judge_feedback,
                    error = EXCLUDED.error
                RETURNING id
            """)
            
            result_proxy = await session.execute(query, {
                "p1": result.flow_id,
                "p2": result.branch_id,
                "p3": result.run_date,
                "p4": result.iteration,
                "p5": result.test_case_id,
                "p6": result.task_id,
                "p7": result.status,
                "p8": result.duration_ms,
                "p9": result.turns_count,
                "p10": json.dumps(result.dialog) if result.dialog else None,
                "p11": json.dumps(result.scores) if result.scores else None,
                "p12": result.judge_feedback,
                "p13": result.error,
                "p14": result.created_at or datetime.now(timezone.utc),
            })
            await session.commit()
            row = result_proxy.first()
            return row[0] if row else 0

    async def get_by_run(
        self,
        flow_id: str,
        branch_id: str,
        run_date: date,
        iteration: Optional[int] = None,
    ) -> List[EvaluationResult]:
        """
        Получает все результаты для конкретного запуска.

        Args:
            flow_id: ID агента
            branch_id: ID skill
            run_date: Дата запуска
            iteration: Номер итерации (если None - все итерации за день)

        Returns:
            Список результатов
        """
        async with self._storage._get_session() as session:
            if iteration is not None:
                query = text("""
                    SELECT * FROM evaluation_results
                    WHERE flow_id = :flow_id AND branch_id = :branch_id
                          AND run_date = :run_date AND iteration = :iteration
                    ORDER BY test_case_id
                """)
                result = await session.execute(query, {
                    "flow_id": flow_id,
                    "branch_id": branch_id,
                    "run_date": run_date,
                    "iteration": iteration,
                })
            else:
                query = text("""
                    SELECT * FROM evaluation_results
                    WHERE flow_id = :flow_id AND branch_id = :branch_id AND run_date = :run_date
                    ORDER BY iteration, test_case_id
                """)
                result = await session.execute(query, {
                    "flow_id": flow_id,
                    "branch_id": branch_id,
                    "run_date": run_date,
                })
            
            rows = result.mappings().all()
            return [self._row_to_model(row) for row in rows]

    async def get_latest_results(
        self,
        flow_id: str,
        branch_id: str,
        limit: int = 10,
    ) -> List[EvaluationResult]:
        """
        Получает последние результаты для агента/skill.

        Сортировка: свежий run (run_date, iteration), внутри прогона — по
        created_at и id (последний сохранённый результат — первый в списке).

        Args:
            flow_id: ID агента
            branch_id: ID skill
            limit: Максимум записей

        Returns:
            Список результатов
        """
        async with self._storage._get_session() as session:
            query = text("""
                SELECT * FROM evaluation_results
                WHERE flow_id = :flow_id AND branch_id = :branch_id
                ORDER BY run_date DESC, iteration DESC, created_at DESC, id DESC
                LIMIT :limit
            """)
            result = await session.execute(query, {
                "flow_id": flow_id,
                "branch_id": branch_id,
                "limit": limit,
            })
            rows = result.mappings().all()
            return [self._row_to_model(row) for row in rows]

    async def get_next_iteration(self, flow_id: str, branch_id: str, run_date: date) -> int:
        """
        Возвращает следующий номер итерации для даты.

        Args:
            flow_id: ID агента
            branch_id: ID skill
            run_date: Дата

        Returns:
            Следующий номер итерации (начиная с 1)
        """
        async with self._storage._get_session() as session:
            query = text("""
                SELECT COALESCE(MAX(iteration), 0) + 1 as next_iteration
                FROM evaluation_results
                WHERE flow_id = :flow_id AND branch_id = :branch_id AND run_date = :run_date
            """)
            result = await session.execute(query, {
                "flow_id": flow_id,
                "branch_id": branch_id,
                "run_date": run_date,
            })
            row = result.first()
            return row[0] if row else 1

    async def delete_old_results(self, days_to_keep: int = 30) -> int:
        """
        Удаляет старые результаты.

        Args:
            days_to_keep: Сколько дней хранить

        Returns:
            Количество удалённых записей
        """
        async with self._storage._get_session() as session:
            query = text("""
                DELETE FROM evaluation_results
                WHERE run_date < CURRENT_DATE - CAST(:days AS INTEGER)
            """)
            result = await session.execute(query, {"days": days_to_keep})
            await session.commit()
            count = result.rowcount
            logger.info(f"Удалено {count} старых результатов оценки")
            return count

    def _row_to_model(self, row) -> EvaluationResult:
        """Конвертирует строку БД в модель."""
        dialog = row["dialog"]
        if isinstance(dialog, str):
            dialog = json.loads(dialog) if dialog else []

        scores = row["scores"]
        if isinstance(scores, str):
            scores = json.loads(scores) if scores else None

        return EvaluationResult(
            flow_id=row["flow_id"],
            branch_id=row["branch_id"],
            run_date=row["run_date"],
            iteration=row["iteration"],
            test_case_id=row["test_case_id"],
            task_id=row.get("task_id"),
            status=row["status"],
            duration_ms=row["duration_ms"],
            turns_count=row["turns_count"] or 0,
            dialog=dialog or [],
            scores=scores,
            judge_feedback=row["judge_feedback"],
            error=row["error"],
            created_at=row["created_at"],
        )
