"""
Enums для моделей платформы.

Zero-Guess Architecture: все типы строго типизированы через Enum.
Никаких магических строк - только явные значения.
"""

from enum import Enum


class CodeMode(str, Enum):
    """Режим хранения кода"""

    INLINE_CODE = "inline_code"
    MCP_TOOL = "mcp_tool"  # Внешний MCP инструмент


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
    
    Каждый тип ноды имеет соответствующий класс в apps.flows.src.runtime.nodes
    Zero-Guess: нет magic strings, только Enum значения.
    """
    
    LLM_NODE = "llm_node"          # LLM с ReAct-циклом и tools
    CODE = "code"                   # Выполнение кода (Python, JavaScript, Go)
    FLOW = "flow"                   # Вложенный flow (subflow)
    REMOTE_FLOW = "remote_flow"   # Внешний flow по A2A протоколу
    EXTERNAL_API = "external_api"   # Вызов внешнего HTTP API
    MCP = "mcp"                     # MCP Tool как нода
    CHANNEL = "channel"             # Отправка сообщений в каналы (Telegram, Email)
    HITL_NODE = "hitl_node"         # Передача диалога оператору очереди (operator_task)
    RESOURCE = "resource"           # Нода-ресурс на графе (привязка flow/skill resources; pass-through)


class ReactToolRole(str, Enum):
    """
    Роль инструмента в ReAct-цикле llm_node.

    Не пересекается с NodeType и с полем type у inline-tool (тип исполнения: code, flow, …).
    """

    STANDARD = "standard"
    REASON = "reason"
    EXIT = "exit"


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


class TriggerType(str, Enum):
    """
    Типы триггеров для запуска агента.
    
    Push-based: telegram, webhook - внешний источник делает POST
    Pull-based: cron, email - polling по расписанию
    """
    
    TELEGRAM = "telegram"   # Telegram Bot webhook
    CRON = "cron"           # Cron расписание (TaskIQ scheduler)
    WEBHOOK = "webhook"     # Внешний HTTP webhook
    EMAIL = "email"         # Email polling или webhook
    REDIS = "redis"         # Redis Pub/Sub событие


class TriggerStatus(str, Enum):
    """Статус триггера."""
    
    INACTIVE = "inactive"   # Не зарегистрирован
    ACTIVE = "active"       # Работает
    ERROR = "error"         # Ошибка регистрации


class ChannelType(str, Enum):
    """
    Типы каналов для отправки сообщений.
    
    Используется в ChannelNode и output_actions триггеров.
    """
    
    TELEGRAM = "telegram"   # Telegram Bot API
    EMAIL = "email"         # Email (SMTP, Mailgun, SendGrid)
    WHATSAPP = "whatsapp"   # WhatsApp Business API
    SMS = "sms"             # SMS (Twilio, etc)
    WEBHOOK = "webhook"     # HTTP webhook


class TestTargetType(str, Enum):
    """
    Тип цели тестирования в evaluation.
    
    FLOW - тестируем полный flow
    NODE - тестируем отдельную ноду (BaseNode.run)
    """
    
    FLOW = "flow"
    NODE = "node"
