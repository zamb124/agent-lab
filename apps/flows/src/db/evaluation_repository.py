"""
Репозиторий для результатов оценки.

Использует специфичную таблицу evaluation_results (не key-value).
"""

import json
from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import cast

from pydantic import TypeAdapter
from sqlalchemy import text

from apps.flows.src.models import (
    EvaluationDialogMessage,
    EvaluationResult,
    EvaluationScores,
    EvaluationStatus,
)
from core.db import Storage
from core.db.utils import get_rowcount
from core.logging import get_logger
from core.types import (
    JsonObject,
    parse_json_array,
    parse_json_object,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)
_EVALUATION_SCORES_ADAPTER: TypeAdapter[EvaluationScores] = TypeAdapter(EvaluationScores)
EvaluationResultRowValue = str | int | date | datetime | list[JsonObject] | JsonObject | None


class EvaluationRepository:
    """
    Репозиторий для работы с результатами оценки.

    Таблица evaluation_results имеет составной уникальный ключ:
    (flow_id, branch_id, run_date, iteration, test_case_id)
    """

    def __init__(self, storage: Storage):
        self._storage: Storage = storage

    async def save(self, result: EvaluationResult) -> int:
        """
        Сохраняет результат оценки.

        Args:
            result: Результат для сохранения

        Returns:
            ID записи
        """
        async with self._storage.get_session() as session:
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

            result_proxy = await session.execute(
                query,
                {
                    "p1": result.flow_id,
                    "p2": result.branch_id,
                    "p3": result.run_date,
                    "p4": result.iteration,
                    "p5": result.test_case_id,
                    "p6": result.task_id,
                    "p7": result.status,
                    "p8": result.duration_ms,
                    "p9": result.turns_count,
                    "p10": json.dumps(
                        [message.model_dump(mode="json") for message in result.dialog]
                    ) if result.dialog else None,
                    "p11": json.dumps(result.scores) if result.scores else None,
                    "p12": result.judge_feedback,
                    "p13": result.error,
                    "p14": result.created_at or datetime.now(timezone.utc),
                },
            )
            await session.commit()
            row = result_proxy.first()
            return row[0] if row else 0

    async def get_by_run(
        self,
        flow_id: str,
        branch_id: str,
        run_date: date,
        iteration: int | None = None,
    ) -> list[EvaluationResult]:
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
        async with self._storage.get_session() as session:
            if iteration is not None:
                query = text("""
                    SELECT * FROM evaluation_results
                    WHERE flow_id = :flow_id AND branch_id = :branch_id
                          AND run_date = :run_date AND iteration = :iteration
                    ORDER BY test_case_id
                """)
                result = await session.execute(
                    query,
                    {
                        "flow_id": flow_id,
                        "branch_id": branch_id,
                        "run_date": run_date,
                        "iteration": iteration,
                    },
                )
            else:
                query = text("""
                    SELECT * FROM evaluation_results
                    WHERE flow_id = :flow_id AND branch_id = :branch_id AND run_date = :run_date
                    ORDER BY iteration, test_case_id
                """)
                result = await session.execute(
                    query,
                    {
                        "flow_id": flow_id,
                        "branch_id": branch_id,
                        "run_date": run_date,
                    },
                )

            rows = result.mappings().all()
            return [
                self._row_to_model(cast(Mapping[str, EvaluationResultRowValue], row))
                for row in rows
            ]

    async def get_latest_results(
        self,
        flow_id: str,
        branch_id: str,
        limit: int = 10,
    ) -> list[EvaluationResult]:
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
        async with self._storage.get_session() as session:
            query = text("""
                SELECT * FROM evaluation_results
                WHERE flow_id = :flow_id AND branch_id = :branch_id
                ORDER BY run_date DESC, iteration DESC, created_at DESC, id DESC
                LIMIT :limit
            """)
            result = await session.execute(
                query,
                {
                    "flow_id": flow_id,
                    "branch_id": branch_id,
                    "limit": limit,
                },
            )
            rows = result.mappings().all()
            return [
                self._row_to_model(cast(Mapping[str, EvaluationResultRowValue], row))
                for row in rows
            ]

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
        async with self._storage.get_session() as session:
            query = text("""
                SELECT COALESCE(MAX(iteration), 0) + 1 as next_iteration
                FROM evaluation_results
                WHERE flow_id = :flow_id AND branch_id = :branch_id AND run_date = :run_date
            """)
            result = await session.execute(
                query,
                {
                    "flow_id": flow_id,
                    "branch_id": branch_id,
                    "run_date": run_date,
                },
            )
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
        async with self._storage.get_session() as session:
            query = text("""
                DELETE FROM evaluation_results
                WHERE run_date < CURRENT_DATE - CAST(:days AS INTEGER)
            """)
            result = await session.execute(query, {"days": days_to_keep})
            await session.commit()
            count = get_rowcount(result)
            logger.info(f"Удалено {count} старых результатов оценки")
            return count

    def _row_to_model(self, row: Mapping[str, EvaluationResultRowValue]) -> EvaluationResult:
        """Конвертирует строку БД в модель."""
        flow_id = row["flow_id"]
        if not isinstance(flow_id, str):
            raise ValueError("evaluation_results.flow_id must be a string")
        branch_id = row["branch_id"]
        if not isinstance(branch_id, str):
            raise ValueError("evaluation_results.branch_id must be a string")
        run_date = row["run_date"]
        if not isinstance(run_date, date):
            raise ValueError("evaluation_results.run_date must be a date")
        iteration = row["iteration"]
        if not isinstance(iteration, int) or isinstance(iteration, bool):
            raise ValueError("evaluation_results.iteration must be an int")
        test_case_id = row["test_case_id"]
        if not isinstance(test_case_id, str):
            raise ValueError("evaluation_results.test_case_id must be a string")
        task_id = row["task_id"]
        if task_id is not None and not isinstance(task_id, str):
            raise ValueError("evaluation_results.task_id must be a string or null")
        status = row["status"]
        if status not in ("passed", "failed", "error", "timeout"):
            raise ValueError("evaluation_results.status has unsupported value")
        status_value = cast(EvaluationStatus, status)
        duration_ms = row["duration_ms"]
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool):
            raise ValueError("evaluation_results.duration_ms must be an int")
        turns_count = row["turns_count"]
        if turns_count is not None and (
            not isinstance(turns_count, int) or isinstance(turns_count, bool)
        ):
            raise ValueError("evaluation_results.turns_count must be an int or null")
        judge_feedback = row["judge_feedback"]
        if judge_feedback is not None and not isinstance(judge_feedback, str):
            raise ValueError("evaluation_results.judge_feedback must be a string or null")
        error = row["error"]
        if error is not None and not isinstance(error, str):
            raise ValueError("evaluation_results.error must be a string or null")
        created_at = row["created_at"]
        if not isinstance(created_at, datetime):
            raise ValueError("evaluation_results.created_at must be a datetime")

        dialog_raw = row["dialog"]
        if isinstance(dialog_raw, str):
            dialog_payload = parse_json_array(dialog_raw, "evaluation_results.dialog") if dialog_raw else []
        elif dialog_raw is None:
            dialog_payload = []
        else:
            dialog_payload = require_json_array(dialog_raw, "evaluation_results.dialog")
        dialog: list[EvaluationDialogMessage] = [
            EvaluationDialogMessage.model_validate(item) for item in dialog_payload
        ]

        scores_raw = row["scores"]
        if isinstance(scores_raw, str):
            scores_payload = parse_json_object(scores_raw, "evaluation_results.scores") if scores_raw else None
        elif scores_raw is None:
            scores_payload = None
        else:
            scores_payload = require_json_object(scores_raw, "evaluation_results.scores")
        scores: EvaluationScores | None = None
        if scores_payload is not None:
            scores = _EVALUATION_SCORES_ADAPTER.validate_python(scores_payload)

        return EvaluationResult(
            flow_id=flow_id,
            branch_id=branch_id,
            run_date=run_date,
            iteration=iteration,
            test_case_id=test_case_id,
            task_id=task_id,
            status=status_value,
            duration_ms=duration_ms,
            turns_count=turns_count or 0,
            dialog=dialog,
            scores=scores,
            judge_feedback=judge_feedback,
            error=error,
            created_at=created_at,
        )
