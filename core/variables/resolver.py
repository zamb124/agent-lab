"""
Резолвер переменных для промптов.
Продвинутая версия с поддержкой условных блоков и валидации.
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from core.context import get_context
from core.logging import get_logger

logger = get_logger(__name__)


class UnmatchedBracesError(Exception):
    """Исключение для непарных скобок {}."""
    pass


class VariableResolutionError(ValueError):
    """Ошибка резолва ссылки @var:."""

    pass


class VarResolver:
    """
    Единый strict-резолвер @var ссылок.

    Контракт:
    - Поддерживает только @var:key и @var:nested.path
    - Отсутствующий ключ или путь всегда приводит к VariableResolutionError
    """

    VAR_REF_PATTERN = re.compile(r"^@var:([a-zA-Z_][a-zA-Z0-9_.]*)$")
    _VAR_TOKEN_PATTERN = re.compile(r"@var:([a-zA-Z_][a-zA-Z0-9_.]*)")

    @classmethod
    def resolve_ref(
        cls,
        value: str,
        variables: Dict[str, Any],
        _visited: Optional[set[str]] = None,
    ) -> Any:
        """Резолвит только полную ссылку формата @var:path."""
        if not isinstance(value, str):
            raise VariableResolutionError(
                f"@var reference must be string, got {type(value).__name__}"
            )
        match = cls.VAR_REF_PATTERN.match(value)
        if match is None:
            raise VariableResolutionError(
                f"Invalid @var reference format: '{value}'"
            )
        path = match.group(1)
        visited = set() if _visited is None else set(_visited)
        if path in visited:
            raise VariableResolutionError(
                f"Circular @var reference detected: '@var:{path}'"
            )
        visited.add(path)
        resolved = cls._resolve_path(path, variables)
        return cls.resolve_deep(resolved, variables, visited)

    @classmethod
    def resolve_text(
        cls,
        value: str,
        variables: Dict[str, Any],
        _visited: Optional[set[str]] = None,
    ) -> str:
        """
        Резолвит все @var:path токены в строке.
        Если любой токен неразрешим, бросает VariableResolutionError.
        """
        if not isinstance(value, str):
            raise VariableResolutionError(
                f"Text for @var resolution must be string, got {type(value).__name__}"
            )

        visited = set() if _visited is None else set(_visited)

        def replace_var(match: re.Match[str]) -> str:
            ref_path = match.group(1)
            resolved = cls.resolve_ref(f"@var:{ref_path}", variables, visited)
            return str(resolved)

        resolved_text = value
        while "@var:" in resolved_text:
            updated_text = cls._VAR_TOKEN_PATTERN.sub(replace_var, resolved_text)
            if updated_text == resolved_text:
                break
            resolved_text = updated_text
        return resolved_text

    @classmethod
    def resolve_deep(
        cls,
        value: Any,
        variables: Dict[str, Any],
        _visited: Optional[set[str]] = None,
    ) -> Any:
        """
        Рекурсивно резолвит @var во всех строках dict/list.
        """
        if isinstance(value, dict):
            return {
                key: cls.resolve_deep(item, variables, _visited)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls.resolve_deep(item, variables, _visited) for item in value]
        if isinstance(value, str):
            if cls.VAR_REF_PATTERN.match(value):
                return cls.resolve_ref(value, variables, _visited)
            if "@var:" in value:
                return cls.resolve_text(value, variables, _visited)
            return value
        return value

    @classmethod
    def _resolve_path(cls, path: str, variables: Dict[str, Any]) -> Any:
        value: Any = variables
        for key in path.split("."):
            if isinstance(value, dict) and key in value:
                value = value[key]
                continue
            raise VariableResolutionError(f"Variable '@var:{path}' not found")
        return value

    @classmethod
    def resolve_for_flow_variable(
        cls,
        value: str,
        company_variables: Dict[str, Any],
    ) -> Any:
        """
        Резолвит значение поля flow/skill variables (строка из FlowVariableConfig.value).

        Контракт (без «висячих» @var: в state.variables):
        - строка без ``@var:`` — без изменений;
        - полная ссылка ``@var:path`` — значение из company_variables или None, если
          корневого ключа нет или путь/цепочка не резолвится;
        - смешанная строка (текст + токены) — если корень любого токена отсутствует в
          company_variables, результат целиком None; иначе подстановка как в resolve_text;
          при ошибке резолва (нет вложенного пути и т.д.) — None.

        Отличается от resolve_ref/resolve_text: не бросает исключение при отсутствии
        переменной — возвращает None (опциональные секреты и ссылки в агенте).
        """
        if not isinstance(value, str):
            raise VariableResolutionError(
                f"resolve_for_flow_variable expects str, got {type(value).__name__}"
            )
        if "@var:" not in value:
            return value
        for match in cls._VAR_TOKEN_PATTERN.finditer(value):
            path = match.group(1)
            root_key = path.split(".", 1)[0]
            if root_key not in company_variables:
                return None
        try:
            if cls.VAR_REF_PATTERN.match(value):
                return cls.resolve_ref(value, company_variables)
            return cls.resolve_text(value, company_variables)
        except VariableResolutionError:
            return None


class VariableResolver:
    """
    Резолвер переменных с приоритетами.

    Приоритет (от высшего к низшему):
    1. Локальные переменные агента
    2. Переменные агента
    3. Переменные компании
    4. Системные переменные
    """

    @staticmethod
    def resolve_all(
        local_vars: Optional[Dict[str, Any]] = None, include_system: bool = True
    ) -> Dict[str, Any]:
        """
        Собирает все переменные с учетом приоритета.

        Args:
            local_vars: Локальные переменные (наивысший приоритет)
            include_system: Включать системные переменные

        Returns:
            Словарь всех переменных
        """
        variables = {}

        context = get_context()

        # Системные переменные (с учётом таймзоны из state.store.timezone если есть)
        if include_system:
            tz = None
            if context and getattr(context, "state", None):
                store = context.state.get("store", {}) if isinstance(context.state, dict) else {}
                tz_name = store.get("timezone") if isinstance(store, dict) else None
                if tz_name:
                    try:
                        tz = ZoneInfo(tz_name)
                    except Exception:
                        tz = None
            now = datetime.now(tz) if tz else datetime.now()
            variables.update(
                {
                    "current_date": now.strftime("%Y-%m-%d"),
                    "current_time": now.strftime("%H:%M"),
                    "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "current_year": now.year,
                    "current_month": now.month,
                    "current_day": now.day,
                }
            )

        if not context:
            if local_vars:
                local_vars_clean = {}
                for key, value in local_vars.items():
                    if isinstance(value, dict) and "value" in value and ("public" in value or "title" in value or "description" in value):
                        local_vars_clean[key] = value["value"]
                    else:
                        local_vars_clean[key] = value
                variables.update(local_vars_clean)
            return variables

        # Переменные компании
        if context.company_variables:
            variables.update(context.company_variables)

        # Переменные пользователя
        if context.user:
            variables.update(
                {
                    "user_name": context.user.name,
                    "user_id": context.user.user_id,
                }
            )
            if context.metadata.get("email"):
                variables["user_email"] = context.metadata["email"]

        # Переменные агента
        if context.flow_variables:
            flow_vars = {}
            for key, value in context.flow_variables.items():
                if isinstance(value, dict) and "value" in value and ("public" in value or "title" in value or "description" in value):
                    flow_vars[key] = value["value"]
                else:
                    flow_vars[key] = value
            variables.update(flow_vars)

        # Локальные переменные (наивысший приоритет)
        if local_vars:
            local_vars_clean = {}
            for key, value in local_vars.items():
                if isinstance(value, dict) and "value" in value and ("public" in value or "title" in value or "description" in value):
                    local_vars_clean[key] = value["value"]
                else:
                    local_vars_clean[key] = value
            variables.update(local_vars_clean)

        return variables

    @staticmethod
    def _is_empty_value(value: Any) -> bool:
        """Проверяет, является ли значение пустым (None, '', False)."""
        return value is None or value == "" or value is False

    @staticmethod
    def _resolve_variable_value(
        expr: str, variables: Dict[str, Any]
    ) -> tuple[Any, bool]:
        """
        Резолвит значение переменной из словаря.

        Args:
            expr: Выражение переменной (может быть с точками для вложенных)
            variables: Словарь переменных

        Returns:
            (value, found) - значение и флаг найденности
        """
        value = variables
        parts = expr.split(".")

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None, False

        if isinstance(value, dict) and "value" in value and ("public" in value or "title" in value or "description" in value):
            value = value["value"]

        return value, True

    @staticmethod
    def render_template(
        template: str,
        local_vars: Optional[Dict[str, Any]] = None,
        safe: bool = True,
        include_system: bool = True,
    ) -> str:
        """
        Рендерит шаблон с подстановкой переменных.

        Форматы:
        - {variable} - обязательная подстановка
        - {variable|default} - обязательная, но если нет/None/'' - используется default
        - {?variable} - опциональная (пустая строка если нет)
        - {?variable|default} - опциональная со значением по умолчанию
        - {?variable|...блок...} - условный блок (показывается если переменная есть/True/не пустая)
        - {dict.key} - доступ к вложенным dict
        - ?variable - короткий формат опциональной (без скобок)
        - ?variable|default - короткий формат опциональной с default

        Args:
            template: Шаблон строки
            local_vars: Локальные переменные
            safe: Если True, не падает на отсутствующие переменные
            include_system: Включать системные переменные

        Returns:
            Строка с подставленными переменными
        """
        if not template:
            return template

        def validate_braces(text: str) -> None:
            """Проверяет, что все скобки {} парные."""
            depth = 0
            i = 0
            while i < len(text):
                if text[i] == '\\' and i + 1 < len(text):
                    i += 2
                    continue

                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth < 0:
                        raise UnmatchedBracesError(f"Непарная закрывающая скобка '}}' на позиции {i}")
                i += 1

            if depth > 0:
                raise UnmatchedBracesError(f"Непарная открывающая скобка '{{' - не закрыто {depth} скобок")
            elif depth < 0:
                raise UnmatchedBracesError(f"Непарная закрывающая скобка '}}' - лишних {abs(depth)} скобок")

        validate_braces(template)

        variables = VariableResolver.resolve_all(
            local_vars=local_vars, include_system=include_system
        )

        def process_for_loops(text: str, loop_vars: Optional[Dict[str, Any]] = None) -> str:
            """Обрабатывает {for...}...{endfor} циклы."""
            if loop_vars is None:
                loop_vars = {}

            result = []
            i = 0

            while i < len(text):
                if text[i:i+5] == '{for ' or text[i:i+4] == '{for':
                    start = i
                    i += 1

                    while i < len(text) and text[i] != ' ':
                        i += 1

                    if i >= len(text):
                        result.append(text[start])
                        i = start + 1
                        continue

                    i += 1
                    var_name_start = i
                    while i < len(text) and text[i] not in ' \n\t':
                        i += 1
                    var_name = text[var_name_start:i]

                    while i < len(text) and text[i] in ' \n\t':
                        i += 1

                    if not text[i:i+3] == 'in ':
                        result.append(text[start:i])
                        continue

                    i += 3

                    while i < len(text) and text[i] in ' \n\t':
                        i += 1

                    list_name_start = i
                    while i < len(text) and text[i] not in '}\n\t ':
                        i += 1
                    list_name = text[list_name_start:i]

                    while i < len(text) and text[i] != '}':
                        i += 1

                    if i >= len(text):
                        result.append(text[start])
                        i = start + 1
                        continue

                    i += 1

                    body_start = i
                    depth = 1
                    while i < len(text) and depth > 0:
                        if text[i:i+5] == '{for ':
                            depth += 1
                            i += 5
                        elif text[i:i+8] == '{endfor}':
                            depth -= 1
                            if depth == 0:
                                break
                            i += 8
                        else:
                            i += 1

                    if i >= len(text):
                        result.append(text[start])
                        i = start + 1
                        continue

                    body = text[body_start:i]

                    i += 8

                    merged_vars = {**variables, **loop_vars}
                    list_value, found = VariableResolver._resolve_variable_value(list_name, merged_vars)

                    if found and isinstance(list_value, list):
                        for item in list_value:
                            item_vars = {**loop_vars, var_name: item}
                            rendered_body = process_for_loops(body, item_vars)
                            rendered_body = process_blocks_recursive(rendered_body, item_vars)
                            result.append(rendered_body)

                    continue

                result.append(text[i])
                i += 1

            return ''.join(result)

        def process_blocks_recursive(text: str, extra_vars: Optional[Dict[str, Any]] = None) -> str:
            """Рекурсивно обрабатывает все блоки {}."""
            if extra_vars is None:
                extra_vars = {}

            merged_vars = {**variables, **extra_vars}

            result = []
            i = 0

            while i < len(text):
                if text[i] == '{':
                    start = i
                    i += 1

                    optional = False
                    if i < len(text) and text[i] == '?':
                        optional = True
                        i += 1

                    expr_start = i
                    while i < len(text) and (text[i].isalnum() or text[i] == '_' or text[i] == '.'):
                        i += 1

                    if i == expr_start:
                        result.append(text[start])
                        i = start + 1
                        continue

                    expr = text[expr_start:i]
                    default = ""
                    has_default = False

                    if i < len(text) and text[i] == '|':
                        has_default = True
                        i += 1
                        default_start = i

                        depth = 1
                        while i < len(text):
                            if text[i] == '\\' and i + 1 < len(text):
                                i += 2
                                continue

                            if text[i] == '{':
                                depth += 1
                            elif text[i] == '}':
                                depth -= 1
                                if depth == 0:
                                    break
                            i += 1

                        if i >= len(text):
                            default = text[default_start:].rstrip()
                        else:
                            default = text[default_start:i].rstrip()

                    if i < len(text) and text[i] == '}':
                        i += 1
                    else:
                        result.append(text[start:i])
                        continue

                    value, found = VariableResolver._resolve_variable_value(expr, merged_vars)

                    if optional:
                        if found and not VariableResolver._is_empty_value(value):
                            if has_default:
                                has_nested_blocks = False
                                i_check = 0
                                while i_check < len(default):
                                    if default[i_check] == '\\' and i_check + 1 < len(default):
                                        i_check += 2
                                    elif default[i_check] == '{':
                                        has_nested_blocks = True
                                        break
                                    else:
                                        i_check += 1

                                if has_nested_blocks or '\n' in default:
                                    processed_default = process_blocks_recursive(default, extra_vars)
                                    processed_default = processed_default.replace('\\\\', '\x00')
                                    processed_default = processed_default.replace('\\}', '}').replace('\\{', '{')
                                    processed_default = processed_default.replace('\x00', '\\')
                                    result.append(processed_default)
                                else:
                                    result.append(str(value))
                            else:
                                result.append(str(value))
                        else:
                            if has_default:
                                has_nested_blocks = False
                                i_check = 0
                                while i_check < len(default):
                                    if default[i_check] == '\\' and i_check + 1 < len(default):
                                        i_check += 2
                                    elif default[i_check] == '{':
                                        has_nested_blocks = True
                                        break
                                    else:
                                        i_check += 1

                                if has_nested_blocks or '\n' in default:
                                    result.append("")
                                else:
                                    processed_default = process_blocks_recursive(default, extra_vars)
                                    processed_default = processed_default.replace('\\\\', '\x00')
                                    processed_default = processed_default.replace('\\}', '}').replace('\\{', '{')
                                    processed_default = processed_default.replace('\x00', '\\')
                                    result.append(processed_default)
                            else:
                                result.append("")
                    else:
                        if not found:
                            if has_default:
                                processed_default = process_blocks_recursive(default, extra_vars)
                                processed_default = processed_default.replace('\\\\', '\x00')
                                processed_default = processed_default.replace('\\}', '}').replace('\\{', '{')
                                processed_default = processed_default.replace('\x00', '\\')
                                result.append(processed_default)
                            elif safe:
                                result.append(text[start:i])
                            else:
                                raise ValueError(f"Переменная '{expr}' не найдена и нет default значения")
                        else:
                            if VariableResolver._is_empty_value(value):
                                if has_default:
                                    processed_default = process_blocks_recursive(default, extra_vars)
                                    processed_default = processed_default.replace('\\\\', '\x00')
                                    processed_default = processed_default.replace('\\}', '}').replace('\\{', '{')
                                    processed_default = processed_default.replace('\x00', '\\')
                                    result.append(processed_default)
                                else:
                                    result.append(str(value))
                            else:
                                result.append(str(value))
                else:
                    result.append(text[i])
                    i += 1

            return ''.join(result)

        def process_short_format(text: str, extra_vars: Optional[Dict[str, Any]] = None) -> str:
            """Обрабатывает короткий формат ?variable и ?variable|default"""
            if extra_vars is None:
                extra_vars = {}

            result = []
            i = 0
            while i < len(text):
                if text[i] == '?' and (i == 0 or (text[i-1] != '{' and text[i-1] != '\\')):
                    j = i + 1
                    while j < len(text) and (text[j].isalnum() or text[j] == '_' or text[j] == '.'):
                        j += 1

                    if j > i + 1:
                        expr = text[i+1:j]
                        default = ""
                        has_default = False

                        if j < len(text) and text[j] == '|':
                            has_default = True
                            j += 1
                            default_start = j
                            while j < len(text):
                                if text[j] == '\n':
                                    break
                                if text[j] == '{':
                                    break
                                if text[j] in ' \t':
                                    space_end = j
                                    while space_end < len(text) and text[space_end] in ' \t':
                                        space_end += 1
                                    if space_end < len(text) and text[space_end] in '{?':
                                        break
                                j += 1
                            default = text[default_start:j].rstrip()

                        merged_vars = {**variables, **extra_vars}
                        value, found = VariableResolver._resolve_variable_value(expr, merged_vars)

                        if found and not VariableResolver._is_empty_value(value):
                            result.append(str(value))
                        elif has_default:
                            result.append(default or "")
                        else:
                            result.append("")

                        i = j
                        continue

                result.append(text[i])
                i += 1

            return ''.join(result)

        result = process_short_format(template)
        result = process_for_loops(result)
        result = process_blocks_recursive(result)

        return result


def get_state() -> Optional[Dict[str, Any]]:
    """
    Получает state агента из контекста.
    Используется в тулах для доступа к store и другим данным state.

    Returns:
        State агента или None если не доступен
    """
    context = get_context()
    if context is None:
        return None
    return context.state


def set_state_in_context(state: Dict[str, Any]) -> None:
    """
    Устанавливает state в контекст.
    Вызывается автоматически при входе в агента.

    Args:
        state: State агента для установки в контекст
    """
    context = get_context()
    if context is None:
        raise RuntimeError("Нельзя установить state: контекст запроса не установлен")
    context.state = state
