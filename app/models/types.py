"""
Кастомные Pydantic типы для моделей.
Каждый тип может иметь свою валидацию, рендеринг и шаблон.
"""

from typing import Any


class HistorySource(str):
    """Специальный тип для источника истории диалогов"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

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
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, validation_info=None):
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("Python код должен быть строкой")
        
        # Валидация синтаксиса Python
        try:
            compile(v, '<string>', 'exec')
        except SyntaxError as e:
            raise ValueError(f"Ошибка синтаксиса Python: {e}")
        
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

