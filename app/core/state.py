"""
State для агентов.
Единый state доступный во всех типах агентов (ReAct и StateGraph) и в тулах через контекст.
"""

from typing import Annotated, TypedDict, Dict, Any, List
from langgraph.graph.message import add_messages


def merge_store(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """
    Умное слияние store с сохранением вложенности.
    Если оба значения dict - мержим, иначе перезаписываем.
    """
    result = left.copy()
    for key, value in right.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result


class State(TypedDict, total=False):
    """
    Единый state для всех типов агентов.
    
    Доступен:
    - В StateGraph агентах как state параметр нод
    - В ReAct агентах через state_schema
    - В тулах через get_state() из контекста
    
    Поля:
    - messages: История диалога (автоматически персистится)
    - store: Сессионное хранилище для любых данных агентов (автоматически персистится)
    - remaining_steps: Счетчик оставшихся шагов для ReAct агентов
    - task_id: ID текущей задачи
    - session_id: ID текущей сессии
    - user_id: ID пользователя
    """
    
    messages: Annotated[List, add_messages]
    store: Annotated[Dict[str, Any], merge_store]
    remaining_steps: int
    
    task_id: str
    session_id: str
    user_id: str


def get_default_state() -> State:
    """Возвращает пустой state с дефолтными значениями"""
    return {
        "messages": [],
        "store": {},
        "remaining_steps": 25,
        "task_id": "",
        "session_id": "",
        "user_id": "",
    }
