"""
Кастомные Pydantic типы для моделей.
Каждый тип может иметь свою валидацию, рендеринг и шаблон.
"""

from typing import Any
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema


class HistorySource(str):
    """Специальный тип для источника истории диалогов"""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler):
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.union_schema([
                core_schema.str_schema(),
                core_schema.list_schema(core_schema.str_schema()),
                core_schema.none_schema(),
            ])
        )

    @classmethod
    def validate(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, list) and all(isinstance(item, str) for item in v):
            return v
        raise ValueError("history_from должен быть строкой, списком строк или None")

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {
            "anyOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
                {"type": "null"}
            ]
        }

    def __repr__(self):
        return f"HistorySource({super().__repr__()})"


class PythonCode(str):
    """
    Специальный тип для Python кода.
    
    Особенности:
    - Валидация синтаксиса Python при сохранении
    - Автоматический рендер через code-editor
    - JSON schema с widget="code-editor"
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler):
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.union_schema([
                core_schema.str_schema(),
                core_schema.none_schema(),
            ])
        )

    @classmethod
    def validate(cls, v):
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("Python код должен быть строкой")
        
        compile(v, '<string>', 'exec')
        
        return cls(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {
            "type": "string",
            "format": "python",
            "widget": "code-editor",
            "x-widget-attrs": {
                "mode": "python",
                "rows": 10
            }
        }

    def __repr__(self):
        return f"PythonCode({len(self) if self else 0} chars)"


__all__ = ['HistorySource', 'PythonCode']

