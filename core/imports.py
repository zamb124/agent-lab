"""Границы нетипизированного импорта и просмотра значения как Protocol."""

import importlib
from collections.abc import Mapping
from types import FrameType, FunctionType, MethodType, ModuleType, TracebackType
from typing import cast, override
from typing import cast as type_cast

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


type _LazyModuleAttr = (
    ModuleType | type | FunctionType | MethodType | int | str | bytes | bool
)


class _LazyModule(ModuleType):
    """Модуль-прокси: реальный ``importlib.import_module`` при первом доступе к атрибуту.

    Родительские пакеты dotted-имени тоже откладываются (find_spec их импортировал
    бы eagerly), поэтому резолв идёт целиком через import_module в sys.modules.
    Новая форма атрибута у ленивого модуля — расширить ``_LazyModuleAttr``.
    """

    @override
    def __getattr__(self, name: str) -> _LazyModuleAttr:
        return type_cast(
            _LazyModuleAttr,
            getattr(importlib.import_module(self.__name__), name),
        )


def lazy_module(qualified_name: str) -> ModuleType:
    """Тяжёлый модуль, загружаемый при первом обращении к атрибуту.

    Связывается под тем же именем, что ``if TYPE_CHECKING: import <qualified_name>``
    в else-ветке — pyright видит реальный модуль, рантайм платит за импорт
    только при вызове.
    """
    return _LazyModule(qualified_name)
