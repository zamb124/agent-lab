"""Service Kit: единый DI платформы.

Процесс описывает свои компоненты одним классом ``<Svc>Di(ServiceDi)``: поле — компонент,
который читает boundary-код. Kit строит граф по типам параметров конструкторов и
recipes, создаёт всё eagerly до начала обслуживания и отдаёт frozen-экземпляр.
Одна область жизни — процесс; данные запроса живут в ``core.context``.
"""

from __future__ import annotations

import dataclasses
import inspect
import types
import typing
from collections import Counter
from collections.abc import AsyncGenerator, Callable, Coroutine, Generator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import ClassVar, Literal, NewType, TypeGuard, TypeVar, dataclass_transform, final

from pydantic import BaseModel

from core.config import BaseSettings
from core.di.errors import DiError
from core.di.reflection import (
    NOT_COMPONENT_TYPES,
    DiKey,
    RecipeKind,
    annotation_key,
    class_initializer,
    dependency_parameters,
    initializer_hints,
    key_label,
    recipe_kind,
    recipe_output,
    resolved_hints,
)


@final
@dataclass(frozen=True, slots=True, eq=False)
class Recipe:
    """Способ собрать компонент, который не собирается из ``__init__``: конфиг, IO, Protocol, teardown."""

    function: Callable[..., object]
    kind: RecipeKind
    label: str


def recipe(function: Callable[..., object]) -> Recipe:
    """Функция-recipe: sync, async или генератор (ресурс с teardown); ключ — тип возврата."""
    if not isinstance(function, types.FunctionType):
        raise DiError(("@recipe decorates plain Python functions",))
    return Recipe(
        function=function,
        kind=recipe_kind(function),
        label=f"@recipe {function.__qualname__}",
    )


@dataclass_transform(frozen_default=True, kw_only_default=True, eq_default=False)
class ServiceDi:
    """База DI процесса: подкласс — frozen kw-only dataclass, поле — компонент для boundary."""

    di_recipes: ClassVar[tuple[Recipe, ...]] = ()

    def __init__(self, **components: object) -> None:
        _ = components
        raise TypeError("ServiceDi is abstract: build a subclass with build_di")

    def __init_subclass__(cls, *, recipes: tuple[Recipe, ...] = ()) -> None:
        super().__init_subclass__()
        cls.di_recipes = recipes
        _ = dataclasses.dataclass(frozen=True, kw_only=True, eq=False, repr=False)(cls)


DiT = TypeVar("DiT", bound=ServiceDi)


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessIdentity:
    """Корень графа, который даёт runner: кто этот процесс."""

    service_name: str
    files_route_segment: str


@final
@dataclass(frozen=True, slots=True)
class DiEdge:
    parameter: str
    key: DiKey


@final
@dataclass(frozen=True, slots=True)
class DiStep:
    key: DiKey | None
    label: str
    factory: Callable[..., object]
    edges: tuple[DiEdge, ...]


@final
@dataclass(frozen=True, slots=True)
class DiPlan:
    """Проверенный граф: шаги в порядке зависимостей и поля результата."""

    di_class: type[ServiceDi]
    steps: tuple[DiStep, ...]
    fields: tuple[DiEdge, ...]


def _core_settings_sections() -> tuple[tuple[str, type[BaseModel]], ...]:
    found: list[tuple[str, type[BaseModel]]] = []
    for name, field_info in BaseSettings.model_fields.items():
        annotation = field_info.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            found.append((name, annotation))
    repeated = Counter(section_type for _, section_type in found)
    return tuple((name, section_type) for name, section_type in found if repeated[section_type] == 1)


CORE_SETTINGS_SECTIONS: tuple[tuple[str, type[BaseModel]], ...] = _core_settings_sections()
_CORE_SECTION_TYPES: frozenset[type[BaseModel]] = frozenset(
    section_type for _, section_type in CORE_SETTINGS_SECTIONS
)


def process_roots(settings: BaseSettings, identity: ProcessIdentity) -> dict[DiKey, object]:
    """Корни графа процесса: settings по классам MRO, секции core ``BaseSettings``, identity."""
    roots: dict[DiKey, object] = {ProcessIdentity: identity}
    for settings_class in type(settings).__mro__:
        if issubclass(settings_class, BaseSettings):
            roots[settings_class] = settings
    sections: dict[str, object] = dict(settings)
    for name, section_type in CORE_SETTINGS_SECTIONS:
        section = sections[name]
        if not isinstance(section, section_type):
            raise DiError((f"settings.{name} is not {section_type.__qualname__}",))
        roots[section_type] = section
    return roots


def _static_root(key: DiKey) -> bool:
    if key is ProcessIdentity or key in _CORE_SECTION_TYPES:
        return True
    return isinstance(key, type) and issubclass(key, BaseSettings)


