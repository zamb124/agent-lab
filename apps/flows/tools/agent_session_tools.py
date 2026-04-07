"""
Тулы жизненного цикла ответа агента: рассуждение, ввод пользователя, самопроверка, финальный ответ, завершение.

Группа для ReAct: reason, ask_user, self_check, final_answer, finish.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.eval.platform_services import get_operator_handoff_service
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools import tool
from core.state.interrupt import HandoffMode, OperatorTaskInterrupt

if TYPE_CHECKING:
    from core.state import ExecutionState


class ReasonArgs(BaseModel):
    """Аргументы тула reason: структурированные рассуждения перед действием."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    observation: str = Field(..., min_length=1, description="Что видишь в данных, сообщениях и контексте задачи.")
    analysis: str = Field(..., min_length=1, description="Разбор ситуации, связи фактов, риски и допущения.")
    plan: str = Field(..., min_length=1, description="План шагов до цели; что сделать дальше в общих чертах.")
    next_action: str = Field(
        ...,
        min_length=1,
        description="Конкретный следующий шаг (какой тул или ответ пользователю).",
    )


class AskUserArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        ...,
        min_length=1,
        description="Вопрос пользователю: одна ясная формулировка, без лишнего JSON вокруг.",
    )


class HitlOperatorTaskArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        ...,
        min_length=1,
        description="Текст для оператора: что нужно уточнить или сделать.",
    )
    task_title: str = Field(..., min_length=1, description="Краткий заголовок задачи в очереди оператора.")
    assignee_queue: str = Field(
        ...,
        min_length=1,
        description="Имя очереди или группы назначения (как настроено в продукте).",
    )
    handoff_mode: str = Field(
        default="single_reply",
        description="Режим: single_reply — один ответ оператора; takeover — полный перехват диалога.",
    )


class SelfCheckArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    hypothesis: str = Field(..., min_length=1, description="Проверяемая гипотеза или утверждение.")
    supporting_facts: List[str] = Field(
        ...,
        min_length=1,
        description="Список фактов из контекста, которые поддерживают гипотезу.",
    )
    verification_result: str = Field(
        ...,
        description='Итог проверки: например "confirmed" если гипотеза подтверждена, иначе другое значение.',
    )
    contradicting_facts: Optional[List[str]] = Field(
        None,
        description="Факты, которые противоречат гипотезе; можно не передавать.",
    )
    notes: Optional[str] = Field(None, description="Дополнительные заметки по проверке.")


class FinalAnswerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(..., min_length=1, description="Итоговый ответ пользователю.")
    justification: str = Field(..., min_length=1, description="Почему этот ответ следует из фактов и шагов.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Уверенность от 0 до 1.",
    )
    sources: Optional[List[str]] = Field(
        None,
        description="Ссылки на источники, цитаты или идентификаторы документов; опционально.",
    )


class FinishArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(..., min_length=1, description="Финальный текст, который увидит пользователь.")


@tool(
    name="reason",
    description="Запиши свои рассуждения перед принятием решения. Опиши: что наблюдаешь, анализ ситуации, план действий, следующий шаг.",
    tags=["reasoning", "internal"],
    react_role=ReactToolRole.REASON,
    args_schema=ReasonArgs,
)
async def reason(
    observation: str,
    analysis: str,
    plan: str,
    next_action: str,
    state: Optional[Dict[str, Any]] = None,
) -> str:
    if state is not None:
        reasoning_entry = {
            "observation": observation,
            "analysis": analysis,
            "plan": plan,
            "next_action": next_action,
        }
        if "reasoning_history" not in state:
            state["reasoning_history"] = []
        state["reasoning_history"].append(reasoning_entry)
        state["pending_reasoning"] = reasoning_entry

    return f"Рассуждения записаны. Выполняй: {next_action}"


@tool(
    name="ask_user",
    description="Задает вопрос пользователю и ожидает ответ. Используй когда нужна информация от пользователя.",
    tags=["misc"],
    args_schema=AskUserArgs,
)
async def ask_user(question: str, state: Optional[dict] = None) -> str:
    raise FlowInterrupt(question=question)


@tool(
    name="hitl_operator_task",
    description="Ставит выполнение на паузу до обработки оператором: заголовок задачи, очередь назначения, текст статуса для пользователя в чате.",
    tags=["misc", "hitl"],
    args_schema=HitlOperatorTaskArgs,
)
async def hitl_operator_task(
    question: str,
    task_title: str,
    assignee_queue: str,
    handoff_mode: str = "single_reply",
    state: Optional["ExecutionState"] = None,
) -> str:
    if state is None:
        raise ValueError("hitl_operator_task: параметр state обязателен")

    mode = HandoffMode(handoff_mode)
    handoff = get_operator_handoff_service()
    cid, op_task_id = await handoff.register_handoff(
        state,
        question=question.strip(),
        task_title=task_title.strip(),
        assignee_queue_slug=assignee_queue.strip(),
        handoff_mode=mode,
    )
    raise FlowInterrupt(
        body=OperatorTaskInterrupt(
            question=question.strip(),
            task_title=task_title.strip(),
            assignee_queue=assignee_queue.strip(),
            handoff_mode=mode,
            operator_task_id=op_task_id,
        ),
        correlation_id=cid,
    )


@tool(
    name="self_check",
    description="Самопроверка гипотезы. Требует указать гипотезу, подтверждающие и противоречащие факты, результат.",
    tags=["validation"],
    args_schema=SelfCheckArgs,
)
async def self_check(
    hypothesis: str,
    supporting_facts: List[str],
    verification_result: str,
    contradicting_facts: List[str] = None,
    notes: str = None,
    state: Optional[dict] = None,
) -> dict:
    return {
        "hypothesis": hypothesis,
        "supporting_facts": supporting_facts,
        "contradicting_facts": contradicting_facts or [],
        "verification_result": verification_result,
        "notes": notes,
        "is_confirmed": verification_result == "confirmed",
    }


@tool(
    name="final_answer",
    description="Формирует финальный обоснованный ответ. Требует указать ответ, обоснование, уверенность и источники.",
    tags=["validation"],
    react_role=ReactToolRole.EXIT,
    args_schema=FinalAnswerArgs,
)
async def final_answer(
    answer: str,
    justification: str,
    confidence: float,
    sources: List[str] = None,
    state: Optional[dict] = None,
) -> dict:
    return {
        "answer": answer,
        "justification": justification,
        "confidence": confidence,
        "sources": sources or [],
    }


@tool(
    name="finish",
    description="Завершает выполнение и возвращает финальный ответ пользователю",
    tags=["misc"],
    react_role=ReactToolRole.EXIT,
    args_schema=FinishArgs,
)
async def finish(answer: str, state: Optional[dict] = None) -> str:
    return answer
