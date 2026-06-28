"""
Единый движок резолвинга переменных компании.

Один проход на старте flow (или по явному запросу) превращает версионируемые
определения ``PlatformVariable`` в плоский map ``{key: value}``:

- выбор эффективного значения по scoped overrides (условия по company/user/namespace/
  channel/значению другой переменной);
- подстановка ссылок ``@var:other`` и ``@ctx:field`` (static-значения и expression-шаблоны);
- топосорт зависимостей между переменными с детекцией циклов (Zero-Guess: цикл/missing → raise).

Движок не ходит в хранилище: он получает уже загруженные определения и seed
(identity/system переменные) и детерминированно считает результат.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import ClassVar, Final

from core.types import JsonValue
from core.variables.models import (
    PlatformVariable,
    ResolutionContext,
    ScopeCondition,
    ScopeField,
    ScopeOp,
    VariableScopeOverride,
    VariableValueKind,
    VariableValuePayload,
    VariableValueSpec,
)
from core.variables.resolver import VariableResolutionError, VarResolver

_CTX_FULL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^@ctx:([a-zA-Z_][a-zA-Z0-9_]*)$")
_CTX_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"@ctx:([a-zA-Z_][a-zA-Z0-9_]*)")
_VAR_TOKEN_ROOT_PATTERN: Final[re.Pattern[str]] = re.compile(r"@var:([a-zA-Z_][a-zA-Z0-9_.]*)")

_CTX_FIELDS: Final[frozenset[str]] = frozenset(
    {ScopeField.COMPANY_ID.value, ScopeField.USER_ID.value, ScopeField.NAMESPACE.value, ScopeField.CHANNEL.value}
)


class VariableCycleError(VariableResolutionError):
    """Обнаружен цикл зависимостей между переменными."""


class ResolutionEngine:
    """Детерминированный резолвер версионируемых переменных компании."""

    _CTX_FIELD_BY_NAME: ClassVar[dict[str, ScopeField]] = {
        ScopeField.COMPANY_ID.value: ScopeField.COMPANY_ID,
        ScopeField.USER_ID.value: ScopeField.USER_ID,
        ScopeField.NAMESPACE.value: ScopeField.NAMESPACE,
        ScopeField.CHANNEL.value: ScopeField.CHANNEL,
    }

    @classmethod
    def resolve(
        cls,
        definitions: list[PlatformVariable],
        context: ResolutionContext,
        seed: Mapping[str, JsonValue] | None = None,
    ) -> dict[str, JsonValue]:
        """Резолвит определения переменных в плоский map значений.

        Аргументы:
            definitions: версионируемые переменные компании (resolvable).
            context: контекст исполнителя для scope/`@ctx:`.
            seed: уже резолвнутые внешние переменные (identity/system/request override),
                видимые как ``@var:`` зависимости.
        """
        by_key: dict[str, PlatformVariable] = {definition.variable_key: definition for definition in definitions}
        resolved: dict[str, JsonValue] = dict(seed or {})
        order = cls._topological_order(by_key)
        for key in order:
            resolved[key] = cls._resolve_one(by_key[key], resolved, context)
        return resolved

    @classmethod
    def _resolve_one(
        cls,
        definition: PlatformVariable,
        resolved: Mapping[str, JsonValue],
        context: ResolutionContext,
    ) -> JsonValue:
        spec = cls._select_spec(definition.payload, resolved, context)
        if spec.value_kind == VariableValueKind.EXPRESSION:
            if spec.expression is None:
                raise VariableResolutionError(
                    f"Variable '{definition.variable_key}' имеет value_kind=expression, но expression не задан"
                )
            return cls._substitute_string(spec.expression, resolved, context)
        return cls._substitute(spec.value, resolved, context)

    @classmethod
    def _select_spec(
        cls,
        payload: VariableValuePayload,
        resolved: Mapping[str, JsonValue],
        context: ResolutionContext,
    ) -> VariableValueSpec:
        for override in sorted(payload.scopes, key=lambda scope: scope.priority, reverse=True):
            if cls._override_matches(override, resolved, context):
                return override
        return payload.base

    @classmethod
    def _override_matches(
        cls,
        override: VariableScopeOverride,
        resolved: Mapping[str, JsonValue],
        context: ResolutionContext,
    ) -> bool:
        return all(cls._condition_matches(condition, resolved, context) for condition in override.match)

    @classmethod
    def _condition_matches(
        cls,
        condition: ScopeCondition,
        resolved: Mapping[str, JsonValue],
        context: ResolutionContext,
    ) -> bool:
        actual = cls._condition_actual(condition, resolved, context)
        match condition.op:
            case ScopeOp.EXISTS:
                return actual is not None
            case ScopeOp.EQ:
                return actual == condition.value
            case ScopeOp.IN:
                if not isinstance(condition.value, list):
                    raise VariableResolutionError("ScopeOp.IN требует list в value условия")
                return actual in condition.value

    @classmethod
    def _condition_actual(
        cls,
        condition: ScopeCondition,
        resolved: Mapping[str, JsonValue],
        context: ResolutionContext,
    ) -> JsonValue:
        if condition.field == ScopeField.VAR:
            if not condition.ref_key:
                raise VariableResolutionError("ScopeField.VAR требует ref_key")
            if condition.ref_key not in resolved:
                raise VariableResolutionError(
                    f"Условие scope ссылается на нерезолвнутую переменную '@var:{condition.ref_key}'"
                )
            return resolved[condition.ref_key]
        return context.field_value(condition.field)

    @classmethod
    def _substitute(
        cls,
        value: JsonValue,
        resolved: Mapping[str, JsonValue],
        context: ResolutionContext,
    ) -> JsonValue:
        if isinstance(value, Mapping):
            return {key: cls._substitute(item, resolved, context) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._substitute(item, resolved, context) for item in value]
        if isinstance(value, str):
            return cls._substitute_scalar(value, resolved, context)
        return value

    @classmethod
    def _substitute_scalar(
        cls,
        value: str,
        resolved: Mapping[str, JsonValue],
        context: ResolutionContext,
    ) -> JsonValue:
        ctx_full = _CTX_FULL_PATTERN.match(value)
        if ctx_full is not None:
            return cls._context_value(ctx_full.group(1), context)
        if VarResolver.VAR_REF_PATTERN.match(value):
            return VarResolver.resolve_ref(value, resolved)
        if "@ctx:" not in value and "@var:" not in value:
            return value
        return cls._substitute_string(value, resolved, context)

    @classmethod
    def _substitute_string(
        cls,
        template: str,
        resolved: Mapping[str, JsonValue],
        context: ResolutionContext,
    ) -> str:
        def replace_ctx(match: re.Match[str]) -> str:
            return str(cls._context_value(match.group(1), context))

        rendered = _CTX_TOKEN_PATTERN.sub(replace_ctx, template)
        if "@var:" in rendered:
            rendered = VarResolver.resolve_text(rendered, resolved)
        return rendered

    @classmethod
    def _context_value(cls, name: str, context: ResolutionContext) -> JsonValue:
        if name not in _CTX_FIELDS:
            raise VariableResolutionError(f"Неизвестное поле контекста '@ctx:{name}'")
        return context.field_value(cls._CTX_FIELD_BY_NAME[name])

    @classmethod
    def _topological_order(cls, by_key: Mapping[str, PlatformVariable]) -> list[str]:
        dependencies: dict[str, set[str]] = {
            key: {dep for dep in cls._dependencies(definition) if dep in by_key}
            for key, definition in by_key.items()
        }
        order: list[str] = []
        visited: dict[str, int] = {}

        def visit(node: str, stack: tuple[str, ...]) -> None:
            state = visited.get(node, 0)
            if state == 2:
                return
            if state == 1:
                cycle = " -> ".join((*stack, node))
                raise VariableCycleError(f"Цикл зависимостей переменных: {cycle}")
            visited[node] = 1
            for dep in sorted(dependencies[node]):
                visit(dep, (*stack, node))
            visited[node] = 2
            order.append(node)

        for key in sorted(by_key):
            visit(key, ())
        return order

    @classmethod
    def _dependencies(cls, definition: PlatformVariable) -> set[str]:
        keys: set[str] = set()
        cls._collect_spec_refs(definition.payload.base, keys)
        for override in definition.payload.scopes:
            cls._collect_spec_refs(override, keys)
            for condition in override.match:
                if condition.field == ScopeField.VAR and condition.ref_key:
                    keys.add(condition.ref_key)
        return keys

    @classmethod
    def _collect_spec_refs(cls, spec: VariableValueSpec, keys: set[str]) -> None:
        if spec.value_kind == VariableValueKind.EXPRESSION:
            if spec.expression is not None:
                cls._collect_string_refs(spec.expression, keys)
            return
        cls._collect_value_refs(spec.value, keys)

    @classmethod
    def _collect_value_refs(cls, value: JsonValue, keys: set[str]) -> None:
        if isinstance(value, Mapping):
            for item in value.values():
                cls._collect_value_refs(item, keys)
        elif isinstance(value, list):
            for item in value:
                cls._collect_value_refs(item, keys)
        elif isinstance(value, str):
            cls._collect_string_refs(value, keys)

    @classmethod
    def _collect_string_refs(cls, value: str, keys: set[str]) -> None:
        for match in _VAR_TOKEN_ROOT_PATTERN.finditer(value):
            keys.add(match.group(1).split(".", 1)[0])
