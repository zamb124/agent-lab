"""
Модель EvaluationResult - результат оценки тест-кейса.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, NotRequired, TypedDict

from pydantic import Field

from core.clients.llm.messages import LLMToolCall
from core.models import StrictBaseModel

EvaluationStatus = Literal["passed", "failed", "error", "timeout"]
EvaluationRunStatus = Literal["running", "passed", "failed", "partial", "error"]
EvaluationDialogRole = Literal["user", "assistant", "tester"]
EvaluationScoreValue = float | bool
EvaluationScores = dict[str, EvaluationScoreValue]


class EvaluationDialogMessage(StrictBaseModel):
    """Одна реплика evaluation-диалога, сохраняемая в результатах."""

    role: EvaluationDialogRole
    content: str


class EvaluationJudgeResult(StrictBaseModel):
    """Строгий JSON-контракт ответа judge-ноды."""

    scores: EvaluationScores = Field(default_factory=dict)
    total_score: float | None = None
    passed: bool | None = None
    feedback: str | None = None


class EvaluationLLMResponse(StrictBaseModel):
    """Собранный ответ LLM evaluation-ноды из A2A stream-событий."""

    content: str = ""
    reasoning: str | None = None
    tool_calls: list[LLMToolCall] | None = None


class EvaluationStartEvent(TypedDict):
    type: Literal["start"]
    test_case_id: str
    name: str


class EvaluationErrorEvent(TypedDict):
    type: Literal["error"]
    message: str


class EvaluationMessageEvent(TypedDict):
    type: Literal["user", "assistant"]
    content: str


class EvaluationResultEvent(TypedDict):
    type: Literal["result"]
    status: EvaluationStatus
    duration_ms: int
    task_id: str
    context_id: str
    turns_count: NotRequired[int]
    scores: NotRequired[EvaluationScores]
    dialog: NotRequired[list[EvaluationDialogMessage]]
    judge_feedback: NotRequired[str | None]
    error: NotRequired[str]


class EvaluationRunStartEvent(TypedDict):
    type: Literal["run_start"]
    flow_id: str
    branch_id: str
    run_date: str
    iteration: int
    total_tests: int


class EvaluationTestStartEvent(TypedDict):
    type: Literal["test_start"]
    test_case_id: str
    name: str


class EvaluationTestResultEvent(TypedDict):
    type: Literal["test_result"]
    test_case_id: str
    status: EvaluationStatus
    duration_ms: NotRequired[int]
    dialog: NotRequired[list[EvaluationDialogMessage]]
    scores: NotRequired[EvaluationScores | None]
    total_score: NotRequired[float | None]
    judge_feedback: NotRequired[str | None]
    error: NotRequired[str | None]


class EvaluationSummaryEvent(TypedDict):
    type: Literal["summary"]
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_tests: int
    average_score: float | None
    status: Literal["passed", "failed", "partial"]


EvaluationRunnerEvent = EvaluationMessageEvent | EvaluationResultEvent
EvaluationServiceStreamEvent = (
    EvaluationStartEvent | EvaluationErrorEvent | EvaluationMessageEvent | EvaluationResultEvent
)
EvaluationAllTestsStreamEvent = (
    EvaluationRunStartEvent
    | EvaluationErrorEvent
    | EvaluationTestStartEvent
    | EvaluationTestResultEvent
    | EvaluationSummaryEvent
)


class EvaluationResult(StrictBaseModel):
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

    status: EvaluationStatus = Field(..., description="Статус: passed, failed, error, timeout")
    duration_ms: int = Field(..., description="Длительность в миллисекундах")
    turns_count: int = Field(default=0, description="Количество итераций диалога")

    dialog: list[EvaluationDialogMessage] = Field(
        default_factory=list, description="История диалога [{role, content}, ...]"
    )

    scores: EvaluationScores | None = Field(
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

        values: list[float] = []
        for v in self.scores.values():
            if isinstance(v, bool):
                values.append(10.0 if v else 0.0)
            else:
                values.append(v)

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
            if not isinstance(v, bool) and v < 5.0:
                return False

        return True


class EvaluationRunSummary(StrictBaseModel):
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
    status: EvaluationRunStatus = Field(default="running", description="running, passed, failed, partial")
