"""Runtime-аннотации конструкторов и recipes — единственное место Kit, которое читает сигнатуры.

Каждое значение аннотации сразу сужается до ключа DI (класс или ``NewType``);
всё остальное — ``DiError`` с именем владельца и параметра.
"""

from __future__ import annotations

import inspect
import types
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Generator, Iterator, Mapping
from typing import Literal, NewType, get_type_hints

from core.di.errors import DiError

DiKey = type[object] | NewType
RecipeKind = Literal["sync", "async", "async_generator", "generator"]

NOT_COMPONENT_TYPES: frozenset[DiKey] = frozenset(
    {str, int, float, bool, bytes, bytearray, complex, list, dict, set, frozenset, tuple, type, object}
)


def annotation_key(annotation: object) -> DiKey | None:
    if isinstance(annotation, NewType):
        return annotation
    if isinstance(annotation, type):
        return annotation
    return None


def key_label(key: DiKey) -> str:
    if isinstance(key, NewType):
        return key.__name__
    return key.__qualname__


def resolved_hints(target: Callable[..., object], *, owner: str) -> Mapping[str, object]:
    try:
        hints: Mapping[str, object] = get_type_hints(target)
    except NameError as error:
        raise DiError(
            (
                f"{owner}: annotation {error.name!r} is not importable at runtime; "
                + "import it at module level instead of TYPE_CHECKING",
            )
        ) from error
    return hints


def dependency_parameters(
    target: Callable[..., object],
    *,
    bound: bool,
    owner: str,
) -> tuple[str, ...]:
    """Параметры без default: только они — зависимости; default оставляется как есть."""
    if not isinstance(target, types.FunctionType):
        raise DiError((f"{owner}: only Python functions can be autowired",))
    function = target
    code = function.__code__
    if code.co_flags & inspect.CO_VARARGS or code.co_flags & inspect.CO_VARKEYWORDS:
        raise DiError((f"{owner}: *args/**kwargs cannot be autowired; add a @recipe",))
    positional_count = code.co_argcount
    names = code.co_varnames[: positional_count + code.co_kwonlyargcount]
    first = 1 if bound else 0
    defaults = function.__defaults__
    default_count = len(defaults) if defaults is not None else 0
    required_positional = names[first : positional_count - default_count]
    if code.co_posonlyargcount > first and required_positional[: code.co_posonlyargcount - first]:
        raise DiError((f"{owner}: positional-only parameters cannot be injected",))
    keyword_defaults = function.__kwdefaults__
    keyword_default_names: frozenset[str] = (
        frozenset(keyword_defaults) if keyword_defaults is not None else frozenset()
    )
    required_keyword = tuple(
        name for name in names[positional_count:] if name not in keyword_default_names
    )
    return (*required_positional, *required_keyword)


def class_initializer(cls: type[object]) -> types.FunctionType | None:
    """``None`` — у класса нет своего ``__init__``: зависимостей нет."""
    initializer = cls.__init__
    if initializer is object.__init__:
        return None
    if isinstance(initializer, types.FunctionType):
        return initializer
    raise DiError((f"{cls.__qualname__}: __init__ is not a Python function; add a @recipe",))


def initializer_hints(
    cls: type[object],
    initializer: types.FunctionType,
    *,
    owner: str,
) -> Mapping[str, object]:
    """Типы параметров ``__init__`` класса.

    ``__init__`` от dataclasses собирает аннотации полей со всех баз, а ``get_type_hints``
    разрешает их в модуле самого ``__init__``: строковая аннотация базы из другого модуля
    там не видна. Поэтому типы такого ``__init__`` читаются с объявившего его класса —
    каждое поле в модуле своего класса.
    """
    if not _generated_by_dataclasses(initializer):
        return resolved_hints(initializer, owner=owner)
    declaring_class = next(klass for klass in cls.__mro__ if "__init__" in klass.__dict__)
    return resolved_hints(declaring_class, owner=owner)


def _generated_by_dataclasses(function: types.FunctionType) -> bool:
    annotate = function.__annotate__
    return isinstance(annotate, types.FunctionType) and "__generated_by_dataclasses__" in annotate.__dict__


def recipe_kind(function: Callable[..., object]) -> RecipeKind:
    if inspect.isasyncgenfunction(function):
        return "async_generator"
    if inspect.iscoroutinefunction(function):
        return "async"
    if inspect.isgeneratorfunction(function):
        return "generator"
    return "sync"


def recipe_output(
    kind: RecipeKind,
    hints: Mapping[str, object],
    *,
    owner: str,
) -> DiKey:
    """Ключ, который даёт recipe: тип возврата, для генератора — тип ``yield``."""
    declared = hints.get("return")
    if declared is None:
        raise DiError((f"{owner}: return annotation is required",))
    produced = declared
    if kind == "async_generator" or kind == "generator":
        if not isinstance(declared, types.GenericAlias):
            raise DiError(
                (f"{owner}: generator recipe returns collections.abc.AsyncIterator[T] or Iterator[T]",)
            )
        allowed = (AsyncIterator, AsyncGenerator) if kind == "async_generator" else (Iterator, Generator)
        if declared.__origin__ not in allowed:
            raise DiError((f"{owner}: generator recipe return type {declared!r} is not supported",))
        arguments: tuple[object, ...] = declared.__args__
        produced = types.NoneType if arguments[0] is None else arguments[0]
    key = annotation_key(produced)
    if key is None:
        raise DiError((f"{owner}: return type {produced!r} is not a component type",))
    return key
