"""
Иерархия исключений платформы Iman.

Все исключения должны наследоваться от ImanBaseError для единообразной обработки
и конвертации в A2A error format.
"""

from core.types import JsonArray, JsonObject


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
        message: str | None = None,
        code: str | None = None,
        payload: JsonObject | None = None,
    ) -> None:
        """
        Args:
            message: Человекочитаемое описание ошибки
            code: Код ошибки для программной обработки
            payload: Дополнительные данные об ошибке
        """
        self.message = message or self.message
        self.code = code or self.code
        self.payload: JsonObject = payload if payload is not None else {}
        super().__init__(self.message)

    def to_a2a_error(self) -> JsonObject:
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

    def to_dict(self) -> JsonObject:
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

    code: str = "CONFIG_ERROR"
    message: str = "Ошибка конфигурации"


class ValidationError(ConfigError):
    """
    Ошибка валидации конфигурации.

    Выбрасывается когда Pydantic валидация не прошла или
    кастомные валидаторы обнаружили проблемы.
    """

    code: str = "VALIDATION_ERROR"
    message: str = "Ошибка валидации конфигурации"


class MissingFieldError(ValidationError):
    """
    Отсутствует обязательное поле в конфигурации.

    Zero-Guess: система не должна угадывать значения,
    все обязательные поля должны быть явно указаны.
    """

    code: str = "MISSING_FIELD"
    message: str = "Отсутствует обязательное поле"

    def __init__(self, field: str, entity: str, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Поле '{field}' отсутствует в конфигурации {entity}",
            code=code,
            payload={"field": field, "entity": entity},
        )


class UnknownFieldError(ValidationError):
    """
    Неизвестное поле в конфигурации (extra='forbid').

    Zero-Guess: система не должна игнорировать неизвестные поля,
    это может быть опечатка или устаревший конфиг.
    """

    code: str = "UNKNOWN_FIELD"
    message: str = "Неизвестное поле в конфигурации"

    def __init__(self, field: str, entity: str, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Неизвестное поле '{field}' в конфигурации {entity}",
            code=code,
            payload={"field": field, "entity": entity},
        )


class CyclicDependencyError(ConfigError):
    """
    Циклическая зависимость в графе агента.

    Выбрасывается GraphCompiler при обнаружении цикла без выхода.
    """

    code: str = "CYCLIC_DEPENDENCY"
    message: str = "Обнаружена циклическая зависимость в графе"

    def __init__(self, cycle_path: list[str], *, code: str | None = None) -> None:
        cycle_path_payload: JsonArray = [*cycle_path]
        super().__init__(
            message=f"Циклическая зависимость: {' -> '.join(cycle_path)}",
            code=code,
            payload={"cycle_path": cycle_path_payload},
        )


class NodeConflictError(ConfigError):
    """
    Конфликт нод при применении веток (branches).

    Выбрасывается GraphCompiler когда две ветки пытаются
    модифицировать одну и ту же ноду несовместимым образом.
    """

    code: str = "NODE_CONFLICT"
    message: str = "Конфликт нод между ветками"

    def __init__(self, node_id: str, branches: list[str], *, code: str | None = None) -> None:
        branch_payload: JsonArray = [*branches]
        super().__init__(
            message=f"Нода '{node_id}' конфликтует между ветками: {', '.join(branches)}",
            code=code,
            payload={"node_id": node_id, "branches": branch_payload},
        )


class InvalidGraphError(ConfigError):
    """
    Невалидная структура графа агента.

    Например: entry нода не существует, нода без исходящих edges,
    недостижимые ноды, несовместимые input/output схемы.
    """

    code: str = "INVALID_GRAPH"
    message: str = "Невалидная структура графа"


# ============================================================================
# Ошибки ресурсов (поиск, загрузка)
# ============================================================================


class ResourceError(ImanBaseError):
    """
    Базовая ошибка работы с ресурсами.

    Ресурсы: агенты, ноды, tools, переменные.
    """

    code: str = "RESOURCE_ERROR"
    message: str = "Ошибка работы с ресурсом"


class ResourceNotFoundError(ResourceError):
    """
    Ресурс не найден в реестре или БД.

    Zero-Guess: система не должна создавать ресурс по умолчанию,
    если его нет - это явная ошибка конфигурации.
    """

    code: str = "RESOURCE_NOT_FOUND"
    message: str = "Ресурс не найден"

    def __init__(self, resource_type: str, resource_id: str, *, code: str | None = None) -> None:
        super().__init__(
            message=f"{resource_type} '{resource_id}' не найден",
            code=code,
            payload={"resource_type": resource_type, "resource_id": resource_id},
        )


