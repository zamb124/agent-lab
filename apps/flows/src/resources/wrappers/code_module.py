"""
CodeModule - wrapper для code ресурса.

Предоставляет доступ к функциям и классам из inline кода.
"""

from typing import Any, Dict


class CodeModule:
    """
    Модуль с функциями/классами из inline кода.

    Доступен в namespace по resource_id.
    Все функции и классы из кода становятся атрибутами модуля.

    Пример:
        # В конфиге ресурса:
        # "code": "def format_phone(p): return '+7' + p[-10:]"

        # В inline коде ноды:
        phone = helpers.format_phone("9161234567")
    """

    def __init__(self, namespace: Dict[str, Any], source_code: str):
        """
        Args:
            namespace: Namespace с выполненным кодом
            source_code: Исходный код для отладки
        """
        self._namespace = namespace
        self._source_code = source_code

        # Копируем все публичные объекты в атрибуты
        for name, obj in namespace.items():
            if not name.startswith("_"):
                setattr(self, name, obj)

    def __repr__(self) -> str:
        public_names = [n for n in dir(self) if not n.startswith("_")]
        return f"<CodeModule with {len(public_names)} items: {', '.join(public_names[:5])}...>"

    def __contains__(self, name: str) -> bool:
        return hasattr(self, name)

    def get(self, name: str, default: Any = None) -> Any:
        """Получить объект по имени."""
        return getattr(self, name, default)
