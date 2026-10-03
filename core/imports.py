"""Границы нетипизированного импорта и просмотра значения как Protocol."""

from collections.abc import Mapping
from types import FrameType, FunctionType, MethodType, ModuleType, TracebackType
from typing import cast

type NamespaceOwner = (
    ModuleType | type | MethodType | FunctionType | TracebackType | FrameType
)


def imported_attr[T](owner: NamespaceOwner, name: str, _view: type[T]) -> T | None:
    """Атрибут объекта. ``vars()`` отдаёт ``dict[str, Any]``."""
    attrs = cast(Mapping[str, T], vars(owner))
    return attrs.get(name)


def _erased[S](value: S, kind: type[S]) -> object:
    _ = kind
    return value


def typed_view[T, S](value: S, kind: type[S], view: type[T]) -> T:
    """Значение известного класса как Protocol. Прямой cast в Protocol — reportInvalidCast."""
    _ = view
    return cast(T, _erased(value, kind))


def module_sdk[T](module: ModuleType, view: type[T]) -> T:
    """Модуль без stub как Protocol вызывающего."""
    return typed_view(module, ModuleType, view)