class _Planner:
    def __init__(self, di_class: type[ServiceDi], *, is_root: Callable[[DiKey], bool]) -> None:
        self._di_class: type[ServiceDi] = di_class
        self._is_root: Callable[[DiKey], bool] = is_root
        self._recipes: dict[DiKey, Recipe] = {}
        self._own_recipes: dict[DiKey, Recipe] = {}
        self._used_recipes: set[DiKey] = set()
        self._state: dict[DiKey, Literal["open", "done"]] = {}
        self._steps: list[DiStep] = []
        self._problems: list[str] = []

    def plan(self, lifecycle: tuple[Recipe, ...]) -> DiPlan:
        name = self._di_class.__qualname__
        if not name.endswith("Di"):
            self._problems.append(f"{name}: DI class name ends with 'Di'")
        self._collect_recipes()
        fields = self._fields()
        for edge in fields:
            self._visit(edge.key, (f"{name}.{edge.parameter}",))
        for item in lifecycle:
            self._lifecycle_step(item)
        for key, item in self._own_recipes.items():
            if key not in self._used_recipes:
                self._problems.append(f"{name}: {item.label} ({key_label(key)}) is not used by the graph")
        if self._problems:
            raise DiError(self._problems)
        return DiPlan(di_class=self._di_class, steps=tuple(self._steps), fields=fields)

    def _collect_recipes(self) -> None:
        for klass in reversed(self._di_class.__mro__):
            if klass is ServiceDi or not issubclass(klass, ServiceDi):
                continue
            local: dict[DiKey, Recipe] = {}
            for item in klass.di_recipes:
                try:
                    hints = resolved_hints(item.function, owner=item.label)
                    key = recipe_output(item.kind, hints, owner=item.label)
                except DiError as error:
                    self._problems.extend(error.problems)
                    continue
                if key is types.NoneType:
                    self._problems.append(f"{item.label}: returns None; pass it as lifecycle=(...)")
                    continue
                if key in local:
                    self._problems.append(
                        f"{klass.__qualname__}: two recipes provide {key_label(key)}: "
                        + f"{local[key].label}, {item.label}"
                    )
                    continue
                local[key] = item
            self._recipes.update(local)
            if klass is self._di_class:
                self._own_recipes = local

    def _fields(self) -> tuple[DiEdge, ...]:
        name = self._di_class.__qualname__
        if not dataclasses.is_dataclass(self._di_class):
            self._problems.append(f"{name}: DI class is not built by ServiceDi")
            return ()
        try:
            hints = resolved_hints(self._di_class, owner=name)
        except DiError as error:
            self._problems.extend(error.problems)
            return ()
        edges: list[DiEdge] = []
        for field in dataclasses.fields(self._di_class):
            key = annotation_key(hints.get(field.name))
            if key is None:
                self._problems.append(f"{name}.{field.name}: field type is a class or NewType")
                continue
            edges.append(DiEdge(parameter=field.name, key=key))
        if not edges:
            self._problems.append(f"{name}: DI class declares at least one component field")
        return tuple(edges)

    def _visit(self, key: DiKey, path: tuple[str, ...]) -> None:
        if self._is_root(key):
            return
        state = self._state.get(key)
        if state == "done":
            return
        if state == "open":
            self._problems.append("dependency cycle: " + " -> ".join((*path, key_label(key))))
            return
        self._state[key] = "open"
        step = self._step_for(key, path)
        if step is not None:
            for edge in step.edges:
                self._visit(edge.key, (*path, f"{step.label}({edge.parameter})"))
            self._steps.append(step)
        self._state[key] = "done"

    def _step_for(self, key: DiKey, path: tuple[str, ...]) -> DiStep | None:
        where = " -> ".join((*path, key_label(key)))
        provider = self._recipes.get(key)
        try:
            if isinstance(key, type) and issubclass(key, ServiceDi):
                raise DiError(
                    (f"{where}: process DI is built after the graph; depend on the exact components",)
                )
            if provider is not None:
                self._used_recipes.add(key)
                return self._recipe_step(provider, key)
            if isinstance(key, NewType):
                raise DiError((f"{where}: NewType role needs a @recipe",))
            if key in NOT_COMPONENT_TYPES:
                raise DiError((f"{where}: builtin type cannot be a dependency; inject a settings section",))
            if issubclass(key, BaseSettings):
                raise DiError((f"{where}: process settings do not provide {key.__qualname__}",))
            if typing.is_protocol(key) or inspect.isabstract(key):
                raise DiError((f"{where}: abstract type needs a @recipe returning it",))
            label = key.__qualname__
            initializer = class_initializer(key)
            if initializer is None:
                return DiStep(key=key, label=label, factory=key, edges=())
            names = dependency_parameters(initializer, bound=True, owner=label)
            hints = initializer_hints(key, initializer, owner=label)
            return DiStep(key=key, label=label, factory=key, edges=_edges(names, hints, label))
        except DiError as error:
            self._problems.extend(error.problems)
            return None

    def _recipe_step(self, item: Recipe, key: DiKey | None) -> DiStep:
        names = dependency_parameters(item.function, bound=False, owner=item.label)
        hints = resolved_hints(item.function, owner=item.label)
        return DiStep(key=key, label=item.label, factory=item.function, edges=_edges(names, hints, item.label))

    def _lifecycle_step(self, item: Recipe) -> None:
        try:
            hints = resolved_hints(item.function, owner=item.label)
            if recipe_output(item.kind, hints, owner=item.label) is not types.NoneType:
                raise DiError((f"{item.label}: lifecycle recipe returns None or AsyncIterator[None]",))
            step = self._recipe_step(item, None)
        except DiError as error:
            self._problems.extend(error.problems)
            return
        for edge in step.edges:
            self._visit(edge.key, (f"lifecycle {item.label}({edge.parameter})",))
        self._steps.append(step)


