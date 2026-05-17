"""
Иерархия исключений платформы Iman.

Все исключения должны наследоваться от ImanBaseError для единообразной обработки
и конвертации в A2A error format.
"""

from typing import Any, Dict, List, Optional


class ImanBaseError(Exception):
    """
    Базовое исключение платформы Iman.

    Все кастомные исключения должны наследоваться от этого класса.
    Предоставляет унифицированный интерфейс для логирования и A2A ответов.
    """

    code: str = "IMAN_ERROR"
    message: str = "Внутренняя ошибка платформы"

    def __init__(
        self,
        message: Optional[str] = None,
        code: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            message: Человекочитаемое описание ошибки
            code: Код ошибки для программной обработки
            payload: Дополнительные данные об ошибке
        """
        self.message = message or self.message
        self.code = code or self.code
        self.payload = payload or {}
        super().__init__(self.message)

    def to_a2a_error(self) -> Dict[str, Any]:
        """
        Конвертирует исключение в A2A error format.

        Returns:
            Dict с полями error согласно a2a-sdk спецификации
        """
        return {
            "code": self.code,
            "message": self.message,
            "data": self.payload,
        }

    def to_dict(self) -> Dict[str, Any]:
        """
        Конвертирует исключение в dict для логирования.

        Returns:
            Dict с информацией об ошибке
        """
        return {
            "error_type": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "payload": self.payload,
        }


# ============================================================================
# Ошибки конфигурации (этап загрузки/компиляции)
# ============================================================================


class ConfigError(ImanBaseError):
    """
    Ошибка конфигурации агента/ноды.

    Выбрасывается на этапе загрузки конфига из БД или файла.
    Означает что конфиг невалиден или неполный.
    """

    code = "CONFIG_ERROR"
    message = "Ошибка конфигурации"


class ValidationError(ConfigError):
    """
    Ошибка валидации конфигурации.

    Выбрасывается когда Pydantic валидация не прошла или
    кастомные валидаторы обнаружили проблемы.
    """

    code = "VALIDATION_ERROR"
    message = "Ошибка валидации конфигурации"


class MissingFieldError(ValidationError):
    """
    Отсутствует обязательное поле в конфигурации.

    Zero-Guess: система не должна угадывать значения,
    все обязательные поля должны быть явно указаны.
    """

    code = "MISSING_FIELD"
    message = "Отсутствует обязательное поле"

    def __init__(self, field: str, entity: str, **kwargs):
        super().__init__(
            message=f"Поле '{field}' отсутствует в конфигурации {entity}",
            payload={"field": field, "entity": entity},
            **kwargs,
        )


class UnknownFieldError(ValidationError):
    """
    Неизвестное поле в конфигурации (extra='forbid').

    Zero-Guess: система не должна игнорировать неизвестные поля,
    это может быть опечатка или устаревший конфиг.
    """

    code = "UNKNOWN_FIELD"
    message = "Неизвестное поле в конфигурации"

    def __init__(self, field: str, entity: str, **kwargs):
        super().__init__(
            message=f"Неизвестное поле '{field}' в конфигурации {entity}",
            payload={"field": field, "entity": entity},
            **kwargs,
        )


class CyclicDependencyError(ConfigError):
    """
    Циклическая зависимость в графе агента.

    Выбрасывается GraphCompiler при обнаружении цикла без выхода.
    """

    code = "CYCLIC_DEPENDENCY"
    message = "Обнаружена циклическая зависимость в графе"

    def __init__(self, cycle_path: list[str], **kwargs):
        super().__init__(
            message=f"Циклическая зависимость: {' -> '.join(cycle_path)}",
            payload={"cycle_path": cycle_path},
            **kwargs,
        )


class NodeConflictError(ConfigError):
    """
    Конфликт нод при применении веток (branches).

    Выбрасывается GraphCompiler когда две ветки пытаются
    модифицировать одну и ту же ноду несовместимым образом.
    """

    code = "NODE_CONFLICT"
    message = "Конфликт нод между ветками"

    def __init__(self, node_id: str, branches: list[str], **kwargs):
        super().__init__(
            message=f"Нода '{node_id}' конфликтует между ветками: {', '.join(branches)}",
            payload={"node_id": node_id, "branches": branches},
            **kwargs,
        )


class InvalidGraphError(ConfigError):
    """
    Невалидная структура графа агента.

    Например: entry нода не существует, нода без исходящих edges,
    недостижимые ноды, несовместимые input/output схемы.
    """

    code = "INVALID_GRAPH"
    message = "Невалидная структура графа"


# ============================================================================
# Ошибки ресурсов (поиск, загрузка)
# ============================================================================


class ResourceError(ImanBaseError):
    """
    Базовая ошибка работы с ресурсами.

    Ресурсы: агенты, ноды, tools, переменные.
    """

    code = "RESOURCE_ERROR"
    message = "Ошибка работы с ресурсом"


class ResourceNotFoundError(ResourceError):
    """
    Ресурс не найден в реестре или БД.

    Zero-Guess: система не должна создавать ресурс по умолчанию,
    если его нет - это явная ошибка конфигурации.
    """

    code = "RESOURCE_NOT_FOUND"
    message = "Ресурс не найден"

    def __init__(self, resource_type: str, resource_id: str, **kwargs):
        super().__init__(
            message=f"{resource_type} '{resource_id}' не найден",
            payload={"resource_type": resource_type, "resource_id": resource_id},
            **kwargs,
        )


class ResourceAlreadyExistsError(ResourceError):
    """
    Ресурс уже существует (при попытке регистрации дубликата).
    """

    code = "RESOURCE_ALREADY_EXISTS"
    message = "Ресурс уже существует"

    def __init__(self, resource_type: str, resource_id: str, **kwargs):
        super().__init__(
            message=f"{resource_type} '{resource_id}' уже зарегистрирован",
            payload={"resource_type": resource_type, "resource_id": resource_id},
            **kwargs,
        )


# ============================================================================
# Ошибки выполнения (runtime)
# ============================================================================


class ExecutionError(ImanBaseError):
    """
    Ошибка выполнения агента/ноды.

    Выбрасывается во время runtime исполнения графа.
    """

    code = "EXECUTION_ERROR"
    message = "Ошибка выполнения"


class NodeExecutionError(ExecutionError):
    """
    Ошибка выполнения конкретной ноды.
    """

    code = "NODE_EXECUTION_ERROR"
    message = "Ошибка выполнения ноды"

    def __init__(self, node_id: str, error: Exception, **kwargs):
        super().__init__(
            message=f"Ошибка выполнения ноды '{node_id}': {str(error)}",
            payload={"node_id": node_id, "original_error": str(error)},
            **kwargs,
        )


class ToolExecutionError(ExecutionError):
    """
    Ошибка выполнения инструмента.
    """

    code = "TOOL_EXECUTION_ERROR"
    message = "Ошибка выполнения инструмента"

    def __init__(self, tool_id: str, error: Exception, **kwargs):
        super().__init__(
            message=f"Ошибка выполнения инструмента '{tool_id}': {str(error)}",
            payload={"tool_id": tool_id, "original_error": str(error)},
            **kwargs,
        )


class FlowExecutionError(ExecutionError):
    """
    Базовая ошибка выполнения flow.
    """

    code = "FLOW_EXECUTION_ERROR"
    message = "Ошибка выполнения flow"


class NodeCallLimitError(FlowExecutionError):
    """
    Превышен лимит вызовов ноды.
    """

    code = "NODE_CALL_LIMIT"
    message = "Превышен лимит вызовов ноды"

    def __init__(self, node_id: str, limit: int, **kwargs):
        super().__init__(
            message=f"Нода '{node_id}' вызвана больше {limit} раз",
            payload={"node_id": node_id, "limit": limit},
            **kwargs,
        )


class FlowInfiniteLoopError(FlowExecutionError):
    """
    Превышено максимальное количество итераций flow.
    """

    code = "FLOW_INFINITE_LOOP"
    message = "Превышено максимальное количество итераций flow"

    def __init__(self, flow_id: str, max_iterations: int, **kwargs):
        super().__init__(
            message=f"Flow '{flow_id}' превысил лимит итераций: {max_iterations}",
            payload={"flow_id": flow_id, "max_iterations": max_iterations},
            **kwargs,
        )


class FlowPrematureCompletionError(FlowExecutionError):
    """
    Цикл flow остановился без достижения терминала (END / только связи to=null).
    """

    code = "FLOW_PREMATURE_COMPLETION"
    message = "Flow завершился до терминальной ноды"

    def __init__(
        self,
        flow_id: str,
        reason: str,
        *,
        last_nodes: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        payload: Dict[str, Any] = {"flow_id": flow_id, "reason": reason}
        if last_nodes is not None:
            payload["last_nodes"] = last_nodes
        if extra:
            payload.update(extra)
        super().__init__(
            message=f"Flow '{flow_id}': остановка не на END ({reason})",
            code=self.code,
            payload=payload,
            **kwargs,
        )


class FlowWallClockTimeoutError(FlowExecutionError):
    """
    Превышен wall-clock лимит выполнения flow (дедлайн в ExecutionState).
    """

    code = "FLOW_WALL_CLOCK_TIMEOUT"
    message = "Превышен лимит времени выполнения flow"

    def __init__(self, flow_id: str, timeout_seconds: int, **kwargs: Any) -> None:
        super().__init__(
            message=f"Flow '{flow_id}': превышен лимит времени выполнения ({timeout_seconds}с)",
            payload={"flow_id": flow_id, "timeout_seconds": timeout_seconds},
            **kwargs,
        )


class NodeWallClockTimeoutError(FlowExecutionError):
    """
    Превышен wall-clock лимит выполнения одной ноды.
    """

    code = "NODE_WALL_CLOCK_TIMEOUT"
    message = "Превышен лимит времени выполнения ноды"

    def __init__(self, node_id: str, timeout_seconds: int, **kwargs: Any) -> None:
        super().__init__(
            message=f"Нода '{node_id}': превышен лимит времени выполнения ({timeout_seconds}с)",
            payload={"node_id": node_id, "timeout_seconds": timeout_seconds},
            **kwargs,
        )


class SafeEvalError(ExecutionError):
    """
    Ошибка безопасного выполнения кода.
    """

    code = "SAFE_EVAL_ERROR"
    message = "Ошибка безопасного выполнения кода"


class FrozenStateFieldError(SafeEvalError):
    """
    Попытка изменить системное поле ExecutionState из кода ноды или tool.
    """

    code = "FROZEN_STATE_FIELD"

    def __init__(
        self,
        field: str,
        *,
        reason: str = "assign",
        **kwargs: Any,
    ) -> None:
        base = (
            f"Поле '{field}' зарезервировано платформой (лимиты выполнения, история, "
            "идентификаторы сессии). Его нельзя менять из кода ноды или tool. "
            "Используйте variables, result, response или произвольные поля вне системного списка."
        )
        if reason == "in_place_mutation":
            msg = f"{base} Обнаружено изменение содержимого поля (in-place)."
        elif reason == "output_mapping":
            msg = f"{base} Уберите ключ из возвращаемого dict или скорректируйте output_mapping."
        elif reason == "merge":
            msg = f"{base} Уберите ключ из merge_state или вложенного пути set_nested."
        else:
            msg = base
        super().__init__(
            message=msg,
            payload={"field": field, "reason": reason},
            **kwargs,
        )


class ExternalAPIError(ExecutionError):
    """
    Ошибка вызова внешнего API.
    """

    code = "EXTERNAL_API_ERROR"
    message = "Ошибка вызова внешнего API"


class TimeoutError(ExecutionError):
    """
    Превышен таймаут выполнения.
    """

    code = "EXECUTION_TIMEOUT"
    message = "Превышен таймаут выполнения"

    def __init__(self, entity: str, timeout: int, **kwargs):
        super().__init__(
            message=f"Превышен таймаут выполнения {entity}: {timeout}с",
            payload={"entity": entity, "timeout": timeout},
            **kwargs,
        )


class MaxRetriesExceededError(ExecutionError):
    """
    Превышено максимальное количество повторов.
    """

    code = "MAX_RETRIES_EXCEEDED"
    message = "Превышено максимальное количество повторов"

    def __init__(self, entity: str, max_retries: int, **kwargs):
        super().__init__(
            message=f"Превышено максимальное количество повторов для {entity}: {max_retries}",
            payload={"entity": entity, "max_retries": max_retries},
            **kwargs,
        )


# ============================================================================
# Ошибки безопасности и прав доступа
# ============================================================================


class SecurityError(ImanBaseError):
    """
    Ошибка безопасности или прав доступа.
    """

    code = "SECURITY_ERROR"
    message = "Ошибка безопасности"


class PermissionDeniedError(SecurityError):
    """
    Отказ в доступе (недостаточно прав).

    Zero-Guess: система не должна предоставлять доступ если
    permission не указан явно.
    """

    code = "PERMISSION_DENIED"
    message = "Отказано в доступе"

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        required_groups: list[str],
        user_groups: list[str],
        **kwargs
    ):
        super().__init__(
            message=f"Недостаточно прав для доступа к {resource_type} '{resource_id}'. "
                   f"Требуется одна из групп: {', '.join(required_groups)}. "
                   f"У пользователя: {', '.join(user_groups) if user_groups else 'нет групп'}",
            payload={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "required_groups": required_groups,
                "user_groups": user_groups,
            },
            **kwargs,
        )


class AuthenticationError(SecurityError):
    """
    Ошибка аутентификации.
    """

    code = "AUTHENTICATION_ERROR"
    message = "Ошибка аутентификации"


# ============================================================================
# Ошибки данных и состояния
# ============================================================================


class StateError(ImanBaseError):
    """
    Ошибка работы с состоянием выполнения.
    """

    code = "STATE_ERROR"
    message = "Ошибка работы с состоянием"


class InvalidStateError(StateError):
    """
    Невалидное состояние выполнения.
    """

    code = "INVALID_STATE"
    message = "Невалидное состояние выполнения"


class SchemaMismatchError(StateError):
    """
    Несоответствие схем данных между нодами.

    output схема ноды A несовместима с input схемой ноды B.
    """

    code = "SCHEMA_MISMATCH"
    message = "Несоответствие схем данных"

    def __init__(self, from_node: str, to_node: str, details: str, **kwargs):
        super().__init__(
            message=f"Несовместимые схемы между нодами '{from_node}' -> '{to_node}': {details}",
            payload={"from_node": from_node, "to_node": to_node, "details": details},
            **kwargs,
        )


# ============================================================================
# Export всех исключений
# ============================================================================


__all__ = [
    # Базовые
    "ImanBaseError",
    # Конфигурация
    "ConfigError",
    "ValidationError",
    "MissingFieldError",
    "UnknownFieldError",
    "CyclicDependencyError",
    "NodeConflictError",
    "InvalidGraphError",
    # Ресурсы
    "ResourceError",
    "ResourceNotFoundError",
    "ResourceAlreadyExistsError",
    # Выполнение
    "ExecutionError",
    "NodeExecutionError",
    "ToolExecutionError",
    "FlowExecutionError",
    "NodeCallLimitError",
    "FlowInfiniteLoopError",
    "FlowPrematureCompletionError",
    "FlowWallClockTimeoutError",
    "NodeWallClockTimeoutError",
    "SafeEvalError",
    "FrozenStateFieldError",
    "ExternalAPIError",
    "TimeoutError",
    "MaxRetriesExceededError",
    # Безопасность
    "SecurityError",
    "PermissionDeniedError",
    "AuthenticationError",
    # Состояние
    "StateError",
    "InvalidStateError",
    "SchemaMismatchError",
]