class ResourceAlreadyExistsError(ResourceError):
    """
    Ресурс уже существует (при попытке регистрации дубликата).
    """

    code: str = "RESOURCE_ALREADY_EXISTS"
    message: str = "Ресурс уже существует"

    def __init__(self, resource_type: str, resource_id: str, *, code: str | None = None) -> None:
        super().__init__(
            message=f"{resource_type} '{resource_id}' уже зарегистрирован",
            code=code,
            payload={"resource_type": resource_type, "resource_id": resource_id},
        )


# ============================================================================
# Ошибки выполнения (runtime)
# ============================================================================


class ExecutionError(ImanBaseError):
    """
    Ошибка выполнения агента/ноды.

    Выбрасывается во время runtime исполнения графа.
    """

    code: str = "EXECUTION_ERROR"
    message: str = "Ошибка выполнения"


class NodeExecutionError(ExecutionError):
    """
    Ошибка выполнения конкретной ноды.
    """

    code: str = "NODE_EXECUTION_ERROR"
    message: str = "Ошибка выполнения ноды"

    def __init__(self, node_id: str, error: Exception, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Ошибка выполнения ноды '{node_id}': {str(error)}",
            code=code,
            payload={"node_id": node_id, "original_error": str(error)},
        )


class ToolExecutionError(ExecutionError):
    """
    Ошибка выполнения инструмента.
    """

    code: str = "TOOL_EXECUTION_ERROR"
    message: str = "Ошибка выполнения инструмента"

    def __init__(self, tool_id: str, error: Exception, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Ошибка выполнения инструмента '{tool_id}': {str(error)}",
            code=code,
            payload={"tool_id": tool_id, "original_error": str(error)},
        )


class FlowExecutionError(ExecutionError):
    """
    Базовая ошибка выполнения flow.
    """

    code: str = "FLOW_EXECUTION_ERROR"
    message: str = "Ошибка выполнения flow"


class NodeCallLimitError(FlowExecutionError):
    """
    Превышен лимит вызовов ноды.
    """

    code: str = "NODE_CALL_LIMIT"
    message: str = "Превышен лимит вызовов ноды"

    def __init__(self, node_id: str, limit: int, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Нода '{node_id}' вызвана больше {limit} раз",
            code=code,
            payload={"node_id": node_id, "limit": limit},
        )


class FlowInfiniteLoopError(FlowExecutionError):
    """
    Превышено максимальное количество итераций flow.
    """

    code: str = "FLOW_INFINITE_LOOP"
    message: str = "Превышено максимальное количество итераций flow"

    def __init__(self, flow_id: str, max_iterations: int, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Flow '{flow_id}' превысил лимит итераций: {max_iterations}",
            code=code,
            payload={"flow_id": flow_id, "max_iterations": max_iterations},
        )


class FlowPrematureCompletionError(FlowExecutionError):
    """
    Цикл flow остановился без достижения терминала (END / только связи to=null).
    """

    code: str = "FLOW_PREMATURE_COMPLETION"
    message: str = "Flow завершился до терминальной ноды"

    def __init__(
        self,
        flow_id: str,
        reason: str,
        *,
        last_nodes: list[str] | None = None,
        extra: JsonObject | None = None,
        code: str | None = None,
    ) -> None:
        payload: JsonObject = {"flow_id": flow_id, "reason": reason}
        if last_nodes is not None:
            last_node_payload: JsonArray = [*last_nodes]
            payload["last_nodes"] = last_node_payload
        if extra:
            payload.update(extra)
        super().__init__(
            message=f"Flow '{flow_id}': остановка не на END ({reason})",
            code=code,
            payload=payload,
        )


class FlowWallClockTimeoutError(FlowExecutionError):
    """
    Превышен wall-clock лимит выполнения flow (дедлайн в ExecutionState).
    """

    code: str = "FLOW_WALL_CLOCK_TIMEOUT"
    message: str = "Превышен лимит времени выполнения flow"

    def __init__(self, flow_id: str, timeout_seconds: int, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Flow '{flow_id}': превышен лимит времени выполнения ({timeout_seconds}с)",
            code=code,
            payload={"flow_id": flow_id, "timeout_seconds": timeout_seconds},
        )


class NodeWallClockTimeoutError(FlowExecutionError):
    """
    Превышен wall-clock лимит выполнения одной ноды.
    """

    code: str = "NODE_WALL_CLOCK_TIMEOUT"
    message: str = "Превышен лимит времени выполнения ноды"

    def __init__(self, node_id: str, timeout_seconds: int, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Нода '{node_id}': превышен лимит времени выполнения ({timeout_seconds}с)",
            code=code,
            payload={"node_id": node_id, "timeout_seconds": timeout_seconds},
        )


class SafeEvalError(ExecutionError):
    """
    Ошибка безопасного выполнения кода.
    """

    code: str = "SAFE_EVAL_ERROR"
    message: str = "Ошибка безопасного выполнения кода"