def _edges(names: tuple[str, ...], hints: Mapping[str, object], owner: str) -> tuple[DiEdge, ...]:
    edges: list[DiEdge] = []
    problems: list[str] = []
    for name in names:
        key = annotation_key(hints.get(name))
        if key is None:
            problems.append(f"{owner}({name}): parameter type is a class, Protocol or NewType")
            continue
        edges.append(DiEdge(parameter=name, key=key))
    if problems:
        raise DiError(problems)
    return tuple(edges)


def check_di(di_class: type[ServiceDi], *, lifecycle: tuple[Recipe, ...] = ()) -> DiPlan:
    """Статическая проверка графа без сборки: корни — settings, секции core, identity."""
    return _Planner(di_class, is_root=_static_root).plan(lifecycle)


def _is_async_generator_function(
    function: Callable[..., object],
) -> TypeGuard[Callable[..., AsyncGenerator[object, None]]]:
    return inspect.isasyncgenfunction(function)


def _is_generator_function(function: Callable[..., object]) -> TypeGuard[Callable[..., Generator[object, None, None]]]:
    return inspect.isgeneratorfunction(function)


def _is_coroutine_function(function: Callable[..., object]) -> TypeGuard[Callable[..., Coroutine[object, object, object]]]:
    return inspect.iscoroutinefunction(function)


async def _enter_async_resource[ComponentT](
    label: str,
    resource: AsyncGenerator[ComponentT, None],
    stack: AsyncExitStack,
) -> ComponentT:
    try:
        component = await anext(resource)
    except StopAsyncIteration as error:
        raise DiError((f"{label}: resource recipe did not yield its component",)) from error

    async def teardown() -> None:
        try:
            _ = await anext(resource)
        except StopAsyncIteration:
            return
        raise DiError((f"{label}: resource recipe yields exactly once",))

    _ = stack.push_async_callback(teardown)
    return component


def _enter_resource[ComponentT](
    label: str,
    resource: Generator[ComponentT, None, None],
    stack: AsyncExitStack,
) -> ComponentT:
    try:
        component = next(resource)
    except StopIteration as error:
        raise DiError((f"{label}: resource recipe did not yield its component",)) from error

    def teardown() -> None:
        try:
            _ = next(resource)
        except StopIteration:
            return
        raise DiError((f"{label}: resource recipe yields exactly once",))

    _ = stack.callback(teardown)
    return component


async def _produce(step: DiStep, values: dict[DiKey, object], stack: AsyncExitStack) -> None:
    arguments = {edge.parameter: values[edge.key] for edge in step.edges}
    factory = step.factory
    if _is_async_generator_function(factory):
        component = await _enter_async_resource(step.label, factory(**arguments), stack)
    elif _is_generator_function(factory):
        component = _enter_resource(step.label, factory(**arguments), stack)
    elif _is_coroutine_function(factory):
        component = await factory(**arguments)
    else:
        component = factory(**arguments)
    if step.key is not None:
        values[step.key] = component


@asynccontextmanager
async def build_di(
    di_class: type[DiT],
    *,
    roots: Mapping[DiKey, object],
    lifecycle: tuple[Recipe, ...] = (),
) -> AsyncGenerator[DiT]:
    """Собрать DI eagerly: ресурсы входят в порядке зависимостей и закрываются в обратном.

    Код recipe после ``yield`` — teardown: он выполняется всегда, в том числе при ошибке
    сборки или работы процесса; исключение процесса в генератор не передаётся.
    """
    plan = _Planner(di_class, is_root=lambda key: key in roots).plan(lifecycle)
    values: dict[DiKey, object] = dict(roots)
    async with AsyncExitStack() as stack:
        for step in plan.steps:
            try:
                await _produce(step, values, stack)
            except Exception as error:
                error.add_note(f"Service Kit: {di_class.__qualname__} failed at {step.label}")
                raise
        yield di_class(**{edge.parameter: values[edge.key] for edge in plan.fields})
