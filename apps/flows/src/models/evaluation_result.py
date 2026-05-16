"""
Модель EvaluationResult - результат оценки тест-кейса.
"""

from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class EvaluationResult(BaseModel):
    """
    Результат выполнения тест-кейса.

    Первичный ключ: (flow_id, branch_id, run_date, iteration).

    scores - унифицированная структура оценок:
    {"attr_name": float_or_bool, ...}

    Если тест возвращает одну оценку, она хранится как {"result": value}
    """

    flow_id: str = Field(..., description="ID агента")
    branch_id: str = Field(..., description="ID skill")
    run_date: date = Field(..., description="Дата запуска")
    iteration: int = Field(..., description="Номер итерации за день")
    test_case_id: str = Field(..., description="ID тест-кейса")
    task_id: str | None = Field(default=None, description="ID задачи для трейсинга")

    status: str = Field(..., description="Статус: passed, failed, error, timeout")
    duration_ms: int = Field(..., description="Длительность в миллисекундах")
    turns_count: int = Field(default=0, description="Количество итераций диалога")

    dialog: list[dict[str, Any]] = Field(
        default_factory=list, description="История диалога [{role, content}, ...]"
    )

    scores: dict[str, float | bool] | None = Field(
        default=None, description="Оценки {attr_name: score/passed}"
    )
    judge_feedback: str | None = Field(default=None, description="Комментарий судьи")

    error: str | None = Field(default=None, description="Сообщение об ошибке")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_id(self) -> str:
        """Возвращает составной ID для хранения."""
        return f"{self.flow_id}:{self.branch_id}:{self.run_date.isoformat()}:{self.iteration}:{self.test_case_id}"

    def get_total_score(self) -> float | None:
        """
        Вычисляет общую оценку из scores.

        bool преобразуется: True -> 10.0, False -> 0.0
        float используется как есть.

        Returns:
            Среднее значение всех оценок или None если scores пуст
        """
        if not self.scores:
            return None

        values = []
        for v in self.scores.values():
            if isinstance(v, bool):
                values.append(10.0 if v else 0.0)
            else:
                values.append(float(v))

        return sum(values) / len(values) if values else None

    def is_passed(self) -> bool:
        """
        Определяет пройден ли тест на основе scores.

        Тест пройден если все bool значения True и все float >= 5.0
        """
        if not self.scores:
            return self.status == "passed"

        for v in self.scores.values():
            if isinstance(v, bool) and not v:
                return False
            if isinstance(v, (int, float)) and v < 5.0:
                return False

        return True


class EvaluationRunSummary(BaseModel):
    """
    Сводка по запуску всех тестов для skill.
    """

    flow_id: str
    branch_id: str
    run_date: date
    iteration: int
    started_at: datetime
    finished_at: datetime | None = None

    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    error_tests: int = 0

    average_score: float | None = None
    status: str = Field(default="running", description="running, passed, failed, partial")