class CodeExecutionRuntimeError(ExecutionError):
    """
    Ошибка исполнения пользовательского кода в isolated code runner.
    """

    code: str = "CODE_EXECUTION_RUNTIME_ERROR"
    message: str = "Ошибка исполнения пользовательского кода"

    def __init__(
        self,
        *,
        language: str,
        service: str,
        stage: str,
        message: str,
        exception_type: str,
        traceback: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        code: str | None = None,
    ) -> None:
        payload: JsonObject = {
            "language": language,
            "service": service,
            "stage": stage,
            "exception_type": exception_type,
        }
        if traceback:
            payload["traceback"] = traceback
        if stdout:
            payload["stdout"] = stdout
        if stderr:
            payload["stderr"] = stderr
        if request_id:
            payload["request_id"] = request_id
        if trace_id:
            payload["trace_id"] = trace_id
        super().__init__(
            message=f"{service}/{language}/{stage}: {message}",
            code=code,
            payload=payload,
        )


class FrozenStateFieldError(SafeEvalError):
    """
    Попытка изменить системное поле ExecutionState из кода ноды или tool.
    """

    code: str = "FROZEN_STATE_FIELD"

    def __init__(
        self,
        field: str,
        *,
        reason: str = "assign",
        code: str | None = None,
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
            code=code,
            payload={"field": field, "reason": reason},
        )


class ExternalAPIError(ExecutionError):
    """
    Ошибка вызова внешнего API.
    """

    code: str = "EXTERNAL_API_ERROR"
    message: str = "Ошибка вызова внешнего API"


class TimeoutError(ExecutionError):
    """
    Превышен таймаут выполнения.
    """

    code: str = "EXECUTION_TIMEOUT"
    message: str = "Превышен таймаут выполнения"

    def __init__(self, entity: str, timeout: int, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Превышен таймаут выполнения {entity}: {timeout}с",
            code=code,
            payload={"entity": entity, "timeout": timeout},
        )


class MaxRetriesExceededError(ExecutionError):
    """
    Превышено максимальное количество повторов.
    """

    code: str = "MAX_RETRIES_EXCEEDED"
    message: str = "Превышено максимальное количество повторов"

    def __init__(self, entity: str, max_retries: int, *, code: str | None = None) -> None:
        super().__init__(
            message=f"Превышено максимальное количество повторов для {entity}: {max_retries}",
            code=code,
            payload={"entity": entity, "max_retries": max_retries},
        )


# ============================================================================
# Ошибки безопасности и прав доступа
# ============================================================================


class SecurityError(ImanBaseError):
    """
    Ошибка безопасности или прав доступа.
    """

    code: str = "SECURITY_ERROR"
    message: str = "Ошибка безопасности"


class PermissionDeniedError(SecurityError):
    """
    Отказ в доступе (недостаточно прав).

    Zero-Guess: система не должна предоставлять доступ если
    permission не указан явно.
    """

    code: str = "PERMISSION_DENIED"
    message: str = "Отказано в доступе"

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        required_groups: list[str],
        user_groups: list[str],
        code: str | None = None,
    ) -> None:
        user_groups_text = ", ".join(user_groups) if user_groups else "нет групп"
        required_groups_payload: JsonArray = [*required_groups]
        user_groups_payload: JsonArray = [*user_groups]
        super().__init__(
            message=(
                f"Недостаточно прав для доступа к {resource_type} '{resource_id}'. "
                + f"Требуется одна из групп: {', '.join(required_groups)}. "
                + f"У пользователя: {user_groups_text}"
            ),
            code=code,
            payload={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "required_groups": required_groups_payload,
                "user_groups": user_groups_payload,
            },
        )


class AuthenticationError(SecurityError):
    """
    Ошибка аутентификации.
    """

    code: str = "AUTHENTICATION_ERROR"
    message: str = "Ошибка аутентификации"


# ============================================================================
# Ошибки данных и состояния
# ============================================================================


class StateError(ImanBaseError):
    """
    Ошибка работы с состоянием выполнения.
    """

    code: str = "STATE_ERROR"
    message: str = "Ошибка работы с состоянием"


class InvalidStateError(StateError):
    """
    Невалидное состояние выполнения.
    """

    code: str = "INVALID_STATE"
    message: str = "Невалидное состояние выполнения"


class SchemaMismatchError(StateError):
    """
    Несоответствие схем данных между нодами.

    output схема ноды A несовместима с input схемой ноды B.
    """

    code: str = "SCHEMA_MISMATCH"
    message: str = "Несоответствие схем данных"

    def __init__(
        self,
        from_node: str,
        to_node: str,
        details: str,
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(
            message=f"Несовместимые схемы между нодами '{from_node}' -> '{to_node}': {details}",
            code=code,
            payload={"from_node": from_node, "to_node": to_node, "details": details},
        )


# ============================================================================
# Экспорт всех исключений
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
    "CodeExecutionRuntimeError",
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
