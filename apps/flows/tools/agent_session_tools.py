"""
Тулы жизненного цикла ответа агента: рассуждение, ввод пользователя, финальный ответ, завершение.

Группа для ReAct: reason, ask_user, final_answer, finish.
"""

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.tool_call_context import get_active_tool_call_context
from apps.flows.src.services.operator_handoff_service import build_operator_handoff_command
from apps.flows.src.services.platform_facades import get_operator_handoff_service
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.state.interrupt import HandoffMode, OperatorTaskInterrupt
from core.types import JsonObject

if TYPE_CHECKING:
    from core.state import ExecutionState


class ReasonArgs(BaseModel):
    """Аргументы тула reason: структурированные рассуждения перед действием."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    observation: str = Field(..., min_length=1, description="Что видишь в данных, сообщениях и контексте задачи.")
    analysis: str = Field(..., min_length=1, description="Разбор ситуации, связи фактов, риски и допущения.")
    plan: str = Field(..., min_length=1, description="План шагов до цели; что сделать дальше в общих чертах.")
    next_action: str = Field(
        ...,
        min_length=1,
        description="Конкретный следующий шаг (какой тул или ответ пользователю).",
    )


class AskUserArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        ...,
        min_length=1,
        description="Вопрос пользователю: одна ясная формулировка, без лишнего JSON вокруг.",
    )


class HitlOperatorTaskArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

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


class FinalAnswerArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(..., min_length=1, description="Итоговый ответ пользователю.")
    justification: str = Field(..., min_length=1, description="Почему этот ответ следует из фактов и шагов.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Уверенность от 0 до 1.",
    )
    sources: list[str] | None = Field(
        None,
        description="Ссылки на источники, цитаты или идентификаторы документов; опционально.",
    )


@tool(
    name="reason",
    description="Запиши свои рассуждения перед принятием решения. Опиши: что наблюдаешь, анализ ситуации, план действий, следующий шаг.",
    tags=["reasoning", "internal"],
    react_role=ReactToolRole.REASON,
    parameters_model=ReasonArgs,
)
async def reason(
    observation: str,
    analysis: str,
    plan: str,
    next_action: str,
    *,
    state: "ExecutionState",
) -> str:
    reasoning_entry: JsonObject = {
        "observation": observation,
        "analysis": analysis,
        "plan": plan,
        "next_action": next_action,
    }
    state.reasoning_history.append(reasoning_entry)
    state.pending_reasoning = reasoning_entry

    return f"Рассуждения записаны. Выполняй: {next_action}"


@tool(
    name="ask_user",
    description="Задает вопрос пользователю и ожидает ответ. Используй когда нужна информация от пользователя.",
    tags=["misc"],
    parameters_model=AskUserArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def ask_user(question: str, *, state: "ExecutionState") -> str:
    _ = state
    raise FlowInterrupt(question=question)


@tool(
    name="hitl_operator_task",
    description="Ставит выполнение на паузу до обработки оператором: заголовок задачи, очередь назначения, текст статуса для пользователя в чате.",
    tags=["misc", "hitl"],
    parameters_model=HitlOperatorTaskArgs,
)
async def hitl_operator_task(
    question: str,
    task_title: str,
    assignee_queue: str,
    handoff_mode: str = "single_reply",
    *,
    state: "ExecutionState",
) -> str:
    mode = HandoffMode(handoff_mode)
    tool_context = get_active_tool_call_context()
    if tool_context is None:
        raise RuntimeError("hitl_operator_task requires active durable tool call context")
    command = build_operator_handoff_command(
        state=state,
        node_id=tool_context.node_id,
        tool_call_id=tool_context.tool_call_id,
    )
    handoff = get_operator_handoff_service()
    cid, op_task_id = await handoff.register_handoff(
        state,
        question=question.strip(),
        task_title=task_title.strip(),
        assignee_queue_slug=assignee_queue.strip(),
        handoff_mode=mode,
        command=command,
    )
    raise FlowInterrupt(
        body=OperatorTaskInterrupt(
            question=question.strip(),
            task_title=task_title.strip(),
            assignee_queue=assignee_queue.strip(),
            handoff_mode=mode,
            operator_task_id=op_task_id,
            handoff_command_id=command.idempotency_key,
            execution_branch_id=command.execution_branch_id,
            node_schedule_sequence=command.node_schedule_sequence,
            node_id=tool_context.node_id,
            tool_call_id=tool_context.tool_call_id,
        ),
        correlation_id=cid,
    )


@tool(
    name="final_answer",
    description="Формирует финальный обоснованный ответ. Требует указать ответ, обоснование, уверенность и источники.",
    tags=["validation"],
    react_role=ReactToolRole.EXIT,
    parameters_model=FinalAnswerArgs,
)
async def final_answer(
    answer: str,
    justification: str,
    confidence: float,
    sources: list[str] | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    return {
        "answer": answer,
        "justification": justification,
        "confidence": confidence,
        "sources": sources or [],
    }
