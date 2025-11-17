"""
Инспектор для анализа и визуализации состояний агентов.
Работает с state_manager вместо checkpointer.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import asdict, is_dataclass

from app.core.state_manager import get_state_manager
from app.core.state import State

logger = logging.getLogger(__name__)


class StateInspector:
    """Инспектор для анализа и визуализации состояний агентов"""

    def __init__(self):
        self.state_manager = None

    async def _get_state_manager(self):
        """Ленивая загрузка state_manager"""
        if self.state_manager is None:
            self.state_manager = await get_state_manager()
        return self.state_manager

    async def get_checkpoint_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Алиас для обратной совместимости с CheckpointInspector"""
        return await self.get_state_history(session_id)

    async def get_state_history(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Получает историю состояний для session_id.
        В новой архитектуре у нас одно состояние на сессию, но можем вернуть его в формате истории.

        Args:
            session_id: ID сессии

        Returns:
            Список состояний с метаданными
        """
        state_manager = await self._get_state_manager()
        state = await state_manager.load_state(session_id)

        if not state:
            return []

        messages = state.get("messages", [])
        store = state.get("store", {})
        task_id = state.get("task_id", "")
        
        tool_calls = self._extract_tool_calls_from_messages(messages)
        store_vars = self._extract_store_variables(store)

        state_data = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "step": len(messages),
            "source": "agent_execution",
            "node_name": "agent",
            "task_id": task_id,
            "tool_calls": tool_calls,
            "store_variables": store_vars,
            "metadata": {
                "message_count": len(messages),
                "store_keys": list(store.keys()) if isinstance(store, dict) else []
            },
            "values": {
                "messages": self._sanitize_messages(messages),
                "store": store
            }
        }

        return [state_data]

    async def get_checkpoint_connections(self, session_id: str) -> Dict[str, Any]:
        """Алиас для обратной совместимости с CheckpointInspector"""
        return await self.get_state_connections(session_id)

    async def get_state_connections(self, session_id: str) -> Dict[str, Any]:
        """
        Получает связи между состояниями для session_id.
        В новой архитектуре у нас одно состояние, но возвращаем формат для совместимости.

        Args:
            session_id: ID сессии

        Returns:
            Словарь с информацией о связях состояний
        """
        states = await self.get_state_history(session_id)

        if not states:
            return {
                "session_id": session_id,
                "connections": [],
                "summary": {
                    "total_states": 0,
                    "total_checkpoints": 0,
                    "total_connections": 0,
                    "transition_stats": {}
                }
            }

        state_data = states[0]
        
        return {
            "session_id": session_id,
            "connections": [],
            "summary": {
                "total_states": 1,
                "total_checkpoints": 1,
                "total_connections": 0,
                "transition_stats": {},
                "first_state": state_data,
                "last_state": state_data
            }
        }

    async def get_timeline(self, session_id: str, include_values: bool = False) -> Dict[str, Any]:
        """
        Получает timeline представление выполнения агента.

        Args:
            session_id: ID сессии
            include_values: Включать ли детальные значения сообщений

        Returns:
            Словарь с timeline данными
        """
        states = await self.get_state_history(session_id)

        if not states:
            return {
                "session_id": session_id,
                "timeline": [],
                "tree": [],
                "summary": {"total_steps": 0}
            }

        state_data = states[0]
        
        timeline_entry = {
            "step": state_data["step"],
            "timestamp": state_data["timestamp"],
            "source": state_data["source"],
            "node_name": state_data["node_name"],
            "session_id": state_data["session_id"],
            "tool_calls": state_data.get("tool_calls", []),
            "store_variables": state_data.get("store_variables", {}),
            "task_id": state_data.get("task_id")
        }

        if include_values:
            timeline_entry["messages"] = state_data.get("values", {}).get("messages", [])

        all_tool_calls = timeline_entry["tool_calls"]
        tool_stats = {}
        for tool_call in all_tool_calls:
            name = tool_call.get("name", "unknown")
            tool_stats[name] = tool_stats.get(name, 0) + 1

        summary = {
            "total_steps": 1,
            "transition_stats": {},
            "tool_stats": tool_stats
        }

        tree = [{
            "session_id": state_data["session_id"],
            "step": state_data["step"],
            "timestamp": state_data["timestamp"],
            "source": state_data["source"],
            "node_name": state_data["node_name"],
            "tool_calls": state_data.get("tool_calls", []),
            "store_variables": state_data.get("store_variables", {}),
            "task_id": state_data.get("task_id"),
            "values": state_data.get("values", {}),
            "metadata": state_data.get("metadata", {}),
            "children": []
        }]

        return {
            "session_id": session_id,
            "timeline": [timeline_entry],
            "tree": tree,
            "summary": summary
        }

    def _extract_tool_calls_from_messages(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """Извлекает вызовы инструментов из сообщений"""
        tool_calls = []

        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    if isinstance(tool_call, dict):
                        tool_call_info = {
                            "name": str(tool_call.get("name", "unknown")),
                            "arguments": self._sanitize_for_json(tool_call.get("args") or tool_call.get("arguments", {})),
                            "id": str(tool_call.get("id", "")),
                            "type": str(tool_call.get("type", "function"))
                        }
                    else:
                        tool_call_info = {
                            "name": str(getattr(tool_call, "name", "unknown")),
                            "arguments": self._sanitize_for_json(getattr(tool_call, "args", {})),
                            "id": str(getattr(tool_call, "id", "")),
                            "type": str(getattr(tool_call, "type", "function"))
                        }
                    tool_calls.append(tool_call_info)

        return tool_calls

    def _extract_store_variables(self, store: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает переменные store"""
        if not isinstance(store, dict):
            return {}

        formatted_store = {}
        for key, value in store.items():
            if value is None:
                formatted_store[key] = None
            elif isinstance(value, (str, int, float, bool)):
                formatted_store[key] = value
            elif isinstance(value, list):
                if len(value) == 0:
                    formatted_store[key] = "[]"
                else:
                    formatted_store[key] = f"list({len(value)})"
            elif isinstance(value, dict):
                if len(value) == 0:
                    formatted_store[key] = "{}"
                else:
                    formatted_store[key] = f"dict({len(value)} keys)"
            else:
                formatted_store[key] = str(value)[:100] if len(str(value)) > 100 else str(value)

        return formatted_store

    def _sanitize_messages(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """Конвертирует сообщения в словари для JSON"""
        result = []
        for msg in messages:
            if hasattr(msg, "content"):
                msg_dict = {
                    "type": msg.__class__.__name__,
                    "content": str(msg.content),
                }
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    msg_dict["tool_calls"] = [
                        {
                            "name": getattr(tc, "name", "") if not isinstance(tc, dict) else tc.get("name", ""),
                            "args": getattr(tc, "args", {}) if not isinstance(tc, dict) else tc.get("args", {}),
                            "id": str(getattr(tc, "id", "")) if not isinstance(tc, dict) else str(tc.get("id", ""))
                        }
                        for tc in msg.tool_calls
                    ]
                result.append(msg_dict)
            elif isinstance(msg, dict):
                result.append(msg)
        return result

    def _sanitize_for_json(self, value: Any, _depth: int = 0) -> Any:
        """Рекурсивно очищает значение для JSON сериализации"""
        if _depth > 8:
            return str(value)

        if value is None or isinstance(value, (bool, int, float, str)):
            return value

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except Exception:
                return value.hex()

        if isinstance(value, dict):
            return {
                str(self._sanitize_for_json(k, _depth + 1)):
                    self._sanitize_for_json(v, _depth + 1)
                for k, v in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [self._sanitize_for_json(item, _depth + 1) for item in value]

        if is_dataclass(value):
            return self._sanitize_for_json(asdict(value), _depth + 1)

        for attr in ("model_dump", "dict", "to_dict"):
            if hasattr(value, attr) and callable(getattr(value, attr)):
                try:
                    result = getattr(value, attr)()
                    return self._sanitize_for_json(result, _depth + 1)
                except Exception:
                    continue

        if hasattr(value, "__dict__"):
            try:
                return self._sanitize_for_json(value.__dict__, _depth + 1)
            except Exception:
                pass

        return str(value)

