"""Исполнение команды в строгих полосах.

Полоса — строка ``lane_cursors`` в базе данных команды. ``run_in_lanes`` открывает одну
транзакцию: захватывает строки полос в отсортированном порядке (ожидающие стоят в очереди
блокировок PostgreSQL в порядке прихода), проверяет квитанцию ``idempotency_key``,
исполняет тело команды и пишет ``LaneCommit`` — всё атомарно. Перед захватом строки
команды одного процесса выстраиваются в ``asyncio.Lock`` полосы, чтобы ожидание не
держало соединения пула.

Вызывается только из ``@classmethod`` моделей: это граница транзакции.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
import weakref
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass

from oxyde import atomic, execute_raw
from oxyde.exceptions import UniqueViolationError
from pydantic import BaseModel

from core.config import get_settings
from core.errors.boundary import PlatformConflictError, PlatformUnavailableError
from core.events.contract import PlatformEvent
from core.lanes.models.lane_commit import LaneCommit
from core.lanes.models.lane_cursor import LaneCursor
from core.logging import get_logger
from core.types import JsonArray, parse_json_object
from core.utils.time import utcnow

logger = get_logger(__name__)

_LOCK_CONTENTION_MARKERS = ("lock timeout", "deadlock detected")


@dataclass(frozen=True, slots=True)
class LaneScope:
    """Контекст тела команды: номера полос и счётчики той же транзакции."""

    company_id: str
    using: str
    seqs: dict[str, int]
    lane_wait_ms: float

    def seq(self, lane_id: str) -> int:
        if lane_id not in self.seqs:
            raise KeyError(f"lane {lane_id!r} is not held by this transaction")
        return self.seqs[lane_id]

    async def next_value(self, sequence_id: str) -> int:
        """Номер без пропусков из курсора ``sequence_id`` внутри той же транзакции."""
        values = await LaneCursor.next_seq(
            [sequence_id], company_id=self.company_id, using=self.using
        )
        return values[sequence_id]


@dataclass(frozen=True, slots=True)
class LaneOutcome[R: BaseModel]:
    """Результат тела: ответ команды и события для публикации после commit."""

    result: R
    events: list[PlatformEvent]


@dataclass(frozen=True, slots=True)
class LaneRun[R: BaseModel]:
    """Исход ``run_in_lanes``; ``replayed`` — ответ взят из квитанции."""

    result: R
    commit: LaneCommit
    replayed: bool


class _Replay(Exception):
    def __init__(self, commit: LaneCommit) -> None:
        super().__init__(commit.lane_commit_id)
        self.commit: LaneCommit = commit


_gates_guard = threading.Lock()
_gates: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, weakref.WeakValueDictionary[str, asyncio.Lock]
] = weakref.WeakKeyDictionary()


def _gate(lane_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    with _gates_guard:
        per_loop: weakref.WeakValueDictionary[str, asyncio.Lock] | None = _gates.get(loop)
        if per_loop is None:
            per_loop = weakref.WeakValueDictionary[str, asyncio.Lock]()
            _gates[loop] = per_loop
        gate: asyncio.Lock | None = per_loop.get(lane_id)
        if gate is None:
            gate = asyncio.Lock()
            per_loop[lane_id] = gate
        return gate


def lane_id_for(kind: str, company_id: str, key: str) -> str:
    """Канонический ``lane_id``: ``<kind>:<company_id>:<key>``."""
    if not kind or not company_id or not key:
        raise ValueError("lane kind, company_id and key are required")
    return f"{kind}:{company_id}:{key}"


def _replayed[R: BaseModel](
    commit: LaneCommit, command_type: str, result_type: type[R]
) -> LaneRun[R]:
    if commit.command_type != command_type:
        raise PlatformConflictError(
            "Idempotency key was used by another command",
            error_code="idempotency_key_reused",
            error_params={"command_type": commit.command_type},
        )
    return LaneRun(
        result=result_type.model_validate(commit.result_payload),
        commit=commit,
        replayed=True,
    )


def _is_lock_contention(error: RuntimeError) -> bool:
    """Ошибка драйвера Oxyde (``DatabaseError`` — подкласс ``RuntimeError``) без SQLSTATE: только текст."""
    message = str(error)
    return any(marker in message for marker in _LOCK_CONTENTION_MARKERS)


async def run_in_lanes[R: BaseModel](
    lane_ids: Sequence[str],
    *,
    company_id: str,
    using: str,
    idempotency_key: str,
    command_type: str,
    actor_user_id: str,
    result_type: type[R],
    body: Callable[[LaneScope], Awaitable[LaneOutcome[R]]],
) -> LaneRun[R]:
    """Исполнить ``body`` строго последовательно в полосах ``lane_ids``."""
    if not lane_ids:
        raise ValueError("run_in_lanes requires at least one lane")
    if not idempotency_key:
        raise ValueError("run_in_lanes requires idempotency_key")
    ordered = sorted(set(lane_ids))
    stored = await LaneCommit.by_idempotency_key(company_id, idempotency_key, using=using)
    if stored is not None:
        return _replayed(stored, command_type, result_type)
    async with AsyncExitStack() as gates:
        for lane_id in ordered:
            _ = await gates.enter_async_context(_gate(lane_id))
        try:
            return await _commit(
                ordered,
                company_id=company_id,
                using=using,
                idempotency_key=idempotency_key,
                command_type=command_type,
                actor_user_id=actor_user_id,
                body=body,
            )
        except _Replay as replay:
            return _replayed(replay.commit, command_type, result_type)
        except UniqueViolationError:
            raced = await LaneCommit.by_idempotency_key(company_id, idempotency_key, using=using)
            if raced is None:
                raise
            return _replayed(raced, command_type, result_type)
        except RuntimeError as exc:
            if not _is_lock_contention(exc):
                raise
            logger.warning("lanes.lane_busy", lane_ids=ordered, command_type=command_type)
            raise PlatformUnavailableError(
                "Lane is busy, retry the command with the same idempotency key",
                error_code="lane_busy",
                error_params={"lane_ids": list(ordered)},
            ) from exc


async def _commit[R: BaseModel](
    ordered: list[str],
    *,
    company_id: str,
    using: str,
    idempotency_key: str,
    command_type: str,
    actor_user_id: str,
    body: Callable[[LaneScope], Awaitable[LaneOutcome[R]]],
) -> LaneRun[R]:
    lock_timeout_ms = get_settings().lanes.lock_timeout_ms
    async with atomic(using=using):
        _ = await execute_raw(f"SET LOCAL lock_timeout = '{lock_timeout_ms}ms'", [], using=using)
        wait_started = time.perf_counter()
        seqs = await LaneCursor.next_seq(ordered, company_id=company_id, using=using)
        lane_wait_ms = round((time.perf_counter() - wait_started) * 1000.0, 3)
        stored = await LaneCommit.by_idempotency_key(company_id, idempotency_key, using=using)
        if stored is not None:
            raise _Replay(stored)
        scope = LaneScope(
            company_id=company_id, using=using, seqs=seqs, lane_wait_ms=lane_wait_ms
        )
        outcome = await body(scope)
        primary = ordered[0]
        events: JsonArray = [
            parse_json_object(event.model_dump_json(), "lane event") for event in outcome.events
        ]
        commit = await LaneCommit.append(
            LaneCommit(
                lane_commit_id=uuid.uuid7().hex,
                company_id=company_id,
                lane_id=primary,
                lane_seq=seqs[primary],
                idempotency_key=idempotency_key,
                command_type=command_type,
                actor_user_id=actor_user_id,
                result_payload=parse_json_object(
                    outcome.result.model_dump_json(), "lane result"
                ),
                events=events,
                created_at=utcnow(),
            ),
            using=using,
        )
    logger.info(
        "lanes.committed",
        lane_id=primary,
        lane_seq=seqs[primary],
        lane_wait_ms=lane_wait_ms,
        command_type=command_type,
    )
    return LaneRun(result=outcome.result, commit=commit, replayed=False)
