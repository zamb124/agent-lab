"""
Утилиты для работы со state в inline коде.
"""

from __future__ import annotations

import base64
import copy
import pathlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.message_metadata import MESSAGE_SOURCE_EVAL
from apps.flows.src.utils import extract_json_from_response
from core.errors import SafeEvalError
from core.state.mutation_policy import forbid_frozen_update_key

if TYPE_CHECKING:
    from core.state import ExecutionState

UI_EVENTS_KEY = "ui_events_pending"


def deep_copy_state(state: 'ExecutionState | dict') -> 'ExecutionState | dict':
    """
    Глубокое копирование state.

    Args:
        state: Исходный state (ExecutionState или dict)

    Returns:
        Копия state
    """
    from core.state import ExecutionState

    if isinstance(state, ExecutionState):
        return ExecutionState.model_validate(state.model_dump(exclude_none=False))
    elif isinstance(state, dict):
        return copy.deepcopy(state)
    else:
        raise SafeEvalError("state must be ExecutionState or dict")


def merge_state(base: 'ExecutionState | dict', updates: dict) -> 'ExecutionState | dict':
    """
    Безопасный merge двух state.

    Args:
        base: Базовый state (ExecutionState или dict)
        updates: Обновления (dict)

    Returns:
        Объединенный state
    """
    from core.state import ExecutionState

    if isinstance(base, ExecutionState):
        if not isinstance(updates, dict):
            raise SafeEvalError("updates must be a dict")
        for key, value in updates.items():
            forbid_frozen_update_key(key, reason="merge")
            if key == "prompt_history" and value is not None:
                value = ExecutionState._normalize_prompt_history(value)
            setattr(base, key, value)
        return base
    elif isinstance(base, dict):
        if not isinstance(updates, dict):
            raise SafeEvalError("updates must be a dict")
    else:
        raise SafeEvalError("base must be ExecutionState or dict")

    result = copy.deepcopy(base)
    for key, value in updates.items():
        forbid_frozen_update_key(key, reason="merge")
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_state(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def get_nested(data: 'ExecutionState | dict', path: str, default: Any = None) -> Any:
    """
    Получение вложенного значения по пути.

    Args:
        data: ExecutionState или словарь
        path: Путь через точку (например, "user.name")
        default: Значение по умолчанию

    Returns:
        Значение по пути или default
    """
    from core.state import ExecutionState

    keys = path.split(".")
    result = data

    for key in keys:
        if isinstance(result, ExecutionState):
            result = getattr(result, key, None)
        elif isinstance(result, dict):
            result = result.get(key)
        else:
            return default

        if result is None:
            return default

    return result


def set_nested(data: 'ExecutionState | dict', path: str, value: Any) -> 'ExecutionState | dict':
    """
    Установка вложенного значения по пути.

    Args:
        data: ExecutionState или словарь
        path: Путь через точку (например, "user.name")
        value: Значение для установки

    Returns:
        Модифицированный data
    """
    from core.state import ExecutionState

    keys = path.split(".")

    if isinstance(data, ExecutionState):
        forbid_frozen_update_key(keys[0], reason="merge")
        if len(keys) == 1:
            setattr(data, keys[0], value)
        else:
            current = data
            for key in keys[:-1]:
                if not hasattr(current, key) or getattr(current, key) is None:
                    setattr(current, key, {})
                current = getattr(current, key)
                if not isinstance(current, dict):
                    raise SafeEvalError(f"Cannot set nested value: {key} is not a dict")
            current[keys[-1]] = value
        return data
    elif isinstance(data, dict):
        forbid_frozen_update_key(keys[0], reason="merge")
        current = data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        return data
    else:
        raise SafeEvalError("data must be ExecutionState or dict")


def get_files(state: 'ExecutionState | dict') -> List[Dict[str, Any]]:
    """
    Возвращает список файлов из state.

    Args:
        state: Текущий state (ExecutionState или dict)

    Returns:
        Список файлов [{name, path, mime_type, size}, ...]
    """
    from core.state import ExecutionState

    if isinstance(state, ExecutionState):
        return state.files or []
    elif isinstance(state, dict):
        return state.get("files", [])
    else:
        return []


def find_file(files: List[Dict[str, Any]], name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Ищет файл в списке state.files по имени.

    Точное совпадение по полю name, затем case-insensitive подстрока.
    Без name — последний элемент списка (как у read_file без file_name).

    Args:
        files: Список записей файлов (state.files)
        name: Имя файла для поиска

    Returns:
        Запись файла или None
    """
    if not files:
        return None
    if not name:
        return files[-1]
    for f in files:
        if f.get("name") == name:
            return f
    name_lower = name.lower()
    for f in files:
        if name_lower in (f.get("name") or "").lower():
            return f
    return None


def read_path_bytes(file_path: str, mode: str = "rb") -> bytes:
    """
    Читает сырые байты или текст с диска по пути (без семантики документа).

    Args:
        file_path: Путь к файлу
        mode: Режим чтения ("rb" для бинарного, "r" для текстового)

    Returns:
        Содержимое файла (bytes для "rb", str для "r")

    Raises:
        SafeEvalError: Если файл не найден или ошибка чтения
    """
    path = pathlib.Path(file_path)
    if not path.exists():
        raise SafeEvalError(f"File not found: {file_path}")

    if mode == "rb":
        return path.read_bytes()
    else:
        return path.read_text(encoding="utf-8")


def read_path_base64(file_path: str) -> str:
    """
    Читает файл и возвращает base64 строку.

    Args:
        file_path: Путь к файлу

    Returns:
        Base64 строка

    Raises:
        SafeEvalError: Если файл не найден или ошибка чтения
    """
    data = read_path_bytes(file_path, mode="rb")
    return base64.b64encode(data).decode("utf-8")


def get_user(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Возвращает информацию о пользователе из state.

    Args:
        state: Текущий state

    Returns:
        Информация о пользователе {id, groups}
    """
    return {"id": state.get("user_id", ""), "groups": state.get("user_groups", [])}


def get_tool_result(state: Dict[str, Any], tool_name: str) -> Any:
    """
    Возвращает результат выполнения tool.

    Args:
        state: Текущий state
        tool_name: Имя tool

    Returns:
        Результат tool или None
    """
    return state.get("tool_results", {}).get(tool_name)


def get_messages(state: Dict[str, Any]) -> List[Message]:
    """
    Возвращает историю сообщений из state.

    Args:
        state: Текущий state

    Returns:
        Список A2A Message
    """
    return state.get("messages", [])


def add_user_message(state: Dict[str, Any], content: str) -> Dict[str, Any]:
    """
    Добавляет сообщение пользователя в state.

    Args:
        state: Текущий state
        content: Текст сообщения

    Returns:
        Обновленный state
    """
    if "messages" not in state:
        state["messages"] = []

    task_id = state.get("task_id")
    message = Message(
        messageId=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=content))],
        taskId=task_id,
        metadata={"node_id": MESSAGE_SOURCE_EVAL},
    )
    state["messages"].append(message)
    return state


