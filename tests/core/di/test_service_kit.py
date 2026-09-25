"""Service Kit (``core/di``): autowiring по типам конструкторов, recipes, lifecycle и ошибки графа."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, Iterator
from typing import NewType, Protocol

import pytest

from apps.secrets.config import SecretsSettings
from core.app.factory import load_service_settings
from core.config import BaseSettings, DatabaseConfig
from core.di import (
    DiError,
    ProcessIdentity,
    Recipe,
    ServiceDi,
    build_di,
    check_di,
    process_roots,
    recipe,
)
from core.di.kit import CORE_SETTINGS_SECTIONS
from tests.core.di.inherited_base import Ledger
from tests.core.di.inherited_child import AuditDi, watch_ledger


class Journal:
    """Порядок создания и закрытия компонентов — наблюдаемый результат сборки."""

    def __init__(self) -> None:
        self.entries: list[str] = []


class Clock:
    """Класс без своего ``__init__``: собирается без зависимостей."""


class FrozenClock(Clock):
    pass


class Repository:
    def __init__(self, clock: Clock, journal: Journal) -> None:
        self.clock: Clock = clock
        journal.entries.append("repository")


class Service:
    def __init__(self, repository: Repository, clock: Clock, retries: int = 3) -> None:
        self.repository: Repository = repository
        self.clock: Clock = clock
        self.retries: int = retries


class AutowireDi(ServiceDi):
    service: Service
    clock: Clock


Endpoint = NewType("Endpoint", str)


class Connection:
    def __init__(self, endpoint: Endpoint) -> None:
        self.endpoint: Endpoint = endpoint


class Cache:
    def __init__(self, connection: Connection) -> None:
        self.connection: Connection = connection


class Session:
    def __init__(self, cache: Cache) -> None:
        self.cache: Cache = cache


@recipe
def endpoint_url() -> Endpoint:
    return Endpoint("postgres://kit")


@recipe
async def open_connection(endpoint: Endpoint, journal: Journal) -> AsyncIterator[Connection]:
    journal.entries.append("connection.open")
    yield Connection(endpoint)
    journal.entries.append("connection.close")


@recipe
def open_cache(connection: Connection, journal: Journal) -> Iterator[Cache]:
    journal.entries.append("cache.open")
    yield Cache(connection)
    journal.entries.append("cache.close")


@recipe
async def start_session(cache: Cache, journal: Journal) -> Session:
    journal.entries.append("session")
    return Session(cache)


class ResourcesDi(ServiceDi, recipes=(endpoint_url, open_connection, open_cache, start_session)):
    session: Session
    cache: Cache


@recipe
def broken_session(cache: Cache) -> Session:
    _ = cache
    raise RuntimeError("session backend is down")


class BrokenDi(ServiceDi, recipes=(endpoint_url, open_connection, open_cache, broken_session)):
    session: Session


@recipe
async def announce(service: Service, journal: Journal) -> AsyncIterator[None]:
    journal.entries.append(f"lifecycle.start retries={service.retries}")
    yield
    journal.entries.append("lifecycle.stop")


@recipe
def frozen_clock() -> Clock:
    return FrozenClock()


class OverrideDi(AutowireDi, recipes=(frozen_clock,)):
    pass


ReadReplica = NewType("ReadReplica", Repository)


class Reports:
    def __init__(self, replica: ReadReplica) -> None:
        self.replica: ReadReplica = replica


@recipe
def read_replica(repository: Repository) -> ReadReplica:
    return ReadReplica(repository)


class RoleDi(ServiceDi, recipes=(read_replica,)):
    reports: Reports


class DatabaseProbe:
    def __init__(self, database: DatabaseConfig, identity: ProcessIdentity) -> None:
        self.redis_url: str = database.redis_url
        self.service_name: str = identity.service_name


class SectionDi(ServiceDi):
    probe: DatabaseProbe


class MissingRoleDi(ServiceDi):
    reports: Reports


class Timeouts:
    def __init__(self, seconds: float) -> None:
        self.seconds: float = seconds


class BuiltinDependencyDi(ServiceDi):
    timeouts: Timeouts


class Notifier(Protocol):
    def notify(self, text: str) -> None: ...


class Alerts:
    def __init__(self, notifier: Notifier) -> None:
        self.notifier: Notifier = notifier


class ProtocolDi(ServiceDi):
    alerts: Alerts


class Ping:
    def __init__(self, pong: Pong) -> None:
        self.pong: Pong = pong


class Pong:
    def __init__(self, ping: Ping) -> None:
        self.ping: Ping = ping


class CycleDi(ServiceDi):
    ping: Ping


@recipe
def system_clock() -> Clock:
    return Clock()


@recipe
def another_clock() -> Clock:
    return Clock()


class AmbiguousDi(ServiceDi, recipes=(system_clock, another_clock)):
    clock: Clock


class UnusedRecipeDi(ServiceDi, recipes=(endpoint_url,)):
    clock: Clock


class Components(ServiceDi):
    clock: Clock


class CollectionFieldDi(ServiceDi):
    clock: Clock
    clocks: list[Clock]


@recipe
async def lifecycle_as_component() -> AsyncIterator[None]:
    yield


class NoneRecipeDi(ServiceDi, recipes=(lifecycle_as_component,)):
    clock: Clock


class BrokenGraphDi(ServiceDi):
    reports: Reports
    timeouts: Timeouts
    ping: Ping


class DiReader:
    def __init__(self, di: AutowireDi) -> None:
        self.di: AutowireDi = di


class DiReaderDi(ServiceDi):
    reader: DiReader


class NestedDi(ServiceDi):
    autowire: AutowireDi


async def test_build_di_autowires_constructor_types_into_one_instance_per_type() -> None:
    journal = Journal()

    async with build_di(AutowireDi, roots={Journal: journal}) as di:
        assert di.service.clock is di.clock
        assert di.service.repository.clock is di.clock
        assert di.service.retries == 3
        assert type(di.clock) is Clock
    assert journal.entries == ["repository"]


async def test_built_di_is_frozen() -> None:
    field_name = "clock"

    async with build_di(AutowireDi, roots={Journal: Journal()}) as di:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(di, field_name, Clock())


async def test_build_di_enters_resources_in_dependency_order_and_closes_them_in_reverse() -> None:
    journal = Journal()

    async with build_di(ResourcesDi, roots={Journal: journal}) as di:
        assert di.session.cache is di.cache
        assert di.cache.connection.endpoint == "postgres://kit"
        assert journal.entries == ["connection.open", "cache.open", "session"]
    assert journal.entries == [
        "connection.open",
        "cache.open",
        "session",
        "cache.close",
        "connection.close",
    ]


async def test_build_di_closes_opened_resources_when_a_later_step_fails() -> None:
    journal = Journal()

    with pytest.raises(RuntimeError, match="session backend is down") as caught:
        async with build_di(BrokenDi, roots={Journal: journal}):
            pytest.fail("BrokenDi must not open")
    assert journal.entries == ["connection.open", "cache.open", "cache.close", "connection.close"]
    assert caught.value.__notes__ == ["Service Kit: BrokenDi failed at @recipe broken_session"]


async def test_teardown_runs_when_the_process_fails_inside_the_di_scope() -> None:
    journal = Journal()

    with pytest.raises(RuntimeError, match="request handling crashed"):
        async with build_di(ResourcesDi, roots={Journal: journal}):
            raise RuntimeError("request handling crashed")
    assert journal.entries == [
        "connection.open",
        "cache.open",
        "session",
        "cache.close",
        "connection.close",
    ]


async def test_lifecycle_recipe_runs_inside_the_di_scope_without_becoming_a_field() -> None:
    journal = Journal()

    async with build_di(AutowireDi, roots={Journal: journal}, lifecycle=(announce,)) as di:
        assert journal.entries == ["repository", "lifecycle.start retries=3"]
        assert [field.name for field in dataclasses.fields(di)] == ["service", "clock"]
    assert journal.entries == ["repository", "lifecycle.start retries=3", "lifecycle.stop"]


async def test_subclass_recipe_overrides_the_component_for_the_whole_graph() -> None:
    async with build_di(OverrideDi, roots={Journal: Journal()}) as di:
        assert type(di.clock) is FrozenClock
        assert di.service.clock is di.clock
        assert di.service.repository.clock is di.clock


async def test_newtype_role_is_built_by_its_recipe() -> None:
    async with build_di(RoleDi, roots={Journal: Journal()}) as di:
        assert type(di.reports.replica) is Repository


async def test_dataclass_component_resolves_inherited_fields_in_the_module_that_declares_them() -> None:
    async with build_di(AuditDi, roots={}) as di:
        assert type(di.audit.ledger) is Ledger
        assert di.audit.ledger is di.ledger
        assert di.audit.retries == 3


def test_process_roots_expose_settings_by_class_core_sections_and_identity() -> None:
    settings, _ = load_service_settings("secrets", SecretsSettings)
    identity = ProcessIdentity(service_name="secrets", files_route_segment="secrets")

    roots = process_roots(settings, identity)

    assert roots[SecretsSettings] is settings
    assert roots[BaseSettings] is settings
    assert roots[DatabaseConfig] is settings.database
    assert roots[ProcessIdentity] is identity
    assert {section_type for _, section_type in CORE_SETTINGS_SECTIONS} <= set(roots)


async def test_settings_sections_and_identity_are_injected_by_type() -> None:
    settings, _ = load_service_settings("secrets", SecretsSettings)
    identity = ProcessIdentity(service_name="secrets", files_route_segment="secrets")

    async with build_di(SectionDi, roots=process_roots(settings, identity)) as di:
        assert di.probe.redis_url == settings.database.redis_url
        assert di.probe.service_name == "secrets"


def test_check_di_returns_steps_in_dependency_order() -> None:
    plan = check_di(ResourcesDi)

    assert [step.label for step in plan.steps] == [
        "@recipe endpoint_url",
        "Journal",
        "@recipe open_connection",
        "@recipe open_cache",
        "@recipe start_session",
    ]
    assert [(edge.parameter, edge.key) for edge in plan.fields] == [("session", Session), ("cache", Cache)]


@pytest.mark.parametrize(
    ("di_class", "problem"),
    [
        (
            MissingRoleDi,
            "MissingRoleDi.reports -> Reports(replica) -> ReadReplica: NewType role needs a @recipe",
        ),
        (
            BuiltinDependencyDi,
            "BuiltinDependencyDi.timeouts -> Timeouts(seconds) -> float: "
            + "builtin type cannot be a dependency; inject a settings section",
        ),
        (
            ProtocolDi,
            "ProtocolDi.alerts -> Alerts(notifier) -> Notifier: abstract type needs a @recipe returning it",
        ),
        (CycleDi, "dependency cycle: CycleDi.ping -> Ping(pong) -> Pong(ping) -> Ping"),
        (
            AmbiguousDi,
            "AmbiguousDi: two recipes provide Clock: @recipe system_clock, @recipe another_clock",
        ),
        (UnusedRecipeDi, "UnusedRecipeDi: @recipe endpoint_url (Endpoint) is not used by the graph"),
        (Components, "Components: DI class name ends with 'Di'"),
        (CollectionFieldDi, "CollectionFieldDi.clocks: field type is a class or NewType"),
        (NoneRecipeDi, "@recipe lifecycle_as_component: returns None; pass it as lifecycle=(...)"),
    ],
)
def test_check_di_rejects_an_invalid_graph_with_a_path_to_the_problem(
    di_class: type[ServiceDi],
    problem: str,
) -> None:
    with pytest.raises(DiError) as caught:
        _ = check_di(di_class)

    assert caught.value.problems == (problem,)


def test_check_di_reports_every_problem_of_the_graph_at_once() -> None:
    with pytest.raises(DiError) as caught:
        _ = check_di(BrokenGraphDi)

    assert caught.value.problems == (
        "BrokenGraphDi.reports -> Reports(replica) -> ReadReplica: NewType role needs a @recipe",
        "BrokenGraphDi.timeouts -> Timeouts(seconds) -> float: "
        + "builtin type cannot be a dependency; inject a settings section",
        "dependency cycle: BrokenGraphDi.ping -> Ping(pong) -> Pong(ping) -> Ping",
    )


@pytest.mark.parametrize(
    ("di_class", "lifecycle", "problem"),
    [
        (
            AuditDi,
            (watch_ledger,),
            "lifecycle @recipe watch_ledger(di) -> AuditDi: "
            + "process DI is built after the graph; depend on the exact components",
        ),
        (
            DiReaderDi,
            (),
            "DiReaderDi.reader -> DiReader(di) -> AutowireDi: "
            + "process DI is built after the graph; depend on the exact components",
        ),
        (
            NestedDi,
            (),
            "NestedDi.autowire -> AutowireDi: "
            + "process DI is built after the graph; depend on the exact components",
        ),
    ],
)
def test_check_di_rejects_the_process_di_as_a_dependency(
    di_class: type[ServiceDi],
    lifecycle: tuple[Recipe, ...],
    problem: str,
) -> None:
    with pytest.raises(DiError) as caught:
        _ = check_di(di_class, lifecycle=lifecycle)

    assert caught.value.problems == (problem,)


def test_check_di_rejects_a_lifecycle_recipe_that_returns_a_component() -> None:
    with pytest.raises(DiError) as caught:
        _ = check_di(AutowireDi, lifecycle=(frozen_clock,))

    assert caught.value.problems == (
        "@recipe frozen_clock: lifecycle recipe returns None or AsyncIterator[None]",
    )
