"""
Enums для моделей платформы.

Zero-Guess Architecture: все типы строго типизированы через Enum.
Никаких магических строк - только явные значения.
"""

from enum import Enum


class CodeMode(str, Enum):
    """Режим хранения кода - только inline"""

    INLINE_CODE = "inline_code"


class SessionStatus(str, Enum):
    """Статусы сессии"""

    ACTIVE = "active"
    PROCESSING = "processing"
    WAITING_INPUT = "waiting_input"
    INACTIVE = "inactive"
    EXPIRED = "expired"


class NodeType(str, Enum):
    """
    Типы нод - синхронизировано с реализацией.
    
    Каждый тип ноды имеет соответствующий класс в apps/agents/src/agent/nodes.py
    Zero-Guess: нет magic strings, только Enum значения.
    """
    
    REACT_NODE = "react_node"       # ReAct агент с LLM и tools
    FUNCTION = "function"           # Python функция (inline код)
    TOOL = "tool"                   # BaseTool как нода
    AGENT = "agent"                 # Вложенный agent (subflow)
    REMOTE_AGENT = "remote_agent"   # Внешний агент по A2A протоколу
    EXTERNAL_API = "external_api"   # Вызов внешнего HTTP API


class ToolType(str, Enum):
    """
    Типы инструментов.
    
    Определяет способ выполнения инструмента.
    """
    
    FUNCTION = "function"           # Python функция (inline или CODE_REFERENCE)
    EXTERNAL_API = "external_api"   # HTTP API вызов
    SYSTEM = "system"               # Системный tool (ask_user, finish)
    TOOL = "tool"                   # Обычный tool (default)


class EventType(str, Enum):
    """
    Типы событий streaming - синхронизировано с a2a-sdk.
    
    События публикуются через EventEmitter в Redis Pub/Sub.
    Zero-Guess: строго соответствуют a2a-sdk спецификации.
    """
    
    # Streaming события
    TEXT_CHUNK = "text_chunk"           # Чанк текста от LLM
    TOOL_CALL = "tool_call"             # Вызов инструмента
    TOOL_RESULT = "tool_result"         # Результат инструмента
    ARTIFACT = "artifact"               # Артефакт (файлы, данные)
    REASONING = "reasoning"             # Reasoning данные (chain-of-thought)
    
    # Lifecycle события
    INTERRUPT = "interrupt"             # Запрос ввода от пользователя (ask_user)
    COMPLETE = "complete"               # Завершение выполнения
    ERROR = "error"                     # Ошибка выполнения
    
    # Status события
    STATUS_UPDATE = "status_update"     # Обновление статуса задачи


class ReasoningType(str, Enum):
    """
    Типы reasoning данных.
    
    Используется для структурирования chain-of-thought.
    """
    
    THOUGHT = "thought"                 # Размышление агента
    OBSERVATION = "observation"         # Наблюдение/результат
    PLAN = "plan"                       # План действий
    REFLECTION = "reflection"           # Рефлексия/анализ


class MergeMode(str, Enum):
    """
    Режимы применения skill к базовой конфигурации агента.
    
    Zero-Guess: явно указываем как мержить - merge или replace.
    """
    
    MERGE = "merge"         # Слияние с базовой конфигурацией
    REPLACE = "replace"     # Полная замена базовой конфигурации
