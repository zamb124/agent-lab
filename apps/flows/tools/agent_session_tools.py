"""
Тулы жизненного цикла ответа агента: рассуждение, ввод пользователя, самопроверка, финальный ответ, завершение.

Группа для ReAct: reason, ask_user, self_check, final_answer, finish.
"""

from typing import Any, Dict, List, Optional

from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools import tool


@tool(
    name="reason",
    description="Запиши свои рассуждения перед принятием решения. Опиши: что наблюдаешь, анализ ситуации, план действий, следующий шаг.",
    tags=["reasoning", "internal"],
    react_role=ReactToolRole.REASON,
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
)
async def ask_user(question: str, state: Optional[dict] = None) -> str:
    raise FlowInterrupt(question=question)


@tool(
    name="self_check",
    description="Самопроверка гипотезы. Требует указать гипотезу, подтверждающие и противоречащие факты, результат.",
    tags=["validation"],
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
)
async def finish(answer: str, state: Optional[dict] = None) -> str:
    return answer
