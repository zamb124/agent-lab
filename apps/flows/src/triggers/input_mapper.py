"""
InputMapper — маппинг данных триггера в state.

Сырой payload хранится в state.triggers[trigger_id].payload.
Поля output_mapping (левая часть) допускают только:
- content — входной текст для графа;
- context и context.* — в state.triggers[trigger_id].context (не в variables).
"""

import copy
import re
from typing import ClassVar

from core.types import JsonObject, JsonValue, require_json_array, require_json_object

PathPart = str | int


class InputMapper:
    """
    Маппер данных триггера в state.

    В map() для каждого trigger_id строится снимок:
    triggers[trigger_id] = { "payload": <копия входа>, "context": { ... } }.
    """

    CONST_PREFIX: ClassVar[str] = "@const:"
    TRIGGER_PREFIX: ClassVar[str] = "@trigger:"

    def map(
        self,
        trigger_id: str,
        payload: JsonObject,
        output_mapping: dict[str, str],
    ) -> JsonObject:
        """
        Применяет маппинг к payload.

        Возвращает:
            { "triggers": { trigger_id: { "payload", "context" } }, "content": str }
        """
        if not trigger_id or not str(trigger_id).strip():
            msg = "trigger_id is required for InputMapper.map"
            raise ValueError(msg)
        trigger_context: JsonObject = {}
        trigger_snapshot: JsonObject = {
            "payload": copy.deepcopy(payload),
            "context": trigger_context,
        }
        result: JsonObject = {
            "triggers": {
                trigger_id: trigger_snapshot,
            }
        }
        for state_path, payload_path in output_mapping.items():
            value = self._get_value(payload_path, payload)
            if state_path == "content" or state_path.strip() == "content":
                result["content"] = value
                continue
            sp = state_path.strip()
            if sp == "context" or sp.startswith("context."):
                sub = sp[8:].lstrip(".") if sp.startswith("context.") else ""
                if sp == "context":
                    if not isinstance(value, dict):
                        msg = "output_mapping: для ключа 'context' ожидается объект-словарь в payload"
                        raise TypeError(msg)
                    self._merge_shallow(trigger_context, require_json_object(value, "trigger.context"))
                else:
                    self._set_nested(trigger_context, sub, value)
                continue
            msg = f"InputMapper: неподдерживаемая левая часть маппинга: {state_path!r}"
            raise ValueError(msg)

        if "content" not in result:
            result["content"] = ""
        return result

    def _merge_shallow(self, target: JsonObject, source: JsonObject) -> None:
        for k, v in source.items():
            target[k] = v

    def _get_value(self, expr: str, payload: JsonObject) -> JsonValue:
        if expr.startswith(self.CONST_PREFIX):
            return expr[len(self.CONST_PREFIX) :]

        if expr.startswith(self.TRIGGER_PREFIX):
            path = expr[len(self.TRIGGER_PREFIX) :]
            return self._get_nested(payload, path)

        return self._get_nested(payload, expr)

    def _get_nested(self, data: JsonObject, path: str) -> JsonValue:
        if not path:
            return data

        current: JsonValue = data
        parts = self._parse_path(path)

        for part in parts:
            if current is None:
                return None

            if isinstance(part, int):
                if isinstance(current, list) and 0 <= part < len(current):
                    current_array = require_json_array(current, "trigger payload array")
                    current = current_array[part]
                else:
                    return None
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None

        return current

    def _parse_path(self, path: str) -> list[PathPart]:
        parts: list[PathPart] = []
        pattern = re.compile(r"(\w+)|\[(\d+)\]")

        for match in pattern.finditer(path):
            if match.group(1):
                parts.append(match.group(1))
            elif match.group(2):
                parts.append(int(match.group(2)))

        return parts

    def _set_nested(self, data: JsonObject, path: str, value: JsonValue) -> None:
        if not path:
            msg = "вложенный путь для context пуст"
            raise ValueError(msg)
        parts = path.split(".")
        current = data
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            nxt = current[part]
            if not isinstance(nxt, dict):
                msg = f"конфликт: {part} в context не является объектом"
                raise TypeError(msg)
            current = nxt
        current[parts[-1]] = value


__all__ = ["InputMapper"]
