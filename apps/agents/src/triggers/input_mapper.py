"""
InputMapper - маппинг данных триггера в state.

Логика:
1. Payload автоматически записывается в state.triggers.{trigger_id}
2. output_mapping указывает какие данные куда положить в state
   Формат: {"куда_в_state": "откуда_из_payload"}
   Пути без префиксов!
"""

import re
from typing import Any, Dict

from core.logging import get_logger

logger = get_logger(__name__)


class InputMapper:
    """
    Маппер данных триггера в state.
    
    Payload автоматически записывается в state.triggers.{trigger_id}.
    output_mapping определяет какие данные куда положить.
    
    Пример output_mapping:
        {
            "content": "message.text",
            "variables.chat_id": "message.chat.id",
            "variables.username": "message.from.username"
        }
        
    Слева - путь в state куда записать
    Справа - путь в payload откуда взять
    """
    
    CONST_PREFIX = "@const:"
    
    def map(
        self,
        trigger_id: str,
        payload: Dict[str, Any],
        output_mapping: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Применяет маппинг к payload.
        
        Args:
            trigger_id: ID триггера
            payload: Входящие данные (Telegram Update, webhook body, etc.)
            output_mapping: Маппинг {state_path: payload_path}
            
        Returns:
            Словарь для инициализации state:
            {
                "triggers": {trigger_id: payload},
                "content": "...",
                "variables": {...}
            }
        """
        # Payload записывается в triggers.{trigger_id}
        result: Dict[str, Any] = {
            "triggers": {trigger_id: payload}
        }
        
        # Применяем output_mapping
        for state_path, payload_path in output_mapping.items():
            value = self._get_value(payload_path, payload)
            self._set_nested(result, state_path, value)
        
        return result
    
    def _get_value(self, expr: str, payload: Dict[str, Any]) -> Any:
        """
        Получает значение из payload или константу.
        """
        if expr.startswith(self.CONST_PREFIX):
            return expr[len(self.CONST_PREFIX):]
        
        return self._get_nested(payload, expr)
    
    def _get_nested(self, data: Dict[str, Any], path: str) -> Any:
        """
        Извлекает значение по nested пути.
        
        "message.chat.id" -> data["message"]["chat"]["id"]
        """
        if not path:
            return data
        
        current = data
        parts = self._parse_path(path)
        
        for part in parts:
            if current is None:
                return None
            
            if isinstance(part, int):
                if isinstance(current, (list, tuple)) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None
        
        return current
    
    def _parse_path(self, path: str) -> list:
        """
        Парсит путь в список частей.
        
        "message.chat.id" -> ["message", "chat", "id"]
        "items[0].name" -> ["items", 0, "name"]
        """
        parts = []
        pattern = re.compile(r'(\w+)|\[(\d+)\]')
        
        for match in pattern.finditer(path):
            if match.group(1):
                parts.append(match.group(1))
            elif match.group(2):
                parts.append(int(match.group(2)))
        
        return parts
    
    def _set_nested(self, data: Dict[str, Any], path: str, value: Any) -> None:
        """
        Устанавливает значение по nested пути.
        
        "variables.chat_id" -> data["variables"]["chat_id"] = value
        """
        parts = path.split(".")
        
        current = data
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value


__all__ = ["InputMapper"]
