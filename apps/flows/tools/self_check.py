"""
Self Check - инструмент для самопроверки анализа перед финальным ответом.
"""

from typing import List, Optional

from apps.flows.src.tools import tool


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
    """Возвращает результат самопроверки."""
    return {
        "hypothesis": hypothesis,
        "supporting_facts": supporting_facts,
        "contradicting_facts": contradicting_facts or [],
        "verification_result": verification_result,
        "notes": notes,
        "is_confirmed": verification_result == "confirmed",
    }