def add_agent_message(state: Dict[str, Any], content: str) -> Dict[str, Any]:
    """
    Добавляет сообщение агента в state.

    Args:
        state: Текущий state dict
        content: Текст сообщения

    Returns:
        Обновленный state dict
    """
    if "messages" not in state:
        state["messages"] = []

    task_id = state.get("task_id")
    message = Message(
        messageId=str(uuid.uuid4()),
        role=Role.agent,
        parts=[Part(root=TextPart(text=content))],
        taskId=task_id,
        metadata={"node_id": MESSAGE_SOURCE_EVAL},
    )
    state["messages"].append(message)
    return state


def ask_user(question: str) -> None:
    """
    Запрашивает информацию у пользователя через interrupt.

    Args:
        question: Вопрос для пользователя

    Raises:
        FlowInterrupt: Всегда, для прерывания выполнения
    """
    raise FlowInterrupt(question=question)


def extract_json(text: str) -> Any:
    """
    Извлекает JSON из текста.

    Поддерживает:
    - JSON в markdown блоке ```json ... ```
    - Прямой JSON объект или массив

    Args:
        text: Текст с JSON

    Returns:
        Распарсенный JSON или None
    """
    return extract_json_from_response(text)


def push_ui_event(
    state: "ExecutionState | dict | None",
    event_type: str,
    payload: Dict[str, Any],
    *,
    event_id: Optional[str] = None,
    version: str = "1.0.0",
    source: str = "assistant",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Добавляет UI событие в очередь state для последующей публикации в stream."""
    if state is None:
        raise SafeEvalError("state is required")
    if not isinstance(event_type, str) or not event_type.strip():
        raise SafeEvalError("event_type must be a non-empty string")
    if not isinstance(payload, dict):
        raise SafeEvalError("payload must be a dict")
    if not isinstance(version, str) or not version.strip():
        raise SafeEvalError("version must be a non-empty string")
    if not isinstance(source, str) or not source.strip():
        raise SafeEvalError("source must be a non-empty string")

    event = {
        "id": (event_id.strip() if isinstance(event_id, str) and event_id.strip() else str(uuid.uuid4())),
        "type": event_type.strip(),
        "payload": payload,
        "version": version.strip(),
        "timestamp": datetime.now(UTC).isoformat(),
        "source": source.strip(),
        "correlation_id": correlation_id.strip() if isinstance(correlation_id, str) and correlation_id.strip() else None,
    }
    events = get_nested(state, UI_EVENTS_KEY, default=None)
    if events is None:
        events = []
        set_nested(state, UI_EVENTS_KEY, events)
    if not isinstance(events, list):
        raise SafeEvalError(f"state.{UI_EVENTS_KEY} must be a list")
    events.append(event)
    return event


def push_ui_events(
    state: "ExecutionState | dict | None",
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Добавляет пачку UI событий в очередь state."""
    if not isinstance(events, list):
        raise SafeEvalError("events must be a list")
    queued: List[Dict[str, Any]] = []
    for item in events:
        if not isinstance(item, dict):
            raise SafeEvalError("each event must be a dict")
        event_type = item.get("type")
        payload = item.get("payload")
        event_id = item.get("id")
        version = item.get("version", "1.0.0")
        source = item.get("source", "assistant")
        correlation_id = item.get("correlation_id")
        if not isinstance(payload, dict):
            raise SafeEvalError("event payload must be a dict")
        queued.append(
            push_ui_event(
                state,
                event_type=event_type,
                payload=payload,
                event_id=event_id if isinstance(event_id, str) else None,
                version=version if isinstance(version, str) else "1.0",
                source=source if isinstance(source, str) else "assistant",
                correlation_id=correlation_id if isinstance(correlation_id, str) else None,
            )
        )
    return queued


def pop_ui_events(state: "ExecutionState | dict | None") -> List[Dict[str, Any]]:
    """Извлекает и очищает очередь UI событий из state."""
    if state is None:
        raise SafeEvalError("state is required")
    events = get_nested(state, UI_EVENTS_KEY, default=None)
    if events is None:
        return []
    if not isinstance(events, list):
        raise SafeEvalError(f"state.{UI_EVENTS_KEY} must be a list")
    extracted = list(events)
    set_nested(state, UI_EVENTS_KEY, [])
    return extracted
